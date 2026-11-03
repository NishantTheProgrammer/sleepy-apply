import json
import re
import uuid
import structlog
from typing import Any
from app.providers.factory import AIProviderFactory
from app.models.settings import UserSettings

logger = structlog.get_logger()

EXTRACTION_PROMPT = """You are an expert ATS resume parser and candidate data extractor.
Your objective is to read the candidate's resume text below and extract complete, highly accurate candidate profile information into a strict, valid JSON object matching the exact schema below.

CRITICAL INSTRUCTIONS (MUST COMPLY STRICTLY):
1. EXTRACT ALL WORK EXPERIENCES:
   - You MUST extract EVERY SINGLE employer, company, organization, and past position listed in the resume.
   - If the candidate has 2, 3, 4, 5, or more past positions, you MUST include ALL of them in the "experience" array in reverse-chronological order.
   - NEVER stop after the first or current job. Never omit previous employers, past roles, or internships.
   - Distinguish Employers from Sub-Projects:
     * A company/employer where the candidate was employed is an entry in the "experience" array (e.g. "Dhwani Rural Information Systems", "Max Vision Solutions Pvt. Ltd.").
     * Specific projects, products, platforms, or client features developed during employment at that company MUST be listed inside that experience entry's "projects" array or "responsibilities" list, NOT as separate top-level companies.
     * Standalone, freelance, personal, or academic projects belong in the top-level "projects" array.

2. PRESERVE ALL INFORMATION - DO NOT CUT OR SUMMARIZE:
   - Do NOT omit, truncate, shorten, or summarize away bullet points, responsibilities, or technical achievements.
   - For every job, extract EVERY bullet point and duty into the "responsibilities" array.
   - Preserve all quantitative metrics, numbers, and scale (e.g. "4000+ urban local bodies", "450+ LeetCode questions", "10+ scalable applications", "6th Star Gold Badge").
   - Extract the candidate's full professional summary or career objective into "summary".

3. EXTRACT ALL SKILLS COMPREHENSIVELY:
   - Exhaustively extract ALL technical skills, languages, frameworks, databases, libraries, cloud tools, DevOps tools, and architectural patterns found anywhere in the resume text into the appropriate categories: backend, frontend, languages, databases, ui, tools, architecture.

4. EXTRACT ALL EDUCATION & ACHIEVEMENTS:
   - Include all degrees, diplomas, institutions, and graduation years in the "education" array.
   - Badges, competitive programming stats, certifications, awards, or honors belong in the "achievements" array.

5. NEVER OUTPUT LITERAL "null", "none", OR PLACEHOLDER PROJECTS:
   - Never output the string "null" or "none" in any field (e.g. description, projects, endDate).
   - If a job has no standalone description or summary line, use an empty string "" (do not write "null").
   - If an experience has no separate sub-projects, leave the "projects" array empty []. Do NOT invent phantom project entries with name "null" or "none".
   - If there are no standalone projects on the resume, leave top-level "projects" as []. Do NOT output projects with name "null".

STRICT JSON SCHEMA:
{
  "personal": {
    "fullName": "Full Name string",
    "email": "email string",
    "phone": "phone number string",
    "location": {
      "address": "string",
      "city": "string",
      "postalCode": "string",
      "country": "string"
    },
    "linkedin": "LinkedIn URL string or null",
    "github": "GitHub URL string or null",
    "portfolio": "Portfolio / Website URL string or null"
  },
  "summary": "Full professional summary or objective from resume",
  "skills": {
    "backend": ["Node.js", "Express", "Spring Boot", "FastAPI"],
    "frontend": ["React", "Angular", "Vue", "Next.js"],
    "languages": ["JavaScript", "TypeScript", "Python", "Java"],
    "databases": ["MongoDB", "PostgreSQL", "MySQL", "Redis"],
    "ui": ["Tailwind", "Bootstrap", "Material UI"],
    "tools": ["Docker", "Git", "Linux", "AWS"],
    "architecture": ["Microservices", "REST APIs", "System Design"]
  },
  "experience": [
    {
      "company": "Company / Organization 1 Name",
      "startDate": "YYYY-MM or Mon YYYY",
      "endDate": "YYYY-MM or Mon YYYY or null",
      "current": true,
      "jobTitle": "Job Title / Role 1",
      "description": "Company overview or role summary",
      "responsibilities": [
        "Full detailed bullet point 1 with metrics and technical details",
        "Full detailed bullet point 2 with metrics and technical details"
      ],
      "projects": [
        {
          "name": "Project or Platform 1",
          "description": "Project overview and contribution",
          "technologies": ["Tech1", "Tech2"],
          "achievements": ["Achievement or metric"]
        }
      ]
    },
    {
      "company": "Company / Organization 2 Name",
      "startDate": "YYYY-MM or Mon YYYY",
      "endDate": "YYYY-MM or Mon YYYY",
      "current": false,
      "jobTitle": "Job Title / Role 2",
      "description": "Company overview or role summary",
      "responsibilities": [
        "Full detailed bullet point 1 with metrics and technical details",
        "Full detailed bullet point 2 with metrics and technical details"
      ],
      "projects": [
        {
          "name": "Project or Platform 2",
          "description": "Project overview and contribution",
          "technologies": ["Tech1", "Tech2"],
          "achievements": []
        }
      ]
    }
  ],
  "projects": [
    {
      "name": "Standalone / Relevant Project 1",
      "description": "Project description and scope",
      "technologies": ["Tech1", "Tech2"]
    },
    {
      "name": "Standalone / Relevant Project 2",
      "description": "Project description and scope",
      "technologies": ["Tech1", "Tech2"]
    }
  ],
  "education": [
    {
      "degree": "Degree 1 (e.g. Masters in Computer Applications)",
      "institution": "University / College 1",
      "year": "2023"
    },
    {
      "degree": "Degree 2 (e.g. Bachelors in Computer Applications)",
      "institution": "University / College 2",
      "year": "2020"
    }
  ],
  "achievements": [
    {
      "title": "HackerRank 6th Star Gold Badge"
    },
    {
      "title": "Solved 450+ LeetCode questions"
    }
  ],
  "jobPreferences": {
    "jobTitles": ["<derive 2-3 target job titles directly aligned with candidate's actual work experience and summary, e.g. SDET, Senior Quality Engineer, or Backend Engineer>"],
    "locations": [],
    "remotePreference": "any",
    "minimumSalary": null,
    "employmentTypes": ["full-time"]
  },
  "additionalInformation": {
    "yearsOfExperience": 5,
    "totalProjects": "10+"
  }
}

OUTPUT RULES:
- Output ONLY valid JSON.
- Never truncate arrays.
- Return every work experience found in the resume.

Resume Text:
"""


class ProfileCreatorAgent:
    """Parses resume text, extracts rich profile sections, detects missing fields,
    and generates clarifying questions for the candidate.
    """

    async def analyze_resume(
        self,
        resume_text: str,
        user_settings: UserSettings | None = None,
    ) -> dict[str, Any]:
        extracted_data = None

        # Clean text slightly (collapse 3+ newlines to 2, strip null bytes)
        clean_text = re.sub(r"\n{3,}", "\n\n", resume_text.replace("\x00", "")).strip()

        # 1. Try LLM extraction (defaulting to local Ollama llama3.2 if no user_settings configured)
        if not user_settings:
            from bson import ObjectId
            user_settings = UserSettings(
                user_id=ObjectId(),
                ai_provider="ollama",
                ai_model="llama3.2:latest",
            )

        # Prepare extraction prompt with large context limit (up to 35,000 characters)
        prompt = EXTRACTION_PROMPT + clean_text[:35000]

        app_prefs = user_settings.application_preferences if user_settings else None
        extract_temp = float(getattr(app_prefs, "extraction_temperature", 0.1) if app_prefs else 0.1)

        try:
            provider = AIProviderFactory.resolve(user_settings)
            resp = await provider.complete(
                [{"role": "user", "content": prompt}],
                temperature=extract_temp,
                num_ctx=8192,
                format="json",
            )
            extracted_data = self._extract_json_from_response(resp)
        except Exception as e:
            logger.warning("Primary AI extraction failed, trying default local Ollama llama3.2", error=str(e))
            if user_settings.ai_provider != "ollama":
                try:
                    from bson import ObjectId
                    local_settings = UserSettings(
                        user_id=ObjectId(),
                        ai_provider="ollama",
                        ai_model="llama3.2:latest",
                    )
                    provider = AIProviderFactory.resolve(local_settings)
                    resp = await provider.complete(
                        [{"role": "user", "content": prompt}],
                        temperature=extract_temp,
                        num_ctx=8192,
                        format="json",
                    )
                    extracted_data = self._extract_json_from_response(resp)
                except Exception as fallback_err:
                    logger.warning("AI extraction failed, falling back to heuristic parsing", error=str(fallback_err))
            else:
                logger.warning("Ollama AI extraction failed, falling back to heuristic parsing", error=str(e))

        # 2. Heuristic fallback
        if not extracted_data:
            extracted_data = self._heuristic_parse(clean_text)

        # 3. Normalize fields (populate both camelCase and snake_case for maximum compatibility)
        extracted_data = self._normalize_extracted_data(extracted_data)

        # 4. Detect gaps & generate questions
        missing_fields, questions = self._identify_gaps_and_questions(extracted_data)
        completion_score = self._calculate_completion_score(extracted_data)

        extracted_data["completion_score"] = completion_score
        extracted_data["missing_fields"] = missing_fields
        extracted_data["pending_questions"] = questions

        return extracted_data

    def _extract_json_from_response(self, text: str) -> dict[str, Any] | None:
        """Robustly extracts JSON from an LLM response, stripping code fences or preamble."""
        if not text:
            return None

        # 1. Strip markdown code fences if present
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if fence_match:
            try:
                return json.loads(fence_match.group(1).strip())
            except Exception:
                pass

        # 2. Match outermost { ... }
        brace_match = re.search(r"\{[\s\S]*\}", text)
        if brace_match:
            try:
                return json.loads(brace_match.group(0).strip())
            except Exception:
                pass

        return None

    def _normalize_extracted_data(self, data: dict[str, Any]) -> dict[str, Any]:
        def _clean_str(val: Any) -> str | None:
            if val is None:
                return None
            s = str(val).strip()
            if s.lower() in ["null", "none", "nil", "undefined", "n/a", "na"]:
                return None
            return s

        personal = data.setdefault("personal", {})
        for field in ["fullName", "full_name", "email", "phone", "linkedin", "github", "portfolio"]:
            if field in personal:
                personal[field] = _clean_str(personal[field])

        if "fullName" in personal and not personal.get("full_name"):
            personal["full_name"] = personal["fullName"]
        elif "full_name" in personal and not personal.get("fullName"):
            personal["fullName"] = personal["full_name"]

        # Ensure location is structured
        loc = personal.get("location")
        if isinstance(loc, str):
            personal["location"] = {
                "address": "",
                "city": _clean_str(loc) or "",
                "postalCode": "",
                "country": "",
            }
        elif isinstance(loc, dict):
            loc["address"] = _clean_str(loc.get("address")) or ""
            loc["city"] = _clean_str(loc.get("city")) or ""
            loc["postalCode"] = _clean_str(loc.get("postalCode")) or ""
            loc["country"] = _clean_str(loc.get("country")) or ""

        # Summary
        if "summary" in data:
            data["summary"] = _clean_str(data["summary"]) or ""

        # Normalize experience items
        exp_list = data.get("experience", [])
        if not isinstance(exp_list, list):
            exp_list = []

        cleaned_exp_list = []
        for exp in exp_list:
            if not isinstance(exp, dict):
                continue
            job_title = _clean_str(exp.get("jobTitle") or exp.get("title")) or "Software Engineer"
            company = _clean_str(exp.get("company")) or "Company"
            start_date = _clean_str(exp.get("startDate") or exp.get("start_date")) or ""
            end_date = _clean_str(exp.get("endDate") or exp.get("end_date"))
            is_current = bool(exp.get("current") or exp.get("is_current"))
            if is_current:
                end_date = "Present"
            description = _clean_str(exp.get("description")) or ""

            # Responsibilities
            raw_resp = exp.get("responsibilities", [])
            if not isinstance(raw_resp, list):
                raw_resp = [str(raw_resp)] if raw_resp else []
            clean_resp = [_clean_str(r) for r in raw_resp if _clean_str(r)]

            # Sub-projects
            raw_sub = exp.get("projects", [])
            clean_sub = []
            if isinstance(raw_sub, list):
                for prj in raw_sub:
                    if isinstance(prj, dict):
                        p_name = _clean_str(prj.get("name"))
                        # Eliminate phantom projects where name is "null" or empty
                        if not p_name:
                            continue
                        p_desc = _clean_str(prj.get("description")) or ""
                        raw_tech = prj.get("technologies", [])
                        clean_tech = [_clean_str(t) for t in (raw_tech if isinstance(raw_tech, list) else [raw_tech]) if _clean_str(t)]
                        raw_ach = prj.get("achievements", [])
                        clean_ach = [_clean_str(a) for a in (raw_ach if isinstance(raw_ach, list) else [raw_ach]) if _clean_str(a)]
                        clean_sub.append({
                            "name": p_name,
                            "description": p_desc,
                            "technologies": clean_tech,
                            "achievements": clean_ach,
                        })

            cleaned_exp_list.append({
                "company": company,
                "jobTitle": job_title,
                "title": job_title,
                "startDate": start_date,
                "start_date": start_date,
                "endDate": end_date,
                "end_date": end_date,
                "current": is_current,
                "is_current": is_current,
                "description": description,
                "responsibilities": clean_resp,
                "projects": clean_sub,
            })
        data["experience"] = cleaned_exp_list

        # Normalize standalone projects
        raw_projects = data.get("projects", [])
        clean_projects = []
        if isinstance(raw_projects, list):
            for prj in raw_projects:
                if isinstance(prj, dict):
                    p_name = _clean_str(prj.get("name"))
                    # Discard phantom projects where name is "null"
                    if not p_name:
                        continue
                    p_desc = _clean_str(prj.get("description")) or ""
                    raw_tech = prj.get("technologies", [])
                    clean_tech = [_clean_str(t) for t in (raw_tech if isinstance(raw_tech, list) else [raw_tech]) if _clean_str(t)]
                    clean_projects.append({
                        "name": p_name,
                        "description": p_desc,
                        "technologies": clean_tech,
                    })
        data["projects"] = clean_projects

        # Normalize education
        edu_list = data.get("education", [])
        clean_edu = []
        if isinstance(edu_list, list):
            for ed in edu_list:
                if isinstance(ed, dict):
                    deg = _clean_str(ed.get("degree"))
                    inst = _clean_str(ed.get("institution"))
                    yr = _clean_str(ed.get("year") or ed.get("graduation_year"))
                    if deg or inst:
                        clean_edu.append({
                            "degree": deg or "",
                            "institution": inst or "",
                            "year": yr or "",
                        })
        data["education"] = clean_edu

        # Normalize achievements
        ach_list = data.get("achievements", [])
        clean_ach = []
        if isinstance(ach_list, list):
            for ach in ach_list:
                if isinstance(ach, str):
                    c = _clean_str(ach)
                    if c:
                        clean_ach.append({"title": c})
                elif isinstance(ach, dict):
                    c = _clean_str(ach.get("title"))
                    if c:
                        clean_ach.append({"title": c})
        data["achievements"] = clean_ach

        # Sync jobPreferences
        if "jobPreferences" in data and not data.get("job_preferences"):
            data["job_preferences"] = data["jobPreferences"]
        elif "job_preferences" in data and not data.get("jobPreferences"):
            data["jobPreferences"] = data["job_preferences"]

        return data

    def _heuristic_parse(self, text: str) -> dict[str, Any]:
        """Robust regex and section parser when AI is offline or model key is unconfigured."""
        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
        phone_match = re.search(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", text)
        linkedin_match = re.search(r"linkedin\.com/in/([a-zA-Z0-9_-]+)", text, re.IGNORECASE)
        github_match = re.search(r"github\.com/([a-zA-Z0-9_-]+)", text, re.IGNORECASE)
        
        # Portfolio: avoid matching email domains like gmail.com or github.com
        portfolio_match = re.search(
            r"(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+\.(?:dev|me|io|app|tech|site|online))(?:\/[^\s]*)?",
            text,
            re.IGNORECASE,
        )

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        candidate_name = "Candidate"
        for line in lines[:6]:
            cleaned_line = re.sub(r"[\w\.-]+@[\w\.-]+\.\w+", "", line)
            cleaned_line = re.sub(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", "", cleaned_line)
            cleaned_line = re.sub(r"(?:github\.com|linkedin\.com|leetcode\.com)[^\s]*", "", cleaned_line, flags=re.IGNORECASE)
            cleaned_line = re.sub(r"(?:email|mobile|phone|contact|github|linkedin|portfolio)\s*:", "", cleaned_line, flags=re.IGNORECASE)
            parts = re.split(r"(?:\s{2,}|[|•·/])", cleaned_line)
            for part in parts:
                candidate = part.strip()
                if 2 <= len(candidate) <= 35 and re.match(r"^[A-Za-z]+([ .'-][A-Za-z]+)+$", candidate):
                    lower = candidate.lower()
                    if not any(header in lower for header in ["curriculum", "vitae", "resume", "summary", "profile", "engineer", "developer", "tester", "quality", "page"]):
                        candidate_name = candidate
                        break
            if candidate_name != "Candidate":
                break

        backend_skills = ["Node.js", "Express", "Spring Boot", "FastAPI", "Django", "Go", "Java", "Python", "Microservices"]
        frontend_skills = ["React", "Next.js", "Angular", "Vue", "TypeScript", "JavaScript", "HTML", "CSS"]
        database_skills = ["MongoDB", "PostgreSQL", "MySQL", "Redis"]
        ui_skills = ["Tailwind", "Bootstrap", "Material UI"]
        tool_skills = ["Docker", "Git", "Linux", "AWS", "Kubernetes", "Jest"]

        def find_in_text(skill_list):
            return [s for s in skill_list if re.search(r"\b" + re.escape(s) + r"\b", text, re.IGNORECASE)]

        skills = {
            "backend": find_in_text(backend_skills),
            "frontend": find_in_text(frontend_skills),
            "databases": find_in_text(database_skills),
            "ui": find_in_text(ui_skills),
            "tools": find_in_text(tool_skills),
            "languages": find_in_text(["JavaScript", "TypeScript", "Python", "Java", "Go", "C++"]),
            "architecture": find_in_text(["Microservices", "REST APIs", "System Design"]),
        }

        # Extract summary block if present
        summary_text = ""
        summary_match = re.search(r"(?:SUMMARY|PROFESSIONAL SUMMARY|OBJECTIVE)\s*\n+([\s\S]*?)(?=\n+[A-Z\s]{4,}|\Z)", text, re.IGNORECASE)
        if summary_match:
            summary_text = re.sub(r"\s+", " ", summary_match.group(1)).strip()

        # Extract experiences heuristically
        experience_list: list[dict[str, Any]] = []
        exp_match = re.search(r"(?:EXPERIENCE|WORK EXPERIENCE|EMPLOYMENT HISTORY)\s*\n+([\s\S]*?)(?=\n+(?:EDUCATION|PROJECTS|RELEVANT PROJECTS|SKILLS|ACHIEVEMENTS)\b|\Z)", text, re.IGNORECASE)
        if exp_match:
            exp_block = exp_match.group(1)
            # Find company / date chunks
            # Match lines with dates like Jan 2023 – Current or 2021 - 2022
            date_pattern = r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{4})[^\n]*?(?:Current|Present|\d{4}))"
            entries = re.split(date_pattern, exp_block, flags=re.IGNORECASE)
            # Pair companies with date ranges
            if len(entries) > 1:
                # entries[0] = company or header before date, entries[1] = date, entries[2] = content...
                for i in range(1, len(entries), 2):
                    date_str = entries[i].strip()
                    content_chunk = entries[i+1].strip() if i+1 < len(entries) else ""
                    # The company name was likely on the line right before the date
                    prev_chunk = entries[i-1].strip().split("\n")
                    company_name = prev_chunk[-1].strip() if prev_chunk else "Company"
                    # Look for job title at the start of content_chunk
                    chunk_lines = [l.strip() for l in content_chunk.split("\n") if l.strip()]
                    job_title = chunk_lines[0] if chunk_lines else "Software Engineer"
                    bullets = [l.lstrip("●-•* ").strip() for l in chunk_lines[1:] if len(l) > 15]

                    is_current = bool(re.search(r"current|present", date_str, re.IGNORECASE))
                    experience_list.append({
                        "company": company_name,
                        "jobTitle": job_title,
                        "title": job_title,
                        "startDate": date_str.split("–")[0].split("-")[0].strip(),
                        "endDate": "Current" if is_current else (date_str.split("–")[-1].split("-")[-1].strip() if "–" in date_str or "-" in date_str else date_str),
                        "current": is_current,
                        "is_current": is_current,
                        "description": " ".join(chunk_lines[1:3]) if len(chunk_lines) > 1 else "",
                        "responsibilities": bullets[:8],
                        "projects": [],
                    })

        # Extract education heuristically
        education_list: list[dict[str, Any]] = []
        edu_match = re.search(r"(?:EDUCATION)\s*\n+([\s\S]*?)(?=\n+[A-Z\s]{4,}|\Z)", text, re.IGNORECASE)
        if edu_match:
            edu_block = edu_match.group(1)
            for line in edu_block.split("\n"):
                line = line.strip()
                if not line or len(line) < 5:
                    continue
                year_match = re.search(r"\b(19\d{2}|20\d{2})\b", line)
                year_val = year_match.group(0) if year_match else ""
                education_list.append({
                    "degree": line.replace(f"({year_val})", "").replace(year_val, "").strip(" -.,()"),
                    "institution": "University / College",
                    "year": year_val,
                })

        # Extract projects heuristically
        projects_list: list[dict[str, Any]] = []
        proj_match = re.search(r"(?:RELEVANT PROJECTS|PROJECTS)\s*\n+([\s\S]*?)(?=\n+(?:EDUCATION|EXPERIENCE|SKILLS|ACHIEVEMENTS)\b|\Z)", text, re.IGNORECASE)
        if proj_match:
            proj_block = proj_match.group(1)
            for line in proj_block.split("\n"):
                line = line.strip()
                if ":" in line and len(line) > 15:
                    name_part, desc_part = line.split(":", 1)
                    projects_list.append({
                        "name": name_part.strip("●-•* "),
                        "description": desc_part.strip(),
                        "technologies": [t for t in ["React", "Node.js", "Next.js", "Django", "Vue", "Flutter", "Spring Boot", "Stripe"] if t.lower() in desc_part.lower()],
                    })

        # Extract achievements
        achievements_list: list[dict[str, Any]] = []
        for line in lines:
            if any(kw in line.lower() for kw in ["hackerrank", "leetcode", "badge", "certified", "award", "gold"]):
                clean_ach = line.strip("●-•* ")
                if len(clean_ach) > 10:
                    achievements_list.append({"title": clean_ach})

        return {
            "personal": {
                "fullName": candidate_name,
                "full_name": candidate_name,
                "email": email_match.group(0) if email_match else "",
                "phone": phone_match.group(0) if phone_match else "",
                "location": {"address": "", "city": "", "postalCode": "", "country": ""},
                "linkedin": f"https://{linkedin_match.group(0)}" if linkedin_match else None,
                "github": f"https://{github_match.group(0)}" if github_match else None,
                "portfolio": portfolio_match.group(0) if portfolio_match else None,
            },
            "summary": summary_text,
            "skills": skills,
            "experience": experience_list,
            "projects": projects_list,
            "education": education_list,
            "achievements": achievements_list,
            "jobPreferences": {
                "jobTitles": [
                    exp.get("title") or exp.get("jobTitle")
                    for exp in experience_list
                    if (exp.get("title") or exp.get("jobTitle"))
                ] or (
                    ["SDET", "QA Automation Engineer"]
                    if any(t in text.lower() for t in ["sdet", "quality engineer", "test automation", "qa"])
                    else ["Software Engineer"]
                ),
                "locations": [],
                "remotePreference": "any",
                "minimumSalary": None,
                "employmentTypes": ["full-time"],
            },
            "additionalInformation": {
                "yearsOfExperience": 5 if "5 years" in text.lower() else None,
                "totalProjects": "10+" if "10+" in text else None,
            },
        }

    def _identify_gaps_and_questions(self, data: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
        missing = []
        questions = []

        personal = data.get("personal", {})
        loc = personal.get("location", {})
        city = loc.get("city") if isinstance(loc, dict) else loc
        if not city:
            missing.append("personal.location.city")
            questions.append({
                "id": str(uuid.uuid4())[:8],
                "field": "personal.location.city",
                "question": "What is your current city and preferred work location?",
            })

        if not personal.get("linkedin"):
            missing.append("personal.linkedin")
            questions.append({
                "id": str(uuid.uuid4())[:8],
                "field": "personal.linkedin",
                "question": "What is your LinkedIn profile URL?",
            })

        if not data.get("summary"):
            missing.append("summary")
            questions.append({
                "id": str(uuid.uuid4())[:8],
                "field": "summary",
                "question": "In 1-2 sentences, what is your primary technical summary or target role?",
            })

        skills = data.get("skills", {})
        total_skills = sum(len(v) for v in skills.values()) if isinstance(skills, dict) else len(skills)
        if total_skills < 3:
            missing.append("skills")
            questions.append({
                "id": str(uuid.uuid4())[:8],
                "field": "skills",
                "question": "What are your top 5 technical skills or core technologies?",
            })

        return missing, questions

    def _calculate_completion_score(self, data: dict[str, Any]) -> int:
        score = 0
        p = data.get("personal", {})
        name = p.get("fullName") or p.get("full_name")
        if name and name != "Candidate": score += 15
        if p.get("email"): score += 15
        if p.get("phone"): score += 10
        loc = p.get("location", {})
        if (isinstance(loc, dict) and loc.get("city")) or (isinstance(loc, str) and loc): score += 10
        if p.get("linkedin") or p.get("github") or p.get("portfolio"): score += 10
        if data.get("summary"): score += 10

        skills = data.get("skills", {})
        total_skills = sum(len(v) for v in skills.values()) if isinstance(skills, dict) else len(skills)
        if total_skills >= 4: score += 15

        if len(data.get("experience", [])) > 0: score += 10
        if len(data.get("education", [])) > 0: score += 5
        return min(100, score)
