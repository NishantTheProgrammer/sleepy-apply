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
        role_low = role.lower()

        # Extract all candidate skills
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
        seen_cs = set()
        for s in cand_skills:
            if isinstance(s, str) and s.strip() and s.strip().lower() not in seen_cs:
                seen_cs.add(s.strip().lower())
                clean_cand_skills.append(s.strip())

        is_qa = any(k in role_low for k in ["sdet", "qa", "quality", "test", "automation"])
        is_data = any(k in role_low for k in ["data", "etl", "snowflake", "big data", "pyspark", "pipeline"])
        is_fullstack = any(k in role_low for k in ["full stack", "fullstack", "software engineer", "developer", "backend", "sde"])
        is_frontend = any(k in role_low for k in ["frontend", "ui"]) and not is_fullstack and not is_qa

        if is_qa:
            domain_name = "QA & Test Automation"
            tech_question = "Which test automation frameworks, API testing libraries, and CI/CD tools have you worked with hands-on in production?"
            exp_question = "How many total years of hands-on QA & test automation experience do you have?"
            default_chips = ["Playwright", "Selenium WebDriver", "REST Assured", "Cypress", "Appium", "Postman", "Jenkins"]
            matched = [s for s in clean_cand_skills if any(q in s.lower() for q in ["playwright", "selenium", "rest", "cypress", "appium", "postman", "jenkins", "k6", "testng"])]
            tech_options = list(dict.fromkeys(matched + default_chips))[:8]
            ctc_options = ["8 - 12 LPA", "12 - 16 LPA", "16 - 22 LPA", "22+ LPA"]
        elif is_data:
            domain_name = "Data Engineering & ETL Pipelines"
            tech_question = "Which data processing frameworks, ETL tools, databases, and cloud platforms have you worked with hands-on in production?"
            exp_question = "How many total years of hands-on data engineering / ETL experience do you have?"
            default_chips = ["PySpark / Apache Spark", "SQL & Stored Procedures", "Apache Airflow", "Snowflake / BigQuery", "Kafka", "PostgreSQL / MySQL", "dbt"]
            matched = [s for s in clean_cand_skills if any(d in s.lower() for d in ["spark", "sql", "airflow", "snowflake", "bigquery", "kafka", "postgres", "dbt"])]
            tech_options = list(dict.fromkeys(matched + default_chips))[:8]
            ctc_options = ["12 - 18 LPA", "18 - 25 LPA", "25 - 35 LPA", "35+ LPA"]
        elif is_frontend:
            domain_name = "Frontend & UI Engineering"
            tech_question = f"Which frontend frameworks, state management libraries, and web tooling have you worked with hands-on for {role} roles?"
            exp_question = "How many total years of hands-on frontend web development experience do you have?"
            default_chips = ["React.js", "Next.js", "TypeScript", "Tailwind CSS", "Redux / Zustand", "HTML5 & CSS3", "REST / GraphQL APIs", "Jest / Vitest"]
            matched = [s for s in clean_cand_skills if any(f in s.lower() for f in ["react", "next", "type", "tail", "redux", "html", "css", "vue", "angular"])]
            tech_options = list(dict.fromkeys(matched + default_chips))[:8]
            ctc_options = ["12 - 18 LPA", "18 - 25 LPA", "25 - 35 LPA", "35+ LPA"]
        else:
            domain_name = "Full Stack & Software Engineering"
            tech_question = f"Which backend frameworks, frontend libraries, databases, and architectural tools have you worked with hands-on for {role} roles?"
            exp_question = "How many total years of hands-on full stack & software engineering experience do you have?"
            default_chips = ["Node.js & Express", "React.js & Next.js", "TypeScript & JavaScript", "MongoDB", "PostgreSQL / MySQL", "Docker & Microservices", "Spring Boot & Java", "REST & GraphQL APIs"]
            matched = [s for s in clean_cand_skills if any(m in s.lower() for m in ["node", "express", "react", "next", "type", "java", "spring", "mongo", "postgres", "sql", "docker", "micro", "jest"])]
            tech_options = list(dict.fromkeys(matched + default_chips))[:8]
            ctc_options = ["14 - 20 LPA", "20 - 28 LPA", "28 - 40 LPA", "40+ LPA"]

        # Build 100% reliable, instant dynamic questions with matched skills chips (0 ms latency)
        now_iso = datetime.now(timezone.utc).isoformat()
        tailored_questions = [
            {
                "id": "q1",
                "category": "technical",
                "type": "multiselect",
                "question": tech_question,
                "context_hint": "Select all technologies and tools in your active production toolkit.",
                "suggested_options": tech_options,
                "asked_at": now_iso,
                "answer": None,
                "answered_at": None,
            },
            {
                "id": "q2",
                "category": "experience",
                "type": "single_select",
                "question": exp_question,
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
                "question": "What is your expected annual CTC bracket?",
                "context_hint": "Compensation expectation alignment.",
                "suggested_options": ctc_options,
                "asked_at": now_iso,
                "answer": None,
                "answered_at": None,
            },
        ]
        return tailored_questions

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

    def _generate_heuristic_questions(self, profile: dict, role: str) -> list[dict[str, Any]]:
        """Candidate profile details questions (tools checklist, years of exp, notice period, location, CTC)."""
        role_low = role.lower()
        now_iso = datetime.now(timezone.utc).isoformat()

        if "sdet" in role_low or "quality" in role_low or "qa" in role_low:
            return [
                {
                    "id": "q_sdet_tools",
                    "category": "technical",
                    "type": "multiselect",
                    "question": "Which test automation frameworks and tools have you worked with hands-on in production?",
                    "context_hint": "Select all tools in your active toolkit.",
                    "suggested_options": [
                        "Playwright with TypeScript / JavaScript",
                        "Selenium WebDriver with Java & TestNG",
                        "REST Assured for API testing",
                        "Appium for mobile test automation",
                        "Cypress for E2E web testing",
                        "Postman / Newman",
                        "Jenkins / GitHub Actions CI"
                    ],
                    "asked_at": now_iso,
                    "answer": None,
                },
                {
                    "id": "q_sdet_experience",
                    "category": "experience",
                    "type": "single_select",
                    "question": "How many total years of hands-on test automation experience do you have?",
                    "context_hint": "Select your total experience bracket.",
                    "suggested_options": [
                        "1 - 2 Years",
                        "3 - 4 Years",
                        "4.5+ Years",
                        "6+ Years"
                    ],
                    "asked_at": now_iso,
                    "answer": None,
                },
                {
                    "id": "q_logistics_notice",
                    "category": "logistics",
                    "type": "single_select",
                    "question": "What is your official notice period / earliest joining date?",
                    "context_hint": "Recruiter evaluating onboarding timeline.",
                    "suggested_options": [
                        "Immediate (Serving notice)",
                        "15 - 30 Days",
                        "45 - 60 Days",
                        "90 Days (Negotiable buy-out)"
                    ],
                    "asked_at": now_iso,
                    "answer": None,
                },
                {
                    "id": "q_sdet_relocate",
                    "category": "logistics",
                    "type": "boolean",
                    "question": "Are you open to working in a hybrid setup in Delhi NCR or Bengaluru?",
                    "context_hint": "Location flexibility check.",
                    "suggested_options": ["Yes", "No"],
                    "asked_at": now_iso,
                    "answer": None,
                },
                {
                    "id": "q_sdet_ctc",
                    "category": "compensation",
                    "type": "single_select",
                    "question": "What is your expected annual CTC bracket?",
                    "context_hint": "Compensation expectation alignment.",
                    "suggested_options": [
                        "8 - 12 LPA",
                        "12 - 16 LPA",
                        "16 - 22 LPA",
                        "22+ LPA"
                    ],
                    "asked_at": now_iso,
                    "answer": None,
                }
            ]
        elif "intern" in role_low or "fresher" in role_low:
            return [
                {
                    "id": "q_intern_tools",
                    "category": "technical",
                    "type": "multiselect",
                    "question": "Which programming languages and frameworks are in your active toolkit?",
                    "context_hint": "Select all technologies you are comfortable working with.",
                    "suggested_options": [
                        "JavaScript & TypeScript",
                        "React.js & Next.js",
                        "Node.js & Express",
                        "MongoDB & Mongoose",
                        "Tailwind CSS",
                        "Python",
                        "Git & GitHub"
                    ],
                    "asked_at": now_iso,
                    "answer": None,
                },
                {
                    "id": "q_intern_avail",
                    "category": "logistics",
                    "type": "single_select",
                    "question": "What is your availability for full-time work or internship?",
                    "context_hint": "Confirming immediate internship timeline.",
                    "suggested_options": [
                        "Immediate full-time (Graduated)",
                        "Available for 6-month internship with PPO",
                        "Available immediately (Hybrid/Remote in NCR)",
                        "Part-time / Final semester"
                    ],
                    "asked_at": now_iso,
                    "answer": None,
                },
                {
                    "id": "q_intern_relocate",
                    "category": "logistics",
                    "type": "boolean",
                    "question": "Are you comfortable working from office in Noida / Gurugram?",
                    "context_hint": "On-site readiness confirmation.",
                    "suggested_options": ["Yes", "No"],
                    "asked_at": now_iso,
                    "answer": None,
                },
                {
                    "id": "q_intern_stipend",
                    "category": "compensation",
                    "type": "single_select",
                    "question": "What is your expected monthly internship stipend bracket?",
                    "context_hint": "Stipend expectation alignment.",
                    "suggested_options": [
                        "₹15,000 - ₹25,000 / month",
                        "₹25,000 - ₹35,000 / month",
                        "₹35,000+ / month"
                    ],
                    "asked_at": now_iso,
                    "answer": None,
                }
            ]
        else:
            return [
                {
                    "id": "q_dev_stack",
                    "category": "technical",
                    "type": "multiselect",
                    "question": "Which backend technologies, databases, and microservices tools have you used in production?",
                    "context_hint": "Select all technologies in your active toolkit.",
                    "suggested_options": [
                        "Node.js & Express / NestJS",
                        "Python (FastAPI / Django)",
                        "MongoDB & Redis",
                        "PostgreSQL / MySQL",
                        "Docker & Kubernetes",
                        "Kafka & Event queues",
                        "AWS / Cloud services"
                    ],
                    "asked_at": now_iso,
                    "answer": None,
                },
                {
                    "id": "q_dev_experience",
                    "category": "experience",
                    "type": "single_select",
                    "question": "How many total years of hands-on professional software development experience do you have?",
                    "context_hint": "Select your total experience bracket.",
                    "suggested_options": [
                        "1 - 2 Years",
                        "3 - 4 Years",
                        "5+ Years",
                        "7+ Years"
                    ],
                    "asked_at": now_iso,
                    "answer": None,
                },
                {
                    "id": "q_logistics_notice",
                    "category": "logistics",
                    "type": "single_select",
                    "question": "What is your official notice period?",
                    "context_hint": "Key logistics filter for active recruiter outreach.",
                    "suggested_options": [
                        "Immediate (Serving notice)",
                        "15 - 30 Days",
                        "60 Days",
                        "90 Days (Negotiable)"
                    ],
                    "asked_at": now_iso,
                    "answer": None,
                },
                {
                    "id": "q_dev_relocate",
                    "category": "logistics",
                    "type": "boolean",
                    "question": "Are you open to hybrid roles in Delhi NCR or Bengaluru?",
                    "context_hint": "Workplace flexibility check.",
                    "suggested_options": ["Yes", "No"],
                    "asked_at": now_iso,
                    "answer": None,
                },
                {
                    "id": "q_dev_ctc",
                    "category": "compensation",
                    "type": "single_select",
                    "question": "What is your expected annual CTC bracket?",
                    "context_hint": "Compensation expectation alignment.",
                    "suggested_options": [
                        "12 - 18 LPA",
                        "18 - 25 LPA",
                        "25 - 35 LPA",
                        "35+ LPA"
                    ],
                    "asked_at": now_iso,
                    "answer": None,
                }
            ]

