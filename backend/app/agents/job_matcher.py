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

QA_ETL_KEYWORDS = [
    "etl", "data testing", "data quality", "sql testing", "snowflake", "big data test",
    "data warehouse test", "pipeline testing", "data validation", "great expectations"
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

    SENIORITY_LEVELS = ["intern", "junior", "mid", "senior", "lead"]

    @staticmethod
    def _extract_candidate_experience(profile: dict) -> tuple[float, str]:
        """Returns (years_of_experience, seniority_level)."""
        summary = (profile.get("summary") or "").lower()
        target_prefs = profile.get("job_preferences") or profile.get("jobPreferences") or {}
        pref_titles = [str(t).lower() for t in (target_prefs.get("jobTitles") or target_prefs.get("titles") or []) if t]
        combined_text = f"{summary} {' '.join(pref_titles)}"

        is_intern = any(k in combined_text for k in [
            "intern", "fresh graduate", "fresher", "trainee", "0 exp", "0 year", "academic projects"
        ])

        m = re.search(r"(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)", summary)
        if m:
            years = float(m.group(1))
        elif is_intern:
            years = 0.0
        else:
            exps = profile.get("experience", [])
            prof_exps = [e for e in exps if "project" not in str(e.get("company", "")).lower()]
            years = max(1.0, len(prof_exps) * 2.0) if prof_exps else 0.0

        if is_intern or years < 1.0:
            level = "intern"
        elif years < 2.5:
            level = "junior"
        elif years < 4.5:
            level = "mid"
        elif years < 8.0:
            level = "senior"
        else:
            level = "lead"

        return years, level

    @staticmethod
    def _extract_job_seniority(job: dict) -> tuple[float, str]:
        """Returns (min_years_required, seniority_level)."""
        title_low = (job.get("title") or "").lower()
        desc_low = (job.get("description") or "").lower()[:1500]
        db_sen = str(job.get("seniority") or "").lower()

        if any(k in title_low for k in ["intern", "internship", "trainee", "fresher"]):
            return 0.0, "intern"
        if any(k in title_low for k in ["sde-1", "sde 1", "sde1", "engineer 1", "engineer-1", "associate engineer", "junior"]):
            return 1.0, "junior"
        if any(k in title_low for k in ["sde-2", "sde 2", "sde2", "engineer ii", "engineer-ii", "engineer 2", "mid-level", "mid level"]):
            return 3.0, "mid"
        if any(k in title_low for k in ["sde-3", "sde 3", "sde3", "senior", "sr.", "sr ", "sdet-3", "sdet iii"]):
            return 5.0, "senior"
        if any(k in title_low for k in ["lead", "principal", "staff", "architect", "director", "manager", "head"]):
            return 8.0, "lead"

        if "junior" in db_sen or "entry" in db_sen:
            return 1.0, "junior"
        if "senior" in db_sen:
            return 5.0, "senior"
        if "lead" in db_sen or "staff" in db_sen or "management" in db_sen:
            return 8.0, "lead"
        if "mid" in db_sen:
            return 3.0, "mid"

        m = re.search(r"(?:minimum|min|at least|\b)\s*(\d+(?:\.\d+)?)\+?\s*(?:-\s*\d+)?\s*(?:years?|yrs?)", desc_low)
        if m:
            y = float(m.group(1))
            if y <= 1.0:
                return y, "junior"
            elif y <= 3.5:
                return y, "mid"
            elif y <= 7.0:
                return y, "senior"
            else:
                return y, "lead"

        return 2.5, "mid"

    @classmethod
    def _compute_experience_match(
        cls,
        cand_years: float,
        cand_level: str,
        job_years: float,
        job_level: str,
        job_title: str
    ) -> tuple[int, str, int]:
        """
        Returns (experience_score_out_of_25, experience_reason, penalty_cap).
        """
        levels = cls.SENIORITY_LEVELS
        cand_rank = levels.index(cand_level)
        job_rank = levels.index(job_level)
        diff = cand_rank - job_rank

        if cand_level == "intern":
            if job_level == "intern":
                return 25, "Intern / Fresh graduate direct alignment", 98
            elif job_level == "junior":
                return 14, "Entry-level candidate for junior opening (0 yrs exp)", 74
            elif job_level == "mid":
                return 2, "Role requires mid-level industry experience (2-4 yrs); candidate has 0 yrs", 45
            else:
                return 0, f"Role requires senior experience ({int(job_years)}+ yrs); candidate has 0 yrs", 38

        if diff == 0:
            return 25, f"{cand_years:g} yrs exp (Direct {job_level.title()} level match)", 98
        elif diff == 1:
            # 1 step above (e.g. Mid for Junior, or Senior for Mid)
            return 18, f"{cand_years:g} yrs exp (Meets and exceeds requirements)", 95
        elif diff >= 2:
            # 2+ steps above (e.g. Senior 5 yrs for SDE-1 entry)
            return 8, f"{cand_years:g} yrs exp (Overqualified for entry-level {job_title})", 74
        elif diff == -1:
            # 1 step below (e.g. Mid 3 yrs for Senior 5+ yrs)
            return 12, f"{cand_years:g} yrs exp (Stretch role; typically requires {int(job_years)}+ yrs)", 80
        else:
            # 2+ steps below
            return 2, f"{cand_years:g} yrs exp (Significant experience gap; requires {int(job_years)}+ yrs)", 50

    async def match_user_and_job(
        self,
        user_id: str,
        job_id: str,
        user_settings: UserSettings | None = None,
        use_ai_reasoning: bool = False,
        profile: dict | None = None,
        job: dict | None = None,
    ) -> dict | None:
        db = get_db()
        if profile is None:
            profile = await db.profiles.find_one({"user_id": ObjectId(user_id)})
        if job is None:
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

        user_skills_clean = []
        seen_user_skills = set()
        for s in user_skills_list:
            sc = s.strip()
            if sc and sc.lower() not in seen_user_skills:
                seen_user_skills.add(sc.lower())
                user_skills_clean.append(sc)
        user_skills_lower = set(s.lower() for s in user_skills_clean)

        # 2. Extract Candidate's Domain, Seniority & Experience Profile
        cand_years, cand_level = self._extract_candidate_experience(profile)

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
        candidate_is_qa_etl = any(kw in cand_role_text for kw in QA_ETL_KEYWORDS) or "etl" in cand_role_text
        candidate_is_pure_dev = any(
            kw in " ".join(exp_titles) for kw in ["backend", "frontend", "full stack", "software engineer", "developer", "mern"]
        ) and not candidate_is_sdet

        # 3. Clean HTML from job text
        desc_clean = re.sub(r"<[^>]+>", " ", desc_raw)
        title_raw = job.get("title", "")
        job_full_text = f"{title_raw} {desc_clean}".lower()
        title_lower = title_raw.lower()

        # 4. Job Domain & Seniority Classification
        job_years, job_level = self._extract_job_seniority(job)

        is_hardware_mfg = any(kw in title_lower for kw in ["manufacturing", "supplier quality", "plant quality", "civil", "mechanical", "factory"])
        job_is_non_tech = is_hardware_mfg or (any(kw in title_lower for kw in NON_TECH_KEYWORDS) and not any(
            tk in title_lower for tk in ["software", "developer", "engineer", "architect", "tech", "qa", "sdet", "test"]
        ))
        job_is_sdet = not is_hardware_mfg and (any(kw in title_lower for kw in QA_KEYWORDS) or ("test" in title_lower and "engineer" in title_lower))
        job_is_qa_etl = job_is_sdet and (any(kw in job_full_text for kw in QA_ETL_KEYWORDS) or "etl" in title_lower)
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
        seen_matched = set()
        for s in user_skills_clean:
            s_low = s.lower()
            pattern = r"\b" + re.escape(s_low) + r"\b"
            if re.search(pattern, job_full_text) or s_low in [rs.lower() for rs in job.get("required_skills", [])]:
                if s_low not in seen_matched:
                    seen_matched.add(s_low)
                    matching_skills.append(s)

        missing_skills = []
        seen_missing = set()
        for rs in job.get("required_skills", []):
            rs_low = rs.lower()
            if rs_low not in user_skills_lower and rs_low not in seen_missing:
                seen_missing.add(rs_low)
                missing_skills.append(rs)

        for ts in COMMON_TECH_STACK:
            pattern = r"\b" + re.escape(ts) + r"\b"
            if re.search(pattern, job_full_text) and ts not in user_skills_lower and ts not in seen_missing:
                title_case = "AWS" if ts == "aws" else ("GCP" if ts == "gcp" else ts.title())
                if title_case.lower() not in seen_missing:
                    seen_missing.add(title_case.lower())
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

        # 7. Compute Experience & Seniority Match
        experience_score, exp_match_reason, penalty_cap = self._compute_experience_match(
            cand_years=cand_years,
            cand_level=cand_level,
            job_years=job_years,
            job_level=job_level,
            job_title=title_raw,
        )

        # 8. Compute Domain & Title Score (Max 25 pts)
        is_ncr = job.get("is_delhi_ncr", False) or any(h in location.lower() for h in ["gurgaon", "gurugram", "noida", "delhi", "faridabad", "ghaziabad"])
        loc_label = f" ({job.get('delhi_ncr_hub', 'Delhi NCR')})" if is_ncr else ""

        if job_is_non_tech:
            title_score = 4
            skills_score = max(4, min(10, len(matching_skills) * 2))
            default_reason = f"Non-technical role ({title_raw}) does not align with your engineering profile."
        elif candidate_is_sdet:
            if job_is_sdet:
                # Check ETL vs Web QA specialization
                if candidate_is_qa_etl:
                    title_score = 25 if job_is_qa_etl else 17
                else:
                    title_score = 17 if job_is_qa_etl else 25

                total_reqs = len(job.get("required_skills", []))
                coverage = len(matching_skills) / max(1, total_reqs) if total_reqs > 0 else 0.8
                base_skills = int(coverage * 22)
                core_bonus = min(10, len(core_matches) * 4)
                tool_bonus = min(5, len(tool_matches) * 1)
                missing_pen = min(10, len(core_missing) * 2)
                skills_score = max(8, min(35, base_skills + core_bonus + tool_bonus - missing_pen))
                default_reason = f"Quality Engineering role matching your test automation background ({exp_match_reason})."
            elif job_is_dev:
                if title_stack_missing:
                    title_score = 5
                    skills_score = max(4, min(10, len(matching_skills) * 2))
                    stack_label = title_stack.upper() if title_stack else "required tech"
                    default_reason = f"Software developer role requiring specialized {stack_label}; your profile is focused on QA/SDET and lacks {stack_label}."
                elif title_stack_matched:
                    title_score = 14
                    total_reqs = len(job.get("required_skills", []))
                    coverage = len(matching_skills) / max(1, total_reqs) if total_reqs > 0 else 0.4
                    skills_score = max(6, min(24, int(coverage * 18) + min(8, len(core_matches) * 3)))
                    default_reason = f"Software development role where your {title_stack.upper()} foundation provides transferable skills ({exp_match_reason})."
                else:
                    title_score = 10
                    skills_score = max(5, min(20, len(matching_skills) * 2))
                    default_reason = f"Software engineering position with some transferable QA/automation fundamentals."
            else:
                title_score = 8
                skills_score = max(4, min(15, len(matching_skills) * 2))
                default_reason = f"Moderate match for {title_raw} with some overlapping technical tools."
        elif candidate_is_pure_dev:
            if job_is_dev:
                if title_stack_missing:
                    title_score = 8
                    skills_score = max(5, min(14, len(matching_skills) * 2))
                    default_reason = f"Development role requiring {title_stack.upper()}, which is not present in your primary tech stack."
                else:
                    # Role alignment based on target preferences & seniority
                    pref_match = any(pt in title_lower for pt in pref_titles)
                    title_score = 25 if pref_match or job_level == cand_level else 21
                    total_reqs = len(job.get("required_skills", []))
                    coverage = len(matching_skills) / max(1, total_reqs) if total_reqs > 0 else 0.7
                    base_skills = int(coverage * 22)
                    core_bonus = min(12, len(core_matches) * 4)
                    tool_bonus = min(5, len(tool_matches) * 1)
                    missing_pen = min(8, len(core_missing) * 2)
                    skills_score = max(8, min(35, base_skills + core_bonus + tool_bonus - missing_pen))
                    default_reason = f"Strong alignment for this {title_raw}{loc_label} position ({exp_match_reason})."
            else:
                title_score = 10
                skills_score = max(5, min(18, len(matching_skills) * 2))
                default_reason = f"Adjacent engineering role for {title_raw} ({exp_match_reason})."
        else:
            title_score = 12
            skills_score = max(5, min(20, len(matching_skills) * 2))
            default_reason = f"General technical match for {title_raw} based on profile skills."

        # 9. Location & Commute Scoring for Delhi NCR (Max 15 pts)
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
            location_score = 15
        elif is_ncr:
            hub = job.get("delhi_ncr_hub", "").lower()
            if any(h in user_loc for h in [hub, "delhi", "ncr", "gurugram", "noida"]) or any(h in " ".join(pref_locs) for h in [hub, "delhi", "ncr"]):
                location_score = 15
            else:
                location_score = 13
        else:
            location_score = 8

        # 10. Total Score with Experience Penalty Capping
        raw_total = skills_score + title_score + experience_score + location_score
        total_score = min(penalty_cap, min(98, max(15, raw_total)))

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
            "experience_match": exp_match_reason,
            "score_breakdown": {
                "skills": skills_score,
                "title": title_score,
                "experience": experience_score,
                "location": location_score,
                "skills_score": skills_score,
                "preference_score": title_score,
                "experience_score": experience_score,
                "location_score": location_score,
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
