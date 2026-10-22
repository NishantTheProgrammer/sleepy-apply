import httpx
import re
import html
import html2text
from typing import Any
import asyncio
import structlog
from app.sources.base import BaseJobSource, RawJobData

logger = structlog.get_logger()

_html2text_converter = html2text.HTML2Text()
_html2text_converter.ignore_links = False
_html2text_converter.ignore_images = True
_html2text_converter.body_width = 0
_html2text_converter.protect_links = True
_html2text_converter.unicode_snob = True
_html2text_converter.skip_internal_links = True

INDIA_LOCATION_REGEX = re.compile(
    r"\b(india|bengaluru|bangalore|hyderabad|pune|mumbai|delhi|gurgaon|gurugram|noida|chennai|kolkata|ahmedabad|kochi|cochin|trivandrum|chandigarh|jaipur|indore)\b",
    re.IGNORECASE,
)

INDIAN_DOMESTIC_COMPANIES = {
    "razorpay", "cred", "meesho", "groww", "swiggy", "zomato", "zepto",
    "urban company", "postman", "browserstack", "phonepe", "inmobi",
    "hackerrank", "slice", "ola", "flipkart", "chargebee", "freshworks",
    "ather energy", "clevertap", "khatabook", "dream11"
}


def is_indian_job(company: str, location: str, text_snippet: str = "") -> bool:
    """Check if a job posting is in India or remote within India."""
    comp_lower = company.strip().lower()
    loc_lower = location.strip().lower()

    # Check direct location string
    if INDIA_LOCATION_REGEX.search(loc_lower):
        return True

    # Domestic Indian tech companies are in India by default unless explicitly in another country
    if comp_lower in INDIAN_DOMESTIC_COMPANIES:
        foreign_countries = ["united states", "usa", "san francisco", "new york", "london", "dublin", "singapore", "sydney", "berlin", "tokyo", "paris"]
        if not any(fc in loc_lower for fc in foreign_countries):
            return True

    # Remote checking
    if "remote" in loc_lower:
        if "india" in loc_lower or "india" in text_snippet.lower():
            return True
        # If it says Remote (APAC) or Worldwide without US/EU restriction
        if any(term in loc_lower for term in ["apac", "worldwide", "anywhere", "global"]):
            return True

    return False


def standardize_india_location(company: str, loc_name: str, is_remote: bool) -> str:
    """Format and normalize the location string for clean UI display."""
    clean = loc_name.strip()
    loc_lower = clean.lower()

    if not clean:
        if company.lower() in INDIAN_DOMESTIC_COMPANIES:
            return "Bengaluru, India" if not is_remote else "Remote - India"
        return "Remote - India" if is_remote else "India"

    # Normalize common Indian tech hubs
    if "bengaluru" in loc_lower or "bangalore" in loc_lower:
        prefix = "Remote - " if is_remote else ""
        return f"{prefix}Bengaluru, India"
    if "hyderabad" in loc_lower:
        prefix = "Remote - " if is_remote else ""
        return f"{prefix}Hyderabad, India"
    if "pune" in loc_lower:
        prefix = "Remote - " if is_remote else ""
        return f"{prefix}Pune, India"
    if "mumbai" in loc_lower:
        prefix = "Remote - " if is_remote else ""
        return f"{prefix}Mumbai, India"
    if "gurgaon" in loc_lower or "gurugram" in loc_lower:
        prefix = "Remote - " if is_remote else ""
        return f"{prefix}Gurugram, India"
    if "noida" in loc_lower:
        prefix = "Remote - " if is_remote else ""
        return f"{prefix}Noida, India"
    if "chennai" in loc_lower:
        prefix = "Remote - " if is_remote else ""
        return f"{prefix}Chennai, India"
    if "delhi" in loc_lower:
        prefix = "Remote - " if is_remote else ""
        return f"{prefix}Delhi NCR, India"

    if is_remote and "india" in loc_lower:
        return "Remote - India"

    if "india" not in loc_lower and (company.lower() in INDIAN_DOMESTIC_COMPANIES or is_remote):
        return f"{clean}, India"

    return clean


class CompanyATSJobSource(BaseJobSource):
    source_type: str = "career"

    async def fetch_jobs(self, config: dict) -> list[RawJobData]:
        """Fetch jobs concurrently from target companies ATS APIs, specifically filtering for Indian positions."""
        companies: list[dict] = config.get("companies", [])
        limit_per_company = config.get("limit_per_company", 50)
        india_only = config.get("india_only", True)
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
                            for item in data.get("jobs", []):
                                loc = item.get("location", {})
                                loc_name = loc.get("name", "") if isinstance(loc, dict) else str(loc)
                                content = self._clean_html(item.get("content", ""))

                                if not india_only or is_indian_job(company_name, loc_name, content[:400]):
                                    parsed = self._parse_greenhouse_job(item, company_name, career_page)
                                    comp_jobs.append(parsed)
                                    if len(comp_jobs) >= limit_per_company:
                                        break

                    elif ats_type == "lever":
                        url = f"https://api.lever.co/v0/postings/{board_token}?mode=json"
                        res = await client.get(url)
                        if res.status_code == 200:
                            data = res.json()
                            raw_items = data if isinstance(data, list) else []
                            for item in raw_items:
                                cats = item.get("categories", {})
                                loc_name = cats.get("location", "") if isinstance(cats, dict) else ""
                                desc = self._clean_html(item.get("descriptionPlain") or item.get("description", ""))

                                if not india_only or is_indian_job(company_name, loc_name, desc[:400]):
                                    parsed = self._parse_lever_job(item, company_name, career_page)
                                    comp_jobs.append(parsed)
                                    if len(comp_jobs) >= limit_per_company:
                                        break

                    elif ats_type == "ashby":
                        url = f"https://api.ashbyhq.com/posting-api/job-board/{board_token}"
                        res = await client.get(url)
                        if res.status_code == 200:
                            data = res.json()
                            for item in data.get("jobs", []):
                                loc_name = str(item.get("location", ""))
                                desc = self._clean_html(item.get("descriptionHtml") or item.get("descriptionPlain", ""))

                                if not india_only or is_indian_job(company_name, loc_name, desc[:400]):
                                    parsed = self._parse_ashby_job(item, company_name, career_page)
                                    comp_jobs.append(parsed)
                                    if len(comp_jobs) >= limit_per_company:
                                        break

                except Exception as e:
                    logger.debug("Skip company ATS error", company=company_name, ats=ats_type, error=str(e))

            return comp_jobs

        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=headers) as client:
            tasks = [fetch_single_company(client, comp) for comp in companies]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, list):
                    jobs.extend(r)

        logger.info("Company ATS fetch completed", total_fetched=len(jobs), india_only=india_only)
        return jobs

    def _clean_html(self, html_str: str) -> str:
        if not html_str:
            return ""
        text = html.unescape(html_str)
        text = html.unescape(text)
        try:
            converted = _html2text_converter.handle(text)
            return re.sub(r"\n\s*\n\s*\n+", "\n\n", converted).strip()
        except Exception as e:
            logger.warning("html2text parsing failed, falling back to basic strip", error=str(e))
            clean = re.sub(r"<[^>]+>", " ", text)
            return re.sub(r"\s+", " ", clean).strip()

    def _parse_greenhouse_job(self, item: dict, company: str, default_url: str) -> RawJobData:
        loc = item.get("location", {})
        raw_loc = loc.get("name", "") if isinstance(loc, dict) else str(loc)
        content = self._clean_html(item.get("content", ""))
        is_remote = bool("remote" in raw_loc.lower() or "remote" in content[:300].lower())
        std_loc = standardize_india_location(company, raw_loc, is_remote)

        return RawJobData(
            title=str(item.get("title", "Software Engineer")).strip(),
            company=company,
            source="career",
            source_url=default_url,
            description=content[:5000],
            location=std_loc,
            is_remote=is_remote,
            employment_type="full-time",
            application_url=item.get("absolute_url") or default_url,
            external_id=str(item.get("id")) if item.get("id") else None,
        )

    def _parse_lever_job(self, item: dict, company: str, default_url: str) -> RawJobData:
        cats = item.get("categories", {})
        raw_loc = cats.get("location", "") if isinstance(cats, dict) else ""
        desc = self._clean_html(item.get("descriptionPlain") or item.get("description", ""))
        is_remote = bool(cats.get("commitment") == "Remote" or "remote" in raw_loc.lower() or "remote" in desc[:300].lower())
        std_loc = standardize_india_location(company, raw_loc, is_remote)

        return RawJobData(
            title=str(item.get("text", "Software Engineer")).strip(),
            company=company,
            source="career",
            source_url=default_url,
            description=desc[:5000],
            location=std_loc,
            is_remote=is_remote,
            employment_type=str(cats.get("commitment", "full-time")).lower() if isinstance(cats, dict) else "full-time",
            application_url=item.get("applyUrl") or item.get("hostedUrl") or default_url,
            external_id=str(item.get("id")) if item.get("id") else None,
        )

    def _parse_ashby_job(self, item: dict, company: str, default_url: str) -> RawJobData:
        raw_loc = str(item.get("location", ""))
        desc = self._clean_html(item.get("descriptionHtml") or item.get("descriptionPlain", ""))
        is_remote = bool(item.get("isRemote", False) or "remote" in raw_loc.lower())
        std_loc = standardize_india_location(company, raw_loc, is_remote)

        return RawJobData(
            title=str(item.get("title", "Software Engineer")).strip(),
            company=company,
            source="career",
            source_url=default_url,
            description=desc[:5000],
            location=std_loc,
            is_remote=is_remote,
            employment_type=str(item.get("employmentType", "full-time")).lower(),
            application_url=item.get("jobUrl") or default_url,
            external_id=str(item.get("id")) if item.get("id") else None,
        )
