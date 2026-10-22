from datetime import datetime, timezone
import re
import structlog
from bson import ObjectId
from app.db.client import get_db
from app.providers.factory import AIProviderFactory
from app.models.settings import UserSettings

from app.sources.company_ats import is_indian_job, standardize_india_location

logger = structlog.get_logger()

MATCH_EXPLANATION_PROMPT = """You are an AI career advisor. Briefly explain (in 2 concise sentences) why the candidate's profile matches this Indian tech job opening:
Candidate Title/Skills: {skills}
Candidate Summary: {summary}
Job Title: {job_title}
Company: {company}
Location: {location}
Required Skills: {job_skills}
Explanation:"""


NON_TECH_KEYWORDS = [
    "sales", "marketing", "account executive", "business development", "bdr", "sdr",
    "recruiter", "talent acquisition", "human resources", "hr manager", "finance",
    "accounting", "legal", "counsel", "banking alliance", "operations associate",
    "operations specialist", "credit risk", "customer success", "content writer",
    "office manager", "procurement", "supply chain", "commercial account"
]

TECH_KEYWORDS = [
    "software", "engineer", "developer", "full stack", "fullstack", "backend",
    "frontend", "architect", "platform", "systems", "devops", "cloud",
    "data engineer", "machine learning", "ml", "ai", "sre", "web developer",
    "programmer", "technical", "security engineer", "qa engineer", "solutions architect"
]

COMMON_TECH_STACK = [
    "python", "golang", "go", "c++", "c#", ".net", "dotnet", "rust", "ruby", "rails",
    "kubernetes", "k8s", "aws", "gcp", "azure", "kafka", "redis", "graphql", "terraform",
    "spark", "hadoop", "snowflake", "salesforce", "scala", "elixir", "swift", "kotlin"
]


class JobMatcherAgent:
    """Computes compatibility score and detailed match breakdown between a user and job (India Tech Jobs)."""

    async def match_user_and_job(
        self,
        user_id: str,
        job_id: str,
        user_settings: UserSettings | None = None,
    ) -> dict | None:
        db = get_db()
        profile = await db.profiles.find_one({"user_id": ObjectId(user_id)})
        job = await db.jobs.find_one({"_id": ObjectId(job_id)})

        if not profile or not job:
            return None

        # STRICT ENFORCEMENT: Only match Indian jobs
        company = job.get("company", "")
        location = job.get("location", "")
        desc_raw = job.get("description", "")
        if not is_indian_job(company, location, desc_raw[:400]):
            return None

        # 1. Collect all candidate skills with display capitalization
        raw_skills = profile.get("skills", {})
        user_skills_list: list[str] = []
        if isinstance(raw_skills, dict):
            for val in raw_skills.values():
                if isinstance(val, list):
                    user_skills_list.extend(val)
                elif isinstance(val, str):
                    user_skills_list.extend(re.split(r"[,;]\s*", val))
        elif isinstance(raw_skills, list):
            for s in raw_skills:
                if isinstance(s, str):
                    user_skills_list.append(s)

        user_skills_clean = [s.strip() for s in user_skills_list if s.strip()]
        user_skills_lower = set(s.lower() for s in user_skills_clean)

        # 2. Clean HTML from job text
        desc_clean = re.sub(r"<[^>]+>", " ", desc_raw)
        title_raw = job.get("title", "")
        job_full_text = f"{title_raw} {desc_clean}".lower()
        title_lower = title_raw.lower()

        # 3. Determine Role Domain (Tech vs Non-Tech)
        is_non_tech = any(kw in title_lower for kw in NON_TECH_KEYWORDS) and not any(
            tk in title_lower for tk in ["software", "developer", "engineer", "architect", "tech"]
        )
        is_tech = any(tk in title_lower for tk in TECH_KEYWORDS)

        # 4. Extract Matching Skills from Title + Description + required_skills
        matching_skills = []
        for s in user_skills_clean:
            s_low = s.lower()
            pattern = r"\b" + re.escape(s_low) + r"\b"
            if re.search(pattern, job_full_text) or s_low in [rs.lower() for rs in job.get("required_skills", [])]:
                if s not in matching_skills:
                    matching_skills.append(s)

        # Extract Missing Skills mentioned in job that user doesn't have
        missing_skills = []
        for rs in job.get("required_skills", []):
            if rs.lower() not in user_skills_lower and rs not in missing_skills:
                missing_skills.append(rs)

        for ts in COMMON_TECH_STACK:
            pattern = r"\b" + re.escape(ts) + r"\b"
            if re.search(pattern, job_full_text) and ts not in user_skills_lower:
                title_case = "AWS" if ts == "aws" else ("GCP" if ts == "gcp" else ts.title())
                if title_case not in missing_skills:
                    missing_skills.append(title_case)

        # 5. Compute Realistic Breakdown Score
        if is_non_tech:
            title_score = 5
            skills_score = max(5, min(15, len(matching_skills) * 3))
            location_score = 10
            total_score = min(35, skills_score + title_score + location_score)
            default_reason = f"Non-technical role ({title_raw}) does not align with your Software Engineering profile."
        elif is_tech:
            if any(pref in title_lower for pref in ["full stack", "fullstack", "backend", "software engineer", "frontend"]):
                title_score = 30
            elif any(pref in title_lower for pref in ["architect", "lead", "staff", "principal"]):
                title_score = 26
            else:
                title_score = 22

            if matching_skills:
                skills_score = min(48, 18 + (len(matching_skills) * 6))
            else:
                skills_score = 20

            prefs = profile.get("job_preferences") or profile.get("jobPreferences") or {}
            rem_pref = prefs.get("remote_preference") or prefs.get("remotePreference") or "any"
            location_score = 18 if (job.get("is_remote") or rem_pref in ["remote", "any", "open"]) else 14
            total_score = min(98, max(45, skills_score + title_score + location_score))
            matched_str = ", ".join(matching_skills[:3]) if matching_skills else "software engineering fundamentals"
            default_reason = f"Strong alignment with your profile. Matched core capabilities: {matched_str}."
        else:
            title_score = 15
            skills_score = min(35, 12 + (len(matching_skills) * 5))
            location_score = 12
            total_score = min(70, max(25, skills_score + title_score + location_score))
            default_reason = f"Moderate match for {title_raw}. Some relevant skills overlap with your technical background."

        # 6. AI Match Reasoning
        reasoning = default_reason
        if user_settings:
            try:
                # For high-throughput scoring speed with Ollama, prefer fast 3B model
                scoring_settings = user_settings
                if user_settings.ai_provider == "ollama" and "14b" in (user_settings.ai_model or ""):
                    scoring_settings = user_settings.model_copy(update={"ai_model": "llama3.2:latest"})

                provider = AIProviderFactory.resolve(scoring_settings)
                prompt = MATCH_EXPLANATION_PROMPT.format(
                    skills=", ".join(user_skills_clean[:10]),
                    summary=profile.get("summary", ""),
                    job_title=job.get("title"),
                    company=job.get("company"),
                    location=location or "Bengaluru, India",
                    job_skills=", ".join(matching_skills[:5] or missing_skills[:5] or ["Engineering"]),
                )
                resp = await provider.complete([{"role": "user", "content": prompt}], temperature=0.3)
                if resp.strip():
                    reasoning = resp.strip()
            except Exception as e:
                logger.warning("AI match reasoning failed, using default", error=str(e))

        now = datetime.now(timezone.utc)
        match_doc = {
            "user_id": ObjectId(user_id),
            "job_id": ObjectId(job_id),
            "compatibility_score": total_score,
            "matching_skills": matching_skills,
            "missing_skills": missing_skills[:8],
            "experience_match": f"{len(profile.get('experience', []))} previous roles on profile",
            "score_breakdown": {
                "skills_score": skills_score,
                "location_score": location_score,
                "preference_score": title_score,
            },
            "match_reasoning": reasoning,
            "matched_at": now,
        }

        await db.job_matches.update_one(
            {"user_id": ObjectId(user_id), "job_id": ObjectId(job_id)},
            {"$set": match_doc},
            upsert=True,
        )

        logger.info("Job matched for user", user_id=user_id, job_id=job_id, score=total_score)
        return match_doc
