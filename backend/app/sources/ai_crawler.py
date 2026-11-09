import asyncio
import os
import sys
import re
import json
import urllib.parse
from typing import Any
import httpx
import structlog
try:
    from playwright.async_api import Page, Browser, BrowserContext
except ImportError:
    Page = Any  # type: ignore
    Browser = Any  # type: ignore
    BrowserContext = Any  # type: ignore

from app.sources.base import RawJobData
from app.sources.company_ats import standardize_india_location, is_delhi_ncr_job, is_delhi_ncr_or_remote_job, is_relevant_tech_job
from app.core.system_logger import log_system_event

logger = structlog.get_logger()


class CaptchaDetectedException(Exception):
    """Raised when an anti-bot or CAPTCHA challenge is detected on a career page."""
    def __init__(self, message: str, captcha_type: str = "Unknown", url: str = ""):
        super().__init__(message)
        self.captcha_type = captcha_type
        self.url = url


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
        ollama_url: str | None = None,
        model: str = "llama3.2:latest",
        max_steps: int = 5,
    ):
        import os
        if ollama_url:
            self.ollama_url = ollama_url
        elif os.path.exists("/.dockerenv"):
            self.ollama_url = "http://host.docker.internal:11434"
        else:
            self.ollama_url = "http://localhost:11434"
        self.model = model
        self.max_steps = max_steps

    async def _query_llm(self, prompt: str) -> dict[str, Any] | None:
        """Call local Ollama with JSON mode and fast token limit."""
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                r = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                        "options": {
                            "temperature": 0.1,
                            "num_predict": 120,
                            "num_ctx": 2048,
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

    async def detect_captcha(self, page: Page) -> tuple[bool, str]:
        """
        Actively checks if the page is blocked by CAPTCHA, Cloudflare Turnstile,
        reCAPTCHA, hCaptcha, PerimeterX, or human verification barriers.
        Returns (is_captcha, captcha_type).
        """
        try:
            url = page.url.lower()
            title = (await page.title()).lower()

            # URL and title heuristics
            if "challenges.cloudflare.com" in url or "cf-turnstile" in url:
                return True, "Cloudflare Turnstile"
            if "just a moment..." in title or "attention required! | cloudflare" in title:
                return True, "Cloudflare Challenge"
            if "datadome" in url:
                return True, "DataDome"

            captcha_type = await page.evaluate("""() => {
                // Cloudflare Turnstile & Challenge
                if (document.querySelector('iframe[src*="challenges.cloudflare.com"], iframe[src*="turnstile"], #challenge-stage, .cf-turnstile, [name="cf-turnstile-response"]')) {
                    return 'Cloudflare Turnstile';
                }
                // Google reCAPTCHA
                if (document.querySelector('iframe[src*="recaptcha"], iframe[src*="google.com/recaptcha"], .g-recaptcha, #recaptcha')) {
                    return 'Google reCAPTCHA';
                }
                // hCaptcha
                if (document.querySelector('iframe[src*="hcaptcha.com"], .h-captcha, [data-hcaptcha-widget-id]')) {
                    return 'hCaptcha';
                }
                // PerimeterX / HUMAN Security
                if (document.querySelector('#px-captcha, #px-block-container')) {
                    return 'PerimeterX / HUMAN';
                }
                // DataDome / Arkose
                if (document.querySelector('iframe[src*="datadome"], iframe[src*="geo.captcha-delivery.com"], iframe[src*="arkoselabs"]')) {
                    return 'DataDome / Arkose';
                }
                // Textual human verification checks
                const bodyText = (document.body ? document.body.innerText : '').slice(0, 2000).toLowerCase();
                if (bodyText.includes('verify you are human') || 
                    bodyText.includes('verify that you are a human') || 
                    bodyText.includes('security check to continue') ||
                    bodyText.includes('press & hold to confirm') ||
                    bodyText.includes('complete the security check') ||
                    bodyText.includes('enable javascript and cookies to continue')) {
                    return 'Human Verification Challenge';
                }
                return null;
            }""")
            if captcha_type:
                return True, captcha_type
        except Exception as e:
            logger.debug("Captcha detection check error", error=str(e))
        return False, ""

    async def _observe_page(self, page: Page) -> tuple[list[dict[str, Any]], int]:
        """Inspect the current page to collect interactive elements and count visible job cards."""
        await self._auto_dismiss_banners(page)
        observation = await page.evaluate(
            """() => {
                // 1. Detect visible job cards/tiles
                const jobCardSelectors = [
                    '.job-tile', '.requisition-list-item', '[data-testid*="job"]',
                    '.job-card', '.career-card', '.job-listing', '.posting',
                    'li[class*="job"]', 'tr[class*="job"]', '[class*="JobCard"]',
                    'a[href*="gh_jid"]', 'a[href*="/job/"]', 'a[href*="/jobs/"]', 'a[href*="/career/"]'
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
                    
                    // Include surrounding card context (e.g. country name "India") if available
                    let label = s.text;
                    const card = s.el.closest('div[class*="card"], div[class*="item"], div[class*="col"], article');
                    if (card) {
                        const heading = card.querySelector('h2, h3, h4, h5, p, span');
                        if (heading && heading.innerText && !s.text.includes(heading.innerText.trim())) {
                            label = `${heading.innerText.trim()} -> ${s.text}`;
                        }
                    }

                    elements.push({
                        id: id,
                        tag: s.tag,
                        text: label.slice(0, 80),
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
            r"""() => {
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
                        loc = loc.replace(/Posting Date[^\r\n]+/gi, '')
                                 .replace(/Job Location/gi, '')
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
                            const locEl = c.querySelector('.sort-by-location, span.location, [class*="location"], [class*="city"], [data-automation-id="locations"]');
                            let loc = locEl ? locEl.innerText.trim() : '';
                            const cat = c.querySelector('.posting-categories, .categories, .meta');
                            if (cat && (!loc || /^(on-site|hybrid|remote)/i.test(loc) || loc.includes('—'))) {
                                loc = cat.innerText.replace(/\s+/g, ' ').trim();
                            }
                            const title = titleEl ? titleEl.innerText.trim().split('\n')[0] : '';
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
                    const lines = txt.split('\n').map(l => l.trim()).filter(Boolean);
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

            # Check technical relevance: reject sales, HR, marketing, warehouse, non-tech roles
            if not is_relevant_tech_job(title, target_query):
                continue

            # When delhi_ncr_only is set, filter out any location that is definitely not Delhi NCR or Remote
            if delhi_ncr_only and loc:
                if not is_delhi_ncr_or_remote_job(loc, title, item.get("snippet", "")):
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
                    source="career-crawled",
                )
            )

        return extracted

    async def _quick_check_target_jobs(self, page: Page, company: str, target_query: str) -> list[RawJobData]:
        """Rapidly detects if any links on the current page match tech engineering roles."""
        keywords = [w.lower() for w in target_query.split() if len(w) > 2]

        raw_items = await page.evaluate(
            """(kw) => {
                const matches = [];
                const anchors = Array.from(document.querySelectorAll('a[href*="/job"], a[href*="gh_jid"], a[href*="lever.co"], a[href*="workday"], a[class*="job"]'));
                const techTokens = ['engineer', 'developer', 'sde', 'architect', 'full stack', 'backend', 'frontend', 'devops', 'sre', 'cloud', 'data', 'software', 'platform'];
                for (const a of anchors) {
                    const txt = (a.innerText || '').trim();
                    const lower = txt.toLowerCase();
                    const matchesQuery = !kw || kw.length === 0 || kw.some(k => lower.includes(k));
                    const isTech = techTokens.some(t => lower.includes(t));
                    if (matchesQuery && isTech) {
                        matches.push({
                            title: txt.split('\\n')[0].trim(),
                            url: a.href,
                            location: txt.split('\\n').slice(1).join(', ').trim()
                        });
                    }
                }
                return matches;
            }""",
            keywords,
        )

        if not raw_items:
            return []

        jobs = []
        seen = set()
        for r in raw_items:
            url = r.get("url")
            if url and url not in seen:
                seen.add(url)
                if not is_relevant_tech_job(r["title"], target_query):
                    continue
                jobs.append(
                    RawJobData(
                        title=r["title"],
                        company=company,
                        location=standardize_india_location(company, r.get("location", ""), False),
                        is_remote="remote" in r.get("location", "").lower(),
                        source_url=url,
                        application_url=url,
                        description=f"### {r['title']}\n\n**Company**: {company}\n\nDiscovered via AI Browser Agent.",
                        external_id=f"ai_{abs(hash(url))}",
                        source="career-crawled",
                    )
                )
        return jobs

    async def enrich_job_with_full_jd(self, page: Page, job: RawJobData) -> RawJobData:
        """
        Navigates to the posting URL to extract the complete Job Description,
        responsibilities, requirements, and technical skills for profile matching.
        """
        target_url = job.application_url or job.source_url
        if not target_url or not target_url.startswith("http"):
            return job

        try:
            try:
                await page.goto(target_url, wait_until="domcontentloaded", timeout=12000)
            except Exception:
                pass  # DOM may already be partially parsed, proceed with extraction
            await page.wait_for_timeout(1000)

            extracted = await page.evaluate("""() => {
                const selectors = [
                    '[data-automation-id="jobPostingDescription"]',
                    '[data-automation-id="job-posting-details"]',
                    '#content', '.posting-description', '.job-description',
                    '.job-details__content', '[class*="jobDescription"]',
                    '[class*="job-description"]', '[class*="JobDescription"]',
                    '[class*="job-details"]', '[class*="JobDetail"]',
                    '#job-description', '#job-details',
                    'article', 'main', '[role="main"]'
                ];

                let container = null;
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText && el.innerText.trim().length > 150) {
                        container = el;
                        break;
                    }
                }
                if (!container) container = document.body;

                // Extract detail location if explicitly stated on the posting page
                let locText = '';
                const locSelectors = [
                    '[data-automation-id="locations"]',
                    '.location', '.job-location', '[class*="location"]', '[class*="Location"]',
                    '.posting-categories', '.meta', '[class*="subheading"]'
                ];
                for (const sel of locSelectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText && el.innerText.trim().length > 1 && el.innerText.trim().length < 80) {
                        locText = el.innerText.trim();
                        break;
                    }
                }

                return {
                    text: container ? container.innerText.trim() : '',
                    title: document.title || '',
                    detail_location: locText
                };
            }""")

            detail_loc = extracted.get("detail_location", "")
            if detail_loc and (not job.location or job.location in ["(opens in a new tab)", "India", "Unknown", ""]):
                is_rem = bool("remote" in detail_loc.lower() or "remote" in job.title.lower())
                job.location = standardize_india_location(job.company, detail_loc, is_rem)
                job.is_remote = is_rem

            raw_text = extracted.get("text", "")
            if len(raw_text) > 120:
                clean_lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
                
                resp = []
                req = []
                current_sec = None
                
                for line in clean_lines:
                    lower = line.lower()
                    if any(k in lower for k in ['responsibilit', 'what will you do', 'what you will do', 'duties', 'the role', 'key expectations']):
                        current_sec = 'resp'
                        continue
                    elif any(k in lower for k in ['desired experience', 'requirement', 'qualification', 'what you bring', 'what we are looking for', 'who you are', 'skills']):
                        current_sec = 'req'
                        continue
                    elif any(k in lower for k in ['who are we', 'about us', 'about the company', 'benefits', 'compensation', 'perks', 'how we hire']):
                        current_sec = None
                        continue
                    
                    if current_sec == 'resp' and 8 <= len(line) <= 350:
                        resp.append(line.lstrip('•-* ').strip())
                    elif current_sec == 'req' and 8 <= len(line) <= 350:
                        req.append(line.lstrip('•-* ').strip())

                # Format clean readable Markdown Description
                overview_text = raw_text[:3500].strip()
                formatted_jd = (
                    f"### {job.title}\n\n"
                    f"**Company**: {job.company} | **Location**: {job.location}\n\n"
                    f"#### Overview & Job Description\n\n"
                    f"{overview_text}\n"
                )

                job.description = formatted_jd
                if resp:
                    job.responsibilities = resp[:15]
                if req:
                    job.requirements = req[:15]

                # Extract technical skills
                SKILLS_VOCAB = [
                    'Python', 'Java', 'JavaScript', 'TypeScript', 'C++', 'C#', 'Go', 'Rust', 'Ruby', 'PHP', 'Swift', 'Kotlin', 'Scala',
                    'React', 'Next.js', 'Vue', 'Angular', 'Node.js', 'FastAPI', 'Django', 'Flask', 'Spring Boot', 'Express',
                    'SQL', 'PostgreSQL', 'MySQL', 'MongoDB', 'Redis', 'Cassandra', 'Elasticsearch', 'DynamoDB',
                    'AWS', 'Azure', 'GCP', 'Docker', 'Kubernetes', 'Terraform', 'Ansible', 'Linux', 'Unix', 'MacOS', 'Windows', 'Android', 'iOS',
                    'Git', 'CI/CD', 'Jenkins', 'GitHub Actions', 'Jira', 'Confluence',
                    'Bash', 'Shell', 'PowerShell', 'Datacenter', 'Networking', 'TCP/IP', 'VLAN', 'Routing', 'Switching', 'DNS', 'DHCP',
                    'VMware', 'Proxmox', 'Virtualization', 'REST API', 'GraphQL', 'Microservices', 'Kafka', 'RabbitMQ',
                    'Machine Learning', 'Deep Learning', 'PyTorch', 'TensorFlow', 'NLP', 'Computer Vision', 'LLM',
                    'Selenium', 'Playwright', 'Cypress', 'PySpark', 'Databricks', 'Airflow', 'Snowflake', 'BigQuery'
                ]
                found_skills = set(job.required_skills)
                for s in SKILLS_VOCAB:
                    pattern = r'(?<![a-zA-Z0-9])' + re.escape(s) + r'(?![a-zA-Z0-9])'
                    if re.search(pattern, raw_text, re.IGNORECASE):
                        found_skills.add(s)
                job.required_skills = sorted(list(found_skills))[:15]

                print(f"   ✅ Fetched JD ({len(raw_text)} chars, {len(job.required_skills)} skills, {len(resp)} responsibilities, {len(req)} requirements)")
                logger.info("Enriched job with full JD", company=job.company, title=job.title, jd_len=len(raw_text), skills_count=len(job.required_skills))

        except Exception as e:
            logger.warning("Could not fetch full JD for job", url=target_url, error=str(e))

        return job

    async def crawl_career_portal(
        self,
        company: str,
        start_url: str,
        target_query: str,
        headless: bool = False,
        slow_mo: int = 100,
        delhi_ncr_only: bool = True,
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

        is_in_docker = os.path.exists('/.dockerenv') or not os.environ.get('DISPLAY')
        actual_headless = True if is_in_docker else headless
        actual_slow_mo = 0 if is_in_docker else slow_mo

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=actual_headless,
                slow_mo=actual_slow_mo,
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
                await page.goto(start_url, wait_until="domcontentloaded", timeout=25000)
                await page.wait_for_timeout(1000)
            except Exception as e:
                print(f"⚠️ Initial navigation warning: {e}")

            # 🛡️ CAPTCHA Barrier Check (Initial Navigation)
            is_cap, cap_type = await self.detect_captcha(page)
            if is_cap:
                msg = f"CAPTCHA detected on {company} ({start_url}): {cap_type}. Aborting crawl."
                print(f"🚨 {msg}")
                await log_system_event(
                    level="ERROR",
                    category="crawler",
                    message=msg,
                    details={"company": company, "url": page.url, "captcha_type": cap_type, "aborted": True}
                )
                raise CaptchaDetectedException(msg, captcha_type=cap_type, url=page.url)

            for step in range(1, self.max_steps + 1):
                cur_url = page.url
                cur_title = await page.title()

                # 🛡️ CAPTCHA Barrier Check (Step Navigation)
                is_cap, cap_type = await self.detect_captcha(page)
                if is_cap:
                    msg = f"CAPTCHA challenge encountered on {company} at step {step}: {cap_type}. Aborting crawl."
                    print(f"🚨 {msg}")
                    await log_system_event(
                        level="ERROR",
                        category="crawler",
                        message=msg,
                        details={"company": company, "url": cur_url, "step": step, "captcha_type": cap_type, "aborted": True}
                    )
                    raise CaptchaDetectedException(msg, captcha_type=cap_type, url=cur_url)

                print(f"\n🔍 [Step {step}/{self.max_steps}] Observing page: {cur_title}")
                print(f"   URL: {cur_url}")

                # 1. Ultra-fast direct check if target jobs are already visible on this page
                instant_jobs = await self._quick_check_target_jobs(page, company, target_query)
                if instant_jobs:
                    print(f"🎉 Instant match! Discovered {len(instant_jobs)} postings matching '{target_query}' directly on page.")
                    collected_jobs.extend(instant_jobs)
                    break

                elements, job_count = await self._observe_page(page)
                print(f"   Interactive elements found: {len(elements)} | Job listings detected: {job_count}")

                # If job count is significant or target jobs appear, extract first
                if job_count >= 1:
                    print(f"💡 Found {job_count} visible job listings on page; evaluating extraction...")
                    jobs = await self._extract_jobs_from_page(page, company, target_query, delhi_ncr_only)
                    matching = [j for j in jobs if is_relevant_tech_job(j.title, target_query)]
                    if matching:
                        print(f"🎉 Successfully extracted {len(matching)} matching tech jobs!")
                        collected_jobs.extend(matching)
                        if len(collected_jobs) >= limit:
                            break

                # Prepare prompt for LLM decision
                elements_text = "\n".join(
                    f"[{el['id']}] <{el['tag']}> {el.get('text', '') or el.get('placeholder', '')} (href: {el.get('href', '')})"
                    for el in elements[:18]
                )

                prompt = f"""You are an autonomous web crawler agent tasked with finding job postings for: "{target_query}" at {company}.
Starting from the company's career page, navigate through portals, search forms, and listings to discover matching jobs.

STRICT LOCATION CONSTRAINT:
The user only wants jobs located in Delhi NCR (Delhi, Gurgaon / Gurugram, Noida, Greater Noida, Faridabad, Ghaziabad) OR Remote roles.
Do NOT target or click into postings located in foreign countries (e.g. US, Dublin, Mexico, Europe) or on-site roles outside Delhi NCR.
If there are location filters or search inputs, prefer entering or selecting "Delhi", "Gurugram", "Noida", "India", or "Remote".

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
                    matching = [j for j in jobs if is_relevant_tech_job(j.title, target_query)]
                    print(f"✅ Extracted {len(matching)} relevant tech jobs on AI demand.")
                    collected_jobs.extend(matching)
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
                                    await target_el.first.click(force=True, timeout=4000)
                                await page.wait_for_timeout(1200)
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
                                    await target_inp.first.click(force=True, timeout=3000)
                                    await page.wait_for_timeout(800)
                                    visible_inp = page.locator('input[type="text"], input[type="search"], input:not([type])')
                                    if await visible_inp.count() > 0:
                                        await visible_inp.first.fill(value)
                                        if decision.get("submit", True):
                                            await visible_inp.first.press("Enter")
                                            await page.wait_for_timeout(1500)
                                else:
                                    await target_inp.first.fill(value)
                                    await page.wait_for_timeout(300)
                                    if decision.get("submit", True):
                                        await target_inp.first.press("Enter")
                                        await page.wait_for_timeout(1500)
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

            # Deduplicate by URL before fetching JDs
            unique_results = []
            seen_urls = set()
            for j in collected_jobs:
                if j.source_url not in seen_urls:
                    seen_urls.add(j.source_url)
                    unique_results.append(j)

            target_jobs = unique_results[:limit]
            final_jobs = []
            if target_jobs:
                print(f"📥 Extracting full Job Descriptions (JDs) for {len(target_jobs)} postings...")
                for idx, j in enumerate(target_jobs, 1):
                    if j.source_url and j.source_url != start_url:
                        print(f"[{idx}/{len(target_jobs)}] Fetching JD for: '{j.title}'")
                        await self.enrich_job_with_full_jd(page, j)

                    # Strict Delhi NCR and Remote location filter
                    if delhi_ncr_only:
                        if is_delhi_ncr_or_remote_job(j.location, j.title, j.description or ""):
                            final_jobs.append(j)
                        else:
                            print(f"   ⏩ Skipping '{j.title}' (Location: {j.location}) - not Delhi NCR or Remote.")
                    else:
                        final_jobs.append(j)

            await browser.close()

        return final_jobs

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
