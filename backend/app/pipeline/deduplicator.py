import hashlib
import re
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
    from app.sources.company_ats import is_delhi_ncr_job
except ImportError:
    DELHI_NCR_REGEX = re.compile(r"\b(delhi|new delhi|gurgaon|gurugram|noida|greater noida|faridabad|ghaziabad|manesar|cyber city|cybercity|sohna|okhla|aerocity)\b", re.IGNORECASE)
    def is_delhi_ncr_job(location: str, text_snippet: str = "") -> bool:
        return bool(DELHI_NCR_REGEX.search(location.lower()) or (text_snippet and DELHI_NCR_REGEX.search(text_snippet.lower()[:300])))

COMPANY_SUFFIX_REGEX = re.compile(
    r"\b(pvt\.?|ltd\.?|private|limited|technologies|technology|tech|solutions|services|systems|inc\.?|corp\.?|llc|india)\b",
    re.IGNORECASE,
)

TITLE_NOISE_REGEX = re.compile(
    r"\b(m/f/d|m/f/x|f/m|urgent hiring|immediate joiner|hiring|immediate start|apply now|urgent opening)\b",
    re.IGNORECASE,
)


def normalize_company_name(company: str) -> str:
    """Normalize company name by stripping legal suffixes and punctuation for clean matching."""
    comp = company.strip().lower()
    comp = COMPANY_SUFFIX_REGEX.sub("", comp)
    comp = re.sub(r"[^a-z0-9]", "", comp)
    return comp or company.strip().lower()


def normalize_job_title(title: str) -> str:
    """Normalize title by removing noise words and standardizing separators and seniority."""
    t = title.strip().lower()
    t = TITLE_NOISE_REGEX.sub("", t)
    # Replace brackets, punctuation, and separators with a single space so "(Backend)" and "- Backend" match
    t = re.sub(r"[\(\)\[\]/\\_\-,:]", " ", t)
    # Standardize common acronyms & seniority
    t = re.sub(r"\bsde\s*1\b", "sde 1", t)
    t = re.sub(r"\bsde\s*2\b", "sde 2", t)
    t = re.sub(r"\bsde\s*3\b", "sde 3", t)
    t = re.sub(r"\bsr\.?\s*", "senior ", t)
    t = re.sub(r"\bjr\.?\s*", "junior ", t)
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t or title.strip().lower()


def get_location_cluster(location: str) -> str:
    """Group localities into regional clusters to prevent duplicate postings across close hubs."""
    if is_delhi_ncr_job(location):
        return "delhi_ncr"
    loc = location.lower().strip()
    if "bengaluru" in loc or "bangalore" in loc:
        return "bengaluru"
    if "hyderabad" in loc:
        return "hyderabad"
    if "pune" in loc:
        return "pune"
    if "mumbai" in loc:
        return "mumbai"
    return re.sub(r"[^a-z0-9]", "", loc)


class JobDeduplicator:
    """Generates source-agnostic canonical identity hashes to eliminate cross-source duplicates."""

    @staticmethod
    def compute_canonical_hash(title: str, company: str, location: str) -> str:
        norm_comp = normalize_company_name(company)
        norm_title = normalize_job_title(title)
        loc_cluster = get_location_cluster(location)
        raw_key = f"{norm_comp}|{norm_title}|{loc_cluster}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_raw_hash(job: RawJobData) -> str:
        return JobDeduplicator.compute_canonical_hash(job.title, job.company, job.location)
