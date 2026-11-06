"""Comprehensive regression test suite for evidence-driven resume tailoring.

Covers:
1. Technology-specific experience accuracy (no converting 5 yrs fullstack to 5 yrs Java).
2. Project versus professional experience (StaffSync is project, Dhwani is professional).
3. Missing and unverified skills (CI/CD, Jenkins, Maven, TDD flagged as MISSING).
4. Unsupported claims & Hallucination Guard sanitization.
5. Original profile immutability across tailoring operations.
6. Achievement preservation (HackerRank, LeetCode, metrics like 4000+ urban local bodies).
7. Multiple JD tailoring operations independence (tailoring for JD 1 does not affect JD 2).
8. JSON schema validation (TailoredResumeSchema).
9. PDF & DOCX generation compatibility.
10. Candidate verification question generation for missing requirements.
"""

import copy
import os
import pytest
from bson import ObjectId

from app.agents.evidence_mapper import EvidenceMapper
from app.agents.hallucination_guard import HallucinationGuard
from app.agents.resume_builder import ResumeBuilderAgent, select_and_tailor_projects
from app.agents.screening_agent import ScreeningQAAgent
from app.models.profile import TailoredResumeSchema
from app.templates.default import DefaultATSResumeTemplate
from app.templates.manager import render_docx_for_profile


@pytest.fixture
def candidate_profile():
    return {
        "_id": ObjectId("671b5fa8618e9f291071da50"),
        "user_id": ObjectId("67167725dc397cff17e92823"),
        "personal": {
            "fullName": "Nishant",
            "full_name": "Nishant",
            "email": "knishant113@gmail.com",
            "phone": "+91 7838716089",
            "location": {"city": "Delhi", "country": "India"},
            "linkedin": "https://www.linkedin.com/in/nishanttheprogrammer",
            "github": "https://github.com/NishantTheProgrammer",
            "portfolio": "https://nishanttheprogrammer.com",
        },
        "summary": (
            "Full Stack Developer with 5 years of experience delivering 10+ scalable applications across "
            "diverse domains. Possessing advanced technical knowledge and expertise in both front-end and "
            "back-end technologies. Demonstrated proficiency in problem-solving with a HackerRank 6th "
            "Star Gold Badge and a track record of solving 450+ LeetCode questions."
        ),
        "skills": {
            "backend": ["Node.js", "Express", "Spring Boot", "Hibernate", "Java", "Django"],
            "frontend": ["React", "Angular", "Vue", "Next.js", "JavaScript", "TypeScript"],
            "databases": ["MongoDB", "PostgreSQL", "MySQL", "Redis", "SQL"],
            "tools": ["Docker", "Git", "Linux", "Jest"],
            "architecture": ["Microservices", "System Design", "REST APIs"],
        },
        "experience": [
            {
                "company": "Dhwani Rural Information Systems",
                "jobTitle": "SDE-2 Full Stack",
                "title": "SDE-2 Full Stack",
                "startDate": "Jan 2023",
                "start_date": "Jan 2023",
                "endDate": "Present",
                "end_date": "Present",
                "current": True,
                "is_current": True,
                "description": "Technology-driven social impact venture that enables development sector organizations.",
                "responsibilities": [
                    "Conducting interviews, mentored junior developers, developing REST APIs, integrating third-party services.",
                    "Designed and developed a comprehensive full-stack NGO management platform using Node.js/Express and modern Angular frontend.",
                    "Enhanced platform performance through query optimization, materialized views, and session synchronization across multiple tabs.",
                    "Implemented bulk upload service handling data for 4000+ urban local bodies and their finance.",
                ],
            },
            {
                "company": "Max Vision Solutions Pvt. Ltd.",
                "jobTitle": "Mobile Application Developer",
                "title": "Mobile Application Developer",
                "startDate": "Mar 2021",
                "start_date": "Mar 2021",
                "endDate": "Dec 2022",
                "end_date": "Dec 2022",
                "current": False,
                "is_current": False,
                "description": "Web Development company devoted to delivering services with the Global market.",
                "responsibilities": [
                    "Developed video call coaching platform using Flutter with integrated Stripe payment gateway and Twilio APIs.",
                    "Built multi-vendor restaurant web application (pay.mesa-qr.com) with Stripe split payment and QR code generation.",
                    "Contributed to e-commerce applications Kichi-Mall and In1Mall using WordPress, WooCommerce REST API, Ionic, and Angular.",
                ],
            },
        ],
        "projects": [
            {
                "name": "StaffSync",
                "title": "StaffSync",
                "description": "Role-based workforce management system designed to streamline company operations. Built on Spring Boot.",
                "technologies": ["Spring Boot", "Java"],
            },
            {
                "name": "SkillsAkhada",
                "title": "SkillsAkhada",
                "description": "A gaming tournament platform using Flutter, React, and Node.js for APIs.",
                "technologies": ["Flutter", "React", "Node.js"],
            },
            {
                "name": "City Bus Management System",
                "title": "City Bus Management System",
                "description": "Contributed to a college project involving Django REST APIs and Vue.js.",
                "technologies": ["Django", "Vue.js"],
            },
            {
                "name": "DoneMySite",
                "title": "DoneMySite",
                "description": "Building a freelancing platform utilizing React JS and Django REST APIs, integrating Stripe.",
                "technologies": ["React", "Django", "Stripe"],
            },
            {
                "name": "Shoe Shop",
                "title": "Shoe Shop",
                "description": "Developed a mid-level E-Commerce web application in Next.js for an Israeli client.",
                "technologies": ["Next.js"],
            },
        ],
        "education": [
            {"degree": "Masters in computer applications (MCA)", "institution": "IGNOU", "year": "2023"},
            {"degree": "Bachelors in computer application (BCA)", "institution": "IGNOU", "year": "2020"},
        ],
        "achievements": [
            {"title": "HackerRank 6th Star Gold Badge (Problem Solving)"},
            {"title": "Solved 450+ LeetCode problems demonstrating strong data structures & algorithms proficiency"},
        ],
    }


@pytest.fixture
def pocketpills_jd():
    return {
        "_id": ObjectId("6ae471313c8722ed067d8d99"),
        "title": "Senior Backend Engineer",
        "company": "Pocketpills",
        "required_skills": ["Java", "CI/CD"],
        "description": """
        We’re seeking a Senior Backend Engineer to join our Product team.
        Desirables:
        - B.Tech/ BE Computer Science, Engineering, or related field
        - 06 to 08 years of programming in Core Java and with the spring framework
        - Good knowledge of object-oriented design, data structures, algorithms, and SQL.
        - Experience working with hibernate, Jenkins, maven and CI/CD pipelines
        - Well-versed with Test driven development
        - Strong hold on system design and architecture
        - Experience building operationally critical services, especially in eCommerce.
        - Responsible for mentoring team of 4-6 Junior engineers
        """,
    }


@pytest.fixture
def alternative_jd():
    return {
        "_id": ObjectId("6ae471313c8722ed067d8d98"),
        "title": "Full Stack Tech Lead",
        "company": "Meesho",
        "required_skills": ["Node.js", "React", "MongoDB"],
        "description": "Lead full stack web applications with Node.js, React, and MongoDB architecture.",
    }


# ==============================================================================
# 1. Technology-Specific Experience Accuracy & Evidence Mapping
# ==============================================================================

def test_evidence_mapper_pocketpills(candidate_profile, pocketpills_jd):
    mapper = EvidenceMapper()
    result = mapper.map_evidence(candidate_profile, pocketpills_jd)

    skills_cls = result.skills_classification
    # SQL, REST APIs, System Design, E-commerce, Mentoring should be MATCHED or PARTIAL
    assert "SQL" in skills_cls.matched_skills
    assert "Java" in skills_cls.partially_matched_skills or "Spring Boot" in skills_cls.partially_matched_skills

    # CI/CD, Jenkins, Maven, TDD MUST be classified as MISSING
    assert "CI/CD" in skills_cls.missing_skills
    assert "Jenkins" in skills_cls.missing_skills
    assert "Maven" in skills_cls.missing_skills
    assert "TDD" in skills_cls.missing_skills

    # Check evidence source distinction
    staffsync_mapping = next((m for m in result.mappings if m.requirement in ["Spring Boot", "Spring", "Java"]), None)
    assert staffsync_mapping is not None
    assert staffsync_mapping.status == "PARTIAL"
    assert staffsync_mapping.evidence_source == "project"
    assert "StaffSync" in staffsync_mapping.source_entity

    # Education mapping should flag MCA/BCA vs B.Tech/BE
    edu_mapping = next((m for m in result.mappings if "b.tech" in m.requirement.lower() or "education" in m.requirement.lower()), None)
    if edu_mapping:
        assert edu_mapping.status == "PARTIAL"
        assert "MCA" in edu_mapping.evidence_text or "BCA" in edu_mapping.evidence_text


# ==============================================================================
# 2. Project versus Professional Experience Distinction
# ==============================================================================

def test_project_vs_professional_distinction(candidate_profile, pocketpills_jd):
    mapper = EvidenceMapper()
    result = mapper.map_evidence(candidate_profile, pocketpills_jd)
    cand_index = result.candidate_index

    # Dhwani is professional employment
    dhwani_role = next((r for r in cand_index.professional_roles if "Dhwani" in r["company"]), None)
    assert dhwani_role is not None
    assert "Node.js" in dhwani_role["technologies"]
    assert "PostgreSQL" in dhwani_role["technologies"] or "SQL" in dhwani_role["raw_text"]

    # StaffSync is project-level, NEVER professional employer
    staffsync_proj = next((p for p in cand_index.projects if p["name"] == "StaffSync"), None)
    assert staffsync_proj is not None
    assert "Spring Boot" in staffsync_proj["technologies"]
    assert not any(r["company"] == "StaffSync" for r in cand_index.professional_roles)


# ==============================================================================
# 3. Missing and Unverified Skills & Unsupported Claims
# ==============================================================================

def test_hallucination_guard_catches_unsupported_tech(candidate_profile, pocketpills_jd):
    mapper = EvidenceMapper()
    evidence_res = mapper.map_evidence(candidate_profile, pocketpills_jd)

    guard = HallucinationGuard()

    # Create a resume claiming CI/CD and 6-8 years Java
    hallucinated_resume = {
        "target_headline": "Senior Backend Engineer | Java, SQL, Spring Boot & CI/CD",
        "tailored_summary": "Seasoned Backend Engineer with 6-8 years Core Java and Spring Boot experience. Built CI/CD pipelines with Jenkins and Maven.",
        "experience": [
            {
                "company": "Dhwani Rural Information Systems",
                "responsibilities": [
                    "Implemented CI/CD deployment pipelines using Jenkins and Maven.",
                    "Responsible for mentoring team of 4-6 Junior engineers in TDD.",
                ],
            }
        ],
        "education": [
            {"degree": "B.Tech in Computer Science", "institution": "IGNOU", "year": "2023"}
        ],
    }

    val_raw = guard.validate(hallucinated_resume, candidate_profile, evidence_res)
    assert not val_raw.is_valid
    assert len(val_raw.critical_violations) >= 3

    # Check detected categories
    categories = [v.category for v in val_raw.critical_violations]
    assert "unsupported_technology" in categories  # CI/CD, Jenkins
    assert "experience_inflation" in categories     # 6-8 years Java
    assert "invented_metric" in categories          # team of 4-6 junior engineers

    # Check sanitization fixes
    val_res = guard.validate_and_sanitize(hallucinated_resume, candidate_profile, evidence_res)
    sanitized = val_res.sanitized_content
    assert "CI/CD" not in sanitized["target_headline"]
    assert "Jenkins" not in sanitized["tailored_summary"]
    assert "team of 4-6" not in sanitized["experience"][0]["responsibilities"][1]


# ==============================================================================
# 4. Never Claim 5 Years of Java Experience
# ==============================================================================

def test_summary_and_headline_factual_grounding(candidate_profile, pocketpills_jd):
    mapper = EvidenceMapper()
    evidence_res = mapper.map_evidence(candidate_profile, pocketpills_jd)
    guard = HallucinationGuard()

    # Candidate has 5 years overall experience, but Spring Boot was in project StaffSync
    resume_with_java_claim = {
        "target_headline": "Senior Backend Engineer | Java & Spring Boot",
        "tailored_summary": "Full Stack Developer with 5+ years of Java, Spring Boot, and backend systems.",
        "experience": candidate_profile["experience"],
        "education": candidate_profile["education"],
    }

    val_raw = guard.validate(resume_with_java_claim, candidate_profile, evidence_res)
    # Guard must flag the 5+ years of Java claim as experience inflation
    inflation_violation = next((v for v in val_raw.critical_violations if v.category == "experience_inflation"), None)
    assert inflation_violation is not None
    assert "Spring Boot/Java is project experience" in inflation_violation.allowed_boundary

    # Sanitized summary must cleanly clarify hands-on project experience
    val_res = guard.validate_and_sanitize(resume_with_java_claim, candidate_profile, evidence_res)
    assert val_res.sanitized
    sanitized_sum = val_res.sanitized_content["summary"]
    assert "hands-on project experience in Spring Boot" in sanitized_sum


# ==============================================================================
# 5. Original Profile Immutability
# ==============================================================================

@pytest.mark.anyio
async def test_original_profile_immutability(candidate_profile, pocketpills_jd):
    profile_before = copy.deepcopy(candidate_profile)

    builder = ResumeBuilderAgent()
    # Test project selection & tailoring without mutating original
    tailored_projects = select_and_tailor_projects(
        raw_projects=candidate_profile["projects"],
        required_skills=pocketpills_jd["required_skills"],
        matching_skills=["Java", "Spring Boot", "SQL"],
        job_title=pocketpills_jd["title"],
        company=pocketpills_jd["company"],
    )

    assert len(tailored_projects) > 0
    # Original profile must be completely identical
    assert candidate_profile == profile_before
    assert candidate_profile["experience"][0]["company"] == "Dhwani Rural Information Systems"
    assert candidate_profile["education"][0]["degree"] == "Masters in computer applications (MCA)"


# ==============================================================================
# 6. Achievement & Metric Preservation
# ==============================================================================

def test_achievement_and_metric_preservation(candidate_profile, pocketpills_jd):
    # Verify candidate metrics are not dropped
    dhwani_resps = candidate_profile["experience"][0]["responsibilities"]
    assert any("4000+ urban local bodies" in r for r in dhwani_resps)

    achievements = candidate_profile["achievements"]
    assert any("HackerRank 6th Star Gold Badge" in a["title"] for a in achievements)
    assert any("450+ LeetCode" in a["title"] for a in achievements)

    # In tailored project selection for Pocketpills, StaffSync (Spring Boot) should be selected #1
    projects = select_and_tailor_projects(
        raw_projects=candidate_profile["projects"],
        required_skills=pocketpills_jd["required_skills"],
        matching_skills=["Java", "Spring Boot", "SQL"],
        job_title="Senior Backend Engineer",
        company="Pocketpills",
    )
    assert any(p["name"] == "StaffSync" for p in projects)


# ==============================================================================
# 7. Multiple JD Tailoring Operations Independence
# ==============================================================================

def test_multiple_jd_independence(candidate_profile, pocketpills_jd, alternative_jd):
    mapper = EvidenceMapper()

    # Map for Pocketpills (Java Backend)
    res_pocketpills = mapper.map_evidence(candidate_profile, pocketpills_jd)

    # Map for Meesho (Node.js/React Full Stack)
    res_meesho = mapper.map_evidence(candidate_profile, alternative_jd)

    # Pocketpills matched vs Meesho matched
    assert "SQL" in res_pocketpills.skills_classification.matched_skills
    assert "Node.js" in res_meesho.skills_classification.matched_skills
    assert "React" in res_meesho.skills_classification.partially_matched_skills
    assert "MongoDB" in res_meesho.skills_classification.unverified_skills

    # CI/CD is missing for Pocketpills, but not required for Meesho
    assert "CI/CD" in res_pocketpills.skills_classification.missing_skills
    assert "CI/CD" not in res_meesho.skills_classification.missing_skills

    # Neither operation polluted candidate profile
    assert candidate_profile["personal"]["full_name"] == "Nishant"


# ==============================================================================
# 8. Structured JSON Schema Validation
# ==============================================================================

def test_json_schema_validation(candidate_profile, pocketpills_jd):
    content = {
        "job_id": str(pocketpills_jd["_id"]),
        "job_title": pocketpills_jd["title"],
        "company": pocketpills_jd["company"],
        "target_headline": "Senior Backend Engineer | Node.js, SQL & REST APIs",
        "summary": "Full Stack Developer with 5 years overall experience...",
        "tailored_summary": "Full Stack Developer with 5 years overall experience...",
        "matching_skills": ["SQL", "REST APIs"],
        "missing_skills": ["CI/CD", "Jenkins", "Maven", "TDD"],
        "skills_breakdown": {
            "matched_skills": ["SQL"],
            "partially_matched_skills": ["Spring Boot"],
            "missing_skills": ["CI/CD", "Jenkins", "Maven", "TDD"],
            "unverified_skills": [],
            "additional_relevant_skills": ["Node.js", "Express", "PostgreSQL"],
        },
        "evidence_mappings": [],
        "personal": candidate_profile["personal"],
        "skills": candidate_profile["skills"],
        "experience": candidate_profile["experience"],
        "education": candidate_profile["education"],
        "projects": candidate_profile["projects"][:3],
        "achievements": candidate_profile["achievements"],
        "template": "default",
        "generated_at": "2026-11-06T12:00:00Z",
    }

    # Validate against Pydantic schema
    validated = TailoredResumeSchema(**content)
    assert validated.job_id == str(pocketpills_jd["_id"])
    assert validated.target_headline == "Senior Backend Engineer | Node.js, SQL & REST APIs"
    assert "SQL" in validated.skills_breakdown["matched_skills"]


# ==============================================================================
# 9. PDF and DOCX Generation Compatibility
# ==============================================================================

def test_pdf_and_docx_rendering(candidate_profile, pocketpills_jd, tmp_path):
    pdf_out = str(tmp_path / "test_resume.pdf")

    resume_content = {
        "job_id": str(pocketpills_jd["_id"]),
        "job_title": pocketpills_jd["title"],
        "company": pocketpills_jd["company"],
        "target_headline": "Senior Backend Engineer | Node.js, SQL & REST APIs",
        "summary": "Full Stack Developer with 5 years overall experience delivering scalable REST APIs and database optimizations.",
        "personal": candidate_profile["personal"],
        "skills": candidate_profile["skills"],
        "experience": candidate_profile["experience"],
        "education": candidate_profile["education"],
        "projects": candidate_profile["projects"][:3],
        "achievements": candidate_profile["achievements"],
    }

    # Test PDF generation
    template = DefaultATSResumeTemplate()
    res_pdf = template.render_pdf(resume_content, pdf_out)
    assert os.path.exists(res_pdf)
    assert os.path.getsize(res_pdf) > 1000  # Generated valid PDF bytes

    # Test DOCX generation
    docx_stream = render_docx_for_profile("default", resume_content)
    assert docx_stream is not None
    assert docx_stream.getbuffer().nbytes > 1000


# ==============================================================================
# 10. Candidate Verification Questions
# ==============================================================================

def test_candidate_verification_questions(candidate_profile, pocketpills_jd):
    mapper = EvidenceMapper()
    evidence_res = mapper.map_evidence(candidate_profile, pocketpills_jd)
    missing_skills = evidence_res.skills_classification.missing_skills

    agent = ScreeningQAAgent()
    questions = agent.generate_gap_verification_questions(candidate_profile, missing_skills)

    assert len(questions) > 0
    # Should ask about missing technical skills like CI/CD, Jenkins, Maven
    q_fields = [q["field"] for q in questions]
    assert any(f in ["CI/CD", "Jenkins", "Maven", "TDD"] for f in q_fields)
    assert all("question" in q and "suggested_options" in q for q in questions)


# ==============================================================================
# 11. Targeted Fixes Verification (Pocketpills Audit)
# ==============================================================================

def test_evidence_mapping_mentoring_and_sql_precision(candidate_profile, pocketpills_jd):
    """Mentoring must be MATCHED from Dhwani; SQL evidence must use database facts not company mission."""
    mapper = EvidenceMapper()
    res = mapper.map_evidence(candidate_profile, pocketpills_jd)

    # 1. Mentoring requirement must be MATCHED
    mentor_m = next((m for m in res.mappings if "mentor" in m.requirement.lower()), None)
    assert mentor_m is not None
    assert mentor_m.status == "MATCHED"
    assert mentor_m.confidence == 1.0
    assert "mentored junior developers" in mentor_m.evidence_text.lower()
    assert "Dhwani" in mentor_m.source_entity

    # 2. SQL requirement evidence must use real DB bullets, not company descriptions
    sql_m = next((m for m in res.mappings if m.requirement == "SQL" or "sql" in m.requirement.lower()), None)
    assert sql_m is not None
    assert sql_m.status == "MATCHED"
    assert "Technology-driven social impact venture" not in sql_m.evidence_text
    assert any(db_kw in sql_m.evidence_text for db_kw in ["query optimization", "materialized views", "PostgreSQL", "MySQL", "SQL"])


def test_hallucination_guard_semantic_and_bleed_checks(candidate_profile, pocketpills_jd):
    """Validator catches contradictory mappings, cross-employer bleed, and unsupported specialization."""
    mapper = EvidenceMapper()
    evidence_res = mapper.map_evidence(candidate_profile, pocketpills_jd)
    guard = HallucinationGuard()

    # Contradictory mapping: CI/CD is MISSING but candidate claims it in matching_skills
    # Cross-employer bleed: pay.mesa-qr.com placed under Dhwani
    # Unsupported specialization: claiming "specializing in Java"
    faulty_resume = {
        "matching_skills": ["SQL", "CI/CD"],
        "target_headline": "Senior Backend Engineer | Java & SQL",
        "tailored_summary": "Seasoned Backend Engineer specializing in Java and Spring Boot architecture.",
        "experience": [
            {
                "company": "Dhwani Rural Information Systems",
                "responsibilities": [
                    "Enhanced platform performance through query optimization.",
                    "Built multi-vendor restaurant web application (pay.mesa-qr.com) with Stripe split payment.",
                ],
            },
            {
                "company": "Max Vision Solutions Pvt. Ltd.",
                "responsibilities": [
                    "Implemented bulk upload service handling data for 4000+ urban local bodies.",
                ],
            },
        ],
        "education": candidate_profile["education"],
    }

    # 1. Semantic validation catches all issues on raw faulty resume
    val_raw = guard.validate(faulty_resume, candidate_profile, evidence_res)
    assert not val_raw.is_valid
    categories = [v.category for v in val_raw.critical_violations]

    # Verify all semantic checks fired
    assert "contradictory_evidence_mapping" in categories
    assert "cross_employer_bleed" in categories
    assert "unsupported_specialization" in categories

    # 2. Verify auto-sanitization cleaned the output
    val_res = guard.validate_and_sanitize(faulty_resume, candidate_profile, evidence_res)
    sanitized = val_res.sanitized_content
    assert "CI/CD" not in sanitized["matching_skills"]
    assert "specializing in Java" not in sanitized["summary"]


def test_information_preservation_and_reordering(candidate_profile, pocketpills_jd):
    """Restore critical original details (materialized views, 4000+ ULBs, Stripe split payment) and sort by relevance."""
    from app.agents.resume_builder import preserve_and_prioritize_experience_bullets

    # Dhwani test: AI generated 1 bullet dropping materialized views and City Finance
    ai_dhwani_bullets = [
        "Enhanced platform performance through query optimization and session synchronization across multiple tabs."
    ]
    dhwani_orig = candidate_profile["experience"][0]["responsibilities"]

    preserved_dhwani = preserve_and_prioritize_experience_bullets(
        company_name="Dhwani Rural Information Systems",
        original_bullets=dhwani_orig,
        ai_bullets=ai_dhwani_bullets,
        matching_skills=["Node.js", "Express", "SQL", "REST APIs"],
        missing_skills=["CI/CD", "Jenkins"],
        job_title=pocketpills_jd["title"],
        company=pocketpills_jd["company"],
        job_description=pocketpills_jd["description"],
    )

    # Must have restored materialized views into query optimization bullet
    assert any("materialized views" in b for b in preserved_dhwani)
    # Must have restored City Finance with 4000+ urban local bodies
    assert any("4000+ urban local bodies" in b for b in preserved_dhwani)

    # Max Vision test: Pocketpills asks for eCommerce and critical services.
    # pay.mesa-qr.com (Stripe split payment) and Kichi-Mall (WooCommerce Rest API) must rank high
    max_vision_orig = candidate_profile["experience"][1]["responsibilities"]
    preserved_max = preserve_and_prioritize_experience_bullets(
        company_name="Max Vision Solutions Pvt. Ltd.",
        original_bullets=max_vision_orig,
        ai_bullets=None,
        matching_skills=["Stripe", "REST APIs"],
        missing_skills=["CI/CD"],
        job_title=pocketpills_jd["title"],
        company=pocketpills_jd["company"],
        job_description=pocketpills_jd["description"],
    )

    # First bullet must be eCommerce / payment focused
    assert "stripe" in preserved_max[0].lower() or "woocommerce" in preserved_max[0].lower()
    assert any("pay.mesa-qr.com" in b and "split payment" in b.lower() and "stripe" in b.lower() for b in preserved_max)
    assert any("woocommerce" in b.lower() for b in preserved_max)


def test_achievements_normalization_and_url_preservation():
    """Achievements retain full descriptions and verified URLs without fragmented text."""
    from app.agents.profile_creator import ProfileCreatorAgent

    agent = ProfileCreatorAgent()
    fragmented_raw_profile = {
        "personal": {
            "fullName": "Nishant",
            "links": [
                {"name": "HackerRank", "url": "https://www.hackerrank.com/profile/NishantThePro"},
                {"name": "LeetCode", "url": "https://leetcode.com/NishantTheProgrammer"},
            ],
        },
        "achievements": [
            {"title": "back-end technologies. Demonstrated proficiency in problem-solving with a HackerRank 6th"},
            {"title": "Star Gold Badge and a track record of solving 450+ LeetCode questions. Proven ability to"},
            {"title": "https://www.hackerrank.com/profile/NishantThePro"},
            {"title": "https://leetcode.com/NishantTheProgrammer"},
        ],
    }

    normalized = agent._normalize_extracted_data(fragmented_raw_profile)
    achievements = normalized["achievements"]

    assert len(achievements) == 2
    # Check HackerRank entry
    hr_entry = next((a for a in achievements if "hackerrank" in a["title"].lower()), None)
    assert hr_entry is not None
    assert hr_entry["title"] == "HackerRank 6th Star Gold Badge (Problem Solving)"
    assert hr_entry["url"] == "https://www.hackerrank.com/profile/NishantThePro"
    assert "https://" not in hr_entry["title"]

    # Check LeetCode entry
    lc_entry = next((a for a in achievements if "leetcode" in a["title"].lower()), None)
    assert lc_entry is not None
    assert lc_entry["title"] == "Solved 450+ LeetCode questions demonstrating strong algorithmic problem-solving"
    assert lc_entry["url"] == "https://leetcode.com/NishantTheProgrammer"
    assert "https://" not in lc_entry["title"]


def test_mentoring_retrieval_across_all_fields(candidate_profile, pocketpills_jd):
    """Mentoring must be classified as MATCHED regardless of whether it appears in responsibilities, description, or summary."""
    mapper = EvidenceMapper()

    # Case A: Explicit responsibilities (standard profile)
    res_a = mapper.map_evidence(candidate_profile, pocketpills_jd)
    m_a = next((m for m in res_a.mappings if "mentor" in m.requirement.lower()), None)
    assert m_a is not None
    assert m_a.status == "MATCHED"

    # Case B: Mentoring text placed inside role description
    profile_b = copy.deepcopy(candidate_profile)
    profile_b["experience"][0]["responsibilities"] = ["Developing REST APIs and integrations."]
    profile_b["experience"][0]["description"] = "SDE-2 Full Stack, mentored junior developers and conducted technical interviews."
    res_b = mapper.map_evidence(profile_b, pocketpills_jd)
    m_b = next((m for m in res_b.mappings if "mentor" in m.requirement.lower()), None)
    assert m_b is not None
    assert m_b.status == "MATCHED"

    # Case C: Passed as an explicit required_skill "Mentoring" in JD
    jd_c = copy.deepcopy(pocketpills_jd)
    jd_c["required_skills"] = ["Java", "Mentoring"]
    res_c = mapper.map_evidence(candidate_profile, jd_c)
    m_c = next((m for m in res_c.mappings if m.requirement == "Mentoring"), None)
    assert m_c is not None
    assert m_c.status == "MATCHED"


def test_proven_expertise_java_fails_semantic_validation(candidate_profile, pocketpills_jd):
    """Summary claiming proven expertise in project-only Java/Spring Boot must fail validation (is_valid=False)."""
    mapper = EvidenceMapper()
    evidence_res = mapper.map_evidence(candidate_profile, pocketpills_jd)
    guard = HallucinationGuard()

    invalid_resume = {
        "target_headline": "Senior Backend Engineer | Java, SQL",
        "tailored_summary": "Seasoned Full Stack Developer with 5+ years of experience. Proven expertise in Java, Spring Boot, and backend systems.",
        "experience": candidate_profile["experience"],
        "education": candidate_profile["education"],
    }

    val_raw = guard.validate(invalid_resume, candidate_profile, evidence_res)
    assert not val_raw.is_valid
    categories = [v.category for v in val_raw.critical_violations]
    assert "unsupported_specialization" in categories

    # Verify sanitization corrects it to project exposure
    val_res = guard.validate_and_sanitize(invalid_resume, candidate_profile, evidence_res)
    assert val_res.sanitized
    sanitized_summary = val_res.sanitized_content["summary"]
    assert "proven expertise in java" not in sanitized_summary.lower()
    assert "hands-on project experience in spring boot" in sanitized_summary.lower()


def test_city_finance_attribution_to_max_vision_fails_validation(candidate_profile, pocketpills_jd):
    """Attributing City Finance to Max Vision must fail semantic validation with is_valid=False and be corrected."""
    mapper = EvidenceMapper()
    evidence_res = mapper.map_evidence(candidate_profile, pocketpills_jd)
    guard = HallucinationGuard()

    misattributed_resume = {
        "target_headline": "Senior Backend Engineer | Node.js, SQL",
        "tailored_summary": "Full Stack Developer with 5 years experience.",
        "experience": [
            {
                "company": "Dhwani Rural Information Systems",
                "responsibilities": [
                    "Enhanced platform performance through query optimization and materialized views.",
                ],
            },
            {
                "company": "Max Vision Solutions Pvt. Ltd.",
                "responsibilities": [
                    "City Finance: Implemented a bulk upload service handling data for 4000+ urban local bodies and their finance.",
                ],
            },
        ],
        "education": candidate_profile["education"],
    }

    val_raw = guard.validate(misattributed_resume, candidate_profile, evidence_res)
    assert not val_raw.is_valid
    categories = [v.category for v in val_raw.critical_violations]
    assert "cross_employer_bleed" in categories

    # In sanitized output, City Finance must NOT remain under Max Vision
    val_res = guard.validate_and_sanitize(misattributed_resume, candidate_profile, evidence_res)
    assert val_res.sanitized
    sanitized_mv = next((e for e in val_res.sanitized_content["experience"] if "max vision" in e["company"].lower()), None)
    assert sanitized_mv is not None
    assert not any("4000+" in r or "city finance" in r.lower() for r in sanitized_mv["responsibilities"])


def test_unsupported_outcome_claims_fail_validation(candidate_profile, pocketpills_jd):
    """Invented fluff such as 'enhancing workflow efficiency' must fail validation (is_valid=False) and be removed."""
    mapper = EvidenceMapper()
    evidence_res = mapper.map_evidence(candidate_profile, pocketpills_jd)
    guard = HallucinationGuard()

    fluff_resume = {
        "target_headline": "Senior Backend Engineer | Node.js, SQL",
        "tailored_summary": "Full Stack Developer with 5 years experience.",
        "experience": [
            {
                "company": "Dhwani Rural Information Systems",
                "responsibilities": [
                    "Enhanced platform performance through query optimization, enhancing workflow efficiency across all teams.",
                ],
            }
        ],
        "projects": [
            {
                "name": "StaffSync",
                "description": "Role-based workforce management system designed to streamline company operations and enhance workflow efficiency.",
                "technologies": ["Spring Boot"],
            }
        ],
        "education": candidate_profile["education"],
    }

    val_raw = guard.validate(fluff_resume, candidate_profile, evidence_res)
    assert not val_raw.is_valid
    categories = [v.category for v in val_raw.critical_violations]
    assert "unsupported_outcome" in categories

    # In sanitized output, "enhancing workflow efficiency" must be removed
    val_res = guard.validate_and_sanitize(fluff_resume, candidate_profile, evidence_res)
    assert val_res.sanitized
    sanitized_bullet = val_res.sanitized_content["experience"][0]["responsibilities"][0]
    assert "enhancing workflow efficiency" not in sanitized_bullet.lower()
    sanitized_proj = val_res.sanitized_content["projects"][0]["description"]
    assert "enhance workflow efficiency" not in sanitized_proj.lower()


def test_security_expertise_claim_fails_validation(candidate_profile, pocketpills_jd):
    """Unsupported security expertise claims in summary must fail validation with is_valid=False and warning."""
    mapper = EvidenceMapper()
    evidence_res = mapper.map_evidence(candidate_profile, pocketpills_jd)
    guard = HallucinationGuard()

    sec_resume = {
        "target_headline": "Senior Backend Engineer | Node.js, SQL",
        "tailored_summary": "Seasoned Full Stack Developer with 5+ years experience and proven security expertise, with a focus on building robust and secure applications.",
        "experience": candidate_profile["experience"],
        "education": candidate_profile["education"],
    }

    val_raw = guard.validate(sec_resume, candidate_profile, evidence_res)
    assert not val_raw.is_valid
    categories = [v.category for v in val_raw.critical_violations]
    assert "unsupported_claim" in categories
    assert any(w.category == "unsupported_claim" for w in val_raw.warnings)

    # In sanitized summary, security expertise claims must be removed
    val_res = guard.validate_and_sanitize(sec_resume, candidate_profile, evidence_res)
    assert val_res.sanitized
    sanitized_sum = val_res.sanitized_content["summary"]
    assert "security expertise" not in sanitized_sum.lower()
    assert "secure applications" not in sanitized_sum.lower()


def test_fragmented_achievements_fail_validation(candidate_profile, pocketpills_jd):
    """Standalone URLs as titles or fragmented achievement shards must fail validation with is_valid=False and warning."""
    mapper = EvidenceMapper()
    evidence_res = mapper.map_evidence(candidate_profile, pocketpills_jd)
    guard = HallucinationGuard()

    fragmented_resume = {
        "target_headline": "Senior Backend Engineer | Node.js, SQL",
        "tailored_summary": "Full Stack Developer with 5 years experience.",
        "experience": candidate_profile["experience"],
        "education": candidate_profile["education"],
        "achievements": [
            {"title": "back-end technologies. Demonstrated proficiency in problem-solving with a HackerRank 6th"},
            {"title": "https://www.hackerrank.com/profile/NishantThePro"},
            {"title": "https://leetcode.com/NishantTheProgrammer"},
        ],
    }

    val_raw = guard.validate(fragmented_resume, candidate_profile, evidence_res)
    assert not val_raw.is_valid
    categories = [v.category for v in val_raw.critical_violations]
    assert "fragmented_achievement" in categories
    assert any(w.category == "fragmented_achievement" for w in val_raw.warnings)

    # In sanitized output, must recalculate is_valid=True and reconstruct 2 cohesive achievements
    val_res = guard.validate_and_sanitize(fragmented_resume, candidate_profile, evidence_res)
    assert val_res.sanitized
    assert val_res.is_valid is True
    assert len(val_res.critical_violations) == 0

    sanitized_achs = val_res.sanitized_content["achievements"]
    assert len(sanitized_achs) == 2
    for sa in sanitized_achs:
        title = sa["title"]
        assert not title.startswith("http://") and not title.startswith("https://")
        assert "http://" not in title and "https://" not in title
        assert "back-end technologies." not in title
    assert any(sa["title"] == "HackerRank 6th Star Gold Badge (Problem Solving)" and sa.get("url") == "https://www.hackerrank.com/profile/NishantThePro" for sa in sanitized_achs)
    assert any(sa["title"] == "Solved 450+ LeetCode questions demonstrating strong algorithmic problem-solving" and sa.get("url") == "https://leetcode.com/NishantTheProgrammer" for sa in sanitized_achs)


def test_reconstructed_achievements_pass_final_validation(candidate_profile, pocketpills_jd):
    """Properly reconstructed achievements pass semantic validation with is_valid=True and 0 critical violations."""
    guard = HallucinationGuard()
    mapper = EvidenceMapper()
    evidence_res = mapper.map_evidence(candidate_profile, pocketpills_jd)

    clean_resume = {
        "target_headline": "Senior Backend Engineer | SQL, Node.js, PostgreSQL",
        "tailored_summary": "Full Stack Developer with 5 years of overall software development experience with hands-on project experience in Spring Boot through StaffSync.",
        "experience": candidate_profile["experience"],
        "education": candidate_profile["education"],
        "achievements": [
            {
                "title": "HackerRank 6th Star Gold Badge (Problem Solving)",
                "url": "https://www.hackerrank.com/profile/NishantThePro",
            },
            {
                "title": "Solved 450+ LeetCode questions demonstrating strong algorithmic problem-solving",
                "url": "https://leetcode.com/NishantTheProgrammer",
            },
        ],
    }

    val_res = guard.validate(clean_resume, candidate_profile, evidence_res)
    assert val_res.is_valid is True
    assert len(val_res.critical_violations) == 0
    assert "0 critical violations" in val_res.summary_notes


def test_sql_evidence_mapping_company_isolation(candidate_profile, pocketpills_jd):
    """SQL evidence mapping must isolate company boundaries and never leak other company names."""
    # Introduce raw bleed where Max Vision was attached to Dhwani's bullet
    profile_with_bleed = copy.deepcopy(candidate_profile)
    profile_with_bleed["experience"][0]["responsibilities"].append(
        "Which handles data for 4000+ urban local bodies and their finance. Max Vision Solutions Pvt. Ltd."
    )

    mapper = EvidenceMapper()
    res = mapper.map_evidence(profile_with_bleed, pocketpills_jd)

    sql_mapping = next((m for m in res.mappings if m.requirement.upper() == "SQL"), None)
    assert sql_mapping is not None
    assert sql_mapping.status == "MATCHED"
    assert "Dhwani" in sql_mapping.source_entity
    # Must NOT contain foreign company name
    assert "Max Vision Solutions" not in sql_mapping.evidence_text
    assert "Pvt. Ltd." not in sql_mapping.evidence_text


def test_dhwani_preserves_formio_and_amplitude_analytics(pocketpills_jd):
    """Tailoring Dhwani's experience for backend JD must retain Form.io dynamic assessment, Amplitude, and materialized views."""
    from app.agents.resume_builder import preserve_and_prioritize_experience_bullets

    dhwani_orig_bullets = [
        "Conducting interviews, mentored junior developers, developing REST APIs, integrating third-party services.",
        "Indian Partner Network: Designed and developed a comprehensive full-stack NGO management platform, building robust backend systems with Node.js/Express and modern Angular frontend. Seamlessly integrated Form.io for dynamic assessments, form solutions, and form wizard workflows with advanced validation. Implemented personalized email automation using SendGrid with calendar integration, notification triggers, and reminder systems. Built real-time analytics with Amplitude tracking across web applications and WordPress directories. Enhanced platform performance through query optimization, materialized views, and session synchronization across multiple tabs.",
        "City Finance: Worked on complex reactive forms, integrated geographical maps, added Google Analytics, and implemented a bulk upload service. Which handles data for 4000+ urban local bodies and their finance.",
    ]

    ai_short_bullets = [
        "Designed and developed a comprehensive full-stack NGO management platform using Node.js/Express and modern Angular frontend.",
        "Enhanced platform performance through query optimization across multiple tabs.",
    ]

    preserved = preserve_and_prioritize_experience_bullets(
        company_name="Dhwani Rural Information Systems",
        original_bullets=dhwani_orig_bullets,
        ai_bullets=ai_short_bullets,
        matching_skills=["Node.js", "Express", "SQL"],
        missing_skills=["CI/CD", "Jenkins"],
        job_title=pocketpills_jd["title"],
        company=pocketpills_jd["company"],
        job_description=pocketpills_jd["description"],
    )

    full_preserved_text = " ".join(preserved).lower()
    # Must retain Form.io dynamic assessment / form solutions
    assert "form.io" in full_preserved_text
    assert "dynamic assessment" in full_preserved_text or "form solutions" in full_preserved_text
    # Must retain Amplitude analytics tracking
    assert "amplitude" in full_preserved_text
    # Must retain materialized views
    assert "materialized view" in full_preserved_text
    # Must retain City Finance (4000+ ULBs)
    assert "4000+" in full_preserved_text


def test_schema_consolidation_and_backward_compatibility(candidate_profile, pocketpills_jd):
    """Tailored resume JSON schema must consolidate duplicate fields without breaking consumer aliases."""
    from app.agents.resume_builder import select_and_tailor_projects

    projects = select_and_tailor_projects(
        raw_projects=candidate_profile["projects"],
        required_skills=["Java", "Spring Boot"],
        matching_skills=["Java", "Spring Boot"],
        job_title=pocketpills_jd["title"],
        company=pocketpills_jd["company"],
        max_projects=3,
        filter_irrelevant=False,
    )

    for p in projects:
        # Both canonical and backwards-compatible aliases must be synchronized
        assert p.get("name") is not None
        assert p.get("title") == p.get("name")
        assert p.get("technologies") is not None
        assert p.get("tech_stack") == p.get("technologies")


def test_company_attribution_and_leak_prevention(candidate_profile, pocketpills_jd):
    """Company names leaking into bullet text must be stripped, and City Finance must belong exclusively to Dhwani."""
    from app.agents.resume_builder import preserve_and_prioritize_experience_bullets

    leaked_bullet = [
        "Implemented a bulk upload service handling data for 4000+ urban local bodies and their finance. Max Vision Solutions Pvt. Ltd."
    ]

    cleaned = preserve_and_prioritize_experience_bullets(
        company_name="Dhwani Rural Information Systems",
        original_bullets=leaked_bullet,
        ai_bullets=None,
        matching_skills=["SQL"],
        missing_skills=["CI/CD"],
        job_title=pocketpills_jd["title"],
        company=pocketpills_jd["company"],
        job_description=pocketpills_jd["description"],
    )

    # Bullet must have stripped the leaked company name "Max Vision Solutions Pvt. Ltd."
    assert len(cleaned) == 1
    assert "Max Vision Solutions" not in cleaned[0]
    assert "4000+ urban local bodies" in cleaned[0]


def test_clean_achievements_free_of_urls(candidate_profile, pocketpills_jd):
    """Achievement titles must be strictly free of URLs; URLs must be stored only in url field."""
    from app.agents.resume_builder import reconstruct_achievements

    raw_fragmented = [
        {"title": "back-end technologies. Demonstrated proficiency in problem-solving with a HackerRank 6th"},
        {"title": "Star Gold Badge and a track record of solving 450+ LeetCode questions. Proven ability to"},
        {"title": "https://www.hackerrank.com/profile/NishantThePro"},
        {"title": "https://leetcode.com/NishantTheProgrammer"},
    ]

    achs = reconstruct_achievements(raw_fragmented, candidate_profile)
    assert len(achs) == 2
    for a in achs:
        assert "http://" not in a["title"] and "https://" not in a["title"]
        assert a.get("url") is not None
        assert a["url"].startswith("http")

    hr = next((a for a in achs if "HackerRank" in a["title"]), None)
    assert hr is not None
    assert hr["title"] == "HackerRank 6th Star Gold Badge (Problem Solving)"
    assert hr["url"] == "https://www.hackerrank.com/profile/NishantThePro"

    lc = next((a for a in achs if "LeetCode" in a["title"]), None)
    assert lc is not None
    assert lc["title"] == "Solved 450+ LeetCode questions demonstrating strong algorithmic problem-solving"
    assert lc["url"] == "https://leetcode.com/NishantTheProgrammer"


@pytest.mark.anyio
async def test_summary_accuracy_and_evidence_alignment(candidate_profile, pocketpills_jd):
    """Generated tailored resume must retain 5 years overall software development experience,
    distinguish professional backend from project-level StaffSync Java/Spring Boot, and avoid security fluff."""
    from unittest.mock import AsyncMock, patch, MagicMock
    from app.agents.resume_builder import ResumeBuilderAgent

    cand_with_links = copy.deepcopy(candidate_profile)
    cand_with_links["links"] = [
        {"name": "HackerRank", "url": "https://www.hackerrank.com/profile/NishantThePro"},
        {"name": "LeetCode", "url": "https://leetcode.com/NishantTheProgrammer"},
    ]

    mock_db = MagicMock()
    mock_db.profiles.find_one = AsyncMock(return_value=cand_with_links)
    mock_db.jobs.find_one = AsyncMock(return_value=pocketpills_jd)
    mock_db.user_settings.find_one = AsyncMock(return_value=None)
    mock_db.resumes.update_one = AsyncMock(return_value=MagicMock(upserted_id=candidate_profile["_id"]))
    mock_db.job_matches.update_one = AsyncMock()

    with patch("app.agents.resume_builder.get_db", return_value=mock_db):
        builder = ResumeBuilderAgent()
        tailored = await builder.build_tailored_resume(
            user_id=str(candidate_profile["user_id"]),
            job_id=str(pocketpills_jd["_id"]),
        )

    content = tailored["content"]
    summary = content["summary"]

    # 1. Retain 5 years of overall software development experience
    assert "5 years" in summary
    assert "overall software development experience" in summary.lower()

    # 2. Distinguish professional experience from StaffSync project-level Java/Spring Boot
    assert "staffsync" in summary.lower()
    assert "spring boot" in summary.lower()
    assert "project experience" in summary.lower()
    assert "proven expertise in java" not in summary.lower()

    # 3. No unsupported security claims
    assert "security expertise" not in summary.lower()
    assert "secure applications" not in summary.lower()

    # 4. Clean achievements with URLs in url field only
    for ach in content["achievements"]:
        assert "https://" not in ach["title"]
        assert ach.get("url") is not None


def test_generic_multi_company_isolation():
    """Verify generic entity isolation across arbitrary employers without hardcoded names."""
    from app.agents.hallucination_guard import HallucinationGuard
    from app.agents.evidence_mapper import EvidenceMapper
    from app.agents.resume_builder import preserve_and_prioritize_experience_bullets

    candidate = {
        "personal": {"fullName": "Dr. Alex Taylor"},
        "summary": "Software Architect with 6 years experience.",
        "skills": {"backend": ["Go", "Python", "C++"], "databases": ["PostgreSQL"]},
        "experience": [
            {
                "company": "FinTech Labs Inc.",
                "jobTitle": "Lead Systems Engineer",
                "responsibilities": [
                    "Engineered High-Frequency Trading engine processing 50,000 orders/sec.",
                ],
            },
            {
                "company": "BioHealth Corp.",
                "jobTitle": "Data Infrastructure Engineer",
                "responsibilities": [
                    "Genomics Pipeline: processed 10,000 DNA sequences per day with distributed workers.",
                ],
            },
        ],
    }

    mock_jd = {
        "title": "Systems Architect",
        "company": "NextGen Quant",
        "description": "Seeking Systems Architect with Go and low-latency experience.",
    }

    # 1. Test bullet leak stripping for arbitrary companies
    leaked = ["Engineered High-Frequency Trading engine. BioHealth Corp."]
    cleaned = preserve_and_prioritize_experience_bullets(
        company_name="FinTech Labs Inc.",
        original_bullets=leaked,
        ai_bullets=None,
        matching_skills=["Go"],
        missing_skills=[],
        all_other_companies=["BioHealth Corp."],
    )
    assert "BioHealth Corp" not in cleaned[0]

    # 2. Test cross-employer bleed detection
    mapper = EvidenceMapper()
    ev_res = mapper.map_evidence(candidate, mock_jd)
    guard = HallucinationGuard()

    inverted_resume = {
        "target_headline": "Systems Architect | Go",
        "tailored_summary": "Architect with 6 years experience.",
        "experience": [
            {
                "company": "FinTech Labs Inc.",
                "responsibilities": [
                    "Genomics Pipeline: processed 10,000 DNA sequences per day with distributed workers.",
                ],
            },
            {
                "company": "BioHealth Corp.",
                "responsibilities": [
                    "Engineered High-Frequency Trading engine processing 50,000 orders/sec.",
                ],
            },
        ],
    }

    val_raw = guard.validate(inverted_resume, candidate, ev_res)
    assert not val_raw.is_valid
    categories = [v.category for v in val_raw.critical_violations]
    assert "cross_employer_bleed" in categories

    # 3. Test sanitization re-routes bullets to authentic employer
    val_res = guard.validate_and_sanitize(inverted_resume, candidate, ev_res)
    fintech_resps = next(e["responsibilities"] for e in val_res.sanitized_content["experience"] if e["company"] == "FinTech Labs Inc.")
    bio_resps = next(e["responsibilities"] for e in val_res.sanitized_content["experience"] if e["company"] == "BioHealth Corp.")

    # Genomics Pipeline must NOT be in FinTech Labs
    assert not any("genomics pipeline" in r.lower() for r in fintech_resps)
    # Trading engine must NOT be in BioHealth Corp
    assert not any("trading engine" in r.lower() for r in bio_resps)
    # Authentic bullets must be restored to their true employers
    assert any("genomics pipeline" in r.lower() for r in bio_resps)
    assert any("trading engine" in r.lower() for r in fintech_resps)


def test_dynamic_project_to_technology_mapping():
    """Verify arbitrary project-to-technology mapping without StaffSync hardcoding."""
    from app.agents.evidence_mapper import EvidenceMapper
    from app.agents.hallucination_guard import HallucinationGuard

    cand = {
        "personal": {"fullName": "Taylor Swift"},
        "summary": "Systems Developer with 4 years experience.",
        "skills": {"backend": ["Python", "C++"]},
        "experience": [
            {
                "company": "Network Systems",
                "jobTitle": "Systems Developer",
                "responsibilities": ["Maintained TCP/IP daemon."],
            }
        ],
        "projects": [
            {
                "name": "RustTelemetry",
                "description": "High performance metric collector designed for distributed nodes.",
                "technologies": ["Rust", "Actix"],
            }
        ],
    }

    jd = {
        "title": "Rust Developer",
        "company": "FastEdge",
        "required_skills": ["Rust"],
        "description": "Seeking Rust engineer for high performance edge compute.",
    }

    mapper = EvidenceMapper()
    ev_res = mapper.map_evidence(cand, jd)

    # 1. Evidence mapper must classify Rust as PARTIAL project-level match
    rust_ev = next((m for m in ev_res.mappings if m.requirement.lower() == "rust"), None)
    assert rust_ev is not None
    assert rust_ev.status == "PARTIAL"
    assert rust_ev.evidence_source == "project"
    assert rust_ev.source_entity == "RustTelemetry"
    assert "RustTelemetry" in rust_ev.notes

    # 2. Claiming 4 years professional Rust must fail validation
    guard = HallucinationGuard()
    inflated_resume = {
        "target_headline": "Rust Developer | Rust",
        "tailored_summary": "Systems Developer with 4+ years of Rust experience.",
        "experience": cand["experience"],
    }
    val = guard.validate(inflated_resume, cand, ev_res)
    assert not val.is_valid
    inflation_violation = next((v for v in val.critical_violations if v.category == "experience_inflation"), None)
    assert inflation_violation is not None
    assert "RustTelemetry" in inflation_violation.allowed_boundary


def test_arbitrary_platforms_achievement_reconstruction():
    """Verify generic achievement reconstruction across Kaggle, Codeforces, AWS certifications, and broken OCR fragments."""
    from app.agents.resume_builder import reconstruct_achievements

    cand = {
        "personal": {"fullName": "Dana Scully"},
        "summary": "Data Scientist with Kaggle Grandmaster status and Codeforces Candidate Master rating.",
        "links": [
            {"name": "Kaggle", "url": "https://www.kaggle.com/danascully"},
            {"name": "Codeforces", "url": "https://codeforces.com/profile/danascully"},
        ],
    }

    raw_fragmented = [
        {"title": "data pipelines across clouds. Kaggle Grandmaster (Competitions)"},
        {"title": "https://www.kaggle.com/danascully"},
        {"title": "Codeforces Candidate Master (Max rating 1980)"},
        {"title": "https://codeforces.com/profile/danascully"},
        {"title": "AWS Certified Solutions Architect Professional"},
        {"title": "https://www.credly.com/badges/abc-123"},
        {"title": "proven ability to deliver"},
    ]

    achs = reconstruct_achievements(raw_fragmented, cand)

    # 1. Standalone URLs must NOT be titles
    for a in achs:
        assert not a["title"].startswith("http")

    # 2. Fragmented sentence shards must be filtered out
    assert not any("proven ability to" in a["title"].lower() for a in achs)

    # 3. Kaggle achievement extracted and mapped to Kaggle URL
    kg = next((a for a in achs if "kaggle" in a["title"].lower()), None)
    assert kg is not None
    assert "kaggle grandmaster" in kg["title"].lower()
    assert kg["url"] == "https://www.kaggle.com/danascully"

    # 4. Codeforces achievement extracted and mapped to Codeforces URL
    cf = next((a for a in achs if "codeforces" in a["title"].lower()), None)
    assert cf is not None
    assert "candidate master" in cf["title"].lower()
    assert cf["url"] == "https://codeforces.com/profile/danascully"

    # 5. AWS certification mapped to Credly URL
    aws = next((a for a in achs if "aws certified" in a["title"].lower()), None)
    assert aws is not None
    assert aws["url"] == "https://www.credly.com/badges/abc-123"


def test_dynamic_metrics_extraction_and_cross_company_isolation():
    """Phase 5: Test dynamic metrics extraction with provenance and cross-employer metric isolation."""
    from app.agents.profile_creator import ProfileCreatorAgent
    from app.agents.evidence_mapper import EvidenceMapper
    from app.agents.hallucination_guard import HallucinationGuard

    raw_profile = {
        "personal": {"fullName": "Taylor Swift", "email": "taylor@swift.io"},
        "experience": [
            {
                "company": "Alpha HighScale Inc",
                "role": "Staff Systems Engineer",
                "responsibilities": [
                    "Architected event streaming pipelines processing 50,000 req/s with 99.99% uptime.",
                    "Optimized distributed cache reducing latency by 45% and saving $1.2M annually.",
                ],
            },
            {
                "company": "Beta Retail Ltd",
                "role": "Backend Developer",
                "responsibilities": [
                    "Scaled online ordering service to handle 200,000 active shoppers during flash sales.",
                ],
            },
        ],
        "projects": [
            {
                "name": "RustKV",
                "description": "Embedded key-value engine benchmarked at 1.5M QPS on NVMe storage.",
            }
        ],
        "achievements": [
            {"title": "1st place in Global Distributed Systems Hackathon 2024"},
        ],
    }

    creator = ProfileCreatorAgent()
    norm = creator._normalize_extracted_data(raw_profile)

    # 1. Verify dynamic metrics extraction across experience, projects, and achievements
    metrics = norm.get("metrics", [])
    assert len(metrics) >= 4

    alpha_cid = norm["experience"][0]["company_id"]
    beta_cid = norm["experience"][1]["company_id"]
    alpha_metrics = [m for m in metrics if m.get("company_id") == alpha_cid]
    beta_metrics = [m for m in metrics if m.get("company_id") == beta_cid]
    proj_metrics = [m for m in metrics if m.get("source_type") == "personal_project"]

    assert any("50,000" in m["value"] or "99.99%" in m["value"] for m in alpha_metrics)
    assert any("200,000" in m["value"] for m in beta_metrics)
    assert any("1.5M" in m["value"] for m in proj_metrics)

    # 2. Test cross-employer metric bleed detection in HallucinationGuard
    jd = {
        "title": "Principal Systems Engineer",
        "company": "Stripe",
        "required_skills": ["Rust", "Distributed Systems"],
        "responsibilities": ["Lead high-throughput event processing."],
    }

    mapper = EvidenceMapper()
    ev_res = mapper.map_evidence(norm, jd)
    guard = HallucinationGuard()

    # Leaked metric: Beta Retail Ltd claims 50,000 req/s from Alpha HighScale
    leaked_resume = {
        "target_headline": "Principal Systems Engineer | Rust & Distributed Systems",
        "tailored_summary": "Experienced systems engineer with deep distributed systems background.",
        "experience": [
            {
                "company": "Alpha HighScale Inc",
                "responsibilities": [
                    "Architected event streaming pipelines processing 50,000 req/s with 99.99% uptime.",
                ],
            },
            {
                "company": "Beta Retail Ltd",
                "responsibilities": [
                    "Scaled online ordering service to handle 50,000 req/s with 99.99% uptime.",
                ],
            },
        ],
    }

    val_res = guard.validate(leaked_resume, norm, ev_res)
    assert not val_res.is_valid
    categories = [v.category for v in val_res.critical_violations]
    assert "cross_employer_bleed" in categories

    # 3. Test fabricated financial metric detection ($10M ARR never appeared in profile)
    invented_metric_resume = {
        "target_headline": "Principal Systems Engineer | Rust & Distributed Systems",
        "tailored_summary": "Experienced systems engineer.",
        "experience": [
            {
                "company": "Beta Retail Ltd",
                "responsibilities": [
                    "Generated $10M ARR through optimized flash sale infrastructure.",
                ],
            },
        ],
    }

    val_res_inv = guard.validate(invented_metric_resume, norm, ev_res)
    assert not val_res_inv.is_valid
    assert any(v.category == "invented_metric" for v in val_res_inv.critical_violations)


def test_dynamic_jd_analysis_arbitrary_domains():
    """Phase 6: Test dynamic JD requirement extraction, section importance, and degree matching on arbitrary roles."""
    from app.agents.evidence_mapper import EvidenceMapper

    mapper = EvidenceMapper()

    jd = {
        "title": "Cloud Platform Engineer",
        "company": "DataCorp",
        "required_skills": ["Python", "Docker"],
        "description": """
        About the role:
        We are seeking a Cloud Platform Engineer to manage scalable distributed systems.
        
        Requirements:
        - 3 to 5 years experience in building backend cloud services
        - Master's degree in Computer Science or related technical discipline
        - Strong background in Python and FastAPI
        
        Nice to have:
        - Experience with Docker containerization and Redis
        - Knowledge of Microservices architecture
        """,
    }

    reqs = mapper.extract_jd_requirements(jd["title"], jd["required_skills"], jd["description"])
    req_names = {r["name"] for r in reqs}

    # Verify dynamic technology extraction
    assert "Python" in req_names
    assert "Docker" in req_names
    assert "FastAPI" in req_names
    assert "Redis" in req_names
    assert "Microservices" in req_names

    # Verify importance detection: Python & FastAPI are mandatory, Redis is desirable
    py_req = next(r for r in reqs if r["name"] == "Python")
    assert py_req["importance"] == "mandatory"

    redis_req = next(r for r in reqs if r["name"] == "Redis")
    assert redis_req["importance"] == "desirable"

    # Candidate with Master's degree
    candidate = {
        "personal": {"fullName": "Dana Scully", "email": "dana@fbi.gov"},
        "summary": "Cloud engineer with 4 years building APIs in Python and FastAPI.",
        "skills": {
            "backend": ["Python", "FastAPI"],
            "databases": ["Redis"],
            "tools": ["Docker"],
        },
        "experience": [
            {
                "company": "FBI Tech Division",
                "role": "Cloud Platform Engineer",
                "current": True,
                "responsibilities": [
                    "Engineered cloud infrastructure using Python and FastAPI.",
                    "Configured Redis caches and Docker containers.",
                ],
            }
        ],
        "education": [
            {"degree": "Master of Science in Computer Science", "institution": "Stanford University", "year": "2020"},
        ],
    }

    res = mapper.map_evidence(candidate, jd)

    # Master's degree should be MATCHED directly
    edu_m = next((m for m in res.mappings if m.evidence_source == "education" or "master" in m.requirement.lower()), None)
    assert edu_m is not None
    assert edu_m.status == "MATCHED"

    # Matched skills
    assert "Python" in res.skills_classification.matched_skills
    assert "Docker" in res.skills_classification.matched_skills
    assert "FastAPI" in res.skills_classification.matched_skills









