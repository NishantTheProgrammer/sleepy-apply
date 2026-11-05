import asyncio
import re
import json
import argparse
import urllib.parse
from typing import Any
import structlog

from app.sources.base import BaseJobSource, RawJobData
from app.sources.company_ats import standardize_india_location, is_delhi_ncr_job

logger = structlog.get_logger()

# Check if playwright is importable
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.async_api import async_playwright, Browser, Page, Response
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    logger.info("Playwright is not installed in current Python environment.")


def _find_job_dicts(data: Any, max_depth: int = 4) -> list[dict]:
    """Recursively search for job posting dictionaries inside nested JSON responses."""
    found: list[dict] = []
    if max_depth <= 0 or data is None:
        return found

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                # Detect job-like object
                has_title = any(k in item for k in ["title", "job_title", "name", "text", "positionTitle", "jobTitle"])
                has_meta = any(l in item for l in ["location", "city", "url", "applyUrl", "link", "id", "requisitionId", "department", "team"])
                if has_title and has_meta:
                    found.append(item)
                else:
                    found.extend(_find_job_dicts(item, max_depth - 1))
            elif isinstance(item, list):
                found.extend(_find_job_dicts(item, max_depth - 1))

    elif isinstance(data, dict):
        for k in ["jobs", "postings", "positions", "openings", "results", "data", "items", "jobPostings", "requisitions"]:
            if k in data and isinstance(data[k], (list, dict)):
                found.extend(_find_job_dicts(data[k], max_depth - 1))
        # Fallback: traverse values
        for v in data.values():
            if isinstance(v, (list, dict)):
                found.extend(_find_job_dicts(v, max_depth - 1))

    return found


class PlaywrightJobCrawler(BaseJobSource):
    source_type: str = "playwright_crawler"

    def __init__(self, headless: bool = False):
        """
        Initialize the Playwright Crawler.
        Default is headless=False so developers can visibly see Chromium operating.
        """
        self.headless = headless

    async def fetch_jobs(self, config: dict) -> list[RawJobData]:
        """Crawl SPA / career sites using Playwright browser with live network sniffing."""
        companies: list[dict] = config.get("companies", [])
        delhi_ncr_only = config.get("delhi_ncr_only", False)
        limit_per_company = int(config.get("limit_per_company", 25))
        headless_mode = bool(config.get("headless", self.headless))
        slow_mo_ms = int(config.get("slow_mo", 250 if not headless_mode else 0))
        jobs: list[RawJobData] = []

        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("Playwright is unavailable. Skipping browser crawl.")
            return jobs

        if not companies:
            logger.warning("No companies provided to crawl.")
            return jobs

        try:
            async with async_playwright() as p:
                launch_args = [
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                ]
                if headless_mode:
                    launch_args.extend(["--disable-gpu", "--blink-settings=imagesEnabled=false"])

                logger.info(
                    "Launching Playwright Chromium browser",
                    headless=headless_mode,
                    slow_mo=slow_mo_ms,
                    companies_count=len(companies),
                )

                browser = await p.chromium.launch(
                    headless=headless_mode,
                    slow_mo=slow_mo_ms,
                    args=launch_args,
                )

                for comp in companies:
                    career_page = comp.get("career_page")
                    company_name = comp.get("name") or "Target Company"
                    if not career_page:
                        continue

                    try:
                        c_jobs = await self._crawl_single_company(
                            browser=browser,
                            company=company_name,
                            url=career_page,
                            limit=limit_per_company,
                            delhi_ncr_only=delhi_ncr_only,
                            headless=headless_mode,
                        )
                        jobs.extend(c_jobs)
                        logger.info(
                            "Company crawl completed",
                            company=company_name,
                            found=len(c_jobs),
                        )
                    except Exception as e:
                        logger.warning("Playwright crawl error for company", company=company_name, url=career_page, error=str(e))

                await browser.close()

        except Exception as e:
            logger.error("Playwright session failure", error=str(e))

        logger.info("Playwright crawler completed batch", total_crawled=len(jobs))
        return jobs

    async def _crawl_single_company(
        self,
        browser: Any,
        company: str,
        url: str,
        limit: int,
        delhi_ncr_only: bool,
        headless: bool,
    ) -> list[RawJobData]:
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 850},
        )
        page = await context.new_page()

        # If headless, abort heavy media to save bandwidth; in non-headless mode keep visuals intact
        if headless:
            await page.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in ["image", "media", "font"]
                else route.continue_(),
            )

        intercepted_raw_dicts: list[dict] = []

        # Sniff JSON responses from background XHR / fetch requests
        async def handle_response(response: Response):
            try:
                ct = response.headers.get("content-type", "")
                resp_url = response.url.lower()
                if "application/json" in ct or "text/plain" in ct:
                    if any(k in resp_url for k in ["job", "position", "career", "posting", "opening", "graphql", "search", "vacanc"]):
                        data = await response.json()
                        extracted = _find_job_dicts(data)
                        if extracted:
                            intercepted_raw_dicts.extend(extracted)
            except Exception:
                pass

        page.on("response", handle_response)

        logger.info("Navigating to career page", company=company, url=url)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(2000)
        except Exception as e:
            logger.debug("Page goto timeout/warning", url=url, error=str(e))

        # Smooth auto-scroll down to trigger lazy-loaded listings / infinite scroll
        try:
            for _ in range(3):
                await page.evaluate("window.scrollBy(0, 700);")
                await page.wait_for_timeout(800)
        except Exception:
            pass

        results: list[RawJobData] = []
        seen_urls: set[str] = set()

        # 1. Primary Priority: Intercepted JSON network feeds
        if intercepted_raw_dicts:
            logger.info("Processing intercepted background API jobs", count=len(intercepted_raw_dicts))
            for item in intercepted_raw_dicts:
                if len(results) >= limit:
                    break
                if not isinstance(item, dict):
                    continue

                raw_title = str(
                    item.get("title")
                    or item.get("job_title")
                    or item.get("jobTitle")
                    or item.get("name")
                    or item.get("positionTitle")
                    or ""
                ).strip()

                raw_loc = ""
                loc_val = item.get("location") or item.get("city") or item.get("locations") or item.get("jobLocation")
                if isinstance(loc_val, str):
                    raw_loc = loc_val
                elif isinstance(loc_val, dict):
                    raw_loc = str(loc_val.get("name") or loc_val.get("city") or loc_val.get("addressLocality") or "")
                elif isinstance(loc_val, list) and len(loc_val) > 0:
                    first = loc_val[0]
                    raw_loc = first if isinstance(first, str) else str(first.get("name") or first.get("city") or "")

                desc = str(item.get("description") or item.get("summary") or item.get("descriptionPlain") or "")
                job_url = str(item.get("url") or item.get("apply_url") or item.get("applyUrl") or item.get("hostedUrl") or item.get("link") or url)

                # Format relative URL to absolute
                if job_url.startswith("/"):
                    parsed_base = urllib.parse.urlparse(url)
                    job_url = f"{parsed_base.scheme}://{parsed_base.netloc}{job_url}"

                if not raw_title or len(raw_title) < 3 or raw_title.lower() in ["jobs", "openings", "careers"]:
                    continue

                if job_url in seen_urls:
                    continue

                if delhi_ncr_only and not is_delhi_ncr_job(raw_loc, f"{raw_title} {desc}"):
                    continue

                seen_urls.add(job_url)
                is_remote = bool("remote" in raw_loc.lower() or "remote" in raw_title.lower() or item.get("isRemote"))
                std_loc = standardize_india_location(company, raw_loc, is_remote)

                results.append(
                    RawJobData(
                        title=raw_title,
                        company=company,
                        location=std_loc,
                        is_remote=is_remote,
                        source_url=job_url,
                        application_url=job_url,
                        description=desc[:4000] if desc else f"### {raw_title}\n\n**Company**: {company}\n**Location**: {std_loc}",
                        external_id=f"pw_{abs(hash(job_url))}",
                        source="career",
                    )
                )

        # 2. Secondary Priority: Semantic DOM Extraction if API interception returned nothing
        if not results:
            # Check if this is a career landing page with a CTA button pointing to the real job board
            board_link = await page.evaluate(
                """() => {
                    const candidateLinks = Array.from(document.querySelectorAll('a')).map(a => ({
                        text: (a.innerText || '').trim().toLowerCase(),
                        href: a.href || ''
                    }));
                    // Check for external/subdomain ATS links
                    const ats = candidateLinks.find(l => /myworkdayjobs\\.com|greenhouse\\.io|jobs\\.lever\\.co|ashbyhq\\.com|smartrecruiters\\.com|recruitee\\.com/i.test(l.href));
                    if (ats) return ats.href;

                    // Check for CTA buttons like "View Open Positions", "Search Jobs", "Explore Roles"
                    const cta = candidateLinks.find(l => 
                        /view open (positions|roles|jobs)/i.test(l.text) ||
                        /^(view|see|explore|browse)\\s*(all\\s*)?(open\\s*)?(positions|roles|jobs|openings)$/i.test(l.text)
                    );
                    if (cta && cta.href && !cta.href.endsWith('#') && cta.href !== window.location.href) {
                        return cta.href;
                    }
                    return null;
                }"""
            )

            if board_link and board_link != url:
                logger.info("Detected job board portal link on landing page; following", board_url=board_link)
                try:
                    await page.goto(board_link, wait_until="domcontentloaded", timeout=20000)
                    await page.wait_for_timeout(2000)
                    for _ in range(2):
                        await page.evaluate("window.scrollBy(0, 600);")
                        await page.wait_for_timeout(600)
                except Exception as e:
                    logger.debug("Redirect to job board portal timeout", error=str(e))

            logger.info("Performing semantic DOM card extraction on page")
            dom_jobs = await page.evaluate(
                """() => {
                    const jobs = [];
                    // 1. Check for Oracle Cloud HCM (.job-tile)
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
                                jobs.push({ title, location: loc, url: href, desc: '' });
                            }
                        });
                        if (jobs.length > 0) return jobs;
                    }

                    // 2. Schema.org JSON-LD scripts
                    const ldScripts = document.querySelectorAll('script[type="application/ld+json"]');
                    for (const s of ldScripts) {
                        try {
                            const parsed = JSON.parse(s.innerText);
                            const items = Array.isArray(parsed) ? parsed : [parsed];
                            for (const item of items) {
                                if (item && (item['@type'] === 'JobPosting' || item['@type'] === 'jobposting')) {
                                    jobs.push({
                                        title: item.title,
                                        location: item.jobLocation?.address?.addressLocality || item.jobLocation?.address?.addressRegion || (typeof item.jobLocation === 'string' ? item.jobLocation : ''),
                                        url: item.url || window.location.href,
                                        desc: item.description || ''
                                    });
                                }
                            }
                        } catch(e) {}
                    }
                    if (jobs.length > 0) return jobs;

                    // 2. Dedicated Job Card selectors
                    const cardSelectors = [
                        '[data-testid*="job"]', '[data-qa*="job"]', '.job-card', '.career-card',
                        '.job-item', '.posting', '.opening', '[class*="JobCard"]', '[class*="job-listing"]',
                        'tr[class*="job"]', 'li[class*="job"]'
                    ];
                    for (const sel of cardSelectors) {
                        const cards = document.querySelectorAll(sel);
                        if (cards.length >= 2) {
                            cards.forEach(c => {
                                const link = c.querySelector('a') || (c.tagName === 'A' ? c : null);
                                const titleEl = c.querySelector('h2, h3, h4, [class*="title"]') || link || c;
                                const locEl = c.querySelector('[class*="location"], [class*="loc"], [class*="city"]');
                                const title = titleEl ? titleEl.innerText.trim().split('\\n')[0] : '';
                                const loc = locEl ? locEl.innerText.trim() : '';
                                const href = link ? link.href : window.location.href;
                                if (title && title.length >= 4 && title.length <= 110) {
                                    jobs.push({ title, location: loc, url: href, desc: '' });
                                }
                            });
                            if (jobs.length > 0) return jobs;
                        }
                    }

                    // 3. Fallback: Anchors with job-like URLs
                    const anchors = document.querySelectorAll('a[href*="/job/"], a[href*="/jobs/"], a[href*="/career/"], a[href*="/careers/"], a[href*="/position/"], a[href*="/positions/"], a[href*="/opening/"], a[href*="/openings/"]');
                    anchors.forEach(a => {
                        const txt = a.innerText.trim();
                        const lines = txt.split('\\n').map(l => l.trim()).filter(Boolean);
                        if (lines.length > 0) {
                            const firstLine = lines[0];
                            if (firstLine.length >= 4 && firstLine.length <= 95 && !/^(explore|view all|careers|about|search|apply|learn more|see jobs|more info)$/i.test(firstLine)) {
                                jobs.push({
                                    title: firstLine,
                                    location: lines.length > 1 ? lines[1] : '',
                                    url: a.href,
                                    desc: ''
                                });
                            }
                        }
                    });

                    return jobs.slice(0, 40);
                }"""
            )

            for d in dom_jobs:
                if len(results) >= limit:
                    break
                title = str(d.get("title") or "").strip()
                loc = str(d.get("location") or "").strip()
                job_url = str(d.get("url") or url).strip()

                if not title or len(title) < 4:
                    continue
                if job_url in seen_urls:
                    continue

                if delhi_ncr_only and loc and not is_delhi_ncr_job(loc, title):
                    continue

                seen_urls.add(job_url)
                is_remote = bool("remote" in loc.lower() or "remote" in title.lower())
                std_loc = standardize_india_location(company, loc, is_remote)

                results.append(
                    RawJobData(
                        title=title,
                        company=company,
                        location=std_loc,
                        is_remote=is_remote,
                        source_url=job_url,
                        application_url=job_url,
                        description=f"### {title}\n\n**Company**: {company}\n**Location**: {std_loc}\n\nDiscovered via career portal crawler.",
                        external_id=f"pw_{abs(hash(job_url))}",
                        source="career",
                    )
                )

        await context.close()
        return results


# ==============================================================================
# Standalone CLI Entrypoint for Testing a Single Career Page
# ==============================================================================
async def main_cli():
    parser = argparse.ArgumentParser(description="Test Playwright Crawler on a Single Career Page (Non-Headless by default).")
    parser.add_argument("--url", required=True, help="Target Career Page URL (e.g. 'https://openai.com/careers' or 'https://www.anthropic.com/careers')")
    parser.add_argument("--company", default=None, help="Company name (optional; defaults to domain name)")
    parser.add_argument("--headless", action="store_true", default=False, help="Run browser in headless mode (default: False / visible window)")
    parser.add_argument("--limit", type=int, default=15, help="Max jobs to extract (default: 15)")
    parser.add_argument("--delhi-ncr-only", action="store_true", default=False, help="Filter strictly for Delhi NCR jobs")
    parser.add_argument("--slow-mo", type=int, default=300, help="Slow down operations by N milliseconds (default: 300ms for visible viewing)")

    args = parser.parse_args()

    # Determine company name if omitted
    comp_name = args.company
    if not comp_name:
        domain = urllib.parse.urlparse(args.url).netloc.replace("www.", "")
        comp_name = domain.split(".")[0].title()

    print("\n" + "=" * 70)
    print("🚀 SLEEPY APPLY — PLAYWRIGHT CAREER CRAWLER TEST CLI")
    print("=" * 70)
    print(f" Target Company : {comp_name}")
    print(f" Career URL     : {args.url}")
    print(f" Headless Mode  : {args.headless} (Visible window: {not args.headless})")
    print(f" Delhi NCR Only : {args.delhi_ncr_only}")
    print(f" Job Limit      : {args.limit}")
    print("=" * 70 + "\n")

    crawler = PlaywrightJobCrawler(headless=args.headless)
    jobs = await crawler.fetch_jobs({
        "companies": [{"name": comp_name, "career_page": args.url}],
        "delhi_ncr_only": args.delhi_ncr_only,
        "limit_per_company": args.limit,
        "headless": args.headless,
        "slow_mo": args.slow_mo,
    })

    print("\n" + "=" * 70)
    print(f"🎯 CRAWL COMPLETE: Found {len(jobs)} jobs for {comp_name}")
    print("=" * 70)

    if not jobs:
        print("⚠️ No jobs extracted. The page might require deeper selectors, CAPTCHA bypass, or dynamic buttons.")
        return

    for idx, j in enumerate(jobs, 1):
        remote_tag = " [REMOTE]" if j.is_remote else ""
        print(f"[{idx:02d}] {j.title}")
        print(f"     📍 Location: {j.location}{remote_tag}")
        print(f"     🔗 URL: {j.application_url}")
        print("-" * 70)

    print(f"\n✅ Total successfully parsed: {len(jobs)} postings.\n")


if __name__ == "__main__":
    asyncio.run(main_cli())
