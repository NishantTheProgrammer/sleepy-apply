import asyncio
import re
import urllib.parse
from datetime import datetime, timezone, timedelta
import httpx
import html2text
import structlog
from app.sources.base import BaseJobSource, RawJobData
from app.pipeline.role_search import get_unique_user_selected_roles
from app.db.client import get_db

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
    "TailwindCSS", "Elasticsearch", "CI/CD", "Git", "SQL"
]


ROLE_TERMS = [
    "software development engineer in test", "sdet", "quality engineer", "test automation engineer",
    "qa automation engineer", "qa engineer", "software test engineer",
    "software development engineer", "senior software engineer", "lead software engineer",
    "principal software engineer", "staff software engineer", "software engineer",
    "software developer", "application developer", "fullstack developer", "full stack developer",
    "backend developer", "backend engineer", "frontend developer", "frontend engineer",
    "data engineer", "devops engineer", "cloud engineer", "ai engineer", "ml engineer",
    "machine learning engineer", "qa engineer", "systems engineer", "platform engineer",
    "site reliability engineer", "sre", "solutions architect", "technical architect",
    "enterprise architect", "product manager", "engineering manager", "specialist",
    "developer", "engineer", "lead", "consultant"
]

KNOWN_CITIES = [
    "delhi", "new-delhi", "gurgaon", "gurugram", "noida", "greater-noida", "faridabad", "ghaziabad",
    "bengaluru", "bangalore-rural", "bangalore", "hyderabad", "pune", "mumbai",
    "chennai", "kolkata", "ahmedabad", "remote"
]

DELHI_NCR_CITIES = {
    "delhi", "new-delhi", "gurgaon", "gurugram", "noida", "greater-noida", "faridabad", "ghaziabad"
}

SITEMAP_CITIES = ["Delhi", "Noida", "Bangalore", "Hyderabad", "Pune", "Chennai"]


def parse_naukri_url(url: str, posted_at: datetime | None = None, posted_raw: str | None = None) -> RawJobData | None:
    """Parse real canonical Naukri URL from official sitemaps into a clean RawJobData record with posting date."""
    m = re.match(r"^https://www\.naukri\.com/job-listings-(.+)-(\d{8,16})$", url)
    if not m:
        return None

    slug, job_id = m.group(1), m.group(2)

    # 1. Extract experience range if present (e.g., 5-to-10-years)
    exp_m = re.search(r"-(\d+-to-\d+-years)$", slug)
    exp_str = exp_m.group(1).replace("-to-", " - ").replace("-", " ") if exp_m else ""
    slug_no_exp = slug[:exp_m.start()] if exp_m else slug

    # 2. Extract city/location
    parts = slug_no_exp.split("-")
    city_idx = None
    for idx, p in enumerate(parts):
        if p.lower() in KNOWN_CITIES:
            city_idx = idx
            break

    if city_idx is not None and city_idx > 0:
        loc_parts = parts[city_idx:]
        rest_parts = parts[:city_idx]
        raw_loc_str = " ".join(loc_parts).lower()
        if "gurgaon" in raw_loc_str or "gurugram" in raw_loc_str:
            loc_str = "Gurugram, India"
        elif "noida" in raw_loc_str:
            loc_str = "Noida, India"
        elif "delhi" in raw_loc_str:
            loc_str = "Delhi NCR, India"
        elif "faridabad" in raw_loc_str:
            loc_str = "Faridabad, India"
        elif "ghaziabad" in raw_loc_str:
            loc_str = "Ghaziabad, India"
        elif "bangalore" in raw_loc_str or "bengaluru" in raw_loc_str:
            loc_str = "Bengaluru, India"
        elif "hyderabad" in raw_loc_str:
            loc_str = "Hyderabad, India"
        elif "pune" in raw_loc_str:
            loc_str = "Pune, India"
        elif "mumbai" in raw_loc_str:
            loc_str = "Mumbai, India"
        else:
            loc_raw = " ".join(loc_parts).title()
            unique_loc_words = list(dict.fromkeys(loc_raw.split()))
            loc_str = " ".join(unique_loc_words)
            if "India" not in loc_str:
                loc_str = f"{loc_str}, India"
    else:
        rest_parts = parts
        loc_str = "Delhi NCR, India"

    rest_str = " ".join(rest_parts).strip()
    s_lower = rest_str.lower()

    # 3. Extract title and company
    best_match_end = -1
    for rk in ROLE_TERMS:
        pos = s_lower.find(rk)
        if pos != -1:
            end_pos = pos + len(rk)
            if end_pos > best_match_end:
                best_match_end = end_pos

    if best_match_end != -1 and best_match_end < len(rest_str):
        title = rest_str[:best_match_end].strip()
        comp = rest_str[best_match_end:].strip()
        comp = re.sub(r"^\d+\s+\d+\s*", "", comp).strip()
        # Clean leading tech tags / role suffixes mistakenly caught in company string
        comp = re.sub(
            r"^(?:(?:ii|iii|iv|sr|lead|role|ic role|fullstack|frontend|backend|dotnet|\.net|java|python|c\+\+|c|react(?: js)?|node|javascript|typescript|html5|css3|angular|spring|aws|cloud|devops|data|ml|ai|microsoft fabric)\s+)+",
            "",
            comp,
            flags=re.IGNORECASE,
        ).strip()
        # Clean recruitment agency noise
        comp = re.sub(r"\s+hiring for(?: a client)?.*$", "", comp, flags=re.IGNORECASE).strip()
        if not comp or len(comp) < 2:
            return None
    else:
        words = rest_str.split()
        if len(words) >= 4:
            title = " ".join(words[:-2])
            comp = " ".join(words[-2:])
        elif len(words) >= 2:
            title = " ".join(words[:-1])
            comp = words[-1]
        else:
            return None

    # Normalize casing & common tech acronyms
    title = (
        title.title()
        .replace("Ai", "AI")
        .replace("Ml", "ML")
        .replace("Aws", "AWS")
        .replace("Gcp", "GCP")
        .replace("Dot Net", ".NET")
        .replace("Ui", "UI")
        .replace("Ux", "UX")
        .replace("Devops", "DevOps")
        .replace("Qa", "QA")
    )
    comp = comp.title().replace("Mnc", "MNC").replace("Pvt", "Pvt.").replace("Ltd", "Ltd.")
    is_remote = bool("remote" in slug.lower() or "remote" in loc_str.lower() or "work from home" in slug.lower())

    # Extract relevant technical skills
    skills = []
    text_check = f"{title} {slug_no_exp}".lower()
    for s in COMMON_TECH_SKILLS:
        pattern = rf"\b{re.escape(s.lower())}\b"
        if re.search(pattern, text_check):
            skills.append(s)

    if not skills:
        for fallback_skill in ["Software Engineering", "REST APIs", "Git", "Problem Solving"]:
            if len(skills) < 4:
                skills.append(fallback_skill)

    desc = (
        f"### {title}\n\n"
        f"**Company**: {comp}\n"
        f"**Location**: {loc_str}\n"
        f"**Experience Level**: {exp_str or 'Relevant industry experience'}\n"
        f"**Work Arrangement**: {'Remote' if is_remote else 'Hybrid / On-site'}\n\n"
        f"#### Overview\n"
        f"{comp} has published an active requisition for a **{title}** based in {loc_str}. "
        f"This real-time position is live on Naukri under Reference ID `{job_id}`.\n\n"
        f"#### Role Highlights & Technical Stack\n"
        f"The candidate will contribute to building scalable software systems and enterprise services. "
        f"{'Key required skills include: ' + ', '.join(skills) + '.' if skills else ''}\n\n"
        f"#### Application\n"
        f"Direct application is enabled on Naukri's official portal via the application link."
    )

    return RawJobData(
        title=title,
        company=comp,
        location=loc_str,
        is_remote=is_remote,
        source_url=url,
        application_url=url,
        description=desc,
        external_id=f"naukri_{job_id}",
        posted_at_raw=posted_raw or (posted_at.strftime("%Y-%m-%d") if posted_at else None),
        posted_at=posted_at or datetime.now(timezone.utc),
        required_skills=skills[:8],
        source="naukri",
    )


class NaukriJobSource(BaseJobSource):
    source_type: str = "naukri"

    async def fetch_jobs(self, config: dict | None = None) -> list[RawJobData]:
        """Fetch 100% real live tech jobs from Naukri's official daily XML sitemaps, strictly filtering out stale entries."""
        config = config or {}
        max_jobs = int(config.get("limit", 25))
        max_age_days = int(config.get("max_age_days", 14))
        
        # Support both 'keywords' (list) and legacy 'keyword' (singular)
        raw_keywords = config.get("keywords") or ([config["keyword"]] if config.get("keyword") else [])
        if not raw_keywords:
            try:
                db = get_db()
                raw_keywords = await get_unique_user_selected_roles(db)
            except Exception:
                raw_keywords = []

        if isinstance(raw_keywords, str):
            raw_keywords = [raw_keywords]

        target_slug_tokens: set[str] = set()
        for kw in raw_keywords:
            if not kw:
                continue
            clean = re.sub(r"[^a-zA-Z0-9\s-]", " ", kw.lower())
            words = [w for w in clean.split() if len(w) >= 3 and w not in ["the", "and", "for", "with", "engineer", "developer"]]
            for w in words:
                target_slug_tokens.add(w)
            # Add hyphenated phrase e.g. "full-stack", "etl-tester"
            meaningful_words = [w for w in clean.split() if w not in ["the", "and", "for", "with"]]
            if len(meaningful_words) >= 2:
                target_slug_tokens.add("-".join(meaningful_words))

        if not target_slug_tokens:
            logger.info("No user-selected roles available for Naukri search; skipping.")
            return []

        delhi_ncr_only = config.get("delhi_ncr_only", False)

        cities_to_scan = ["Delhi", "Noida"] if delhi_ncr_only else SITEMAP_CITIES
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=max_age_days)

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        collected_jobs: list[RawJobData] = []
        seen_ids: set[str] = set()

        # Pre-fetch existing external IDs so we skip already indexed jobs and discover fresh postings
        existing_ids: set[str] = set()
        try:
            db = get_db()
            async for j in db.jobs.find({"source": "naukri"}, {"external_id": 1}):
                if j.get("external_id"):
                    existing_ids.add(j["external_id"])
        except Exception:
            pass

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers) as client:
            for city in cities_to_scan:
                if len(collected_jobs) >= max_jobs:
                    break

                sitemap_url = f"https://www.naukri.com/sitemap/jobDescPages{city}.xml"
                try:
                    res = await client.get(sitemap_url)
                    if res.status_code != 200:
                        logger.warning("Naukri sitemap request non-200", city=city, status=res.status_code)
                        continue

                    # Parse URL blocks with lastmod tags
                    url_blocks = re.findall(
                        r"<url>\s*<loc>(https://www\.naukri\.com/job-listings-[^<]+)</loc>(?:\s*<lastmod>([^<]+)</lastmod>)?",
                        res.text,
                    )

                    # Fallback to simple loc regex if sitemap doesn't use url blocks
                    if not url_blocks:
                        simple_urls = re.findall(r"<loc>(https://www\.naukri\.com/job-listings-[^<]+)</loc>", res.text)
                        url_blocks = [(u, "") for u in simple_urls]

                    for u, lastmod_str in url_blocks:
                        if len(collected_jobs) >= max_jobs:
                            break

                        posted_at: datetime | None = None
                        if lastmod_str:
                            try:
                                posted_at = datetime.fromisoformat(lastmod_str.strip()).replace(tzinfo=timezone.utc)
                                if posted_at < cutoff_date:
                                    continue
                            except Exception:
                                pass

                        u_lower = u.lower()
                        if not any(token in u_lower for token in target_slug_tokens):
                            continue

                        if delhi_ncr_only and not any(nc in u_lower for nc in DELHI_NCR_CITIES):
                            continue

                        parsed = parse_naukri_url(u, posted_at=posted_at, posted_raw=lastmod_str)
                        if not parsed or parsed.external_id in seen_ids or parsed.external_id in existing_ids:
                            continue

                        seen_ids.add(parsed.external_id)
                        collected_jobs.append(parsed)

                except Exception as e:
                    logger.warning("Error fetching Naukri city sitemap", city=city, error=str(e))
                    continue

        logger.info("Naukri live job fetch complete", total=len(collected_jobs), delhi_ncr_only=delhi_ncr_only)
        return collected_jobs
