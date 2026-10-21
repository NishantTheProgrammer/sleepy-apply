import json
import re
import uuid
import structlog
from typing import Any
from app.providers.factory import AIProviderFactory
from app.models.settings import UserSettings
from app.models.profile import Profile, PersonalInfo, Experience, Education, Project

logger = structlog.get_logger()

EXTRACTION_PROMPT = """You are an expert ATS resume parser. Extract candidate information from the following resume text into a strict JSON object.

Output JSON format exactly:
{
  "personal": {
    "full_name": "string",
    "email": "string",
    "phone": "string",
    "location": "string",
    "linkedin": "string",
    "github": "string",
    "portfolio": "string"
  },
  "summary": "string",
  "skills": ["string"],
  "experience": [
    {
      "company": "string",
      "title": "string",
      "start_date": "string",
      "end_date": "string or null",
      "is_current": boolean,
      "description": "string",
      "achievements": ["string"]
    }
  ],
  "education": [
    {
      "institution": "string",
      "degree": "string",
      "field": "string",
      "graduation_year": "string"
    }
  ],
  "projects": [
    {
      "name": "string",
      "description": "string",
      "technologies": ["string"]
    }
  ]
}

Resume Text:
"""


class ProfileCreatorAgent:
    """Parses resume text, extracts profile sections, detects missing fields,

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
                prompt = EXTRACTION_PROMPT + resume_text[:8000]
                resp = await provider.complete([{"role": "user", "content": prompt}], temperature=0.1)
                
                # Extract JSON block
                json_match = re.search(r"\{[\s\S]*\}", resp)
                if json_match:
                    extracted_data = json.loads(json_match.group(0))
            except Exception as e:
                logger.warning("AI extraction failed, falling back to heuristic parsing", error=str(e))

        # 2. Heuristic fallback
        if not extracted_data:
            extracted_data = self._heuristic_parse(resume_text)

        # 3. Detect gaps & generate questions
        missing_fields, questions = self._identify_gaps_and_questions(extracted_data)
        completion_score = self._calculate_completion_score(extracted_data)

        return {
            "personal": extracted_data.get("personal", {}),
            "summary": extracted_data.get("summary", ""),
            "skills": extracted_data.get("skills", []),
            "experience": extracted_data.get("experience", []),
            "education": extracted_data.get("education", []),
            "projects": extracted_data.get("projects", []),
            "completion_score": completion_score,
            "missing_fields": missing_fields,
            "pending_questions": questions,
        }

    def _heuristic_parse(self, text: str) -> dict[str, Any]:
        """Simple regex & keyword parser when AI is offline or key is not yet configured."""
        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
        phone_match = re.search(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", text)
        linkedin_match = re.search(r"linkedin\.com/in/[\w-]+", text, re.IGNORECASE)
        github_match = re.search(r"github\.com/[\w-]+", text, re.IGNORECASE)

        # Extract potential skills
        common_skills = [
            "Python", "JavaScript", "TypeScript", "React", "Next.js", "Node.js",
            "Go", "Rust", "Java", "Docker", "Kubernetes", "AWS", "FastAPI",
            "MongoDB", "PostgreSQL", "SQL", "GraphQL", "Git", "Tailwind CSS",
            "Machine Learning", "PyTorch", "TensorFlow", "Pandas", "Scikit-Learn"
        ]
        found_skills = [s for s in common_skills if re.search(r"\b" + re.escape(s) + r"\b", text, re.IGNORECASE)]

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        candidate_name = lines[0] if lines else "Candidate"
        if len(candidate_name) > 40 or "@" in candidate_name:
            candidate_name = "Candidate"

        return {
            "personal": {
                "full_name": candidate_name,
                "email": email_match.group(0) if email_match else "",
                "phone": phone_match.group(0) if phone_match else "",
                "location": "",
                "linkedin": f"https://{linkedin_match.group(0)}" if linkedin_match else "",
                "github": f"https://{github_match.group(0)}" if github_match else "",
                "portfolio": "",
            },
            "summary": "",
            "skills": found_skills,
            "experience": [],
            "education": [],
            "projects": [],
        }

    def _identify_gaps_and_questions(self, data: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
        missing = []
        questions = []

        personal = data.get("personal", {})
        if not personal.get("location"):
            missing.append("personal.location")
            questions.append({
                "id": str(uuid.uuid4())[:8],
                "field": "personal.location",
                "question": "What is your current city and country / preferred work location?",
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
                "question": "In 1-2 sentences, what role are you looking for and what are your primary strengths?",
            })

        if len(data.get("skills", [])) < 3:
            missing.append("skills")
            questions.append({
                "id": str(uuid.uuid4())[:8],
                "field": "skills",
                "question": "What are your top 5 core technical or professional skills?",
            })

        return missing, questions

    def _calculate_completion_score(self, data: dict[str, Any]) -> int:
        score = 0
        p = data.get("personal", {})
        if p.get("full_name") and p.get("full_name") != "Candidate": score += 15
        if p.get("email"): score += 15
        if p.get("phone"): score += 10
        if p.get("location"): score += 10
        if p.get("linkedin") or p.get("github"): score += 10
        if data.get("summary"): score += 10
        if len(data.get("skills", [])) >= 3: score += 15
        if len(data.get("experience", [])) > 0: score += 15
        return min(100, score)
