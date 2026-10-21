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
    assert "Python" in parsed["skills"]
    assert "TypeScript" in parsed["skills"]

    missing, questions = agent._identify_gaps_and_questions(parsed)
    # Location was empty in personal dictionary from heuristic parse
    assert isinstance(missing, list)
    assert isinstance(questions, list)

    score = agent._calculate_completion_score(parsed)
    assert score >= 30
