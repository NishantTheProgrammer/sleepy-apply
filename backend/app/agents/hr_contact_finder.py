import re
import urllib.parse
import asyncio
from datetime import datetime, timezone
from typing import Any
import httpx
import structlog
from bson import ObjectId

from app.db.client import get_db
from app.models.settings import UserSettings
from app.providers.factory import AIProviderFactory

logger = structlog.get_logger()

# Common ignore patterns for non-human or noisy email addresses
IGNORED_EMAIL_DOMAINS = {
    "example.com", "sample.com", "domain.com", "test.com", "yourcompany.com",
    "sentry.io", "w3.org", "schema.org", "github.com", "gitlab.com",
    "png", "jpg", "jpeg", "gif", "webp", "svg", "css", "js",
}
IGNORED_EMAIL_PREFIXES = {
    "noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon",
    "postmaster", "root", "support", "billing", "privacy", "security",
    "press", "legal", "abuse", "admin", "sales", "contact-us",
    "accommodation", "accommodations", "applicantaccommodations", "accessibility",
    "disability", "eeo", "equal-opportunity", "compliance", "investor", "media", "pr",
}

HR_KEYWORDS_IN_EMAIL = {
    "hr", "talent", "careers", "career", "recruiting", "recruiter", "jobs", "hiring",
    "people", "staffing", "resumes", "apply", "work", "join",
}

HR_LLM_PROMPT = """You are an expert HR Contact Discovery Agent.
Analyze this job posting description and extract the recruiter / HR contact details in valid JSON format:
{
  "name": "Recruiter full name or null",
  "email": "Recruiter or HR application email address or null",
  "phone": "Direct phone or WhatsApp number (e.g. +91 9876543210) or null",
  "designation": "Recruiter title (e.g. 'Technical Recruiter', 'HR Manager', 'Talent Acquisition') or null",
  "linkedin": "Recruiter LinkedIn profile URL or null",
  "confidence": "high" | "medium" | "inferred"
}

If no human recruiter is mentioned, look for direct talent application emails (e.g. careers@company.com, jobs@company.com, hr@company.com) or WhatsApp contact numbers for applications.
Do not invent fake contact information. If absent, set field to null.

Job Context:
"""


class HRContactFinderAgent:
    """
    Dedicated agent to find and extract HR and recruiter contact information
    (name, email, phone/WhatsApp, LinkedIn profile, designation) for job postings.
    Uses a multi-tier strategy:
    1. Deterministic regex & heuristic NLP extraction from job text & metadata.
    2. Live portal / job page scraping (mailto, tel, whatsapp, json-ld schema).
    3. LLM extraction via AI provider (when configured).
    4. Domain synthesis and LinkedIn Recruiter search resolution fallback.
    """

    def __init__(self):
        self.http_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def clean_phone(self, raw_phone: str) -> str | None:
        """Standardize phone numbers, especially Indian mobile numbers."""
        if not raw_phone:
            return None
        cleaned = re.sub(r"[^\d+]", "", raw_phone.strip())
        # If 10 digits starting with 6, 7, 8, 9 (Indian mobile)
        if re.match(r"^[6-9]\d{9}$", cleaned):
            return f"+91 {cleaned}"
        if cleaned.startswith("+91") and len(cleaned) == 13:
            return f"+91 {cleaned[3:]}"
        if cleaned.startswith("91") and len(cleaned) == 12:
            return f"+91 {cleaned[2:]}"
        if cleaned.startswith("0") and len(cleaned) == 11 and cleaned[1] in "6789":
            return f"+91 {cleaned[1:]}"
        if len(cleaned) >= 10:
            return raw_phone.strip()
        return None

    def clean_email(self, email: str) -> str | None:
        """Validate and clean email address."""
        if not email or "@" not in email:
            return None
        email = email.strip().strip(".,;:()[]{}<>\"'")
        parts = email.split("@")
        if len(parts) != 2:
            return None
        user, domain = parts[0].lower(), parts[1].lower()
        if domain in IGNORED_EMAIL_DOMAINS or any(domain.endswith("." + d) for d in IGNORED_EMAIL_DOMAINS):
            return None
        if user in IGNORED_EMAIL_PREFIXES or any(bad in user for bad in ["accommodation", "accessibility", "disability"]):
            return None
        # Discard obvious code identifiers or file paths
        if any(char in email for char in ["/", "\\", "{", "}", "=", "$", "%", "*"]):
            return None
        return email

    def extract_from_text(self, text: str, company: str = "", title: str = "") -> dict[str, Any]:
        """
        Extract HR / recruiter contact info from raw description text using regex and heuristics.
        Handles direct patterns commonly seen on Naukri, LinkedIn, and career pages.
        """
        result: dict[str, Any] = {
            "name": None,
            "email": None,
            "phone": None,
            "linkedin": None,
            "designation": None,
            "source": None,
            "confidence": None,
        }
        if not text:
            return result

        # 1. Emails
        # Examples: "Email: rakeshm@vorizoit.com", "Send cv to hr@xyz.com", "careers@abc.in"
        email_matches = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
        valid_emails = []
        for e in email_matches:
            cleaned = self.clean_email(e)
            if cleaned and cleaned not in valid_emails:
                valid_emails.append(cleaned)

        if valid_emails:
            # Prefer emails with HR keywords or personal names over generic info@
            scored_emails = []
            for em in valid_emails:
                u, d = em.split("@")
                score = 1
                if any(k in u for k in HR_KEYWORDS_IN_EMAIL):
                    score += 5
                elif "." in u or "_" in u:  # Personal name format like first.last@
                    score += 4
                if company and company.lower().replace(" ", "") in d:
                    score += 3
                scored_emails.append((score, em))
            scored_emails.sort(key=lambda x: x[0], reverse=True)
            result["email"] = scored_emails[0][1]
            result["source"] = "jd_text"
            result["confidence"] = "high"

        # 2. Phone / WhatsApp Numbers
        # Examples: "WhatsApp: 7032046739", "Call: +91 9876543210", "Phone: 011-2345678", "CALL DEEPAK @ 9315218830"
        call_at_match = re.search(
            r"(?:call|contact|reach)\s+([A-Za-z][A-Za-z\s.]{1,25}?)\s*(?:@|at|on|:)\s*(\+?\d[\d\s\-]{8,14}\d)",
            text,
            re.IGNORECASE,
        )
        if call_at_match:
            rec_name = call_at_match.group(1).strip()
            p = self.clean_phone(call_at_match.group(2))
            if p:
                result["phone"] = p
                result["confidence"] = "high"
                result["source"] = result["source"] or "jd_text"
            if rec_name and len(rec_name.split()) <= 3 and not any(w in rec_name.lower() for w in ["us", "now", "today", "here"]):
                result["name"] = rec_name.title()
                result["designation"] = "Hiring Recruiter"
                result["source"] = result["source"] or "jd_text"

        whatsapp_match = re.search(
            r"(?:whatsapp|wa\.me|wa)\s*(?:no\.?|num\.?|number|contact)?\s*[:\-]?\s*(\+?\d[\d\s\-]{8,14}\d)",
            text,
            re.IGNORECASE,
        )
        if whatsapp_match:
            p = self.clean_phone(whatsapp_match.group(1))
            if p:
                result["phone"] = p
                result["confidence"] = "high"
                result["source"] = result["source"] or "jd_text"

        if not result["phone"]:
            phone_match = re.search(
                r"(?:phone|tel|mobile|call|contact\s*no\.?)\s*[:\-]?\s*(\+?\d[\d\s\-]{8,14}\d)",
                text,
                re.IGNORECASE,
            )
            if phone_match:
                p = self.clean_phone(phone_match.group(1))
                if p:
                    result["phone"] = p
                    result["source"] = result["source"] or "jd_text"

        if not result["phone"]:
            general_phone = re.search(
                r"(?i)(?:call|whatsapp|contact|reach|phone|mobile|msg|sms|apply).*?(?:@|at|:|\s)\s*(\+?(?:91)?[\s-]?[6-9]\d{9})\b",
                text,
            )
            if general_phone:
                p = self.clean_phone(general_phone.group(1))
                if p:
                    result["phone"] = p
                    result["confidence"] = "high"
                    result["source"] = result["source"] or "jd_text"

        # 3. Recruiter Name & Designation
        # Examples: "Posted by: Rakesh M", "Recruiter: Priya Sharma", "HR Contact: Ananya"
        name_match = re.search(
            r"(?:posted\s*by|recruiter|hr\s*contact|point\s*of\s*contact|hiring\s*manager|contact\s*person)\s*[:\-]?\s*([A-Za-z][A-Za-z\s.]{2,35}?)(?:\s*(?:\||\(|\n|\r|\.|\,|$))",
            text,
            re.IGNORECASE,
        )
        if name_match:
            name_candidate = name_match.group(1).strip()
            # Verify candidate name isn't just company name or generic word
            if company and name_candidate.lower() in company.lower():
                # It said "Posted by Company Name", skip or treat as organization
                pass
            elif len(name_candidate.split()) <= 4 and not any(w in name_candidate.lower() for w in ["confidential", "anonymous", "apply", "urgent", "jobs", "careers", "recruitment", "hiring", "team", "talent", "portal", "recruiter", "admin"]):
                result["name"] = name_candidate
                result["designation"] = "Recruiter / Talent Partner"
                result["source"] = result["source"] or "jd_text"

        # Heuristic name extraction from email if name is still missing
        if not result["name"] and result["email"]:
            username = result["email"].split("@")[0]
            if not any(k in username for k in HR_KEYWORDS_IN_EMAIL):
                # e.g. "rakeshm" or "rakesh.kumar"
                clean_user = re.sub(r"\d+", "", username)
                parts = re.split(r"[._-]", clean_user)
                if parts and all(len(p) >= 2 for p in parts):
                    candidate_name = " ".join(p.capitalize() for p in parts)
                    result["name"] = candidate_name
                    result["designation"] = "Talent Acquisition"

        # 4. LinkedIn Profile
        linkedin_match = re.search(
            r"https?://(?:www\.)?linkedin\.com/in/([a-zA-Z0-9_\-%]+)",
            text,
            re.IGNORECASE,
        )
        if linkedin_match:
            result["linkedin"] = f"https://www.linkedin.com/in/{linkedin_match.group(1)}"
            result["source"] = result["source"] or "jd_text"

        return result

    async def fetch_and_extract_live_page(self, url: str, company: str = "", timeout: float = 6.0) -> dict[str, Any]:
        """
        Safely fetch live job page HTML (with short timeout) to detect mailto links,
        WhatsApp links, tel links, or recruiter metadata not captured in brief summaries.
        """
        if not url or not url.startswith("http"):
            return {}

        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=False) as client:
                resp = await client.get(url, headers=self.http_headers)
                if resp.status_code != 200:
                    return {}
                html = resp.text
                if not html or len(html) < 200:
                    return {}

                found: dict[str, Any] = {}

                # Look for mailto: links
                mailtos = re.findall(r'href=[\'"]mailto:([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)[\'"]', html, re.IGNORECASE)
                for m in mailtos:
                    cleaned = self.clean_email(m)
                    if cleaned:
                        found["email"] = cleaned
                        found["source"] = "live_page"
                        found["confidence"] = "high"
                        break

                # Look for tel: or whatsapp links
                wa_links = re.findall(r'href=[\'"](?:https?://wa\.me/|https?://api\.whatsapp\.com/send\?phone=)(\+?\d+)[\'"]', html, re.IGNORECASE)
                if wa_links:
                    phone = self.clean_phone(wa_links[0])
                    if phone:
                        found["phone"] = phone
                        found["source"] = "live_page"

                if not found.get("phone"):
                    tel_links = re.findall(r'href=[\'"]tel:([+\d\s-]+)[\'"]', html, re.IGNORECASE)
                    for t in tel_links:
                        phone = self.clean_phone(t)
                        if phone:
                            found["phone"] = phone
                            found["source"] = "live_page"
                            break

                # Parse text of the HTML
                text_extracted = self.extract_from_text(html, company=company)
                for k, v in text_extracted.items():
                    if v and not found.get(k):
                        found[k] = v
                        if not found.get("source"):
                            found["source"] = "live_page"

                return found
        except Exception as e:
            logger.debug("Live job page fetch skipped or blocked", url=url, error=str(e))
            return {}

    def extract_company_domain(self, company: str, website: str = "", source_url: str = "") -> str | None:
        """Extract a clean apex domain from company website, source URL, or company name."""
        candidate_url = website or source_url
        if candidate_url:
            try:
                parsed = urllib.parse.urlparse(candidate_url)
                netloc = parsed.netloc.lower()
                # Remove common prefixes and portals
                netloc = re.sub(r"^(www|careers|jobs|boards|apply)\.", "", netloc)
                if netloc and not any(portal in netloc for portal in ["naukri.com", "linkedin.com", "indeed.com", "greenhouse.io", "lever.co", "ashbyhq.com"]):
                    return netloc
            except Exception:
                pass

        if company:
            clean_name = re.sub(r"[^a-zA-Z0-9]", "", company.lower())
            if clean_name and len(clean_name) > 2:
                return f"{clean_name}.com"
        return None

    async def search_web_for_recruiters(self, company: str, location: str = "") -> list[dict[str, Any]]:
        """
        Automated Web & LinkedIn Search Dorking Agent.
        Finds actual, current recruiters / talent acquisition professionals for the company in that location.
        Returns a list of verified recruiter profiles (name, designation, direct LinkedIn profile URL).
        """
        import html
        clean_co = re.sub(r"^(With\s+[A-Za-z\s]+?\s+Vorizo|Senior\s+.*?Engineer)\s*", "", company, flags=re.IGNORECASE)
        clean_co = re.sub(r"\b(Pvt\.?|Ltd\.?|Private\s+Limited|Inc\.?|LLC|Technologies|Services)\b", "", clean_co, flags=re.IGNORECASE).strip()
        if not clean_co or len(clean_co) < 2:
            clean_co = company

        loc = "India"
        if location:
            for city in ["Noida", "Gurugram", "Gurgaon", "Delhi", "Bengaluru", "Bangalore", "Hyderabad", "Pune", "Mumbai", "Chennai"]:
                if city.lower() in location.lower():
                    loc = city
                    break

        query = f'site:linkedin.com/in "{clean_co}" ("Talent Acquisition" OR "Recruiter") {loc}'
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        try:
            async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=5.0) as client:
                resp = await client.get(f"https://search.yahoo.com/search?p={urllib.parse.quote_plus(query)}")
                if resp.status_code == 200:
                    blocks = resp.text.split("<li")
                    for b in blocks:
                        ru = re.search(r"\/RU=([^/]+)\/", b)
                        if not ru:
                            continue
                        url = urllib.parse.unquote(ru.group(1))
                        if "linkedin.com/in/" not in url or url in seen_urls:
                            continue

                        t_match = re.search(r"<h3[^>]*>(.*?)</h3>", b, re.DOTALL)
                        raw_t = re.sub(r"<[^>]+>", "", t_match.group(1)).strip() if t_match else ""
                        clean_t = html.unescape(raw_t)
                        parts = re.split(r"\s*[-–|—]\s*", clean_t)
                        name = parts[0].strip() if parts else None
                        if not name or len(name.split()) > 4:
                            continue
                        name = re.sub(r"[\(\[\.\,\s]+$", "", name).strip()
                        if any(w in name.lower() for w in ["jobs", "careers", "hiring", "overview", "about", "internship", "developer", "engineer"]):
                            continue
                        if clean_co.lower() in name.lower() or name.lower() in clean_co.lower():
                            continue

                        role = "Talent Acquisition"
                        if len(parts) > 1:
                            raw_role = parts[1].strip()
                            raw_role = re.sub(r"\s*(?:at|@)\s+.*$", "", raw_role, flags=re.IGNORECASE)
                            raw_role = re.sub(r"\s*LinkedIn.*$", "", raw_role, flags=re.IGNORECASE).strip(" .–-|")
                            if len(raw_role) > 2 and not any(w in raw_role.lower() for w in ["linkedin", "india", "profile"]):
                                role = raw_role

                        if clean_co.lower() in role.lower():
                            role = "Talent Acquisition"

                        seen_urls.add(url)
                        results.append({
                            "name": name,
                            "designation": role,
                            "linkedin": url,
                        })
                        if len(results) >= 4:
                            break
        except Exception as e:
            logger.debug("Web recruiter search skipped or timed out", company=company, error=str(e))

        return results

    def synthesize_company_contact(self, company: str, website: str = "", source_url: str = "", location: str = "") -> dict[str, Any]:
        """
        Provides direct 1-click LinkedIn and Google recruiter search links to locate real recruiters at this company.
        Strictly does NOT invent guessed/fake email addresses or placeholder names.
        """
        clean_company = re.sub(r"^(With\s+[A-Za-z\s]+?\s+Vorizo|Senior\s+.*?Engineer)\s*", "", company, flags=re.IGNORECASE).strip()
        if not clean_company:
            clean_company = company

        loc_str = location or "India"
        search_query = urllib.parse.quote_plus(f"{clean_company} Talent Acquisition OR Recruiter {loc_str}")
        linkedin_search = f"https://www.linkedin.com/search/results/people/?keywords={search_query}"
        google_search = f"https://www.google.com/search?q={urllib.parse.quote_plus(f'site:linkedin.com/in \"{clean_company}\" (\"Talent Acquisition\" OR \"Recruiter\") {loc_str}')}"

        return {
            "name": None,
            "email": None,
            "phone": None,
            "linkedin": linkedin_search,
            "google_search_url": google_search,
            "designation": None,
            "source": "linkedin_search",
            "confidence": None,
            "recruiters": [],
        }

    async def extract_with_llm(self, text: str, user_settings: UserSettings | None = None) -> dict[str, Any] | None:
        """Use configured AI provider to extract recruiter details with high accuracy."""
        if not user_settings or not text:
            return None
        try:
            provider = AIProviderFactory.resolve(user_settings)
            prompt = HR_LLM_PROMPT + text[:3500]
            resp = await provider.complete([{"role": "user", "content": prompt}], temperature=0.1)
            import json
            match = re.search(r"\{[\s\S]*\}", resp)
            if match:
                data = json.loads(match.group(0))
                # Validate extracted fields
                cleaned_email = self.clean_email(data.get("email")) if data.get("email") else None
                cleaned_phone = self.clean_phone(data.get("phone")) if data.get("phone") else None
                return {
                    "name": data.get("name"),
                    "email": cleaned_email,
                    "phone": cleaned_phone,
                    "designation": data.get("designation") or "Recruiter",
                    "linkedin": data.get("linkedin"),
                    "source": "ai_llm_extraction",
                    "confidence": data.get("confidence") or "high",
                }
        except Exception as e:
            logger.debug("AI HR contact extraction skipped/fallback", error=str(e))
        return None

    async def find_hr_contact_for_job(
        self,
        job: dict[str, Any],
        user_settings: UserSettings | None = None,
        fetch_live: bool = True,
    ) -> dict[str, Any]:
        """
        Complete end-to-end HR contact discovery pipeline for a single job document.
        """
        title = job.get("title", "")
        company = job.get("company", "")
        description = job.get("description", "")
        location = job.get("location", "")
        source_url = job.get("source_url") or job.get("application_url", "")
        company_website = job.get("company_info", {}).get("website", "") if isinstance(job.get("company_info"), dict) else ""

        # Step 1: Text regex & heuristic analysis from job description & fields
        combined_text = f"{title}\n{company}\n{description}"
        reqs = job.get("requirements", [])
        if isinstance(reqs, list):
            combined_text += "\n" + "\n".join(str(r) for r in reqs)

        contact = self.extract_from_text(combined_text, company=company, title=title)

        # Pre-generate smart search shortcuts (LinkedIn search & Google recruiter dork)
        synth = self.synthesize_company_contact(company, website=company_website, source_url=source_url, location=location)
        contact["google_search_url"] = synth["google_search_url"]
        contact["recruiters"] = []

        # Step 2: If direct contact was not found and live extraction is requested
        if (not contact.get("email") or not contact.get("phone")) and fetch_live:
            # 2a. Fast LLM extraction attempt (capped at 2.5s timeout)
            if user_settings and len(description) > 100:
                try:
                    llm_result = await asyncio.wait_for(
                        self.extract_with_llm(description, user_settings=user_settings),
                        timeout=2.5,
                    )
                    if llm_result:
                        for k in ["name", "email", "phone", "designation", "linkedin"]:
                            if llm_result.get(k) and not contact.get(k):
                                contact[k] = llm_result[k]
                        if llm_result.get("email") or llm_result.get("phone"):
                            contact["source"] = "ai_llm_extraction"
                            contact["confidence"] = llm_result.get("confidence", "high")
                except (asyncio.TimeoutError, Exception) as e:
                    logger.debug("LLM HR extraction skipped due to timeout/error", error=str(e))

            # 2b. Live page fetch (capped at 2.5s timeout)
            if not contact.get("email") and not contact.get("phone") and source_url:
                try:
                    live_result = await asyncio.wait_for(
                        self.fetch_and_extract_live_page(source_url, company=company, timeout=2.0),
                        timeout=2.5,
                    )
                    if live_result:
                        for k in ["name", "email", "phone", "designation", "linkedin"]:
                            if live_result.get(k) and not contact.get(k):
                                contact[k] = live_result[k]
                        if live_result.get("email") or live_result.get("phone"):
                            contact["source"] = live_result.get("source", "live_page")
                            contact["confidence"] = live_result.get("confidence", "high")
                except (asyncio.TimeoutError, Exception) as e:
                    logger.debug("Live HR page fetch skipped due to timeout", error=str(e))

            # 2c. Automated Web & LinkedIn Search Dorking Agent (finds real recruiters on the web)
            if not contact.get("name") or not contact.get("linkedin"):
                try:
                    discovered_recruiters = await asyncio.wait_for(
                        self.search_web_for_recruiters(company, location=location),
                        timeout=5.0,
                    )
                    if discovered_recruiters:
                        contact["recruiters"] = discovered_recruiters
                        if not contact.get("name"):
                            contact["name"] = discovered_recruiters[0]["name"]
                            contact["designation"] = discovered_recruiters[0]["designation"]
                            contact["linkedin"] = discovered_recruiters[0]["linkedin"]
                            if not contact.get("source"):
                                contact["source"] = "web_recruiter_dork"
                                contact["confidence"] = "high"
                except (asyncio.TimeoutError, Exception) as e:
                    logger.debug("Automated web recruiter search timed out or skipped", error=str(e))

        # Step 3: Fallback LinkedIn search URL if no individual profile found
        if not contact.get("linkedin"):
            contact["linkedin"] = synth["linkedin"]
            if not contact.get("source"):
                contact["source"] = synth["source"]

        contact["discovered_at"] = datetime.now(timezone.utc).isoformat()
        return contact

    async def find_and_enrich_job(
        self,
        job_id: str | ObjectId,
        user_settings: UserSettings | None = None,
        fetch_live: bool = True,
    ) -> dict[str, Any]:
        """
        Finds HR contact for a job in MongoDB and updates the document.
        """
        db = get_db()
        obj_id = ObjectId(job_id) if isinstance(job_id, str) else job_id
        job = await db.jobs.find_one({"_id": obj_id})
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        contact = await self.find_hr_contact_for_job(job, user_settings=user_settings, fetch_live=fetch_live)

        await db.jobs.update_one(
            {"_id": obj_id},
            {
                "$set": {
                    "hr_contact": {
                        "name": contact.get("name"),
                        "email": contact.get("email"),
                        "phone": contact.get("phone"),
                        "linkedin": contact.get("linkedin"),
                        "designation": contact.get("designation"),
                        "source": contact.get("source"),
                        "confidence": contact.get("confidence"),
                        "google_search_url": contact.get("google_search_url"),
                        "recruiters": contact.get("recruiters", []),
                        "discovered_at": contact.get("discovered_at"),
                    }
                }
            },
        )

        logger.info(
            "HR contact enriched for job",
            job_id=str(job_id),
            company=job.get("company"),
            email=contact.get("email"),
            phone=contact.get("phone"),
            confidence=contact.get("confidence"),
        )
        return contact

    async def enrich_all_jobs(
        self,
        limit: int = 100,
        force: bool = False,
        user_settings: UserSettings | None = None,
    ) -> dict[str, Any]:
        """
        Batch enrich HR contacts for jobs in MongoDB.
        """
        db = get_db()
        query: dict[str, Any] = {"is_active": True}
        if not force:
            query["$or"] = [
                {"hr_contact": None},
                {"hr_contact": {}},
                {"hr_contact.email": None},
                {"hr_contact.source": "company_domain_synthesis"},
            ]

        cursor = db.jobs.find(query).limit(limit)
        processed = 0
        direct_contacts_found = 0

        async for job in cursor:
            try:
                contact = await self.find_and_enrich_job(job["_id"], user_settings=user_settings, fetch_live=False)
                processed += 1
                if contact.get("confidence") in ["high", "medium"]:
                    direct_contacts_found += 1
            except Exception as e:
                logger.warning("Failed to enrich HR contact for job", job_id=str(job["_id"]), error=str(e))

        logger.info("Batch HR contact enrichment completed", processed=processed, direct_found=direct_contacts_found)
        return {
            "ok": True,
            "processed": processed,
            "direct_contacts_found": direct_contacts_found,
        }


# Singleton instance
hr_contact_finder = HRContactFinderAgent()

