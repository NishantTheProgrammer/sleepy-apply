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
    "office manager", "procurement", "supply chain", "commercial account", "receptionist"
]

QA_KEYWORDS = [
    "sdet", "qa", "quality engineer", "test engineer", "automation engineer",
    "software test", "testing", "quality assurance", "test automation", "qa automation",
    "playwright", "selenium", "testng", "cypress", "appium", "rest assured", "software development engineer in test"
]

DEV_KEYWORDS = [
    "software engineer", "software developer", "backend", "frontend", "full stack",
    "fullstack", "web developer", "application engineer", "systems engineer", "platform engineer",
    "developer", "architect"
]

CORE_LANGUAGES = [
    "python", "java", "javascript", "typescript", "golang", "go", "c++", "c#",
    ".net", "dotnet", "rust", "ruby", "php", "scala", "kotlin", "swift"
]

CORE_FRAMEWORKS = [
    "django", "fastapi", "flask", "spring", "spring boot", "react", "angular", "vue",
    "node", "nodejs", "playwright", "selenium", "appium", "rest assured", "testng", "cypress"
]

COMMON_TECH_STACK = [
    "python", "golang", "go", "c++", "c#", ".net", "dotnet", "rust", "ruby", "rails",
    "kubernetes", "k8s", "aws", "gcp", "azure", "kafka", "redis", "graphql", "terraform",
    "spark", "hadoop", "snowflake", "salesforce", "scala", "elixir", "swift", "kotlin",
    "django", "fastapi", "flask", "docker", "microservices"
]


class JobMatcherAgent:
    """Computes compatibility score and detailed match breakdown between a user and job (India Tech Jobs)."""

    async def match_user_and_job(
        self,
        user_id: str,
        job_id: str,
        user_settings: UserSettings | None = None,
        use_ai_reasoning: bool = False,
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

        # 2. Extract Candidate's Domain & Experience Profile
        exp_titles = [
            (e.get("title") or e.get("jobTitle") or "").lower()
            for e in profile.get("experience", [])
            if (e.get("title") or e.get("jobTitle"))
        ]
        target_prefs = profile.get("job_preferences") or profile.get("jobPreferences") or {}
        pref_titles = [str(t).lower() for t in (target_prefs.get("jobTitles") or target_prefs.get("titles") or []) if t]
        summary_lower = (profile.get("summary") or "").lower()
        cand_role_text = f"{' '.join(exp_titles)} {' '.join(pref_titles)} {summary_lower}"

        candidate_is_sdet = any(kw in cand_role_text for kw in QA_KEYWORDS)
        candidate_is_pure_dev = any(
            kw in " ".join(exp_titles) for kw in ["backend", "frontend", "full stack", "software engineer", "developer"]
        ) and not candidate_is_sdet

        # 3. Clean HTML from job text
        desc_clean = re.sub(r"<[^>]+>", " ", desc_raw)
        title_raw = job.get("title", "")
        job_full_text = f"{title_raw} {desc_clean}".lower()
        title_lower = title_raw.lower()

        # 4. Job Domain Classification
        is_hardware_mfg = any(kw in title_lower for kw in ["manufacturing", "supplier quality", "plant quality", "civil", "mechanical", "factory"])
        job_is_non_tech = is_hardware_mfg or (any(kw in title_lower for kw in NON_TECH_KEYWORDS) and not any(
            tk in title_lower for tk in ["software", "developer", "engineer", "architect", "tech", "qa", "sdet", "test"]
        ))
        job_is_sdet = not is_hardware_mfg and (any(kw in title_lower for kw in QA_KEYWORDS) or ("test" in title_lower and "engineer" in title_lower))
        job_is_dev = any(kw in title_lower for kw in DEV_KEYWORDS) and not job_is_sdet

        # 5. Extract Tech Stack Declared Directly in Job Title (e.g. "Software Engineer - Python", "React Developer")
        title_stack = None
        for st in ["python", "react", "golang", "go", "dotnet", ".net", "c#", "c++", "ruby", "php", "flutter", "ios", "android", "java", "angular"]:
            pattern = r"\b" + re.escape(st) + r"\b"
            if re.search(pattern, title_lower):
                title_stack = st
                break

        title_stack_missing = False
        title_stack_matched = False
        if title_stack:
            if title_stack == "go" and ("golang" in user_skills_lower or "go" in user_skills_lower):
                title_stack_matched = True
            elif title_stack in ["dotnet", ".net", "c#"] and any(k in user_skills_lower for k in [".net", "dotnet", "c#"]):
                title_stack_matched = True
            elif title_stack in user_skills_lower:
                title_stack_matched = True
            else:
                title_stack_missing = True

        # 6. Extract Matching Skills and Missing Skills
        matching_skills = []
        for s in user_skills_clean:
            s_low = s.lower()
            pattern = r"\b" + re.escape(s_low) + r"\b"
            if re.search(pattern, job_full_text) or s_low in [rs.lower() for rs in job.get("required_skills", [])]:
                if s not in matching_skills:
                    matching_skills.append(s)

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

        # Categorize matches and gaps
        core_matches = [
            s for s in matching_skills
            if s.lower() in CORE_LANGUAGES or s.lower() in CORE_FRAMEWORKS
        ]
        tool_matches = [
            s for s in matching_skills
            if s not in core_matches
        ]
        core_missing = [
            s for s in missing_skills
            if s.lower() in CORE_LANGUAGES or s.lower() in CORE_FRAMEWORKS
        ]

        # 7. Compute Realistic Domain-Aware Breakdown Score
        is_ncr = job.get("is_delhi_ncr", False) or any(h in location.lower() for h in ["gurgaon", "gurugram", "noida", "delhi", "faridabad", "ghaziabad"])
        loc_label = f" ({job.get('delhi_ncr_hub', 'Delhi NCR')})" if is_ncr else ""

        if job_is_non_tech:
            title_score = 5
            skills_score = max(5, min(10, len(matching_skills) * 2))
            default_reason = f"Non-technical role ({title_raw}) does not align with your technical profile."
        elif candidate_is_sdet:
            # Candidate is SDET / QA Automation Engineer
            if job_is_sdet:
                # Direct domain match
                title_score = 35
                total_reqs = len(job.get("required_skills", []))
                coverage = len(matching_skills) / max(1, total_reqs) if total_reqs > 0 else 0.8
                base_skills = int(coverage * 30)
                core_bonus = min(15, len(core_matches) * 5)
                missing_penalty = min(15, len(core_missing) * 3)
                tool_bonus = min(5, len(tool_matches) * 1)
                skills_score = max(10, min(45, base_skills + core_bonus + tool_bonus - missing_penalty))
                default_reason = f"Excellent direct match for this {title_raw}{loc_label} role with your SDET and test automation background."
            elif job_is_dev:
                # Candidate is SDET applying for a Software Engineering role
                if title_stack_missing:
                    # CRITICAL MISMATCH: e.g. Software Engineer - Python when candidate has NO Python
                    title_score = 5
                    skills_score = max(5, min(10, len(matching_skills) * 2))
                    stack_label = title_stack.upper() if title_stack else "required technology"
                    default_reason = f"Role requires specialized {stack_label} developer expertise; your profile is focused on SDET / Quality Engineering and lacks {stack_label}."
                elif title_stack_matched:
                    # Shared language (e.g. Java Backend Engineer, and candidate knows Java)
                    title_score = 18
                    total_reqs = len(job.get("required_skills", []))
                    coverage = len(matching_skills) / max(1, total_reqs) if total_reqs > 0 else 0.4
                    base_skills = int(coverage * 25)
                    core_bonus = min(10, len(core_matches) * 4)
                    missing_penalty = min(12, len(core_missing) * 2)
                    skills_score = max(8, min(35, base_skills + core_bonus - missing_penalty))
                    default_reason = f"Software development role where your {title_stack.upper()} foundation provides transferable skills, though your primary experience is in Quality Engineering."
                else:
                    # Generic Software Engineer role
                    has_testing_mention = any(k in job_full_text for k in ["test", "quality", "automation", "ci/cd"])
                    title_score = 22 if has_testing_mention else 12
                    total_reqs = len(job.get("required_skills", []))
                    coverage = len(matching_skills) / max(1, total_reqs) if total_reqs > 0 else 0.3
                    skills_score = max(5, min(30, int(coverage * 20) + min(10, len(core_matches) * 3)))
                    default_reason = f"Software Engineering role with moderate overlap on technical fundamentals."
            else:
                title_score = 10
                skills_score = max(5, min(15, len(matching_skills) * 2))
                default_reason = f"Moderate match for {title_raw} with some overlapping technical tools."
        elif candidate_is_pure_dev:
            if job_is_dev:
                if title_stack_missing:
                    title_score = 10
                    skills_score = max(5, min(15, len(matching_skills) * 2))
                    default_reason = f"Development role requiring {title_stack.upper()}, which is not present in your primary tech stack."
                else:
                    title_score = 30
                    total_reqs = len(job.get("required_skills", []))
                    coverage = len(matching_skills) / max(1, total_reqs) if total_reqs > 0 else 0.7
                    skills_score = max(10, min(45, int(coverage * 30) + min(15, len(core_matches) * 5)))
                    default_reason = f"Strong alignment with your profile for this {title_raw}{loc_label} development position."
            else:
                title_score = 14
                skills_score = max(5, min(20, len(matching_skills) * 3))
                default_reason = f"Adjacent engineering role for {title_raw}."
        else:
            title_score = 16
            skills_score = max(5, min(25, len(matching_skills) * 3))
            default_reason = f"General match for {title_raw} based on profile skills."

        # 8. Location & Commute Scoring for Delhi NCR
        rem_pref = target_prefs.get("remote_preference") or target_prefs.get("remotePreference") or "any"
        pref_locs = [str(l).lower() for l in (target_prefs.get("preferred_locations") or target_prefs.get("locations") or []) if l]
        raw_loc = profile.get("personal", {}).get("location")
        user_loc = ""
        if isinstance(raw_loc, str):
            user_loc = raw_loc.lower()
        elif isinstance(raw_loc, dict):
            user_loc = " ".join(str(v).lower() for v in raw_loc.values() if v)

        is_remote_job = job.get("is_remote") or job.get("work_model") == "Remote"
        if is_remote_job or rem_pref in ["remote", "any", "open"]:
            location_score = 20
        elif is_ncr:
            hub = job.get("delhi_ncr_hub", "").lower()
            if any(h in user_loc for h in [hub, "delhi", "ncr", "gurugram", "noida"]) or any(h in " ".join(pref_locs) for h in [hub, "delhi", "ncr"]):
                location_score = 20
            else:
                location_score = 18
        else:
            location_score = 12

        total_score = min(98, max(15, skills_score + title_score + location_score))

        # 6. AI Match Reasoning
        reasoning = default_reason
        if use_ai_reasoning and user_settings:
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
