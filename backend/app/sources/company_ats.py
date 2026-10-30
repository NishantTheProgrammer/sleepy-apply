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
    r"\b(india|bengaluru|bangalore|hyderabad|pune|mumbai|delhi|new delhi|gurgaon|gurugram|noida|greater noida|faridabad|ghaziabad|manesar|cyber city|chennai|kolkata|ahmedabad|kochi|cochin|trivandrum|chandigarh|jaipur|indore)\b",
    re.IGNORECASE,
)

DELHI_NCR_LOCATION_REGEX = re.compile(
    r"\b(delhi|new delhi|gurgaon|gurugram|noida|greater noida|faridabad|ghaziabad|manesar|cyber city|cybercity|sohna|okhla|aerocity|connaught place|nehru place)\b",
    re.IGNORECASE,
)

INDIAN_DOMESTIC_COMPANIES = {
    # Delhi NCR Tech Giants & Unicorns
    "zomato", "blinkit", "paytm", "policybazaar", "urban company", "delhivery",
    "makemytrip", "sprinklr", "pine labs", "bharatpe", "cars24", "nykaa",
    "airtel", "lenskart", "spinny", "moglix", "shiprocket", "mamaearth",
    "pristyn care", "unacademy", "physicswallah", "ixigo", "indiamart",
    # Other Pan-India Domestic Tech
    "razorpay", "cred", "meesho", "groww", "swiggy", "zepto",
    "postman", "browserstack", "phonepe", "inmobi", "hackerrank", "slice",
    "ola", "flipkart", "chargebee", "freshworks", "ather energy", "clevertap",
    "khatabook", "dream11"
}


def is_delhi_ncr_job(location: str, text_snippet: str = "") -> bool:
    """Check if job is located specifically in Delhi NCR."""
    loc_lower = location.strip().lower()
    if DELHI_NCR_LOCATION_REGEX.search(loc_lower):
        return True
    if "remote" in loc_lower and ("delhi" in loc_lower or "ncr" in loc_lower or "gurugram" in loc_lower or "noida" in loc_lower):
        return True
    if text_snippet and DELHI_NCR_LOCATION_REGEX.search(text_snippet.lower()[:300]):
        return True
    return False


def is_indian_job(company: str, location: str, text_snippet: str = "") -> bool:
    """Check if a job posting is in India or remote within India."""
    comp_lower = company.strip().lower()
    loc_lower = location.strip().lower()

    # Check direct location string
    if INDIA_LOCATION_REGEX.search(loc_lower):
        return True

    # Domestic Indian tech companies are in India by default unless explicitly in another country
    if comp_lower in INDIAN_DOMESTIC_COMPANIES:
        foreign_locations = [
            "united states", "usa", "san francisco", "new york", "london", "dublin",
            "singapore", "sydney", "berlin", "tokyo", "paris", "santa clara", "san mateo",
            "egypt", "cairo", "dubai", "malaysia", "skopje", "debar", "pristina", "canada",
            "australia", "germany", "japan", "netherlands", "brazil", "poland"
        ]
        if any(fl in loc_lower for fl in foreign_locations):
            return False
        if not loc_lower or INDIA_LOCATION_REGEX.search(loc_lower):
            return True

    # Remote checking
    if "remote" in loc_lower:
        foreign_terms = ["us only", "us/canada", "emea", "latam", "americas", "north america"]
        if any(ft in loc_lower for ft in foreign_terms):
            return False
        if "india" in loc_lower or "india" in text_snippet.lower():
            return True
        # If it says Remote (APAC) or Worldwide without foreign restriction
        if any(term in loc_lower for term in ["apac", "worldwide", "anywhere", "global"]):
            return True

    return False


def standardize_india_location(company: str, loc_name: str, is_remote: bool) -> str:
    """Format and normalize the location string for clean UI display, prioritizing Delhi NCR hubs."""
    clean = loc_name.strip()
    loc_lower = clean.lower()

    if not clean:
        if company.lower() in ["zomato", "blinkit", "urban company", "delhivery", "paytm", "policybazaar", "sprinklr", "pine labs"]:
            return "Gurugram, India" if not is_remote else "Remote - Gurugram, India"
        if company.lower() in INDIAN_DOMESTIC_COMPANIES:
            return "Delhi NCR, India" if not is_remote else "Remote - India"
        return "Remote - India" if is_remote else "India"

    # Normalize Delhi NCR Tech Hubs first
    if "gurgaon" in loc_lower or "gurugram" in loc_lower or "cyber city" in loc_lower or "manesar" in loc_lower:
        prefix = "Remote - " if is_remote else ""
        return f"{prefix}Gurugram, India"
    if "noida" in loc_lower or "greater noida" in loc_lower:
        prefix = "Remote - " if is_remote else ""
        return f"{prefix}Noida, India"
    if "delhi" in loc_lower or "new delhi" in loc_lower or "okhla" in loc_lower or "aerocity" in loc_lower:
        prefix = "Remote - " if is_remote else ""
        return f"{prefix}Delhi NCR, India"
    if "faridabad" in loc_lower:
        prefix = "Remote - " if is_remote else ""
        return f"{prefix}Faridabad, India"
    if "ghaziabad" in loc_lower:
        prefix = "Remote - " if is_remote else ""
        return f"{prefix}Ghaziabad, India"

    # Other common Indian tech hubs
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
    if "chennai" in loc_lower:
        prefix = "Remote - " if is_remote else ""
        return f"{prefix}Chennai, India"

    if is_remote and "india" in loc_lower:
        return "Remote - India"

    if "india" not in loc_lower and INDIA_LOCATION_REGEX.search(loc_lower):
        return f"{clean}, India"

    return clean


class CompanyATSJobSource(BaseJobSource):
    source_type: str = "career"

    async def fetch_jobs(self, config: dict) -> list[RawJobData]:
        """Fetch jobs concurrently from target companies ATS APIs (Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Darwinbox, Keka)."""
        companies: list[dict] = config.get("companies", [])
        limit_per_company = config.get("limit_per_company", 50)
        india_only = config.get("india_only", True)
        delhi_ncr_only = config.get("delhi_ncr_only", False)
        jobs: list[RawJobData] = []
        sem = asyncio.Semaphore(15)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        }

        async def fetch_single_company(client: httpx.AsyncClient, comp: dict) -> list[RawJobData]:
            ats_type = (comp.get("ats_type") or "").lower().strip()
            board_token = comp.get("board_token")
            company_name = comp.get("name", "Unknown")
            career_page = comp.get("career_page", "")

            valid_ats = ["greenhouse", "lever", "ashby", "smartrecruiters", "workday", "darwinbox", "keka"]
            if not board_token or ats_type not in valid_ats:
                return []

            comp_jobs: list[RawJobData] = []
            async with sem:
                try:
                    # 1. Greenhouse
                    if ats_type == "greenhouse":
                        url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
                        res = await client.get(url)
                        if res.status_code == 200:
                            data = res.json()
                            for item in data.get("jobs", []):
                                loc = item.get("location", {})
                                loc_name = loc.get("name", "") if isinstance(loc, dict) else str(loc)
                                content = self._clean_html(item.get("content", ""))

                                if self._matches_geo_filter(company_name, loc_name, content[:400], india_only, delhi_ncr_only):
                                    comp_jobs.append(self._parse_greenhouse_job(item, company_name, career_page))
                                    if len(comp_jobs) >= limit_per_company:
                                        break

                    # 2. Lever
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

                                if self._matches_geo_filter(company_name, loc_name, desc[:400], india_only, delhi_ncr_only):
                                    comp_jobs.append(self._parse_lever_job(item, company_name, career_page))
                                    if len(comp_jobs) >= limit_per_company:
                                        break

                    # 3. Ashby
                    elif ats_type == "ashby":
                        url = f"https://api.ashbyhq.com/posting-api/job-board/{board_token}"
                        res = await client.get(url)
                        if res.status_code == 200:
                            data = res.json()
                            for item in data.get("jobs", []):
                                loc_name = str(item.get("location", ""))
                                desc = self._clean_html(item.get("descriptionHtml") or item.get("descriptionPlain", ""))

                                if self._matches_geo_filter(company_name, loc_name, desc[:400], india_only, delhi_ncr_only):
                                    comp_jobs.append(self._parse_ashby_job(item, company_name, career_page))
                                    if len(comp_jobs) >= limit_per_company:
                                        break

                    # 4. SmartRecruiters (Public API)
                    elif ats_type == "smartrecruiters":
                        url = f"https://api.smartrecruiters.com/v1/companies/{board_token}/postings?limit=100"
                        res = await client.get(url)
                        if res.status_code == 200:
                            data = res.json()
                            for item in data.get("content", []):
                                loc = item.get("location", {})
                                city = loc.get("city", "") if isinstance(loc, dict) else ""
                                region = loc.get("region", "") if isinstance(loc, dict) else ""
                                loc_name = f"{city}, {region}".strip(", ")
                                title = item.get("name", "")

                                if self._matches_geo_filter(company_name, loc_name, title, india_only, delhi_ncr_only):
                                    comp_jobs.append(self._parse_smartrecruiters_job(item, company_name, board_token, career_page))
                                    if len(comp_jobs) >= limit_per_company:
                                        break

                    # 5. Workday CXS (Candidate Experience Service JSON API)
                    elif ats_type == "workday":
                        tenant = board_token
                        site = "careers"
                        if "/" in board_token:
                            tenant, site = board_token.split("/", 1)
                        wd_url = f"https://{tenant}.wd3.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
                        payload = {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "India"}
                        res = await client.post(wd_url, json=payload)
                        if res.status_code == 200:
                            data = res.json()
                            for item in data.get("jobPostings", []):
                                loc_name = str(item.get("locationsText", ""))
                                title = str(item.get("title", ""))

                                if self._matches_geo_filter(company_name, loc_name, title, india_only, delhi_ncr_only):
                                    comp_jobs.append(self._parse_workday_job(item, company_name, tenant, site, career_page))
                                    if len(comp_jobs) >= limit_per_company:
                                        break

                    # 6. Darwinbox (Indian Tech Public Career API)
                    elif ats_type == "darwinbox":
                        url = f"https://{board_token}.darwinbox.in/careers/getjobs"
                        res = await client.get(url)
                        if res.status_code == 200:
                            data = res.json()
                            raw_list = data.get("data") if isinstance(data, dict) else data
                            if isinstance(raw_list, list):
                                for item in raw_list:
                                    loc_name = str(item.get("location") or item.get("city") or "")
                                    title = str(item.get("job_title") or item.get("title") or "")
                                    desc = self._clean_html(str(item.get("job_description") or ""))

                                    if self._matches_geo_filter(company_name, loc_name, desc[:400], india_only, delhi_ncr_only):
                                        comp_jobs.append(self._parse_darwinbox_job(item, company_name, board_token, career_page))
                                        if len(comp_jobs) >= limit_per_company:
                                            break

                    # 7. Keka Hire (Indian Tech Public API)
                    elif ats_type == "keka":
                        url = f"https://{board_token}.keka.com/careers/api/joblistings"
                        res = await client.get(url)
                        if res.status_code == 200:
                            data = res.json()
                            raw_list = data if isinstance(data, list) else data.get("jobs", [])
                            for item in raw_list:
                                loc = item.get("location", {})
                                loc_name = loc.get("city", "") if isinstance(loc, dict) else str(loc)
                                desc = self._clean_html(str(item.get("description") or ""))

                                if self._matches_geo_filter(company_name, loc_name, desc[:400], india_only, delhi_ncr_only):
                                    comp_jobs.append(self._parse_keka_job(item, company_name, board_token, career_page))
                                    if len(comp_jobs) >= limit_per_company:
                                        break

                except Exception as e:
                    logger.debug("Skip company ATS error", company=company_name, ats=ats_type, error=str(e))

            return comp_jobs

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers) as client:
            tasks = [fetch_single_company(client, comp) for comp in companies]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, list):
                    jobs.extend(r)

        logger.info("Company ATS fetch completed", total_fetched=len(jobs), india_only=india_only, delhi_ncr_only=delhi_ncr_only)
        return jobs

    def _matches_geo_filter(self, company: str, location: str, text: str, india_only: bool, delhi_ncr_only: bool) -> bool:
        """Evaluate if job passes Indian or Delhi NCR geo criteria."""
        if delhi_ncr_only:
            return is_delhi_ncr_job(location, text)
        if india_only:
            return is_indian_job(company, location, text)
        return True

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

    def _parse_smartrecruiters_job(self, item: dict, company: str, board_token: str, default_url: str) -> RawJobData:
        loc = item.get("location", {})
        city = loc.get("city", "") if isinstance(loc, dict) else ""
        region = loc.get("region", "") if isinstance(loc, dict) else ""
        raw_loc = f"{city}, {region}".strip(", ")
        is_remote = bool(loc.get("remote", False) if isinstance(loc, dict) else False)
        std_loc = standardize_india_location(company, raw_loc, is_remote)
        job_id = str(item.get("id", ""))
        app_url = f"https://jobs.smartrecruiters.com/{board_token}/{job_id}" if job_id else default_url
        emp_type = item.get("typeOfEmployment", {}).get("label", "full-time").lower() if isinstance(item.get("typeOfEmployment"), dict) else "full-time"

        desc = (
            f"### {item.get('name', 'Software Engineer')}\n\n"
            f"**Company**: {company}\n"
            f"**Location**: {std_loc}\n"
            f"**Employment Type**: {emp_type.title()}\n\n"
            f"Active requisition sourced via SmartRecruiters for {company} in {std_loc}."
        )

        return RawJobData(
            title=str(item.get("name", "Software Engineer")).strip(),
            company=company,
            source="career",
            source_url=default_url,
            description=desc,
            location=std_loc,
            is_remote=is_remote,
            employment_type=emp_type if emp_type in ["full-time", "part-time", "contract", "internship"] else "full-time",
            application_url=app_url,
            external_id=f"sr_{job_id}" if job_id else None,
        )

    def _parse_workday_job(self, item: dict, company: str, tenant: str, site: str, default_url: str) -> RawJobData:
        raw_loc = str(item.get("locationsText", ""))
        is_remote = bool("remote" in raw_loc.lower())
        std_loc = standardize_india_location(company, raw_loc, is_remote)
        ext_path = str(item.get("externalPath", ""))
        app_url = f"https://{tenant}.wd3.myworkdayjobs.com/en-US/{site}{ext_path}" if ext_path else default_url
        job_id = ext_path.split("_")[-1] if "_" in ext_path else ext_path.replace("/job/", "").replace("/", "_")

        desc = (
            f"### {item.get('title', 'Software Engineer')}\n\n"
            f"**Company**: {company}\n"
            f"**Location**: {std_loc}\n"
            f"**Workday Requisition ID**: `{job_id}`\n\n"
            f"Active engineering requisition from {company} powered by Workday CXS for {std_loc}."
        )

        return RawJobData(
            title=str(item.get("title", "Software Engineer")).strip(),
            company=company,
            source="career",
            source_url=default_url,
            description=desc,
            location=std_loc,
            is_remote=is_remote,
            employment_type="full-time",
            application_url=app_url,
            external_id=f"wd_{job_id}" if job_id else None,
        )

    def _parse_darwinbox_job(self, item: dict, company: str, board_token: str, default_url: str) -> RawJobData:
        raw_loc = str(item.get("location") or item.get("city") or "")
        is_remote = bool("remote" in raw_loc.lower())
        std_loc = standardize_india_location(company, raw_loc, is_remote)
        job_id = str(item.get("job_id") or item.get("id") or "")
        app_url = f"https://{board_token}.darwinbox.in/careers/job-details?job_id={job_id}" if job_id else default_url
        desc_raw = self._clean_html(str(item.get("job_description") or item.get("description") or ""))

        desc = desc_raw if len(desc_raw) > 50 else (
            f"### {item.get('job_title') or item.get('title') or 'Software Engineer'}\n\n"
            f"**Company**: {company}\n"
            f"**Location**: {std_loc}\n"
            f"Active posting on Darwinbox for {company}."
        )

        return RawJobData(
            title=str(item.get("job_title") or item.get("title") or "Software Engineer").strip(),
            company=company,
            source="career",
            source_url=default_url,
            description=desc[:5000],
            location=std_loc,
            is_remote=is_remote,
            employment_type="full-time",
            application_url=app_url,
            external_id=f"db_{job_id}" if job_id else None,
        )

    def _parse_keka_job(self, item: dict, company: str, board_token: str, default_url: str) -> RawJobData:
        loc = item.get("location", {})
        raw_loc = loc.get("city", "") if isinstance(loc, dict) else str(loc)
        is_remote = bool("remote" in raw_loc.lower())
        std_loc = standardize_india_location(company, raw_loc, is_remote)
        job_id = str(item.get("id") or "")
        app_url = f"https://{board_token}.keka.com/careers/jobdetails/{job_id}" if job_id else default_url
        desc_raw = self._clean_html(str(item.get("description") or ""))

        desc = desc_raw if len(desc_raw) > 50 else (
            f"### {item.get('title', 'Software Engineer')}\n\n"
            f"**Company**: {company}\n"
            f"**Location**: {std_loc}\n"
            f"Active tech posting hosted on Keka Hire for {company}."
        )

        return RawJobData(
            title=str(item.get("title", "Software Engineer")).strip(),
            company=company,
            source="career",
            source_url=default_url,
            description=desc[:5000],
            location=std_loc,
            is_remote=is_remote,
            employment_type="full-time",
            application_url=app_url,
            external_id=f"keka_{job_id}" if job_id else None,
        )
