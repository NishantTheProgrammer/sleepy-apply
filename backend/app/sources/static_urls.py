import httpx
import re
from typing import Any
import structlog
from .base import BaseJobSource, RawJobData

logger = structlog.get_logger()


class StaticUrlJobSource(BaseJobSource):
    source_type: str = "static_urls"

    async def fetch_jobs(self, config: dict) -> list[RawJobData]:
        """Fetch jobs from a list of URLs specified in config['urls'].

        Supports JSON APIs and standard HTML career pages.
        """
        urls: list[str] = config.get("urls", [])
        jobs: list[RawJobData] = []

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for url in urls:
                try:
                    res = await client.get(url)
                    if res.status_code != 200:
                        logger.warning("Failed to fetch jobs from URL", url=url, status=res.status_code)
                        continue

                    content_type = res.headers.get("content-type", "")
                    if "application/json" in content_type:
                        data = res.json()
                        jobs.extend(self._parse_json_jobs(data, url))
                    else:
                        jobs.extend(self._parse_html_jobs(res.text, url))

                except Exception as e:
                    logger.warning("Error fetching job source URL", url=url, error=str(e))

        return jobs

    def _parse_json_jobs(self, data: Any, source_url: str) -> list[RawJobData]:
        """Extract jobs from common JSON API response formats (e.g., Lever, Greenhouse, RemoteOK)."""
        results: list[RawJobData] = []
        items = data if isinstance(data, list) else data.get("jobs", data.get("results", []))

        for item in items:
            if not isinstance(item, dict):
                continue
            title = item.get("title") or item.get("text") or item.get("position")
            company = item.get("company") or item.get("company_name") or "Unknown Company"
            if not title:
                continue

            results.append(
                RawJobData(
                    title=str(title).strip(),
                    company=str(company).strip(),
                    source_url=source_url,
                    description=str(item.get("description", "") or item.get("content", "")),
                    location=str(item.get("location", "") or item.get("categories", {}).get("location", "")),
                    is_remote=bool(item.get("is_remote", False) or "remote" in str(item.get("location", "")).lower()),
                    employment_type=str(item.get("employment_type", "full-time")),
                    application_url=str(item.get("url") or item.get("apply_url") or source_url),
                    external_id=str(item.get("id")) if item.get("id") else None,
                )
            )
        return results

    def _parse_html_jobs(self, html: str, source_url: str) -> list[RawJobData]:
        """Clean HTML and find title/company headings."""
        clean_text = re.sub(r"<[^>]+>", " ", html)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()
        title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE)
        page_title = title_match.group(1).strip() if title_match else "Job Opening"

        return [
            RawJobData(
                title=page_title,
                company="Unknown",
                source_url=source_url,
                description=clean_text[:4000],
                application_url=source_url,
            )
        ]
