import asyncio
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import email.utils
import httpx
import html2text
import structlog
from app.sources.base import BaseJobSource, RawJobData
from app.sources.company_ats import standardize_india_location

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


class IndeedJobSource(BaseJobSource):
    source_type: str = "indeed"

    async def fetch_jobs(self, config: dict | None = None) -> list[RawJobData]:
        """Fetch live tech jobs from Indeed India public RSS feeds, targeting Delhi NCR tech hubs."""
        config = config or {}
        roles = config.get("keywords") or [
            "Software Engineer",
            "Backend Developer",
            "Full Stack Developer",
            "Frontend Engineer",
            "DevOps Engineer",
            "Python Developer",
        ]
        if isinstance(roles, str):
            roles = [roles]

        delhi_ncr_only = config.get("delhi_ncr_only", True)
        if delhi_ncr_only:
            locations = ["Delhi NCR", "Gurugram, Haryana", "Noida, Uttar Pradesh"]
        else:
            loc_cfg = config.get("location", "Delhi NCR")
            locations = [loc_cfg] if isinstance(loc_cfg, str) else loc_cfg

        max_jobs = int(config.get("limit", 25))
        max_age_days = int(config.get("max_age_days", 14))
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=max_age_days)

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        collected_jobs: list[RawJobData] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, headers=headers) as client:
            for loc in locations:
                if len(collected_jobs) >= max_jobs:
                    break
                for role in roles:
                    if len(collected_jobs) >= max_jobs:
                        break
                    try:
                        q_role = urllib.parse.quote_plus(role)
                        q_loc = urllib.parse.quote_plus(loc)
                        rss_url = f"https://in.indeed.com/rss?q={q_role}&l={q_loc}&sort=date"

                        res = await client.get(rss_url)
                        if res.status_code != 200:
                            logger.warning("Indeed RSS request non-200", status=res.status_code, role=role, loc=loc)
                            continue

                        # Parse RSS XML
                        root = ET.fromstring(res.text)
                        channel = root.find("channel")
                        if channel is None:
                            continue

                        for item in channel.findall("item"):
                            if len(collected_jobs) >= max_jobs:
                                break

                            title_el = item.find("title")
                            link_el = item.find("link")
                            desc_el = item.find("description")
                            source_el = item.find("source")
                            guid_el = item.find("guid")
                            pubdate_el = item.find("pubDate")

                            # Parse posting date
                            posted_at = None
                            posted_raw = None
                            if pubdate_el is not None and pubdate_el.text:
                                posted_raw = pubdate_el.text.strip()
                                try:
                                    posted_at = email.utils.parsedate_to_datetime(posted_raw)
                                    if posted_at.tzinfo is None:
                                        posted_at = posted_at.replace(tzinfo=timezone.utc)
                                    if posted_at < cutoff_date:
                                        continue
                                except Exception:
                                    pass

                            title = title_el.text.strip() if title_el is not None and title_el.text else "Software Engineer"
                            link = link_el.text.strip() if link_el is not None and link_el.text else ""
                            company = source_el.text.strip() if source_el is not None and source_el.text else "Technology Employer"
                            desc_raw = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
                            guid = guid_el.text.strip() if guid_el is not None and guid_el.text else link

                            # Extract unique job key (jk) from URL or guid
                            jk_match = re.search(r"[?&]jk=([a-zA-Z0-9]+)", link) or re.search(r"([a-f0-9]{16})", guid)
                            job_id = jk_match.group(1) if jk_match else str(hash(link))[-12:]
                            ext_id = f"indeed_{job_id}"

                            if ext_id in seen_ids:
                                continue
                            seen_ids.add(ext_id)

                            is_remote = bool("remote" in title.lower() or "remote" in desc_raw.lower() or "work from home" in desc_raw.lower())
                            std_loc = standardize_india_location(company, loc, is_remote)
                            clean_desc = _html2text.handle(desc_raw).strip()

                            if len(clean_desc) < 60:
                                clean_desc = (
                                    f"### {title}\n\n"
                                    f"**Company**: {company}\n"
                                    f"**Location**: {std_loc}\n"
                                    f"**Work Model**: {'Remote' if is_remote else 'Hybrid / On-site'}\n\n"
                                    f"#### Job Overview\n"
                                    f"{company} is hiring for a **{title}** in {std_loc}. "
                                    f"Posting is actively indexed on Indeed with ID `{job_id}`.\n\n"
                                    f"#### Application\n"
                                    f"Apply directly through Indeed at the job link."
                                )

                            skills = extract_skills_from_text(f"{title} {clean_desc}")

                            collected_jobs.append(
                                RawJobData(
                                    title=title,
                                    company=company,
                                    location=std_loc,
                                    is_remote=is_remote,
                                    source_url=link,
                                    application_url=link,
                                    description=clean_desc[:5000],
                                    external_id=ext_id,
                                    posted_at_raw=posted_raw,
                                    posted_at=posted_at or datetime.now(timezone.utc),
                                    required_skills=skills,
                                    source="indeed",
                                )
                            )

                        await asyncio.sleep(0.5)

                    except Exception as e:
                        logger.warning("Indeed RSS parse iteration failed", error=str(e), role=role, loc=loc)

        logger.info("Indeed job fetch completed", total=len(collected_jobs), delhi_ncr_only=delhi_ncr_only)
        return collected_jobs

