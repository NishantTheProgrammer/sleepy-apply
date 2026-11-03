import json
import re
import uuid
import structlog
import urllib.request
from typing import Any
from datetime import datetime, timezone
from bson import ObjectId
from app.db.client import get_db
from app.models.settings import UserSettings
from app.providers.factory import AIProviderFactory

logger = structlog.get_logger()


class ScreeningQAAgent:
    """
    Dynamic AI Screening & Q/A Agent.
    Analyzes uploaded resumes, suggests target profile chips, and generates recruiter screening questions
    using a fast local model (Ollama llama3.2 / llama3.1) with reliable fallbacks.
    """

    OLLAMA_URL = "http://host.docker.internal:11434"

    def _call_local_ollama(self, prompt: str, model: str = "llama3.2:latest") -> dict[str, Any] | None:
        """Calls local Ollama instance with timeout and returns parsed JSON if successful."""
        try:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are an expert technical recruiter and hiring manager assistant. Return strict JSON only."},
                    {"role": "user", "content": prompt}
                ],
                "stream": False,
                "format": "json"
            }
            req = urllib.request.Request(
                f"{self.OLLAMA_URL}/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=12) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                content = res_data.get("message", {}).get("content", "")
                return self._parse_json(content)
        except Exception as e:
            logger.warning("Local Ollama chat call failed, will try fallback", error=str(e))
            return None

    def _parse_json(self, text: str) -> dict[str, Any] | None:
        if not text:
            return None
        # Strip code blocks if any
        clean = re.sub(r"```(?:json)?\s*([\s\S]*?)\s*```", r"\1", text).strip()
        try:
            return json.loads(clean)
        except Exception:
            # Try finding outer braces
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    pass
        return None

    def generate_suggested_roles(self, profile: dict) -> list[str]:
        """Infers candidate's strongest target role options as chips from skills and experience."""
        summary = (profile.get("summary") or "").lower()
        skills = profile.get("skills", {})
        all_skills = []
        if isinstance(skills, dict):
            for v in skills.values():
                if isinstance(v, list): all_skills.extend(v)
        elif isinstance(skills, list):
            all_skills = skills

        exp_titles = [
            (e.get("title") or e.get("jobTitle") or "")
            for e in profile.get("experience", [])
            if (e.get("title") or e.get("jobTitle"))
        ]

        text = f"{summary} {' '.join(exp_titles)} {' '.join(all_skills)}".lower()

        # SDET / QA Automation
        if any(k in text for k in ["sdet", "qa", "playwright", "selenium", "cypress", "quality engineer", "test automation"]):
            return [
                "Senior SDET",
                "QA Automation Engineer (Playwright/Selenium)",
                "Lead Quality Engineer",
                "Software Development Engineer in Test (SDET)",
                "API & Performance Test Engineer"
            ]
        # ETL / Data QA
        elif any(k in text for k in ["etl", "snowflake", "pyspark", "airflow", "data quality", "data warehouse"]):
            return [
                "Senior Quality Engineer (ETL & Data)",
                "Data Platform QA Engineer",
                "Big Data Test Engineer",
                "Data Quality Engineer",
                "Senior Data Engineer"
            ]
        # Intern / Fresh Graduate
        elif any(k in text for k in ["intern", "fresh graduate", "fresher", "trainee", "0 exp", "academic projects"]):
            return [
                "MERN Stack Intern",
                "Software Engineering Intern",
                "Junior React Developer",
                "Junior Fullstack Developer",
                "Graduate Trainee Engineer"
            ]
        # Python Backend
        elif any(k in text for k in ["python", "django", "fastapi", "flask"]) and "react" not in text:
            return [
                "Senior Python Developer",
                "Software Engineer - Python",
                "Backend Engineer (FastAPI / Django)",
                "Python Microservices Architect",
                "Data Platform Engineer"
            ]
        # Full Stack / JS / React
        else:
            return [
                "Senior Full Stack Engineer (Node.js & React)",
                "Software Development Engineer II (SDE-2)",
                "Senior Backend Engineer (Node.js)",
                "Senior Frontend Engineer (React/Next.js)",
                "Full Stack Developer"
            ]

    async def generate_screening_questions(
        self,
        profile: dict,
        target_role: str | None = None,
        user_settings: UserSettings | None = None
    ) -> list[dict[str, Any]]:
        """Generates 3-5 recruiter screening questions tailored to the resume and target role."""
        name = profile.get("personal", {}).get("fullName") or "Candidate"
        summary = profile.get("summary") or ""
        skills = profile.get("skills", {})
        skills_summary = ", ".join(
            (v if isinstance(v, str) else ", ".join(v[:4]))
            for v in (skills.values() if isinstance(skills, dict) else [skills])
        )[:200]

        role = target_role or (profile.get("job_preferences", {}).get("jobTitles") or ["Software Engineer"])[0]

        prompt = f"""You are an expert technical recruiter and engineering hiring manager.
Generate 3 to 4 realistic screening questions a recruiter will ask this candidate for their target role.
Candidate: {name}
Target Role: {role}
Summary: {summary[:300]}
Key Skills: {skills_summary}

Requirements:
1. Cover core technical depth on their primary tech stack (e.g. scale, framework architecture, concurrency).
2. Cover practical experience details (e.g. project scale, testing, or system architecture).
3. Cover availability / logistics (e.g. Notice Period, Expected CTC, or Work Location preference in Delhi NCR/Bengaluru).
4. For each question, provide 3 to 4 quick multiple-choice chip options so the user can easily click to answer.

Return strict JSON only in this format:
{{
  "questions": [
    {{
      "id": "q1",
      "category": "technical",
      "question": "Clear, direct recruiter question?",
      "context_hint": "Why the recruiter is asking this",
      "suggested_options": ["Option 1", "Option 2", "Option 3", "Option 4"]
    }}
  ]
}}
"""

        # 1. Try Fast Local Ollama (llama3.2:latest or llama3.2:1b)
        ollama_res = self._call_local_ollama(prompt, model="llama3.2:latest")
        if not ollama_res:
            ollama_res = self._call_local_ollama(prompt, model="llama3.2:1b")

        if ollama_res and isinstance(ollama_res.get("questions"), list) and len(ollama_res["questions"]) > 0:
            return self._format_questions(ollama_res["questions"])

        # 2. Try configured AI provider (e.g. Gemini / OpenAI) if settings provided
        if user_settings and user_settings.ai_provider != "ollama":
            try:
                provider = AIProviderFactory.resolve(user_settings)
                resp = await provider.complete([{"role": "user", "content": prompt}], temperature=0.3)
                parsed = self._parse_json(resp)
                if parsed and isinstance(parsed.get("questions"), list):
                    return self._format_questions(parsed["questions"])
            except Exception as e:
                logger.warning("Remote AI provider screening question generation failed", error=str(e))

        # 3. Deterministic Heuristic Questions Fallback
        return self._generate_heuristic_questions(profile, role)

    def _format_questions(self, raw_questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        formatted = []
        for i, q in enumerate(raw_questions):
            if not isinstance(q, dict):
                continue
            qid = q.get("id") or f"q_{i+1}_{str(uuid.uuid4())[:6]}"
            formatted.append({
                "id": str(qid),
                "category": q.get("category", "technical"),
                "question": q.get("question", "").strip(),
                "context_hint": q.get("context_hint", "Recruiter screening evaluation"),
                "suggested_options": q.get("suggested_options", []),
                "asked_at": datetime.now(timezone.utc).isoformat(),
                "answer": None,
                "answered_at": None,
            })
        return formatted

    def _generate_heuristic_questions(self, profile: dict, role: str) -> list[dict[str, Any]]:
        """Fallback recruiter questions when LLM is unavailable."""
        role_low = role.lower()
        now_iso = datetime.now(timezone.utc).isoformat()

        if "sdet" in role_low or "quality" in role_low or "qa" in role_low:
            return [
                {
                    "id": "q_sdet_framework",
                    "category": "technical",
                    "question": "Which test automation frameworks have you designed or maintained from scratch in production?",
                    "context_hint": "Recruiter evaluating framework architecture and fixture design depth.",
                    "suggested_options": [
                        "Playwright with TypeScript (POM & Custom Fixtures)",
                        "Selenium WebDriver with Java & TestNG",
                        "Cypress with JavaScript",
                        "REST Assured for Backend APIs"
                    ],
                    "asked_at": now_iso,
                    "answer": None,
                },
                {
                    "id": "q_sdet_api",
                    "category": "technical",
                    "question": "What is your primary approach for backend API automated regression suites?",
                    "context_hint": "Validating microservices test coverage beyond UI automation.",
                    "suggested_options": [
                        "REST Assured with JSON schema validation",
                        "Playwright API request context",
                        "Postman / Newman automated CLI pipelines",
                        "Custom Python requests test harness"
                    ],
                    "asked_at": now_iso,
                    "answer": None,
                },
                {
                    "id": "q_logistics_notice",
                    "category": "logistics",
                    "question": "What is your current notice period and earliest date of joining?",
                    "context_hint": "Essential for recruiter shortlisting in Delhi NCR & Bengaluru.",
                    "suggested_options": [
                        "Immediate / Serving notice",
                        "15 - 30 Days",
                        "60 Days",
                        "90 Days (Negotiable buy-out)"
                    ],
                    "asked_at": now_iso,
                    "answer": None,
                }
            ]
        elif "intern" in role_low or "fresher" in role_low:
            return [
                {
                    "id": "q_intern_project",
                    "category": "technical",
                    "question": "Which full stack MERN project are you most proud of and what was your key contribution?",
                    "context_hint": "Assessing hands-on coding and problem-solving skills.",
                    "suggested_options": [
                        "Full stack E-commerce with auth & Stripe payments",
                        "Real-time chat / collaborative board (Socket.io)",
                        "Task management portal with REST APIs & MongoDB",
                        "Responsive frontend portfolio with React & Tailwind"
                    ],
                    "asked_at": now_iso,
                    "answer": None,
                },
                {
                    "id": "q_intern_avail",
                    "category": "logistics",
                    "question": "What is your availability for an internship and can you work full-time on-site/hybrid in Delhi NCR?",
                    "context_hint": "Confirming immediate internship timeline.",
                    "suggested_options": [
                        "Immediate full-time (Graduated)",
                        "Available for 6-month internship with PPO",
                        "Available immediately (Hybrid/Remote in NCR)",
                        "Part-time / Final semester"
                    ],
                    "asked_at": now_iso,
                    "answer": None,
                }
            ]
        else:
            return [
                {
                    "id": "q_dev_scale",
                    "category": "technical",
                    "question": "What scale (concurrent users, requests per second, or data volume) did your microservices handle in your last role?",
                    "context_hint": "Hiring manager evaluating production readiness and distributed systems experience.",
                    "suggested_options": [
                        "10,000+ req/sec high-throughput platform",
                        "1,000 - 5,000 req/min enterprise web portal",
                        "200k+ monthly active users",
                        "Internal enterprise tools & dashboards"
                    ],
                    "asked_at": now_iso,
                    "answer": None,
                },
                {
                    "id": "q_dev_stack",
                    "category": "technical",
                    "question": "What is your core production backend & database stack?",
                    "context_hint": "Recruiter matching against company tech radar.",
                    "suggested_options": [
                        "Node.js, Express, TypeScript, MongoDB & Redis",
                        "Python, FastAPI / Django, PostgreSQL",
                        "Java, Spring Boot, MySQL & Kafka",
                        "Next.js full stack with Server Actions"
                    ],
                    "asked_at": now_iso,
                    "answer": None,
                },
                {
                    "id": "q_logistics_notice",
                    "category": "logistics",
                    "question": "What is your notice period and current work preference in Delhi NCR?",
                    "context_hint": "Key logistics filter for active recruiter outreach.",
                    "suggested_options": [
                        "Immediate / 15 Days (Open to Hybrid NCR)",
                        "30 Days notice (Prefer Remote / Noida / Gurugram)",
                        "60 Days notice",
                        "Open to relocation across India"
                    ],
                    "asked_at": now_iso,
                    "answer": None,
                }
            ]

