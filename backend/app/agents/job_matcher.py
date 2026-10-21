from datetime import datetime, timezone
import structlog
from bson import ObjectId
from app.db.client import get_db
from app.providers.factory import AIProviderFactory
from app.models.settings import UserSettings

logger = structlog.get_logger()

MATCH_EXPLANATION_PROMPT = """You are an AI career advisor. Briefly explain (in 2 concise sentences) why the candidate's profile matches this job opening:
Candidate Title/Skills: {skills}
Candidate Summary: {summary}
Job Title: {job_title}
Company: {company}
Required Skills: {job_skills}
Explanation:"""


class JobMatcherAgent:
    """Computes compatibility score and detailed match breakdown between a user and job."""

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

        user_skills = set(s.lower() for s in profile.get("skills", []))
        job_skills = set(s.lower() for s in job.get("required_skills", []))

        # 1. Skills score
        matching_skills = [s for s in job.get("required_skills", []) if s.lower() in user_skills]
        missing_skills = [s for s in job.get("required_skills", []) if s.lower() not in user_skills]

        if job_skills:
            skills_ratio = len(matching_skills) / len(job_skills)
            skills_score = int(skills_ratio * 50)  # Max 50 pts
        else:
            skills_score = 35

        # 2. Location & Remote score
        prefs = profile.get("job_preferences", {})
        location_score = 20
        if job.get("is_remote") or prefs.get("remote_preference") in ["remote", "any"]:
            location_score = 25
        elif prefs.get("locations"):
            job_loc = (job.get("location") or "").lower()
            if any(l.lower() in job_loc for l in prefs.get("locations", [])):
                location_score = 25
            else:
                location_score = 10

        # 3. Title / Preference match
        pref_titles = [t.lower() for t in prefs.get("titles", [])]
        job_title = job.get("title", "").lower()
        title_score = 15
        if any(t in job_title for t in pref_titles):
            title_score = 25

        total_score = min(100, max(10, skills_score + location_score + title_score))

        # 4. Narrative reasoning
        reasoning = f"Matched {len(matching_skills)} required skill(s) including {', '.join(matching_skills[:3]) or 'core capabilities'}."
        if user_settings:
            try:
                provider = AIProviderFactory.resolve(user_settings)
                prompt = MATCH_EXPLANATION_PROMPT.format(
                    skills=", ".join(profile.get("skills", [])[:10]),
                    summary=profile.get("summary", ""),
                    job_title=job.get("title"),
                    company=job.get("company"),
                    job_skills=", ".join(job.get("required_skills", [])[:8]),
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
            "missing_skills": missing_skills,
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
