import asyncio
import os
import io
from app.agents.evidence_mapper import EvidenceMapper, JDAnalysisReport, ATSScoringBreakdown
from app.agents.resume_builder import ResumeBuilderAgent, select_and_tailor_projects
from app.templates.default import DefaultATSResumeTemplate

def test_jd_analysis_and_classification():
    em = EvidenceMapper()
    title = "Senior Generative AI Engineer (Agentic Workflows)"
    skills = ["Python", "LangChain", "LangGraph", "ChromaDB", "Kubernetes", "AWS"]
    desc = """
    We are looking for a Senior Generative AI Engineer with 4+ years of experience.
    Core Qualifications (Must Have):
    - Python programming, LangGraph or LangChain multi-agent architectures
    - RAG retrieval-augmented generation and vector databases (e.g. ChromaDB)
    - Strong understanding of REST APIs and Microservices

    Nice to have / Preferred:
    - Experience with Ollama, Docker, and CI/CD pipelines
    - Kubernetes and AWS deployment
    - Knowledge of Microsoft Copilot Studio
    """
    reqs, report = em.analyze_jd(title, skills, desc)

    assert report.has_genai_or_agentic is True
    assert "Python" in report.languages
    assert any("LangGraph" in s or "LangChain" in s for s in report.ai_ml)
    assert any("ChromaDB" in s or "RAG" in s for s in report.ai_ml)
    assert "Kubernetes" in report.cloud_devops or "AWS" in report.cloud_devops
    assert len(report.mandatory_technical_skills) > 0
    print("✓ test_jd_analysis_and_classification PASSED")


def test_evidence_matching_and_anti_hallucination():
    em = EvidenceMapper()
    candidate_profile = {
        "personal": {"full_name": "Nishant"},
        "summary": "Full Stack Engineer with 6 years experience in Node.js, Python, and PostgreSQL.",
        "skills": {
            "languages": ["JavaScript", "TypeScript", "Python"],
            "backend": ["Node.js", "Express", "FastAPI"],
            "databases": ["PostgreSQL", "MongoDB"],
            "ai_ml": ["Generative AI", "Agentic AI", "RAG", "LangGraph"]
        },
        "experience": [
            {
                "company": "To The New",
                "title": "Lead Consultant",
                "startDate": "2025-12",
                "current": True,
                "responsibilities": [
                    "Architected scalable backend microservices with Python, Node.js, and FastAPI",
                    "Mentored junior engineers and conducted technical interviews"
                ]
            }
        ],
        "projects": [
            {
                "name": "Sleepy Apply Agent",
                "description": "Autonomous job search agent powered by LangGraph and Ollama",
                "technologies": ["LangGraph", "Ollama"]
            }
        ],
        "education": [{"degree": "Master of Computer Applications (MCA)", "institution": "IGNOU"}]
    }

    job = {
        "title": "AI Agent Developer",
        "company": "Cognitive AI",
        "required_skills": ["Python", "LangGraph", "RAG", "Microsoft Copilot Studio", "Kubernetes"],
        "description": "Requires hands-on experience in LangGraph, RAG, Python, and Microsoft Copilot Studio with Kubernetes."
    }

    result = em.map_evidence(candidate_profile, job)

    # 1. Python is in professional employment -> MATCHED (Source: professional_experience)
    python_item = next((m for m in result.mappings if m.requirement == "Python"), None)
    assert python_item is not None
    assert python_item.status == "MATCHED"
    assert python_item.evidence_source == "professional_experience"

    # 2. LangGraph is in projects -> PARTIAL (Source: project)
    lg_item = next((m for m in result.mappings if m.requirement == "LangGraph"), None)
    assert lg_item is not None
    assert lg_item.status == "PARTIAL"
    assert lg_item.evidence_source == "project"

    # 3. RAG is in self-reported skills -> UNVERIFIED (Source: self_reported)
    rag_item = next((m for m in result.mappings if m.requirement == "RAG"), None)
    assert rag_item is not None
    assert rag_item.status == "UNVERIFIED"
    assert rag_item.evidence_source == "self_reported"

    # 4. Microsoft Copilot Studio & Kubernetes MUST be MISSING (Zero Hallucination)
    copilot_item = next((m for m in result.mappings if "Copilot Studio" in m.requirement), None)
    assert copilot_item is not None
    assert copilot_item.status == "MISSING"

    k8s_item = next((m for m in result.mappings if "Kubernetes" in m.requirement), None)
    assert k8s_item is not None
    assert k8s_item.status == "MISSING"

    print("✓ test_evidence_matching_and_anti_hallucination PASSED")


def test_explainable_7_dimension_ats_scoring():
    em = EvidenceMapper()
    candidate_profile = {
        "personal": {"full_name": "Nishant"},
        "summary": "Full Stack Engineer with 6 years experience in Node.js and PostgreSQL.",
        "skills": {
            "languages": ["Python", "JavaScript"],
            "backend": ["Node.js", "FastAPI"],
            "ai_ml": ["LangGraph", "RAG"]
        },
        "experience": [
            {
                "company": "Dhwani Rural Information Systems",
                "title": "Module Lead",
                "startDate": "2023-01",
                "endDate": "2025-12",
                "responsibilities": ["Built REST APIs in Node.js", "Mentored team of 4 engineers"]
            }
        ],
        "projects": [
            {
                "name": "AI Agent Platform",
                "description": "Multi-agent LangGraph platform",
                "technologies": ["LangGraph", "Python"]
            }
        ],
        "education": [{"degree": "MCA", "institution": "IGNOU"}]
    }

    job = {
        "title": "Senior Backend & GenAI Engineer",
        "company": "TechCorp",
        "required_skills": ["Node.js", "Python", "REST APIs", "AWS", "Kubernetes"],
        "description": "Requires Node.js, Python, REST APIs. Nice to have: AWS, Kubernetes."
    }

    result = em.map_evidence(candidate_profile, job)
    score = result.ats_score

    assert 0.0 <= score.overall_score <= 100.0
    dims = score.dimensions
    assert "mandatory_technical_skills" in dims
    assert "preferred_technical_skills" in dims
    assert "relevant_professional_experience" in dims
    assert "responsibilities_and_projects" in dims
    assert "domain_and_role_keywords" in dims
    assert "education_and_certifications" in dims
    assert "ats_formatting_and_readability" in dims

    # Verify dimension weights sum to 1.0 (100%)
    total_weights = sum(d.weight for d in dims.values())
    assert abs(total_weights - 1.0) < 0.001

    assert score.mandatory_skill_coverage_pct > 0
    assert len(score.missing_requirements) > 0
    assert len(score.recommendations) > 0

    print(f"✓ test_explainable_7_dimension_ats_scoring PASSED (Overall: {score.overall_score}/100)")


def test_pdf_rendering_and_text_integrity(tmp_path):
    renderer = DefaultATSResumeTemplate()
    output_pdf = os.path.join(str(tmp_path), "test_ats_resume.pdf")

    sample_resume_content = {
        "personal": {
            "full_name": "Nishant",
            "email": "knishant113@gmail.com",
            "phone": "+91 9876543210",
            "location": "Delhi NCR, India",
            "linkedin": "linkedin.com/in/knishant",
            "github": "github.com/knishant"
        },
        "target_headline": "Senior Full Stack & GenAI Engineer | Node.js, Python, LangGraph",
        "summary": "Full Stack & Generative AI Engineer with 6 years experience building high-scale distributed backend systems and agentic workflows.",
        "skills": {
            "languages": ["Python", "JavaScript", "TypeScript", "SQL"],
            "backend": ["Node.js", "Express", "FastAPI", "REST APIs", "Microservices"],
            "ai_ml": ["Generative AI", "Agentic AI", "LangGraph", "RAG", "Ollama", "ChromaDB"],
            "databases": ["PostgreSQL", "MongoDB", "Redis"]
        },
        "experience": [
            {
                "title": "Lead Consultant",
                "company": "To The New",
                "startDate": "Dec 2025",
                "endDate": "Present",
                "is_current": True,
                "responsibilities": [
                    "Engineered distributed backend microservices utilizing Node.js and FastAPI.",
                    "Mentored junior engineers and conducted technical interviews."
                ]
            }
        ],
        "projects": [
            {
                "name": "Sleepy Apply AI Agent",
                "technologies": ["LangGraph", "Ollama", "Python"],
                "description": "Engineered autonomous job matching and resume generation engine with strict hallucination guardrails."
            }
        ],
        "education": [
            {
                "degree": "Master of Computer Applications (MCA)",
                "institution": "IGNOU",
                "year": "2023"
            }
        ],
        "achievements": ["Solved 450+ LeetCode problems", "Built scalable civic governance platform"]
    }

    path = renderer.render_pdf(sample_resume_content, output_pdf)
    assert os.path.exists(path)
    assert os.path.getsize(path) > 1000

    with open(path, "rb") as f:
        header = f.read(5)
        assert header == b"%PDF-"

    print(f"✓ test_pdf_rendering_and_text_integrity PASSED (PDF size: {os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    test_jd_analysis_and_classification()
    test_evidence_matching_and_anti_hallucination()
    test_explainable_7_dimension_ats_scoring()
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        test_pdf_rendering_and_text_integrity(td)
    print("\nALL ATS RESUME ENGINE TESTS PASSED!")
