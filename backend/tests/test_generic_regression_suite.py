"""Phase 11: Generic Regression Suite for Version 8 Resume Tailoring Pipeline.

Tests diverse candidate personas, multi-domain JDs, and adversarial attacks
without any candidate-specific or employer-specific hardcodes.
"""

from __future__ import annotations

import pytest
from app.agents.profile_creator import ProfileCreatorAgent
from app.agents.evidence_mapper import EvidenceMapper
from app.agents.hallucination_guard import HallucinationGuard


# ==============================================================================
# 1. Frontend Engineer Persona & JD
# ==============================================================================
def test_frontend_persona_and_jd():
    raw_profile = {
        "personal": {"fullName": "Sarah Connor", "email": "sarah@cyberdyne.dev"},
        "summary": "Frontend Engineer with 4 years building reactive web applications in React, TypeScript, and Next.js.",
        "skills": {
            "frontend": ["React", "TypeScript", "Next.js", "Redux", "HTML", "CSS"],
            "tools": ["Git", "Jest"],
        },
        "experience": [
            {
                "company": "Cyberdyne UI Labs",
                "role": "Frontend Developer",
                "current": True,
                "responsibilities": [
                    "Engineered component library in React and TypeScript adopted by 12 internal products.",
                    "Improved core web vitals by 35% across high-traffic customer portals.",
                ],
            }
        ],
        "projects": [
            {
                "name": "CanvasDraw",
                "description": "Interactive HTML5 canvas application with real-time WebSocket syncing.",
                "technologies": ["React", "TypeScript"],
            }
        ],
        "achievements": [
            {"title": "Open source contributor to React Testing Library (5 PRs merged)"},
        ],
        "education": [
            {"degree": "Bachelor of Science in Computer Science", "institution": "MIT", "year": "2020"},
        ],
    }

    creator = ProfileCreatorAgent()
    norm = creator._normalize_extracted_data(raw_profile)

    jd = {
        "title": "Senior Frontend Engineer",
        "company": "Vercel Partner",
        "required_skills": ["React", "TypeScript", "GraphQL"],
        "description": """
        Requirements:
        - 3 to 5 years experience building complex web applications with React and TypeScript
        - In-depth knowledge of state management and GraphQL APIs
        - Bachelor's degree in Computer Science or related field

        Nice to have:
        - Experience with Next.js and Tailwind CSS
        """,
    }

    mapper = EvidenceMapper()
    ev_res = mapper.map_evidence(norm, jd)

    # Skills classification
    assert "React" in ev_res.skills_classification.matched_skills
    assert "TypeScript" in ev_res.skills_classification.matched_skills
    assert "GraphQL" in ev_res.skills_classification.missing_skills

    # Source attribution
    react_m = next(m for m in ev_res.mappings if m.requirement == "React")
    assert react_m.status == "MATCHED"
    assert "Cyberdyne" in react_m.source_entity

    # Degree match
    edu_m = next(m for m in ev_res.mappings if m.evidence_source == "education")
    assert edu_m.status == "MATCHED"


# ==============================================================================
# 2. Data / ML Engineer Persona & JD
# ==============================================================================
def test_data_ml_persona_and_jd():
    raw_profile = {
        "personal": {"fullName": "Alan Turing", "email": "alan@bletchley.ai"},
        "summary": "Machine Learning Engineer with 5 years designing predictive models and high-throughput data pipelines.",
        "skills": {
            "languages": ["Python", "SQL"],
            "backend": ["FastAPI", "Python"],
            "databases": ["PostgreSQL", "Redis"],
            "tools": ["Docker", "Git"],
        },
        "experience": [
            {
                "company": "Bletchley Analytics",
                "role": "Data Scientist",
                "current": True,
                "responsibilities": [
                    "Developed distributed feature store in Python and PostgreSQL processing 10M records daily.",
                    "Built real-time inference microservice with FastAPI achieving 15ms p99 latency.",
                ],
            }
        ],
        "education": [
            {"degree": "Master of Science in Artificial Intelligence", "institution": "Cambridge", "year": "2019"},
        ],
    }

    creator = ProfileCreatorAgent()
    norm = creator._normalize_extracted_data(raw_profile)

    jd = {
        "title": "Senior ML Platform Engineer",
        "company": "DeepMind Partner",
        "required_skills": ["Python", "Spark", "SQL"],
        "description": """
        Requirements:
        - Strong background in Python and distributed SQL databases
        - Experience with Apache Spark and streaming architectures
        - Master's degree in Computer Science or related field
        """,
    }

    mapper = EvidenceMapper()
    ev_res = mapper.map_evidence(norm, jd)

    assert "Python" in ev_res.skills_classification.matched_skills
    assert "SQL" in ev_res.skills_classification.matched_skills
    assert "Spark" in ev_res.skills_classification.missing_skills

    # Master's degree match
    edu_m = next(m for m in ev_res.mappings if m.evidence_source == "education")
    assert edu_m.status == "MATCHED"


# ==============================================================================
# 3. DevOps / Infrastructure Persona & JD
# ==============================================================================
def test_devops_persona_and_jd():
    raw_profile = {
        "personal": {"fullName": "Linus Torvalds", "email": "linus@kernel.org"},
        "summary": "Platform engineer specializing in Kubernetes clusters and container runtime orchestration.",
        "skills": {
            "tools": ["Docker", "Linux", "Git"],
            "languages": ["Python"],
        },
        "experience": [
            {
                "company": "Linux Foundation Labs",
                "role": "Infrastructure Architect",
                "current": True,
                "responsibilities": [
                    "Maintained automated multi-region deployments using Docker containers and Linux kernel modules.",
                ],
            }
        ],
    }

    creator = ProfileCreatorAgent()
    norm = creator._normalize_extracted_data(raw_profile)

    jd = {
        "title": "Site Reliability Engineer",
        "company": "Global Cloud",
        "required_skills": ["Docker", "Kubernetes", "Terraform"],
        "description": "Looking for SRE with deep Docker container knowledge and Terraform automation experience.",
    }

    mapper = EvidenceMapper()
    ev_res = mapper.map_evidence(norm, jd)

    assert "Docker" in ev_res.skills_classification.matched_skills
    assert "Terraform" in ev_res.skills_classification.missing_skills


# ==============================================================================
# 4. Junior Entry-Level Persona & JD
# ==============================================================================
def test_junior_persona_and_jd():
    raw_profile = {
        "personal": {"fullName": "Jane Doe", "email": "jane@gmail.com"},
        "summary": "Recent computer applications graduate passionate about backend development with Django.",
        "skills": {
            "languages": ["Python", "JavaScript"],
            "backend": ["Django"],
        },
        "experience": [],
        "projects": [
            {
                "name": "TaskTracker",
                "description": "Task management system built with Django REST framework and SQLite.",
                "technologies": ["Django", "Python"],
            }
        ],
        "education": [
            {"degree": "Bachelor of Computer Applications (BCA)", "institution": "State University", "year": "2024"},
        ],
    }

    creator = ProfileCreatorAgent()
    norm = creator._normalize_extracted_data(raw_profile)

    jd = {
        "title": "Junior Backend Developer",
        "company": "WebCorp",
        "required_skills": ["Django", "Python"],
        "description": "Entry-level developer to build APIs in Django.",
    }

    mapper = EvidenceMapper()
    ev_res = mapper.map_evidence(norm, jd)

    # Django is PARTIAL because it's from a personal project, not professional employment
    django_m = next(m for m in ev_res.mappings if m.requirement == "Django")
    assert django_m.status == "PARTIAL"
    assert django_m.evidence_source == "project"
    assert "TaskTracker" in django_m.source_entity


# ==============================================================================
# 5. Adversarial Injections Detected by HallucinationGuard
# ==============================================================================
def test_adversarial_injections_detected_by_guard():
    raw_profile = {
        "personal": {"fullName": "Alex Mercer", "email": "alex@blackwatch.gov"},
        "summary": "Full Stack Developer with 4 years building APIs in Node.js.",
        "skills": {"backend": ["Node.js", "Express"], "databases": ["MongoDB"]},
        "experience": [
            {
                "company": "Gentek Systems",
                "role": "Software Engineer",
                "current": True,
                "responsibilities": [
                    "Engineered RESTful microservices with Node.js and MongoDB serving 50,000 active users.",
                ],
            }
        ],
        "education": [
            {"degree": "Bachelor of Technology in IT", "institution": "State Tech", "year": "2020"},
        ],
    }

    creator = ProfileCreatorAgent()
    norm = creator._normalize_extracted_data(raw_profile)

    jd = {
        "title": "Staff Backend Engineer",
        "company": "Amazon",
        "required_skills": ["Node.js", "AWS", "DynamoDB"],
        "description": "Lead high-scale services using Node.js and AWS cloud infrastructure.",
    }

    mapper = EvidenceMapper()
    ev_res = mapper.map_evidence(norm, jd)
    guard = HallucinationGuard()

    # Adversarial Injection 1: Fabricated employer (Google LLC)
    h_resume_co = {
        "target_headline": "Staff Backend Engineer | Node.js & MongoDB",
        "tailored_summary": "Experienced engineer with 4 years building APIs.",
        "experience": [
            {
                "company": "Google LLC",
                "responsibilities": ["Led search backend optimizations."],
            }
        ],
    }
    res_co = guard.validate(h_resume_co, norm, ev_res)
    assert not res_co.is_valid
    assert any(v.category == "role_fabrication" for v in res_co.critical_violations)

    # Adversarial Injection 2: Invented corporate revenue ($50M ARR)
    h_resume_fin = {
        "target_headline": "Staff Backend Engineer | Node.js & MongoDB",
        "tailored_summary": "Experienced engineer.",
        "experience": [
            {
                "company": "Gentek Systems",
                "responsibilities": [
                    "Generated $50M in new corporate ARR by redesigning cloud microservices.",
                ],
            }
        ],
    }
    res_fin = guard.validate(h_resume_fin, norm, ev_res)
    assert not res_fin.is_valid
    assert any(v.category == "invented_metric" for v in res_fin.critical_violations)

    # Adversarial Injection 3: Claiming unverified missing skill in headline
    h_resume_tech = {
        "target_headline": "Staff Backend Engineer | Node.js, AWS & DynamoDB",
        "tailored_summary": "Experienced engineer.",
        "experience": [
            {
                "company": "Gentek Systems",
                "responsibilities": [
                    "Engineered RESTful microservices with Node.js.",
                ],
            }
        ],
    }
    res_tech = guard.validate(h_resume_tech, norm, ev_res)
    assert not res_tech.is_valid
    assert any(v.category == "unsupported_technology" for v in res_tech.critical_violations)

    # Adversarial Injection 4: Fabricated degree (PhD from MIT)
    h_resume_edu = {
        "target_headline": "Staff Backend Engineer | Node.js & MongoDB",
        "tailored_summary": "Experienced engineer.",
        "education": [
            {"degree": "PhD in Quantum Computing", "institution": "MIT", "year": "2024"},
        ],
        "experience": [
            {
                "company": "Gentek Systems",
                "responsibilities": ["Engineered RESTful microservices with Node.js."],
            }
        ],
    }
    res_edu = guard.validate(h_resume_edu, norm, ev_res)
    assert not res_edu.is_valid
    assert any(v.category in ["role_fabrication", "degree_inflation"] for v in res_edu.critical_violations)
