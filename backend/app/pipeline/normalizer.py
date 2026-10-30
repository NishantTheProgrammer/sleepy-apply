import re
from typing import Any
try:
    import structlog
    logger = structlog.get_logger()
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

try:
    from app.sources.base import RawJobData
except ImportError:
    RawJobData = None

try:
    from app.sources.company_ats import standardize_india_location, is_delhi_ncr_job
except ImportError:
    def standardize_india_location(company: str, loc_name: str, is_remote: bool) -> str:
        return loc_name
    def is_delhi_ncr_job(location: str, text: str = "") -> bool:
        return True

TECH_SKILLS_CANONICAL = {
    "python": "Python",
    "fastapi": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    "react": "React",
    "reactjs": "React",
    "nextjs": "Next.js",
    "next.js": "Next.js",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "java": "Java",
    "springboot": "Spring Boot",
    "spring boot": "Spring Boot",
    "golang": "Go",
    "go": "Go",
    "rust": "Rust",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "docker": "Docker",
    "aws": "AWS",
    "gcp": "GCP",
    "azure": "Azure",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "mysql": "MySQL",
    "mongodb": "MongoDB",
    "redis": "Redis",
    "kafka": "Kafka",
    "graphql": "GraphQL",
    "rest apis": "REST APIs",
    "rest api": "REST APIs",
    "microservices": "Microservices",
    "c++": "C++",
    "c#": "C#",
    ".net": ".NET",
    "dotnet": ".NET",
    "git": "Git",
    "ci/cd": "CI/CD",
}


class DelhiNCRJobNormalizer:
    """Specialized normalizer for Delhi NCR Tech positions."""

    @classmethod
    def classify_delhi_ncr_hub(cls, location: str, text: str = "") -> str:
        """Classify sub-locality into primary Delhi NCR Tech Hub."""
        combined = f"{location} {text}".lower()
        if any(h in combined for h in ["gurgaon", "gurugram", "cyber city", "dlf", "sohna", "manesar", "golf course", "udyog vihar"]):
            return "Gurugram"
        if any(h in combined for h in ["noida", "greater noida", "sector 62", "sector 125", "sector 135", "expressway"]):
            return "Noida"
        if any(h in combined for h in ["delhi", "new delhi", "okhla", "aerocity", "connaught place", "nehru place", "saket"]):
            return "Delhi NCR"
        if "faridabad" in combined:
            return "Faridabad"
        if "ghaziabad" in combined:
            return "Ghaziabad"
        if "remote" in combined:
            return "Remote"
        return "India"

    @classmethod
    def normalize_work_model(cls, is_remote: bool, title: str, description: str) -> str:
        text = f"{title} {description[:400]}".lower()
        if "hybrid" in text:
            return "Hybrid"
        if is_remote or "remote" in text or "work from home" in text:
            return "Remote"
        return "On-site"

    @classmethod
    def normalize_seniority(cls, title: str) -> str:
        t = title.lower()
        if any(w in t for w in ["intern", "trainee", "fellow"]):
            return "Intern"
        if any(w in t for w in ["principal", "staff", "architect", "distinguished"]):
            return "Staff / Principal"
        if any(w in t for w in ["director", "head of", "engineering manager", "em", "vp"]):
            return "Management"
        if any(w in t for w in ["lead", "tech lead", "team lead", "manager"]):
            return "Lead"
        if any(w in t for w in ["senior", "sr.", "sr ", "sde 3", "sde-3", "sde iii", "lead"]):
            return "Senior"
        if any(w in t for w in ["sde 2", "sde-2", "sde ii", "intermediate", "mid"]):
            return "Mid-Level"
        if any(w in t for w in ["junior", "jr.", "jr ", "sde 1", "sde-1", "sde i", "associate", "entry"]):
            return "Junior"
        return "Mid-Level"

    @classmethod
    def extract_salary_inr(cls, text: str) -> dict[str, Any]:
        """Extract compensation in INR Lakhs / LPA if specified in text."""
        lpa_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(?:lpa|lacs|lakhs|lac)", text, re.IGNORECASE)
        if lpa_match:
            try:
                min_lakh = float(lpa_match.group(1))
                max_lakh = float(lpa_match.group(2))
                return {
                    "min": min_lakh * 100_000,
                    "max": max_lakh * 100_000,
                    "currency": "INR",
                }
            except Exception:
                pass
        return {"min": None, "max": None, "currency": "INR"}

    @classmethod
    def normalize_skills(cls, raw_skills: list[str], text: str = "") -> list[str]:
        """Deduplicate and map skills to canonical labels."""
        normalized: set[str] = set()
        for s in raw_skills:
            clean = s.strip().lower()
            if clean in TECH_SKILLS_CANONICAL:
                normalized.add(TECH_SKILLS_CANONICAL[clean])
            elif len(clean) > 1:
                normalized.add(s.strip().title())

        # Also check text against canonical dictionary
        text_lower = text.lower()
        for k, v in TECH_SKILLS_CANONICAL.items():
            pattern = rf"\b{re.escape(k)}\b"
            if re.search(pattern, text_lower):
                normalized.add(v)

        return sorted(list(normalized))[:12]

    @classmethod
    def normalize(cls, raw: RawJobData) -> dict[str, Any]:
        """Process and normalize raw job data into clean database document format."""
        is_ncr = is_delhi_ncr_job(raw.location, raw.description[:300])
        hub = cls.classify_delhi_ncr_hub(raw.location, raw.description[:200])
        std_loc = standardize_india_location(raw.company, raw.location, raw.is_remote)
        work_model = cls.normalize_work_model(raw.is_remote, raw.title, raw.description)
        seniority = cls.normalize_seniority(raw.title)
        salary = cls.extract_salary_inr(raw.description)
        skills = cls.normalize_skills(raw.required_skills, f"{raw.title} {raw.description}")

        return {
            "title": raw.title.strip(),
            "company": raw.company.strip(),
            "location": std_loc,
            "delhi_ncr_hub": hub,
            "is_delhi_ncr": is_ncr,
            "is_remote": raw.is_remote or work_model == "Remote",
            "work_model": work_model,
            "seniority": seniority,
            "employment_type": raw.employment_type if raw.employment_type in ["full-time", "part-time", "contract", "internship"] else "full-time",
            "salary_range": salary,
            "required_skills": skills,
            "description": raw.description,
            "source": raw.source,
            "source_url": raw.source_url,
            "application_url": raw.application_url or raw.source_url,
            "external_id": raw.external_id,
        }
