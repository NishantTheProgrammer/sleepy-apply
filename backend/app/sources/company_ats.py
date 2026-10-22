import httpx
import re
from typing import Any
import structlog
from app.sources.base import BaseJobSource, RawJobData

logger = structlog.get_logger()


import asyncio

class CompanyATSJobSource(BaseJobSource):
    source_type: str = "company_ats"

    async def fetch_jobs(self, config: dict) -> list[RawJobData]:
        """Fetch jobs concurrently from target companies ATS APIs (Greenhouse, Lever, Ashby)."""
        companies: list[dict] = config.get("companies", [])
        limit_per_company = config.get("limit_per_company", 10)
        jobs: list[RawJobData] = []
        sem = asyncio.Semaphore(15)

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        async def fetch_single_company(client: httpx.AsyncClient, comp: dict) -> list[RawJobData]:
            ats_type = (comp.get("ats_type") or "").lower()
            board_token = comp.get("board_token")
            company_name = comp.get("name", "Unknown")
            career_page = comp.get("career_page", "")

            if not board_token or ats_type not in ["greenhouse", "lever", "ashby"]:
                return []

            comp_jobs: list[RawJobData] = []
            async with sem:
                try:
                    if ats_type == "greenhouse":
                        url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
                        res = await client.get(url)
                        if res.status_code == 200:
                            data = res.json()
                            for item in data.get("jobs", [])[:limit_per_company]:
                                comp_jobs.append(self._parse_greenhouse_job(item, company_name, career_page))

                    elif ats_type == "lever":
                        url = f"https://api.lever.co/v0/postings/{board_token}?mode=json"
                        res = await client.get(url)
                        if res.status_code == 200:
                            data = res.json()
                            raw_items = data if isinstance(data, list) else []
                            for item in raw_items[:limit_per_company]:
                                comp_jobs.append(self._parse_lever_job(item, company_name, career_page))

                    elif ats_type == "ashby":
                        url = f"https://api.ashbyhq.com/posting-api/job-board/{board_token}"
                        res = await client.get(url)
                        if res.status_code == 200:
                            data = res.json()
                            for item in data.get("jobs", [])[:limit_per_company]:
                                comp_jobs.append(self._parse_ashby_job(item, company_name, career_page))

                except Exception as e:
                    logger.debug("Skip company ATS error", company=company_name, ats=ats_type, error=str(e))

            return comp_jobs

        async with httpx.AsyncClient(timeout=6.0, follow_redirects=True, headers=headers) as client:
            tasks = [fetch_single_company(client, comp) for comp in companies]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, list):
                    jobs.extend(r)

        logger.info("Company ATS fetch completed", total_fetched=len(jobs))
        return jobs

    def _clean_html(self, html_str: str) -> str:
        if not html_str:
            return ""
        text = re.sub(r"<[^>]+>", " ", html_str)
        return re.sub(r"\s+", " ", text).strip()

    def _parse_greenhouse_job(self, item: dict, company: str, default_url: str) -> RawJobData:
        loc = item.get("location", {})
        loc_name = loc.get("name", "") if isinstance(loc, dict) else str(loc)
        content = self._clean_html(item.get("content", ""))

        return RawJobData(
            title=str(item.get("title", "Software Engineer")).strip(),
            company=company,
            source_url=default_url,
            description=content[:5000],
            location=loc_name,
            is_remote=bool("remote" in loc_name.lower() or "remote" in content[:300].lower()),
            employment_type="full-time",
            application_url=item.get("absolute_url") or default_url,
            external_id=str(item.get("id")) if item.get("id") else None,
        )

    def _parse_lever_job(self, item: dict, company: str, default_url: str) -> RawJobData:
        cats = item.get("categories", {})
        loc_name = cats.get("location", "") if isinstance(cats, dict) else ""
        desc = self._clean_html(item.get("descriptionPlain") or item.get("description", ""))

        return RawJobData(
            title=str(item.get("text", "Software Engineer")).strip(),
            company=company,
            source_url=default_url,
            description=desc[:5000],
            location=loc_name,
            is_remote=bool(cats.get("commitment") == "Remote" or "remote" in loc_name.lower()),
            employment_type=str(cats.get("commitment", "full-time")).lower() if isinstance(cats, dict) else "full-time",
            application_url=item.get("applyUrl") or item.get("hostedUrl") or default_url,
            external_id=str(item.get("id")) if item.get("id") else None,
        )

    def _parse_ashby_job(self, item: dict, company: str, default_url: str) -> RawJobData:
        loc_name = item.get("location", "")
        desc = self._clean_html(item.get("descriptionHtml") or item.get("descriptionPlain", ""))
        is_remote = bool(item.get("isRemote", False) or "remote" in str(loc_name).lower())

        return RawJobData(
            title=str(item.get("title", "Software Engineer")).strip(),
            company=company,
            source_url=default_url,
            description=desc[:5000],
            location=str(loc_name),
            is_remote=is_remote,
            employment_type=str(item.get("employmentType", "full-time")).lower(),
            application_url=item.get("jobUrl") or default_url,
            external_id=str(item.get("id")) if item.get("id") else None,
        )
