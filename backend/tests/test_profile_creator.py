from app.agents.profile_creator import ProfileCreatorAgent


def test_heuristic_parsing_and_scoring():
    agent = ProfileCreatorAgent()
    sample_text = """
    Jordan Lee
    jordan.lee@example.com | (555) 234-5678 | San Francisco, CA
    linkedin.com/in/jordanlee | github.com/jordanlee

    Experienced Full Stack Developer proficient in Python, React, TypeScript, Docker, and PostgreSQL.
    Passionate about automating workflows and scalable systems.
    """

    parsed = agent._heuristic_parse(sample_text)
    assert parsed["personal"]["email"] == "jordan.lee@example.com"
    assert "Python" in parsed["skills"]["backend"]
    assert "TypeScript" in parsed["skills"]["frontend"]

    missing, questions = agent._identify_gaps_and_questions(parsed)
    assert isinstance(missing, list)
    assert isinstance(questions, list)

    score = agent._calculate_completion_score(parsed)
    assert score >= 30


def test_generic_profile_provenance_and_schema_normalization():
    agent = ProfileCreatorAgent()
    raw_data = {
        "personal": {
            "fullName": "Alice Smith",
            "email": "alice@example.com",
        },
        "summary": "Full Stack Engineer with 4 years of experience building microservices and web apps.",
        "skills": {
            "backend": ["Python", "FastAPI"],
            "frontend": ["React", "TypeScript"],
        },
        "experience": [
            {
                "company": "Acme Corp",
                "jobTitle": "Senior Software Engineer",
                "startDate": "2021-01",
                "endDate": "Present",
                "current": True,
                "responsibilities": [
                    "Architected high-throughput ingestion handling 5000+ requests/sec.",
                    "Mentored 4 junior engineers on clean architecture.",
                ],
            }
        ],
        "projects": [
            {
                "name": "CloudMonitor",
                "description": "An open source telemetry agent written in Go.",
                "technologies": ["Go", "Prometheus"],
            }
        ],
        "education": [
            {
                "degree": "B.S. in Computer Science",
                "institution": "University of Tech",
                "year": "2020",
            }
        ],
        "achievements": [
            {
                "title": "AWS Certified Solutions Architect",
                "url": "https://aws.amazon.com/verify/123",
            }
        ],
    }

    norm = agent._normalize_extracted_data(raw_data)

    # 1. Candidate metadata
    assert "candidate" in norm
    assert norm["candidate"]["overall_experience_years"] == 4.0

    # 2. Experience IDs and Provenance
    exp = norm["experience"][0]
    assert exp["id"] == "experience_001"
    assert exp["company_id"] == "company_acme_corp"
    assert exp["role"] == "Senior Software Engineer"
    assert len(exp["evidence"]) == 2
    assert exp["evidence"][0]["source_type"] == "professional_experience"
    assert exp["evidence"][0]["company_id"] == "company_acme_corp"
    assert exp["evidence"][0]["company"] == "Acme Corp"

    # 3. Project Provenance
    proj = norm["projects"][0]
    assert proj["id"] == "project_001"
    assert len(proj["evidence"]) == 1
    assert proj["evidence"][0]["source_type"] == "project"
    assert proj["evidence"][0]["technologies"] == ["Go", "Prometheus"]

    # 4. Education Provenance
    edu = norm["education"][0]
    assert edu["id"] == "education_001"
    assert edu["source_type"] == "education"
    assert len(edu["evidence"]) == 1

    # 5. Achievement Provenance
    ach = norm["achievements"][0]
    assert ach["id"] == "achievement_001"
    assert ach["source"] == "original_resume"
    assert ach["url"] == "https://aws.amazon.com/verify/123"

    # 6. Metrics extraction
    assert len(norm["metrics"]) >= 1
    metric_vals = [m["value"] for m in norm["metrics"]]
    assert any("4" in v or "5000+" in v for v in metric_vals)

