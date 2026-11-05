import asyncio
import re
import urllib.parse
from datetime import datetime, timezone, timedelta
import httpx
import html2text
import structlog
from app.sources.base import BaseJobSource, RawJobData
from app.pipeline.role_search import expand_role_to_search_keywords

logger = structlog.get_logger()

_html2text = html2text.HTML2Text()
_html2text.body_width = 0
_html2text.ignore_images = True
_html2text.unicode_snob = True

COMMON_TECH_SKILLS = [
    "Python", "FastAPI", "Django", "Flask", "React", "Next.js", "Node.js", "TypeScript",
    "JavaScript", "Java", "Spring Boot", "Go", "Golang", "Kubernetes", "Docker", "AWS",
    "Azure", "GCP", "PostgreSQL", "MySQL", "MongoDB", "Redis", "Kafka", "GraphQL",
    "REST APIs", "Microservices", "C++", "C#", ".NET", "Rust", "Swift", "Kotlin",
    "TailwindCSS", "Elasticsearch", "CI/CD", "Git"
]


def extract_skills_from_text(text: str) -> list[str]:
    found = []
    text_lower = text.lower()
    for s in COMMON_TECH_SKILLS:
        pattern = rf"\b{re.escape(s.lower())}\b"
        if re.search(pattern, text_lower):
            found.append(s)
    return found[:8]


def parse_relative_time_to_datetime(raw_text: str) -> datetime | None:
    """Convert relative time strings like '2 days ago', '3 weeks ago', or ISO dates to UTC datetime."""
    if not raw_text:
        return None
    now = datetime.now(timezone.utc)
    text = raw_text.strip().lower()

    # Try ISO date first (e.g. 2026-10-28)
    iso_match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if iso_match:
        try:
            return datetime.fromisoformat(iso_match.group(1)).replace(tzinfo=timezone.utc)
        except Exception:
            pass

    # Relative time parsing
    num_match = re.search(r"(\d+)\s*(hour|minute|day|week|month|year)", text)
    if num_match:
        val = int(num_match.group(1))
        unit = num_match.group(2)
        if "hour" in unit or "minute" in unit:
            return now - timedelta(hours=max(1, val))
        if "day" in unit:
            return now - timedelta(days=val)
        if "week" in unit:
            return now - timedelta(weeks=val)
        if "month" in unit:
            return now - timedelta(days=val * 30)
        if "year" in unit:
            return now - timedelta(days=val * 365)

    if "yesterday" in text:
        return now - timedelta(days=1)
    if "just now" in text or "today" in text:
        return now

    return None


class LinkedInJobSource(BaseJobSource):
    source_type: str = "linkedin"

    async def fetch_jobs(self, config: dict | None = None) -> list[RawJobData]:
        """Fetch fresh live tech jobs from LinkedIn guest API, applying strict recency filters and extracting posting dates."""
        config = config or {}
        raw_keywords = config.get("keywords")
        if raw_keywords:
            if isinstance(raw_keywords, str):
                raw_keywords = [raw_keywords]
            keywords_list = expand_role_to_search_keywords(raw_keywords)
        else:
            keywords_list = [
                "software engineer",
                "full stack developer",
                "backend engineer",
                "frontend engineer",
                "python developer",
                "quality engineer",
                "sdet",
                "cloud engineer",
                "devops engineer",
            ]

        delhi_ncr_only = config.get("delhi_ncr_only", False)
        if delhi_ncr_only:
            locations = ["Gurugram, Haryana, India", "Noida, Uttar Pradesh, India", "Delhi, India"]
        else:
            loc_cfg = config.get("location", "Delhi NCR, India")
            locations = [loc_cfg] if isinstance(loc_cfg, str) else loc_cfg

        max_jobs = int(config.get("limit", 25))
        max_age_days = int(config.get("max_age_days", 14))  # Filter out stale listings older than 14 days

        # LinkedIn recency filter parameter:
        # r86400 = past 24 hours, r604800 = past week, r1209600 = past 14 days
        tpr_param = "r604800" if max_age_days <= 7 else "r1209600"

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        collected_jobs: list[RawJobData] = []
        seen_ids: set[str] = set()
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=max_age_days)

        search_keywords = keywords_list[:5]
        rate_limited = False

        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, headers=headers) as client:
            for loc in locations:
                if len(collected_jobs) >= max_jobs or rate_limited:
                    break
                for kw in search_keywords:
                    if len(collected_jobs) >= max_jobs:
                        break
                    try:
                        q_kw = urllib.parse.quote_plus(kw)
                        q_loc = urllib.parse.quote_plus(loc)
                        search_url = (
                            f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
                            f"?keywords={q_kw}&location={q_loc}&f_TPR={tpr_param}&start=0"
                        )

                        r = await client.get(search_url, headers=headers)
                        if r.status_code == 429:
                            logger.warning("LinkedIn guest search rate limited (429)", kw=kw, loc=loc)
                            rate_limited = True
                            break
                        if r.status_code != 200:
                            logger.warning("LinkedIn guest search returned non-200", status=r.status_code, kw=kw, loc=loc)
                            continue

                        # Parse job cards
                        card_pattern = re.compile(
                            r'<div class="[^"]*base-card[^"]*"[^>]*data-entity-urn="urn:li:jobPosting:(\d+)"[^>]*>([\s\S]*?)<\/li>',
                            re.IGNORECASE,
                        )
                        matches = card_pattern.findall(r.text)

                        for jid, card_html in matches:
                            if jid in seen_ids or len(collected_jobs) >= max_jobs:
                                continue
                            seen_ids.add(jid)

                            # 1. Parse Card Time and Date
                            time_m = re.search(r'<time[^>]*datetime="([^"]+)"[^>]*>([\s\S]*?)<\/time>', card_html)
                            posted_at: datetime | None = None
                            posted_raw: str | None = None
                            if time_m:
                                dt_attr = time_m.group(1).strip()
                                posted_raw = time_m.group(2).strip()
                                try:
                                    posted_at = datetime.fromisoformat(dt_attr).replace(tzinfo=timezone.utc)
                                except Exception:
                                    posted_at = parse_relative_time_to_datetime(posted_raw)
                            else:
                                raw_date_m = re.search(r'<time[^>]*>([\s\S]*?)<\/time>', card_html)
                                if raw_date_m:
                                    posted_raw = raw_date_m.group(1).strip()
                                    posted_at = parse_relative_time_to_datetime(posted_raw)

                            # Reject stale listings based on card time (e.g., '3 months ago', '4 months ago')
                            if posted_raw:
                                p_lower = posted_raw.lower()
                                if any(term in p_lower for term in ["month", "year", "90 days", "60 days", "30 days"]):
                                    logger.debug("Discarding stale LinkedIn posting", jid=jid, age=posted_raw)
                                    continue

                            if posted_at and posted_at < cutoff_date:
                                logger.debug("Discarding LinkedIn posting older than cutoff", jid=jid, posted_at=str(posted_at))
                                continue

                            title_m = re.search(r'<h3 class="[^"]*base-search-card__title[^"]*">\s*([\s\S]*?)\s*<\/h3>', card_html)
                            comp_m = (
                                re.search(r'<h4 class="[^"]*base-search-card__subtitle[^"]*">[\s\S]*?<a[^>]*>\s*([\s\S]*?)\s*<\/a>', card_html)
                                or re.search(r'<h4 class="[^"]*base-search-card__subtitle[^"]*">\s*([\s\S]*?)\s*<\/h4>', card_html)
                            )
                            loc_m = re.search(r'<span class="[^"]*job-search-card__location[^"]*">\s*([\s\S]*?)\s*<\/span>', card_html)
                            link_m = re.search(r'<a class="[^"]*base-card__full-link[^"]*"[^>]*href="([^"]*)"', card_html)

                            title = title_m.group(1).strip() if title_m else "Software Engineer"
                            company = comp_m.group(1).strip() if comp_m else "Company"
                            loc_str = loc_m.group(1).strip() if loc_m else loc
                            job_url = link_m.group(1).strip() if link_m else f"https://www.linkedin.com/jobs/view/{jid}"

                            if "?" in job_url:
                                job_url = job_url.split("?")[0]

                            is_remote = bool(
                                "remote" in title.lower()
                                or "remote" in loc_str.lower()
                                or "work from home" in loc_str.lower()
                            )

                            # Fetch full description and deep time text if possible
                            description = ""
                            try:
                                det_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}"
                                det_res = await client.get(det_url, headers=headers)
                                if det_res.status_code == 200:
                                    desc_html = det_res.text
                                    # Deep check posting time from detail page (e.g. '3 months ago')
                                    detail_time_m = re.search(r'<span class="[^"]*posted-time-ago[^"]*">\s*([\s\S]*?)\s*<\/span>', desc_html)
                                    if detail_time_m:
                                        detail_time_raw = detail_time_m.group(1).strip()
                                        posted_raw = detail_time_raw
                                        dt_from_detail = parse_relative_time_to_datetime(detail_time_raw)
                                        if dt_from_detail:
                                            posted_at = dt_from_detail

                                        # Strict rejection if detail page states 'X months ago'
                                        if any(term in detail_time_raw.lower() for term in ["month", "year", "90 days", "60 days", "30 days"]):
                                            logger.debug("Discarding stale posting from detail page check", jid=jid, age=detail_time_raw)
                                            continue

                                    desc_match = re.search(r'<div class="[^"]*show-more-less-html__markup[^"]*">([\s\S]*?)<\/div>', desc_html)
                                    if desc_match:
                                        description = _html2text.handle(desc_match.group(1)).strip()
                                    else:
                                        description = _html2text.handle(desc_html).strip()
                            except Exception:
                                pass

                            if posted_at and posted_at < cutoff_date:
                                continue

                            # Default fallback posted_at if not detected
                            if not posted_at:
                                posted_at = datetime.now(timezone.utc)
                                posted_raw = "Recently posted"

                            if not description or len(description) < 40:
                                description = (
                                    f"### {title}\n\n"
                                    f"**Company**: {company}\n"
                                    f"**Location**: {loc_str}\n"
                                    f"**Posted**: {posted_raw or 'Recently'}\n"
                                    f"**Work Arrangement**: {'Remote' if is_remote else 'On-site / Hybrid'}\n\n"
                                    f"#### Overview\n"
                                    f"{company} has posted an active opening for **{title}** in {loc_str}. "
                                    f"This live posting is listed on LinkedIn with Job ID `{jid}`.\n\n"
                                    f"#### Application\n"
                                    f"View qualification requirements and submit your application on LinkedIn using the job link."
                                )

                            skills = extract_skills_from_text(f"{title} {description}")

                            collected_jobs.append(
                                RawJobData(
                                    title=title,
                                    company=company,
                                    location=loc_str,
                                    is_remote=is_remote,
                                    source_url=job_url,
                                    application_url=job_url,
                                    description=description,
                                    external_id=f"linkedin_{jid}",
                                    posted_at_raw=posted_raw,
                                    posted_at=posted_at,
                                    required_skills=skills,
                                    source="linkedin",
                                )
                            )

                        await asyncio.sleep(0.5)

                    except Exception as e:
                        logger.warning("LinkedIn search iteration failed", error=str(e), kw=kw, loc=loc)

        logger.info("LinkedIn fresh live job fetch complete", total=len(collected_jobs), delhi_ncr_only=delhi_ncr_only)
        return collected_jobs
