"""
Temporary Test Personas for verifying multi-role matching, AI scoring, and tailored applications.
Can be removed later once testing is complete.
"""
from typing import Any
from datetime import datetime, timezone
from bson import ObjectId
import structlog
from app.db.client import get_db
from app.agents.job_matcher import JobMatcherAgent

logger = structlog.get_logger()

TEST_PERSONAS: list[dict[str, Any]] = [
    {
        "id": "arun_kumar",
        "name": "Arun Kumar",
        "email": "arun.kumar@test.local",
        "discord_username": "arun_kumar",
        "role": "admin",
        "category": "Senior Quality Engineer (Web)",
        "title": "Senior Quality Engineer (5 yrs) — Web Testing",
        "badge_color": "emerald",
        "avatar_letter": "A",
        "location": "Noida, India",
        "target_titles": [
            "Senior Quality Engineer",
            "SDET",
            "QA Automation Engineer",
            "Senior QA Engineer",
            "Web Automation Engineer",
            "Software Development Engineer in Test",
            "Lead Quality Engineer"
        ],
        "summary": "Senior Quality Engineer with 5 years of experience specializing in automated web testing, cross-browser test frameworks, and end-to-end quality engineering using Playwright, Cypress, Selenium WebDriver, and JavaScript/TypeScript.",
        "skills": {
            "languages": ["JavaScript", "TypeScript", "Java", "Python"],
            "web_testing": ["Web Testing", "End-to-End Testing", "Cross-Browser Testing", "Visual Regression", "Page Object Model", "Custom Test Fixtures"],
            "tools": ["Playwright", "Cypress", "Selenium WebDriver", "TestNG", "Postman", "Jenkins", "Git", "GitHub", "Jira", "Allure Reports"],
            "backend": ["REST Assured", "API Testing"]
        },
        "experience": [
            {
                "company": "MakeMyTrip",
                "title": "Senior Quality Engineer",
                "jobTitle": "Senior Quality Engineer",
                "location": "Gurugram, India",
                "start_date": "Dec 2021",
                "end_date": "Present",
                "is_current": True,
                "responsibilities": [
                    "Architected and maintained robust web automation frameworks using Playwright and TypeScript for high-traffic web portals.",
                    "Automated over 500+ critical web user workflows reducing regression test cycle time by 65%.",
                    "Integrated automated test runs into CI/CD pipelines with Jenkins and Docker."
                ]
            },
            {
                "company": "To The New",
                "title": "Quality Assurance Engineer",
                "jobTitle": "Quality Assurance Engineer",
                "location": "Noida, India",
                "start_date": "Nov 2019",
                "end_date": "Nov 2021",
                "is_current": False,
                "responsibilities": [
                    "Implemented cross-browser end-to-end test suites using Selenium WebDriver, Cypress, and TestNG.",
                    "Conducted thorough functional, cross-browser, regression, and API testing across enterprise web applications."
                ]
            }
        ]
    },
    {
        "id": "abhishek_soni",
        "name": "Abhishek Soni",
        "email": "abhishek.soni@test.local",
        "discord_username": "abhishek_soni",
        "role": "user",
        "category": "Senior Quality Engineer (ETL)",
        "title": "Senior Quality Engineer (5 yrs) — ETL & Data Testing",
        "badge_color": "blue",
        "avatar_letter": "A",
        "location": "Gurugram, India",
        "target_titles": [
            "Senior Quality Engineer",
            "ETL QA Engineer",
            "Data Quality Engineer",
            "ETL Tester",
            "Senior QA Automation Engineer - Data",
            "Big Data Test Engineer",
            "Quality Assurance Engineer"
        ],
        "summary": "Senior Quality Engineer with 5 years of experience specializing in ETL testing, data pipeline validation, complex SQL verification, and data warehouse quality assurance across Snowflake, PySpark, and Airflow.",
        "skills": {
            "languages": ["SQL", "Python", "Shell Scripting"],
            "etl_data": ["ETL Testing", "Data Validation", "Snowflake", "PySpark", "Apache Airflow", "Informatica", "dbt", "PostgreSQL", "MySQL"],
            "tools": ["Great Expectations", "Postman", "Git", "GitHub", "Jenkins", "Jira", "TestRail"],
            "testing": ["Data Migration Testing", "Schema Validation", "Reconciliation Frameworks", "End-to-End Pipeline QA", "Data Quality Metrics"]
        },
        "experience": [
            {
                "company": "PolicyBazaar",
                "title": "Senior Quality Engineer - ETL & Data",
                "jobTitle": "Senior Quality Engineer - ETL & Data",
                "location": "Gurugram, India",
                "start_date": "Jan 2022",
                "end_date": "Present",
                "is_current": True,
                "responsibilities": [
                    "Designed automated ETL verification suites validating multi-million row financial transaction pipelines across Snowflake and PostgreSQL.",
                    "Built custom Python reconciliation utilities comparing source-to-target data feeds with 99.99% accuracy.",
                    "Validated schema migrations and data transformation logic across Apache Airflow batch jobs."
                ]
            },
            {
                "company": "Wipro",
                "title": "QA Engineer (Data & ETL)",
                "jobTitle": "QA Engineer (Data & ETL)",
                "location": "Noida, India",
                "start_date": "Nov 2019",
                "end_date": "Dec 2021",
                "is_current": False,
                "responsibilities": [
                    "Authored complex SQL test queries for schema verification, data integrity audits, and boundary checks on enterprise data warehouses.",
                    "Tested end-to-end data feeds and batch jobs in Informatica PowerCenter and MySQL."
                ]
            }
        ]
    },
    {
        "id": "nishant_fullstack",
        "name": "Nishant",
        "email": "knishant113@gmail.com",
        "discord_username": "nishanttheprogrammer",
        "role": "admin",
        "category": "Senior Software Engineer (Full Stack - JS)",
        "title": "Senior Software Engineer (5 yrs) — Full Stack JS",
        "badge_color": "purple",
        "avatar_letter": "N",
        "location": "Delhi NCR, India",
        "target_titles": [
            "Senior Software Engineer",
            "Full Stack Developer",
            "Senior Full Stack Engineer",
            "Senior Frontend Engineer",
            "Node.js Developer",
            "React Developer",
            "Software Engineer - Fullstack"
        ],
        "summary": "Senior Software Engineer with 5 years of expertise in full stack JavaScript/TypeScript ecosystems, building scalable high-performance web applications using React, Next.js, Node.js, Express, and distributed microservices.",
        "skills": {
            "languages": ["JavaScript", "TypeScript", "Node.js", "SQL"],
            "frontend": ["React", "Next.js", "TailwindCSS", "Redux Toolkit", "Zustand", "HTML5", "CSS3"],
            "backend": ["Node.js", "Express", "NestJS", "REST APIs", "GraphQL", "Microservices"],
            "databases": ["MongoDB", "PostgreSQL", "Redis"],
            "tools": ["Docker", "AWS", "Git", "GitHub", "CI/CD", "Jest", "Vite"]
        },
        "experience": [
            {
                "company": "GrowthX",
                "title": "Senior Software Engineer - Full Stack",
                "jobTitle": "Senior Software Engineer - Full Stack",
                "location": "Delhi NCR, India",
                "start_date": "May 2022",
                "end_date": "Present",
                "is_current": True,
                "responsibilities": [
                    "Architected core full stack platforms using Next.js 14, Node.js, TypeScript, and MongoDB handling 200k+ monthly active users.",
                    "Designed responsive real-time dashboards with TailwindCSS, Server Actions, and distributed microservices on AWS.",
                    "Spearheaded microservices decomposition, reducing backend latency by 35%."
                ]
            },
            {
                "company": "Urban Company",
                "title": "Software Engineer - Full Stack",
                "jobTitle": "Software Engineer - Full Stack",
                "location": "Gurugram, India",
                "start_date": "Nov 2019",
                "end_date": "Apr 2022",
                "is_current": False,
                "responsibilities": [
                    "Built customer-facing booking interfaces and service catalog systems with React and Express.js.",
                    "Optimized front-end asset bundles and API caching with Redis, reducing page load times by 40%."
                ]
            }
        ]
    },
    {
        "id": "mohit_mahour",
        "name": "Mohit Mahour",
        "email": "mohit.mahour@test.local",
        "discord_username": "mohit_mahour",
        "role": "user",
        "category": "MERN Intern (0 Exp)",
        "title": "MERN Intern (0 exp)",
        "badge_color": "cyan",
        "avatar_letter": "M",
        "location": "Noida, India",
        "target_titles": [
            "MERN Intern",
            "Software Engineering Intern",
            "Frontend Intern",
            "Junior React Developer",
            "Junior Fullstack Developer",
            "MERN Developer Intern",
            "Graduate Trainee Engineer"
        ],
        "summary": "Enthusiastic fresh software graduate with hands-on project experience in the MERN stack (MongoDB, Express, React, Node.js). Passionate about building modern, responsive web apps and eager to contribute as a software engineering intern.",
        "skills": {
            "languages": ["JavaScript", "HTML5", "CSS3"],
            "frontend": ["React", "Redux", "TailwindCSS", "Bootstrap"],
            "backend": ["Node.js", "Express.js", "REST APIs"],
            "databases": ["MongoDB", "Mongoose"],
            "tools": ["Git", "GitHub", "Postman", "VS Code", "npm"]
        },
        "experience": [
            {
                "company": "Personal & Academic Projects",
                "title": "Full Stack MERN Developer (Projects)",
                "jobTitle": "Full Stack MERN Developer (Projects)",
                "location": "Noida, India",
                "start_date": "2024",
                "end_date": "Present",
                "is_current": True,
                "responsibilities": [
                    "Developed full stack E-commerce application featuring product catalog, shopping cart, user auth with JWT, and Stripe checkout.",
                    "Built real-time task management portal using React, Node.js, Express, and MongoDB with clean REST API architecture.",
                    "Collaborated on open source GitHub repositories following Git branching, pull request reviews, and responsive web design."
                ]
            }
        ]
    },
    {
        "id": "suraj_singh",
        "name": "Suraj Singh",
        "email": "suraj.singh@test.local",
        "discord_username": "suraj_singh",
        "role": "user",
        "category": "SDE-2 Full Stack (3 yrs)",
        "title": "SDE-2 Full stack (3 years)",
        "badge_color": "amber",
        "avatar_letter": "S",
        "location": "Gurugram, India",
        "target_titles": [
            "SDE-2",
            "Software Development Engineer II",
            "Full Stack Engineer",
            "Software Engineer - Fullstack",
            "SDE-2 Full Stack",
            "Full Stack Developer"
        ],
        "summary": "SDE-2 Full Stack Engineer with 3 years of experience developing robust end-to-end systems. Skilled in React, Next.js, TypeScript on the frontend, and Node.js/Python on the backend with cloud deployment on AWS.",
        "skills": {
            "languages": ["TypeScript", "JavaScript", "Python", "SQL"],
            "frontend": ["React", "Next.js", "TypeScript", "TailwindCSS", "Redux"],
            "backend": ["Node.js", "Express", "FastAPI", "REST APIs", "Microservices"],
            "databases": ["PostgreSQL", "MongoDB", "Redis"],
            "tools": ["Docker", "AWS", "Git", "GitHub", "CI/CD", "Postman"]
        },
        "experience": [
            {
                "company": "Innovaccer",
                "title": "SDE-2 Full Stack",
                "jobTitle": "SDE-2 Full Stack",
                "location": "Noida, India",
                "start_date": "Jul 2023",
                "end_date": "Present",
                "is_current": True,
                "responsibilities": [
                    "Engineered interactive healthcare analytics modules using React, Next.js, and TypeScript with state-driven component architectures.",
                    "Developed RESTful microservices with Node.js and FastAPI processing asynchronous health record integrations.",
                    "Collaborated with product designers to ship responsive, accessible web UI components."
                ]
            },
            {
                "company": "Tata 1mg",
                "title": "Software Engineer - Full Stack",
                "jobTitle": "Software Engineer - Full Stack",
                "location": "Gurugram, India",
                "start_date": "Jul 2021",
                "end_date": "Jun 2023",
                "is_current": False,
                "responsibilities": [
                    "Implemented checkout and order tracking frontend workflows with React and Redux.",
                    "Designed backend services in Express.js and MongoDB with Redis caching, supporting 50k+ daily transactions."
                ]
            }
        ]
    }
]


async def seed_persona_profile(user_id: ObjectId, persona: dict[str, Any]) -> None:
    """Ensures profile document exists with persona data and re-scores active jobs."""
    db = get_db()
    now = datetime.now(timezone.utc)

    profile_doc = {
        "user_id": user_id,
        "personal": {
            "fullName": persona["name"],
            "full_name": persona["name"],
            "email": persona["email"],
            "phone": "+91 9971766194",
            "location": {"city": persona["location"].split(",")[0], "country": "India"},
            "github": f"github.com/{persona['discord_username']}",
            "linkedin": f"linkedin.com/in/{persona['id']}",
        },
        "summary": persona["summary"],
        "skills": persona["skills"],
        "experience": persona["experience"],
        "jobPreferences": {
            "jobTitles": persona["target_titles"],
            "locations": ["Noida", "Gurugram", "Delhi NCR"],
            "remotePreference": "any",
            "employmentTypes": ["full-time"],
        },
        "job_preferences": {
            "jobTitles": persona["target_titles"],
            "locations": ["Noida", "Gurugram", "Delhi NCR"],
            "remotePreference": "any",
            "employmentTypes": ["full-time"],
        },
        "completion_score": 95,
        "updated_at": now,
    }

    await db.profiles.update_one(
        {"user_id": user_id},
        {"$set": profile_doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

    # Fast match priority jobs synchronously so matches are instantly populated on /user/jobs
    matcher = JobMatcherAgent()
    cursor = db.jobs.find({"is_active": True}).limit(30)
    async for j in cursor:
        await matcher.match_user_and_job(
            user_id=str(user_id),
            job_id=str(j["_id"]),
            use_ai_reasoning=False,
        )

    # Continue matching the remaining jobs in the background without blocking the login request
    import asyncio
    async def match_remaining():
        try:
            rem_cursor = db.jobs.find({"is_active": True}).skip(30).limit(200)
            async for j in rem_cursor:
                await matcher.match_user_and_job(
                    user_id=str(user_id),
                    job_id=str(j["_id"]),
                    use_ai_reasoning=False,
                )
        except Exception as e:
            logger.warning("Background persona job matching failed", error=str(e))

    asyncio.create_task(match_remaining())
