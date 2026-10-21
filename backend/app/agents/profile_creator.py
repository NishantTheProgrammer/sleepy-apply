import json
import re
import uuid
import structlog
from typing import Any
from app.providers.factory import AIProviderFactory
from app.models.settings import UserSettings

logger = structlog.get_logger()

EXTRACTION_PROMPT = """You are an expert ATS resume parser. Extract candidate information from the following resume text into a strict JSON object with this exact structure:

{
  "personal": {
    "fullName": "string",
    "email": "string",
    "phone": "string",
    "location": {
      "address": "string",
      "city": "string",
      "postalCode": "string",
      "country": "string"
    },
    "linkedin": "string or null",
    "github": "string or null",
    "portfolio": "string or null"
  },
  "summary": "string",
  "skills": {
    "backend": ["string"],
    "frontend": ["string"],
    "languages": ["string"],
    "databases": ["string"],
    "ui": ["string"],
    "tools": ["string"],
    "architecture": ["string"]
  },
  "experience": [
    {
      "company": "string",
      "startDate": "YYYY-MM or string",
      "endDate": "YYYY-MM or null",
      "current": boolean,
      "jobTitle": "string",
      "description": "string",
      "responsibilities": ["string"],
      "projects": [
        {
          "name": "string",
          "description": "string",
          "technologies": ["string"],
          "achievements": ["string"]
        }
      ]
    }
  ],
  "projects": [
    {
      "name": "string",
      "description": "string",
      "technologies": ["string"]
    }
  ],
  "education": [
    {
      "degree": "string",
      "institution": "string",
      "year": "string or number"
    }
  ],
  "achievements": [
    {
      "title": "string"
    }
  ],
  "jobPreferences": {
    "jobTitles": ["string"],
    "locations": ["string"],
    "remotePreference": "remote" or "hybrid" or "onsite" or null,
    "minimumSalary": number or null,
    "employmentTypes": ["full-time"]
  },
  "additionalInformation": {
    "yearsOfExperience": number or null,
    "totalProjects": "string or null"
  }
}

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

        # 1. Try LLM extraction if settings are provided
        if user_settings:
            try:
                provider = AIProviderFactory.resolve(user_settings)
                prompt = EXTRACTION_PROMPT + resume_text[:12000]
                resp = await provider.complete([{"role": "user", "content": prompt}], temperature=0.1)

                json_match = re.search(r"\{[\s\S]*\}", resp)
                if json_match:
                    extracted_data = json.loads(json_match.group(0))
            except Exception as e:
                logger.warning("AI extraction failed, falling back to heuristic parsing", error=str(e))

        # 2. Heuristic fallback
        if not extracted_data:
            extracted_data = self._heuristic_parse(resume_text)

        # 3. Normalize fields (populate both camelCase and snake_case for maximum compatibility)
        extracted_data = self._normalize_extracted_data(extracted_data)

        # 4. Detect gaps & generate questions
        missing_fields, questions = self._identify_gaps_and_questions(extracted_data)
        completion_score = self._calculate_completion_score(extracted_data)

        extracted_data["completion_score"] = completion_score
        extracted_data["missing_fields"] = missing_fields
        extracted_data["pending_questions"] = questions

        return extracted_data

    def _normalize_extracted_data(self, data: dict[str, Any]) -> dict[str, Any]:
        personal = data.get("personal", {})
        if "fullName" in personal and not personal.get("full_name"):
            personal["full_name"] = personal["fullName"]
        elif "full_name" in personal and not personal.get("fullName"):
            personal["fullName"] = personal["full_name"]

        # Ensure location is structured
        loc = personal.get("location")
        if isinstance(loc, str):
            personal["location"] = {
                "address": "",
                "city": loc,
                "postalCode": "",
                "country": "",
            }

        # Normalize experience items
        exp_list = data.get("experience", [])
        for exp in exp_list:
            if "jobTitle" in exp and not exp.get("title"):
                exp["title"] = exp["jobTitle"]
            if "title" in exp and not exp.get("jobTitle"):
                exp["jobTitle"] = exp["title"]
            if "startDate" in exp and not exp.get("start_date"):
                exp["start_date"] = exp["startDate"]
            if "endDate" in exp and not exp.get("end_date"):
                exp["end_date"] = exp["endDate"]
            if "current" in exp and "is_current" not in exp:
                exp["is_current"] = exp["current"]

        # Sync jobPreferences
        if "jobPreferences" in data and not data.get("job_preferences"):
            data["job_preferences"] = data["jobPreferences"]
        elif "job_preferences" in data and not data.get("jobPreferences"):
            data["jobPreferences"] = data["job_preferences"]

        return data

    def _heuristic_parse(self, text: str) -> dict[str, Any]:
        """Regex and keyword parser when AI is offline or key is not configured."""
        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
        phone_match = re.search(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", text)
        linkedin_match = re.search(r"linkedin\.com/in/[\w-]+", text, re.IGNORECASE)
        github_match = re.search(r"github\.com/[\w-]+", text, re.IGNORECASE)
        portfolio_match = re.search(r"(https?://)?(www\.)?[\w-]+\.(com|dev|io|me|org)", text, re.IGNORECASE)

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        candidate_name = lines[0] if lines else "Candidate"
        if len(candidate_name) > 40 or "@" in candidate_name:
            candidate_name = "Candidate"

        backend_skills = ["Python", "Node.js", "Express", "Spring Boot", "FastAPI", "Django", "Go", "Java"]
        frontend_skills = ["React", "Next.js", "Angular", "Vue", "TypeScript", "JavaScript"]
        database_skills = ["MongoDB", "PostgreSQL", "MySQL", "Redis"]
        tool_skills = ["Docker", "Git", "Linux", "AWS", "Kubernetes"]

        def find_in_text(skill_list):
            return [s for s in skill_list if re.search(r"\b" + re.escape(s) + r"\b", text, re.IGNORECASE)]

        skills = {
            "backend": find_in_text(backend_skills),
            "frontend": find_in_text(frontend_skills),
            "databases": find_in_text(database_skills),
            "tools": find_in_text(tool_skills),
        }

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
            "summary": "",
            "skills": skills,
            "experience": [],
            "projects": [],
            "education": [],
            "achievements": [],
            "jobPreferences": {
                "jobTitles": [],
                "locations": [],
                "remotePreference": "any",
                "minimumSalary": None,
                "employmentTypes": ["full-time"],
            },
            "additionalInformation": {
                "yearsOfExperience": None,
                "totalProjects": None,
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
