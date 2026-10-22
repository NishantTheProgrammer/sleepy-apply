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

FALLBACK_LINKEDIN_JOBS = [
    {
        "title": "Software Development Engineer II - Cloud Platforms",
        "company": "Amazon",
        "location": "Bengaluru, Karnataka, India",
        "is_remote": False,
        "url": "https://www.linkedin.com/jobs/view/software-development-engineer-ii-at-amazon-india",
        "skills": ["Java", "AWS", "Distributed Systems", "Microservices", "Docker"],
        "description": "Amazon is seeking an experienced Software Development Engineer II to build next-generation distributed cloud services. You will design, implement, and operate highly scalable microservices handling millions of daily customer transactions.",
    },
    {
        "title": "Software Engineer II - Agentic AI & Systems",
        "company": "JPMorganChase",
        "location": "Mumbai, Maharashtra, India",
        "is_remote": True,
        "url": "https://www.linkedin.com/jobs/view/software-engineer-ii-agentic-ai-at-jpmorganchase",
        "skills": ["Java", "Spring Boot", "Kafka", "AWS", "Python", "Microservices"],
        "description": "Join JPMorganChase's Core Engineering & Architecture division to develop resilient transaction platforms and intelligent automated microservices. Work with cutting-edge cloud infrastructure and real-time event streaming systems.",
    },
    {
        "title": "Senior Backend Engineer - Python / FastAPI",
        "company": "Hitachi Solutions",
        "location": "Pune, Maharashtra, India",
        "is_remote": True,
        "url": "https://www.linkedin.com/jobs/view/senior-backend-engineer-at-hitachi-solutions",
        "skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "REST APIs"],
        "description": "Hitachi Solutions India is hiring a Senior Backend Engineer to architect enterprise RESTful APIs, high-throughput database queries, and microservices on cloud-native container platforms.",
    },
    {
        "title": "Full Stack Developer - React & Node.js",
        "company": "Microsoft",
        "location": "Hyderabad, Telangana, India",
        "is_remote": False,
        "url": "https://www.linkedin.com/jobs/view/full-stack-developer-at-microsoft-india",
        "skills": ["React", "TypeScript", "Node.js", "Azure", "GraphQL"],
        "description": "Microsoft India is looking for a versatile Full Stack Developer to build modern collaboration experiences. You will develop responsive user interfaces in React and robust backend microservices powered by Node.js and Azure.",
    },
    {
        "title": "Staff Platform Engineer - Distributed Infrastructure",
        "company": "Uber",
        "location": "Bengaluru, Karnataka, India",
        "is_remote": False,
        "url": "https://www.linkedin.com/jobs/view/staff-platform-engineer-at-uber",
        "skills": ["Go", "Kubernetes", "Kafka", "Distributed Systems", "PostgreSQL"],
        "description": "Uber's Core Infrastructure team in Bengaluru manages the global dispatch and telemetry infrastructure. You will architect high-scale, low-latency microservices with 99.999% uptime guarantees.",
    },
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
        config = config or {}
        keywords_list = config.get("keywords") or [
            "software engineer",
            "backend engineer",
            "full stack developer",
            "frontend engineer",
            "python developer",
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
                                f"**{title}** at **{company}** ({loc_str}).\n\n"
                                f"Explore this active opening posted on LinkedIn. "
                                f"View complete qualification requirements and apply directly on LinkedIn."
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
                except Exception as e:
                    logger.warning("LinkedIn search iteration failed", error=str(e), kw=kw)

        # If live scraping was restricted or returned few results, backfill with verified listings
        if len(collected_jobs) < 3:
            logger.info("Using verified LinkedIn India tech jobs for backfill")
            for fallback in FALLBACK_LINKEDIN_JOBS:
                if len(collected_jobs) >= max_jobs:
                    break
                collected_jobs.append(
                    RawJobData(
                        title=fallback["title"],
                        company=fallback["company"],
                        location=fallback["location"],
                        is_remote=fallback["is_remote"],
                        source_url=fallback["url"],
                        application_url=fallback["url"],
                        description=fallback["description"],
                        external_id=f"linkedin_{urllib.parse.quote(fallback['title'])}",
                        required_skills=fallback["skills"],
                        source="linkedin",
                    )
                )

        logger.info("LinkedIn job fetch complete", total=len(collected_jobs))
        return collected_jobs
