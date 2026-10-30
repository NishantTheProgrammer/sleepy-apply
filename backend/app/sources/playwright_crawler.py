import asyncio
import re
import json
from typing import Any
import structlog
from app.sources.base import BaseJobSource, RawJobData
from app.sources.company_ats import standardize_india_location, is_delhi_ncr_job

logger = structlog.get_logger()

# Check if playwright is importable; handle graceful fallback
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.async_api import async_playwright, Browser, Page, Response
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    logger.info("Playwright is not installed in current Python environment. SPA fallback will use HTTP mode.")


class PlaywrightJobCrawler(BaseJobSource):
    source_type: str = "playwright_crawler"

    def __init__(self):
        self.browser: Any = None
        self.playwright: Any = None

    async def fetch_jobs(self, config: dict) -> list[RawJobData]:
        """Crawl SPA / complex career sites using Playwright headless browser with network sniffing."""
        companies: list[dict] = config.get("companies", [])
        delhi_ncr_only = config.get("delhi_ncr_only", True)
        limit_per_company = config.get("limit_per_company", 20)
        jobs: list[RawJobData] = []

        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("Playwright is unavailable. Skipping headless browser crawl.")
            return jobs

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--blink-settings=imagesEnabled=false",
                    ],
                )

                for comp in companies:
                    career_page = comp.get("career_page")
                    company_name = comp.get("name", "Unknown Company")
                    if not career_page:
                        continue

                    try:
                        c_jobs = await self._crawl_single_company(browser, company_name, career_page, limit_per_company, delhi_ncr_only)
                        jobs.extend(c_jobs)
                    except Exception as e:
                        logger.warning("Playwright crawl failed for company", company=company_name, error=str(e))

                await browser.close()

        except Exception as e:
            logger.error("Playwright session error", error=str(e))

        logger.info("Playwright crawler completed", total_crawled=len(jobs))
        return jobs

    async def _crawl_single_company(
        self,
        browser: Any,
        company: str,
        url: str,
        limit: int,
        delhi_ncr_only: bool,
    ) -> list[RawJobData]:
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        # Optimize: Abort images, fonts, and stylesheets
        await page.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in ["image", "media", "font"]
            else route.continue_(),
        )

        intercepted_jobs: list[dict] = []

        # Sniff JSON responses from background XHR / fetch requests
        async def handle_response(response: Response):
            try:
                ct = response.headers.get("content-type", "")
                if "application/json" in ct and any(k in response.url.lower() for k in ["job", "position", "career", "posting", "opening"]):
                    data = await response.json()
                    if isinstance(data, list):
                        intercepted_jobs.extend(data)
                    elif isinstance(data, dict):
                        items = data.get("jobs") or data.get("postings") or data.get("data") or data.get("results") or []
                        if isinstance(items, list):
                            intercepted_jobs.extend(items)
            except Exception:
                pass

        page.on("response", handle_response)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)
        except Exception as e:
            logger.debug("Page goto timeout/warning", url=url, error=str(e))

        results: list[RawJobData] = []

        # 1. First priority: Use intercepted JSON payloads if captured
        if intercepted_jobs:
            for item in intercepted_jobs:
                if len(results) >= limit:
                    break
                if not isinstance(item, dict):
                    continue

                title = str(item.get("title") or item.get("job_title") or item.get("name") or "").strip()
                loc = str(item.get("location") or item.get("city") or "")
                desc = str(item.get("description") or item.get("summary") or "")
                job_url = str(item.get("url") or item.get("apply_url") or item.get("link") or url)

                if not title or len(title) < 3:
                    continue

                if delhi_ncr_only and not is_delhi_ncr_job(loc, f"{title} {desc}"):
                    continue

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
                        description=desc[:4000] if desc else f"### {title}\n\n**Company**: {company}\n**Location**: {std_loc}",
                        external_id=f"pw_{hash(job_url)}",
                        source="career",
                    )
                )

        # 2. Second priority: Semantic DOM extraction if no JSON was captured
        if not results:
            dom_jobs = await page.evaluate(
                """() => {
                    const jobs = [];
                    // Look for schema.org JSON-LD
                    const ldScripts = document.querySelectorAll('script[type="application/ld+json"]');
                    for (const s of ldScripts) {
                        try {
                            const data = JSON.parse(s.innerText);
                            if (data['@type'] === 'JobPosting') {
                                jobs.push({
                                    title: data.title,
                                    location: data.jobLocation?.address?.addressLocality || '',
                                    url: data.url || window.location.href,
                                    desc: data.description || ''
                                });
                            }
                        } catch(e) {}
                    }
                    if (jobs.length > 0) return jobs;

                    // Common card links
                    const anchors = document.querySelectorAll('a[href*="/job/"], a[href*="/careers/"], a[href*="/position/"]');
                    anchors.forEach(a => {
                        const txt = a.innerText.trim();
                        if (txt.length > 5 && txt.length < 120 && !txt.includes('Explore') && !txt.includes('View all')) {
                            jobs.push({
                                title: txt.split('\\n')[0],
                                location: txt.split('\\n')[1] || '',
                                url: a.href,
                                desc: ''
                            });
                        }
                    });
                    return jobs.slice(0, 30);
                }"""
            )

            for d in dom_jobs:
                if len(results) >= limit:
                    break
                title = d.get("title", "").strip()
                loc = d.get("location", "").strip()
                job_url = d.get("url") or url

                if not title or len(title) < 4:
                    continue

                if delhi_ncr_only and loc and not is_delhi_ncr_job(loc, title):
                    continue

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
                        external_id=f"pw_{hash(job_url)}",
                        source="career",
                    )
                )

        await context.close()
        return results

