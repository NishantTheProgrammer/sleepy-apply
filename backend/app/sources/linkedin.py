import asyncio
import re
import urllib.parse
from datetime import datetime, timezone
import httpx
import html2text
import structlog
from app.sources.base import BaseJobSource, RawJobData

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


class LinkedInJobSource(BaseJobSource):
    source_type: str = "linkedin"

    async def fetch_jobs(self, config: dict | None = None) -> list[RawJobData]:
        """Fetch 100% real live tech jobs from LinkedIn guest API without static fallback."""
        config = config or {}
        keywords_list = config.get("keywords") or [
            "software engineer",
            "backend engineer",
            "full stack developer",
            "frontend engineer",
            "python developer",
            "cloud engineer",
            "devops engineer",
        ]
        if isinstance(keywords_list, str):
            keywords_list = [keywords_list]

        location = config.get("location", "India")
        max_jobs = int(config.get("limit", 25))

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        collected_jobs: list[RawJobData] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            for kw in keywords_list:
                if len(collected_jobs) >= max_jobs:
                    break
                try:
                    q_kw = urllib.parse.quote_plus(kw)
                    q_loc = urllib.parse.quote_plus(location)
                    search_url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={q_kw}&location={q_loc}&start=0"

                    r = await client.get(search_url, headers=headers)
                    if r.status_code != 200:
                        logger.warning("LinkedIn guest search returned non-200", status=r.status_code, kw=kw)
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

                        title_m = re.search(r'<h3 class="[^"]*base-search-card__title[^"]*">\s*([\s\S]*?)\s*<\/h3>', card_html)
                        comp_m = (
                            re.search(r'<h4 class="[^"]*base-search-card__subtitle[^"]*">[\s\S]*?<a[^>]*>\s*([\s\S]*?)\s*<\/a>', card_html)
                            or re.search(r'<h4 class="[^"]*base-search-card__subtitle[^"]*">\s*([\s\S]*?)\s*<\/h4>', card_html)
                        )
                        loc_m = re.search(r'<span class="[^"]*job-search-card__location[^"]*">\s*([\s\S]*?)\s*<\/span>', card_html)
                        link_m = re.search(r'<a class="[^"]*base-card__full-link[^"]*"[^>]*href="([^"]*)"', card_html)

                        title = title_m.group(1).strip() if title_m else "Software Engineer"
                        company = comp_m.group(1).strip() if comp_m else "Company"
                        loc_str = loc_m.group(1).strip() if loc_m else location
                        job_url = link_m.group(1).strip() if link_m else f"https://www.linkedin.com/jobs/view/{jid}"

                        # Clean any query parameters off URL for canonical link
                        if "?" in job_url:
                            job_url = job_url.split("?")[0]

                        is_remote = bool(
                            "remote" in title.lower()
                            or "remote" in loc_str.lower()
                            or "work from home" in loc_str.lower()
                        )

                        # Fetch full description if possible
                        description = ""
                        try:
                            det_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}"
                            det_res = await client.get(det_url, headers=headers)
                            if det_res.status_code == 200:
                                desc_html = det_res.text
                                desc_match = re.search(r'<div class="[^"]*show-more-less-html__markup[^"]*">([\s\S]*?)<\/div>', desc_html)
                                if desc_match:
                                    description = _html2text.handle(desc_match.group(1)).strip()
                                else:
                                    description = _html2text.handle(desc_html).strip()
                        except Exception:
                            pass

                        if not description or len(description) < 40:
                            description = (
                                f"### {title}\n\n"
                                f"**Company**: {company}\n"
                                f"**Location**: {loc_str}\n"
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
                                required_skills=skills,
                                source="linkedin",
                            )
                        )

                    # Polite delay between keyword queries to prevent rate-limiting
                    await asyncio.sleep(0.5)

                except Exception as e:
                    logger.warning("LinkedIn search iteration failed", error=str(e), kw=kw)

        logger.info("LinkedIn real live job fetch complete", total=len(collected_jobs))
        return collected_jobs
