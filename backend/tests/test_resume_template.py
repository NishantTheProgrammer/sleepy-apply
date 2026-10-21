import os
import tempfile
from app.templates.default import DefaultATSResumeTemplate


def test_resume_pdf_generation():
    template = DefaultATSResumeTemplate()
    content = {
        "personal": {
            "full_name": "Alex Mercer",
            "email": "alex.mercer@example.com",
            "phone": "+1 (555) 019-2834",
            "location": "San Francisco, CA",
            "linkedin": "https://linkedin.com/in/alexmercer",
            "github": "https://github.com/alexmercer",
        },
        "summary": "Full Stack Engineer with 5+ years building distributed cloud systems and AI-powered workflows.",
        "skills": ["Python", "TypeScript", "React", "Next.js", "FastAPI", "Docker", "MongoDB", "LangGraph"],
        "experience": [
            {
                "title": "Senior Software Engineer",
                "company": "Tech Corp",
                "start_date": "2022",
                "is_current": True,
                "description": "Led backend architecture for real-time agent workflows.",
                "achievements": [
                    "Decreased pipeline latency by 45% using async concurrency.",
                    "Designed multi-tenant security vault with Fernet symmetric encryption.",
                ],
            }
        ],
        "education": [
            {
                "degree": "B.S.",
                "field": "Computer Science",
                "institution": "University of California, Berkeley",
                "graduation_year": "2021",
            }
        ],
        "projects": [
            {
                "name": "Sleepy Apply",
                "technologies": ["Python", "FastAPI", "LangGraph", "Next.js"],
                "description": "Autonomous job discovery and application platform.",
            }
        ],
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_file = os.path.join(tmpdir, "test_resume.pdf")
        out = template.render_pdf(content, pdf_file)
        assert os.path.exists(out)
        assert os.path.getsize(out) > 1000  # PDF has real bytes
