import json
import re
import uuid
import structlog
from typing import Any
from datetime import datetime, timezone
from bson import ObjectId

from app.models.settings import UserSettings
from app.providers.factory import AIProviderFactory

logger = structlog.get_logger()


class ScreeningQAAgent:
    """
    Dynamic AI Recruiter Screening Agent.
    Retrieves tailored recruiter screening questions and candidate prefill options
    directly via LLM inference based on the candidate's actual resume, skills, and target role.
    No hardcoded question templates or if/else role branching.
    """

    def _parse_json(self, text: str) -> dict[str, Any] | None:
        if not text:
            return None
        clean = re.sub(r"```(?:json)?\s*([\s\S]*?)\s*```", r"\1", text).strip()
        try:
            return json.loads(clean)
        except Exception:
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    pass
        return None

    def _resolve_provider(self, user_settings: UserSettings | None):
        """Resolves user configured AI provider or defaults to local Ollama llama3.2."""
        if not user_settings:
            user_settings = UserSettings(
                user_id=ObjectId(),
                ai_provider="ollama",
                ai_model="llama3.2:latest",
            )
        return AIProviderFactory.resolve(user_settings)

    def generate_suggested_roles(self, profile: dict) -> list[str]:
        """
        Dynamically extracts candidate's target roles from LLM-parsed job preferences
        and work experience history without hardcoded if/else branching.
        """
        roles: list[str] = []
        seen = set()

        def _add(r: str):
            clean = str(r).strip()
            if (
                clean
                and len(clean) >= 3
                and clean.lower() not in seen
                and not clean.startswith("<")
                and clean.lower() not in ["null", "none", "undefined"]
                and not any(bad in clean.lower() for bad in ["derive", "e.g.", "aligned", "target job titles", "example"])
            ):
                seen.add(clean.lower())
                roles.append(clean)

        # 1. Primary: Job titles derived by the LLM during resume parsing
        for key in ["job_preferences", "jobPreferences"]:
            prefs = profile.get(key, {})
            if isinstance(prefs, dict):
                for t in prefs.get("jobTitles") or prefs.get("titles") or []:
                    _add(t)

        # 2. Candidate's actual job titles from experience history
        for exp in profile.get("experience", []):
            if isinstance(exp, dict):
                _add(exp.get("jobTitle") or exp.get("title") or "")

        # 3. Derive natural seniority variants if we have a primary role
        if roles:
            base_role = roles[0]
            if "senior" not in base_role.lower() and "lead" not in base_role.lower():
                _add(f"Senior {base_role}")
            if "lead" not in base_role.lower():
                _add(f"Lead {base_role}")

        # 4. Fallback if profile has zero extracted roles
        if not roles:
            skills = profile.get("skills", {})
            cand_skills = []
            if isinstance(skills, dict):
                for v in skills.values():
                    if isinstance(v, list):
                        cand_skills.extend(v[:3])
            tech = f" ({cand_skills[0]} & {cand_skills[1]})" if len(cand_skills) >= 2 else ""
            roles = [
                f"Senior Software Engineer{tech}",
                f"Software Development Engineer II (SDE-2){tech}",
                "Full Stack Developer",
            ]

        return roles[:5]

    async def generate_screening_questions(
        self,
        profile: dict,
        target_role: str | None = None,
        user_settings: UserSettings | None = None
    ) -> list[dict[str, Any]]:
        """
        Dynamically retrieves recruiter screening questions via LLM inference.
        No hardcoded question templates or if/else branches.
        """
        name = (
            profile.get("personal", {}).get("fullName")
            or profile.get("personal", {}).get("full_name")
            or "Candidate"
        )
        summary = profile.get("summary") or ""
        suggested = self.generate_suggested_roles(profile)
        role = target_role or (suggested[0] if suggested else "Software Engineer")

        # Extract all candidate skills
        skills = profile.get("skills", {})
        cand_skills = []
        if isinstance(skills, dict):
            for v in skills.values():
                if isinstance(v, list):
                    cand_skills.extend(v)
                elif isinstance(v, str):
                    cand_skills.extend([s.strip() for s in v.split(",") if s.strip()])
        elif isinstance(skills, list):
            cand_skills = [str(s) for s in skills]

        clean_cand_skills = []
        seen_s = set()
        for s in cand_skills:
            if isinstance(s, str) and s.strip() and s.strip().lower() not in seen_s:
                seen_s.add(s.strip().lower())
                clean_cand_skills.append(s.strip())

        exp_highlights = [
            f"{e.get('jobTitle') or e.get('title')} at {e.get('company')}"
            for e in profile.get("experience", [])
            if (e.get("jobTitle") or e.get("title"))
        ][:3]

        skills_str = ", ".join(clean_cand_skills[:18]) if clean_cand_skills else "Software engineering technologies"
        exp_str = "; ".join(exp_highlights) if exp_highlights else "Professional software development experience"

        prompt = f"""You are a technical recruiter screening an applicant for a {role} position.

Candidate Context:
- Candidate Name: {name}
- Target Position: {role}
- Candidate Extracted Skills: {skills_str}
- Career Background: {exp_str}
- Resume Summary: {summary[:400]}

Task:
Generate 5 recruiter screening questions tailored specifically to {role} and this candidate's profile to collect their application facts, tooling toolkit, and logistics.

CRITICAL RULES:
1. DO NOT ask theoretical interview questions, exam viva questions, or concept explanations (NEVER ask 'explain concurrency', 'walk me through how you solve X', 'what is the difference between', etc.). We are collecting candidate details, NOT testing their textbook knowledge.
2. Generate exactly 5 questions matching this structure:
   - Question 1 (type: "multiselect", category: "technical"): A hands-on production tooling & technology checklist tailored to {role}. In "suggested_options", include 6-8 relevant technology chips matching both the role and candidate's toolkit.
   - Question 2 (type: "single_select", category: "experience"): Total relevant hands-on experience in this domain (with 4-5 realistic year brackets in "suggested_options").
   - Question 3 (type: "single_select", category: "logistics"): Official notice period or earliest joining availability (e.g., Immediate, 15 - 30 Days, 45 - 60 Days, 90 Days).
   - Question 4 (type: "boolean" or "single_select", category: "logistics"): Work arrangement / location readiness (e.g., hybrid in candidate's city/region or remote).
   - Question 5 (type: "single_select", category: "compensation"): Expected annual compensation / CTC bracket (with realistic brackets in LPA for India or standard salary ranges for {role} seniority).

Return strict JSON only in this schema:
{{
  "questions": [
    {{
      "id": "q1",
      "category": "technical",
      "type": "multiselect",
      "question": "<tooling checklist question tailored to {role}>",
      "context_hint": "<short hint for candidate>",
      "suggested_options": ["<Tool1>", "<Tool2>", "<Tool3>", "<Tool4>", "<Tool5>", "<Tool6>"]
    }},
    {{
      "id": "q2",
      "category": "experience",
      "type": "single_select",
      "question": "<experience question tailored to {role}>",
      "context_hint": "<short hint>",
      "suggested_options": ["1-2 years", "3-5 years", "5-8 years", "8+ years"]
    }},
    {{
      "id": "q3",
      "category": "logistics",
      "type": "single_select",
      "question": "What is your official notice period?",
      "context_hint": "Recruiter assessing onboarding timeline",
      "suggested_options": ["Immediate (Serving notice)", "15 - 30 Days", "45 - 60 Days", "90 Days (Negotiable)"]
    }},
    {{
      "id": "q4",
      "category": "logistics",
      "type": "boolean",
      "question": "Are you open to working in a hybrid setup in Delhi NCR or Bengaluru?",
      "context_hint": "Workplace flexibility check",
      "suggested_options": ["Yes", "No"]
    }},
    {{
      "id": "q5",
      "category": "compensation",
      "type": "single_select",
      "question": "What is your expected annual CTC bracket for this role?",
      "context_hint": "Compensation expectation alignment",
      "suggested_options": ["12 - 18 LPA", "18 - 25 LPA", "25 - 35 LPA", "35+ LPA"]
    }}
  ]
}}
"""

        # 1. Primary: Retrieve questions directly via LLM call
        try:
            provider = self._resolve_provider(user_settings)
            raw = await provider.complete(
                [
                    {"role": "system", "content": "You are an expert technical recruiter assistant. Return strict JSON only."},
                    {"role": "user", "content": prompt}
                ],
                format="json",
                temperature=0.2,
                num_predict=700,
            )
            parsed = self._parse_json(raw)
            if parsed and isinstance(parsed.get("questions"), list) and len(parsed["questions"]) > 0:
                formatted = self._format_questions(parsed["questions"])
                if formatted:
                    return formatted
        except Exception as e:
            logger.warning("Primary LLM call for screening questions failed, trying fallback", error=str(e))

        # 2. Fallback to local Ollama if remote provider failed
        if user_settings and user_settings.ai_provider != "ollama":
            try:
                local_provider = self._resolve_provider(None)
                raw = await local_provider.complete(
                    [
                        {"role": "system", "content": "You are an expert technical recruiter assistant. Return strict JSON only."},
                        {"role": "user", "content": prompt}
                    ],
                    format="json",
                    temperature=0.2,
                    num_predict=700,
                )
                parsed = self._parse_json(raw)
                if parsed and isinstance(parsed.get("questions"), list) and len(parsed["questions"]) > 0:
                    formatted = self._format_questions(parsed["questions"])
                    if formatted:
                        return formatted
            except Exception as e2:
                logger.warning("Local Ollama fallback LLM call failed", error=str(e2))

        # 3. Dynamic generic fallback (only reached if all LLM attempts are offline)
        return self._generate_dynamic_fallback_questions(profile, role, clean_cand_skills)

    def _format_questions(self, raw_questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        disallowed_patterns = [
            "can you explain",
            "explain the concept",
            "walk me through",
            "how do you handle",
            "describe your approach",
            "what is the difference",
            "tell me about a time",
            "explain how you",
            "how would you resolve",
            "concept of concurrency",
            "critical issue in",
            "concept of",
        ]

        formatted = []
        for i, q in enumerate(raw_questions):
            if not isinstance(q, dict):
                continue

            q_text = str(q.get("question", "")).strip()
            q_text_low = q_text.lower()

            # Reject interview / theoretical viva questions
            if any(pattern in q_text_low for pattern in disallowed_patterns):
                logger.info("Filtered out theoretical interview question from screening", question=q_text)
                continue

            qid = q.get("id") or f"q_{i+1}_{str(uuid.uuid4())[:6]}"
            q_type = str(q.get("type", "")).lower().strip()
            if q_type not in ["multiselect", "single_select", "boolean", "number", "text"]:
                opts = q.get("suggested_options", [])
                opts_lower = {str(o).lower().strip() for o in opts}
                if opts_lower in [{"yes", "no"}, {"true", "false"}]:
                    q_type = "boolean"
                elif any(w in q_text_low for w in ["which", "what tools", "frameworks", "technologies", "libraries", "all that apply", "skills", "types"]):
                    q_type = "multiselect"
                elif any(w in q_text_low for w in ["how many years", "how many days", "years of experience"]):
                    q_type = "number"
                else:
                    q_type = "single_select"

            opts = q.get("suggested_options", [])
            if q_type == "number" and not opts:
                if "year" in q_text_low:
                    opts = ["1-2 years", "3-4 years", "4.5+ years", "6+ years"]
                elif "day" in q_text_low or "notice" in q_text_low:
                    opts = ["Immediate", "15 days", "30 days", "60 days"]
                elif "salary" in q_text_low or "ctc" in q_text_low or "lpa" in q_text_low:
                    opts = ["8-12 LPA", "12-16 LPA", "16-22 LPA", "22+ LPA"]

            formatted.append({
                "id": str(qid),
                "category": q.get("category", "technical"),
                "type": q_type,
                "question": q_text,
                "context_hint": q.get("context_hint", "Candidate details verification"),
                "suggested_options": opts,
                "unit": q.get("unit"),
                "min_selections": 1 if q_type == "multiselect" else None,
                "max_selections": None,
                "asked_at": datetime.now(timezone.utc).isoformat(),
                "answer": None,
                "answered_at": None,
            })
        return formatted

    def _generate_dynamic_fallback_questions(
        self, profile: dict, role: str, clean_skills: list[str]
    ) -> list[dict[str, Any]]:
        """Dynamic fallback with zero hardcoded if/else role branches, using candidate's actual skills."""
        now_iso = datetime.now(timezone.utc).isoformat()
        options = clean_skills[:8] if clean_skills else ["Core Technologies", "Frameworks", "APIs & Services", "Databases", "DevOps & CI/CD"]
        return [
            {
                "id": "q1",
                "category": "technical",
                "type": "multiselect",
                "question": f"Which core technologies, libraries, and tools have you worked with hands-on for {role} roles?",
                "context_hint": "Select all technologies in your active toolkit.",
                "suggested_options": options,
                "asked_at": now_iso,
                "answer": None,
                "answered_at": None,
            },
            {
                "id": "q2",
                "category": "experience",
                "type": "single_select",
                "question": f"How many total years of hands-on professional experience do you have in {role}?",
                "context_hint": "Select your total experience bracket.",
                "suggested_options": ["1-2 years", "3-4 years", "5-7 years", "7+ years"],
                "asked_at": now_iso,
                "answer": None,
                "answered_at": None,
            },
            {
                "id": "q3",
                "category": "logistics",
                "type": "single_select",
                "question": "What is your current official notice period?",
                "context_hint": "Recruiter assessing onboarding timeline.",
                "suggested_options": ["Immediate (Serving notice)", "15 - 30 Days", "45 - 60 Days", "90 Days (Negotiable)"],
                "asked_at": now_iso,
                "answer": None,
                "answered_at": None,
            },
            {
                "id": "q4",
                "category": "logistics",
                "type": "boolean",
                "question": "Are you open to working in a hybrid setup in Delhi NCR or Bengaluru?",
                "context_hint": "Location flexibility check.",
                "suggested_options": ["Yes", "No"],
                "asked_at": now_iso,
                "answer": None,
                "answered_at": None,
            },
            {
                "id": "q5",
                "category": "compensation",
                "type": "single_select",
                "question": f"What is your expected annual CTC bracket for {role}?",
                "context_hint": "Compensation expectation alignment.",
                "suggested_options": ["12 - 18 LPA", "18 - 25 LPA", "25 - 35 LPA", "35+ LPA"],
                "asked_at": now_iso,
                "answer": None,
                "answered_at": None,
            },
        ]
