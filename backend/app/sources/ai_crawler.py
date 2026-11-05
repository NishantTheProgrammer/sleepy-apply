import asyncio
import re
import json
import urllib.parse
from typing import Any
import httpx
import structlog
from playwright.async_api import Page, Browser, BrowserContext

from app.sources.base import RawJobData
from app.sources.company_ats import standardize_india_location, is_delhi_ncr_job

logger = structlog.get_logger()


class AICareerCrawlerAgent:
    """
    Autonomous AI Browser Agent for Career Portals.
    
    Given a company career landing page (e.g. https://www.exlservice.com/careers)
    and a target role/search query, the agent visually/semantically inspects the page,
    decides which buttons to click, navigates to the ATS/job board, enters search queries,
    and extracts matching jobs without requiring hardcoded site-specific selectors.
    """

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        model: str = "llama3.2:latest",
        max_steps: int = 7,
    ):
        self.ollama_url = ollama_url
        self.model = model
        self.max_steps = max_steps

    async def _query_llm(self, prompt: str) -> dict[str, Any] | None:
        """Call local Ollama with JSON mode and timeout."""
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                        "options": {
                            "temperature": 0.1,
                            "num_predict": 450,
                            "num_ctx": 4096,
                        },
                    },
                )
                if r.status_code != 200:
                    logger.warning("Ollama call non-200", status=r.status_code)
                    return None
                data = r.json()
                raw_response = data.get("response", "").strip()
                # Parse JSON
                try:
                    return json.loads(raw_response)
                except Exception:
                    m = re.search(r"\{[\s\S]*\}", raw_response)
                    if m:
                        return json.loads(m.group(0))
        except Exception as e:
            logger.warning("LLM decision call failed", error=str(e))
        return None

    async def _auto_dismiss_banners(self, page: Page):
        """Automatically dismiss cookie consent modals and banners that intercept pointer events."""
        try:
            await page.evaluate("""() => {
                // Find and click accept/agree buttons
                const buttons = Array.from(document.querySelectorAll('button, a, [role="button"]'));
                for (const b of buttons) {
                    const txt = (b.innerText || '').trim().toLowerCase();
                    if (/^(accept|accept all|i accept|agree|allow all|close|got it|ok|continue|dismiss)$/i.test(txt)) {
                        try { b.click(); } catch(e) {}
                    }
                }
                // Remove cookie overlay wrappers that intercept pointer clicks
                const overlays = document.querySelectorAll('#onetrust-consent-sdk, .cookie-banner, .cm__desc, [class*="cookie"], [id*="cookie"]');
                overlays.forEach(o => {
                    if (o.innerText && /cookie|privacy|consent/i.test(o.innerText)) {
                        o.remove();
                    }
                });
            }""")
        except Exception:
            pass

    async def _observe_page(self, page: Page) -> tuple[list[dict[str, Any]], int]:
        """Inspect the current page to collect interactive elements and count visible job cards."""
        await self._auto_dismiss_banners(page)
        observation = await page.evaluate(
            """() => {
                // 1. Detect visible job cards/tiles
                const jobCardSelectors = [
                    '.job-tile', '.requisition-list-item', '[data-testid*="job"]',
                    '.job-card', '.career-card', '.job-listing', '.posting',
                    'li[class*="job"]', 'tr[class*="job"]', '[class*="JobCard"]'
                ];
                let jobCount = 0;
                for (const sel of jobCardSelectors) {
                    const count = document.querySelectorAll(sel).length;
                    if (count > jobCount) jobCount = count;
                }

                // 2. Discover interactive elements
                const elements = [];
                let idx = 1;

                // A. Search Inputs
                const inputs = Array.from(document.querySelectorAll('input[type="text"], input[type="search"], input:not([type])'));
                for (const inp of inputs) {
                    const rect = inp.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        const id = `el_${idx++}`;
                        inp.setAttribute('data-ai-id', id);
                        elements.push({
                            id: id,
                            tag: 'input',
                            type: inp.type || 'text',
                            placeholder: inp.placeholder || '',
                            name: inp.name || '',
                            value: inp.value || '',
                            ariaLabel: inp.getAttribute('aria-label') || ''
                        });
                    }
                }

                // B. Interactive Buttons & Anchor Links (scored by career relevance)
                const candidates = Array.from(document.querySelectorAll('a, button, [role="button"]'));
                const scored = [];

                for (const el of candidates) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width <= 0 || rect.height <= 0) continue;

                    const text = (el.innerText || el.getAttribute('aria-label') || el.title || '').trim().replace(/\\s+/g, ' ');
                    const href = el.href || '';
                    if (!text && !href) continue;

                    // Filter out navigation boilerplate
                    if (/^(skip to|privacy|terms|cookie|explore industries|insights|contact us|about us|services)$/i.test(text)) continue;

                    let score = 0;
                    if (/oraclecloud|myworkdayjobs|greenhouse|lever\\.co|ashbyhq|smartrecruiters/i.test(href)) score += 60;
                    if (/explore open position|view open position|open positions|search jobs|find jobs/i.test(text)) score += 40;
                    if (/india/i.test(text + ' ' + href)) score += 20;
                    if (/requisition|posting|career|job|opportunity/i.test(text + ' ' + href)) score += 15;
                    if (el.tagName === 'BUTTON' && /search|find|filter|apply/i.test(text)) score += 35;

                    if (score > 0) {
                        scored.push({ el, text, href, score, tag: el.tagName.toLowerCase() });
                    }
                }

                scored.sort((a, b) => b.score - a.score);

                for (const s of scored.slice(0, 20)) {
                    const id = `el_${idx++}`;
                    s.el.setAttribute('data-ai-id', id);
                    elements.push({
                        id: id,
                        tag: s.tag,
                        text: s.text.slice(0, 70),
                        href: s.href.slice(0, 160),
                        score: s.score
                    });
                }

                return { elements, jobCount };
            }"""
        )
        return observation.get("elements", []), observation.get("jobCount", 0)

    async def _extract_jobs_from_page(
        self, page: Page, company: str, target_query: str, delhi_ncr_only: bool
    ) -> list[RawJobData]:
        """Extract job listings currently visible on the page."""
        raw_items = await page.evaluate(
            """() => {
                const results = [];

                // 1. Oracle Cloud HCM (.job-tile)
                const oracleTiles = document.querySelectorAll('.job-tile');
                if (oracleTiles.length > 0) {
                    oracleTiles.forEach(tile => {
                        const titleEl = tile.querySelector('.job-tile__title, [class*="title"]');
                        const link = tile.querySelector('a') || titleEl?.closest('a') || tile.closest('a');
                        const locEl = tile.querySelector('.job-tile__subheader, [class*="subheader"], [class*="location"]');
                        const title = titleEl ? titleEl.innerText.trim() : '';
                        let loc = locEl ? locEl.innerText.trim() : '';
                        loc = loc.replace(/Posting Date\\s*\\d{1,2}\\/\\d{1,2}\\/\\d{4}/gi, '')
                                 .replace(/Job Location\\s*(Signed)?/gi, '')
                                 .replace(/(BE THE FIRST TO APPLY|TRENDING|HOT JOB)/gi, '')
                                 .trim();
                        const href = link ? link.href : window.location.href;
                        if (title && title.length >= 3 && !title.toLowerCase().startsWith('posting date')) {
                            results.push({ title, location: loc, url: href });
                        }
                    });
                    if (results.length > 0) return results;
                }

                // 2. Workday / Greenhouse / Lever / Generic Job Cards
                const cardSelectors = [
                    '[data-testid*="job"]', '[data-qa*="job"]', '.job-card', '.career-card',
                    '.job-item', '.posting', '.opening', '[class*="JobCard"]', '[class*="job-listing"]',
                    'tr[class*="job"]', 'li[class*="job"]'
                ];
                for (const sel of cardSelectors) {
                    const cards = document.querySelectorAll(sel);
                    if (cards.length >= 1) {
                        cards.forEach(c => {
                            const link = c.querySelector('a') || (c.tagName === 'A' ? c : null);
                            const titleEl = c.querySelector('h2, h3, h4, [class*="title"]') || link || c;
                            const locEl = c.querySelector('[class*="location"], [class*="loc"], [class*="city"]');
                            const title = titleEl ? titleEl.innerText.trim().split('\\n')[0] : '';
                            const loc = locEl ? locEl.innerText.trim() : '';
                            const href = link ? link.href : window.location.href;
                            if (title && title.length >= 3 && title.length <= 110) {
                                results.push({ title, location: loc, url: href });
                            }
                        });
                        if (results.length > 0) return results;
                    }
                }

                // 3. Fallback: Specific anchors
                const anchors = document.querySelectorAll('a[href*="/job/"], a[href*="/jobs/"], a[href*="/career/"], a[href*="/position/"]');
                anchors.forEach(a => {
                    const txt = a.innerText.trim();
                    const lines = txt.split('\\n').map(l => l.trim()).filter(Boolean);
                    if (lines.length > 0) {
                        const first = lines[0];
                        if (first.length >= 4 && first.length <= 95 && !/^(view all|careers|search|apply|about)$/i.test(first)) {
                            results.push({
                                title: first,
                                location: lines.length > 1 ? lines[1] : '',
                                url: a.href
                            });
                        }
                    }
                });

                return results.slice(0, 30);
            }"""
        )

        extracted: list[RawJobData] = []
        seen = set()

        for item in raw_items:
            title = str(item.get("title") or "").strip()
            loc = str(item.get("location") or "").strip()
            url = str(item.get("url") or page.url).strip()

            if not title or len(title) < 3 or url in seen:
                continue

            if delhi_ncr_only and loc and not is_delhi_ncr_job(loc, title):
                continue

            seen.add(url)
            is_remote = bool("remote" in loc.lower() or "remote" in title.lower())
            std_loc = standardize_india_location(company, loc, is_remote)

            extracted.append(
                RawJobData(
                    title=title,
                    company=company,
                    location=std_loc,
                    is_remote=is_remote,
                    source_url=url,
                    application_url=url,
                    description=f"### {title}\n\n**Company**: {company}\n**Location**: {std_loc}\n\nDiscovered via AI Browser Agent.",
                    external_id=f"ai_{abs(hash(url))}",
                    source="career",
                )
            )

        return extracted

    async def crawl_career_portal(
        self,
        company: str,
        start_url: str,
        target_query: str,
        headless: bool = False,
        slow_mo: int = 300,
        delhi_ncr_only: bool = False,
        limit: int = 15,
    ) -> list[RawJobData]:
        """
        Main Agentic Decision Loop.
        Launches browser, visits start_url, and uses LLM to navigate and search.
        """
        from playwright.async_api import async_playwright

        collected_jobs: list[RawJobData] = []

        print("\n" + "=" * 70)
        print("🤖 AI CAREER CRAWLER AGENT ENGAGED")
        print("=" * 70)
        print(f" Target Company : {company}")
        print(f" Starting URL   : {start_url}")
        print(f" Target Goal    : Search for '{target_query}'")
        print(f" Visible Browser: {not headless} (Slow-Mo: {slow_mo}ms)")
        print(f" AI Model Engine: {self.model} via {self.ollama_url}")
        print("=" * 70 + "\n")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=headless,
                slow_mo=slow_mo,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
            )

            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 850},
            )
            page = await context.new_page()

            # Handle potential new tabs opened via target="_blank"
            async def handle_new_page(new_page: Page):
                nonlocal page
                logger.info("New browser tab opened; switching focus", url=new_page.url)
                page = new_page
                await page.bring_to_front()

            context.on("page", handle_new_page)

            print(f"🌐 [Step 0] Navigating to career page: {start_url}")
            try:
                await page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2500)
            except Exception as e:
                print(f"⚠️ Initial navigation warning: {e}")

            for step in range(1, self.max_steps + 1):
                cur_url = page.url
                cur_title = await page.title()

                print(f"\n🔍 [Step {step}/{self.max_steps}] Observing page: {cur_title}")
                print(f"   URL: {cur_url}")

                elements, job_count = await self._observe_page(page)
                print(f"   Interactive elements found: {len(elements)} | Job listings detected: {job_count}")

                # If job count is significant or target jobs appear, extract first
                if job_count >= 1:
                    print(f"💡 Found {job_count} visible job listings on page; evaluating extraction...")
                    jobs = await self._extract_jobs_from_page(page, company, target_query, delhi_ncr_only)
                    # Check if extracted jobs match target_query
                    matching = [j for j in jobs if any(w.lower() in j.title.lower() for w in target_query.split())]
                    if matching:
                        print(f"🎉 Successfully extracted {len(matching)} matching jobs!")
                        collected_jobs.extend(matching)
                        break
                    elif jobs and len(jobs) >= 3:
                        print(f"📋 Extracted {len(jobs)} jobs from current page.")
                        collected_jobs.extend(jobs)
                        # If we already have what we need, finish
                        if len(collected_jobs) >= limit:
                            break

                # Prepare prompt for LLM decision
                elements_text = "\n".join(
                    f"[{el['id']}] <{el['tag']}> {el.get('text', '') or el.get('placeholder', '')} (href: {el.get('href', '')})"
                    for el in elements[:18]
                )

                prompt = f"""You are an autonomous web crawler agent tasked with finding job postings for: "{target_query}" at {company}.
Starting from the company's career page, navigate through portals, search forms, and listings to discover matching jobs.

CURRENT PAGE STATE:
- Page Title: {cur_title}
- Current URL: {cur_url}
- Job Listings Detected on Page: {job_count}

INTERACTIVE ELEMENTS DETECTED ON THIS PAGE:
{elements_text}

INSTRUCTIONS:
Decide the single next best action to reach or search for jobs matching "{target_query}".
Available actions:
1. "click": Click a button or link (e.g. "Explore Open Positions", "Search Jobs", "India Careers", "View All Jobs", or pagination).
2. "fill": Type your target search query into a search bar / input box.
3. "scroll": Scroll down to reveal more jobs or lazy-loaded elements.
4. "extract": Extract the visible job postings on this page (choose this if you see job postings or search results).
5. "finish": If target jobs have been collected or no further actions are possible.

Return ONLY a valid JSON object matching this schema:
{{
  "thought": "Brief explanation of your observation and rationale",
  "action": "click" | "fill" | "scroll" | "extract" | "finish",
  "element_id": "el_1",
  "value": "{target_query}",
  "submit": true
}}"""

                decision = await self._query_llm(prompt)
                if not decision:
                    print("⚠️ AI decision empty; falling back to heuristic scroll/extract.")
                    decision = {"action": "scroll", "thought": "Fallback scroll to discover elements"}

                action = decision.get("action", "scroll").lower()
                thought = decision.get("thought", "")
                el_id = decision.get("element_id")
                value = decision.get("value") or target_query

                print(f"🧠 AI Thought: {thought}")
                print(f"⚡ AI Action : {action.upper()} (element: {el_id}, value: {value if action == 'fill' else ''})")

                if action == "finish":
                    print("🏁 AI decided to conclude crawl.")
                    break

                elif action == "extract":
                    jobs = await self._extract_jobs_from_page(page, company, target_query, delhi_ncr_only)
                    print(f"✅ Extracted {len(jobs)} jobs on AI demand.")
                    collected_jobs.extend(jobs)
                    break

                elif action == "click":
                    if el_id:
                        try:
                            await self._auto_dismiss_banners(page)
                            target_el = page.locator(f'[data-ai-id="{el_id}"]')
                            if await target_el.count() > 0:
                                # Check if it's an anchor with an href
                                href = await target_el.first.get_attribute("href")
                                if href and not href.startswith("javascript:") and not href.startswith("#"):
                                    if href.startswith("/"):
                                        parsed_base = urllib.parse.urlparse(page.url)
                                        href = f"{parsed_base.scheme}://{parsed_base.netloc}{href}"
                                    print(f"🔗 Clicking link to target: {href}")
                                    try:
                                        await target_el.first.click(force=True, timeout=4000)
                                    except Exception:
                                        print(f"Direct navigating to link href: {href}")
                                        await page.goto(href, wait_until="domcontentloaded", timeout=25000)
                                else:
                                    await target_el.first.click(force=True, timeout=5000)
                                await page.wait_for_timeout(3000)
                            else:
                                print(f"⚠️ Element {el_id} not found in DOM, scrolling instead.")
                                await page.evaluate("window.scrollBy(0, 600);")
                        except Exception as e:
                            print(f"⚠️ Click failed ({e}), continuing...")
                    else:
                        await page.evaluate("window.scrollBy(0, 600);")

                elif action == "fill":
                    if el_id:
                        try:
                            target_inp = page.locator(f'[data-ai-id="{el_id}"]')
                            if await target_inp.count() > 0:
                                tag_name = await target_inp.first.evaluate("el => el.tagName.toLowerCase()")
                                if tag_name not in ["input", "textarea"]:
                                    # If LLM targeted a button/anchor, click it to activate search input
                                    await target_inp.first.click(force=True, timeout=4000)
                                    await page.wait_for_timeout(1000)
                                    visible_inp = page.locator('input[type="text"], input[type="search"], input:not([type])')
                                    if await visible_inp.count() > 0:
                                        await visible_inp.first.fill(value)
                                        if decision.get("submit", True):
                                            await visible_inp.first.press("Enter")
                                            await page.wait_for_timeout(3000)
                                else:
                                    await target_inp.first.fill(value)
                                    await page.wait_for_timeout(500)
                                    if decision.get("submit", True):
                                        await target_inp.first.press("Enter")
                                        await page.wait_for_timeout(3500)
                            else:
                                print(f"⚠️ Input {el_id} not found.")
                        except Exception as e:
                            print(f"⚠️ Fill failed ({e}), continuing...")
                    else:
                        print("⚠️ No element_id provided for fill action.")

                elif action == "scroll":
                    await page.evaluate("window.scrollBy(0, 800);")
                    await page.wait_for_timeout(1500)

                await page.wait_for_timeout(1000)

            # Final check if jobs collected
            if not collected_jobs:
                print("🔄 Performing final sweep extraction on current page...")
                collected_jobs = await self._extract_jobs_from_page(page, company, target_query, delhi_ncr_only)

            await browser.close()

        # Deduplicate by URL
        unique_results = []
        seen_urls = set()
        for j in collected_jobs:
            if j.source_url not in seen_urls:
                seen_urls.add(j.source_url)
                unique_results.append(j)

        return unique_results[:limit]

    async def auto(self, instruction: str, page: Page) -> bool:
        """
        Executes a plain English instruction directly on the Playwright page using the LLM.
        Python equivalent of auto-playwright, e.g.:
            await agent.auto('Type "Lead Assistant Manager" into the search bar', page)
            await agent.auto('Click the search button', page)
            await agent.auto('Click "Explore open position" for India', page)
        """
        await self._auto_dismiss_banners(page)
        elements, _ = await self._observe_page(page)

        elements_text = "\n".join(
            f"[{el['id']}] <{el['tag']}> {el.get('text', '') or el.get('placeholder', '')} (href: {el.get('href', '')})"
            for el in elements[:20]
        )

        cur_title = await page.title()
        prompt = f"""You are an AI browser automation assistant.
Translate this plain English command into a concrete browser action: "{instruction}"

CURRENT PAGE: {cur_title} ({page.url})

PAGE ELEMENTS:
{elements_text}

Available actions:
1. "click": Click an interactive button/link/tab.
2. "fill": Type text into an input box.
3. "scroll": Scroll the page down or up.
4. "press": Press a keyboard key like "Enter".

Return ONLY valid JSON:
{{
  "thought": "Why you chose this element",
  "action": "click" | "fill" | "scroll" | "press",
  "element_id": "el_1",
  "value": "string to fill",
  "key": "Enter"
}}"""

        decision = await self._query_llm(prompt)
        if not decision:
            logger.warning("auto: LLM returned no decision", instruction=instruction)
            return False

        action = decision.get("action", "click").lower()
        el_id = decision.get("element_id")
        value = decision.get("value", "")

        logger.info("auto: executing action", instruction=instruction, action=action, element=el_id, thought=decision.get("thought"))

        try:
            if action == "click" and el_id:
                loc = page.locator(f'[data-ai-id="{el_id}"]')
                if await loc.count() > 0:
                    await loc.first.click(force=True, timeout=5000)
                    await page.wait_for_timeout(2000)
                    return True
                else:
                    # Fallback text click
                    text_hint = decision.get("value") or instruction
                    clean_hint = re.sub(r'^(click|press|open)\s*', '', text_hint, flags=re.IGNORECASE).strip(' "\'')
                    await page.get_by_text(clean_hint, exact=False).first.click(timeout=4000)
                    await page.wait_for_timeout(2000)
                    return True

            elif action == "fill" and el_id:
                loc = page.locator(f'[data-ai-id="{el_id}"]')
                if await loc.count() > 0:
                    val_to_fill = value or re.findall(r'["\']([^"\']+)["\']', instruction)[0] if re.findall(r'["\']([^"\']+)["\']', instruction) else ""
                    await loc.first.fill(val_to_fill)
                    if decision.get("key") == "Enter" or "enter" in instruction.lower():
                        await loc.first.press("Enter")
                    await page.wait_for_timeout(2000)
                    return True

            elif action == "scroll":
                await page.evaluate("window.scrollBy(0, 600);")
                await page.wait_for_timeout(1000)
                return True

            elif action == "press":
                await page.keyboard.press(decision.get("key", "Enter"))
                await page.wait_for_timeout(2000)
                return True

        except Exception as e:
            logger.warning("auto execution error", error=str(e), instruction=instruction)

        return False
