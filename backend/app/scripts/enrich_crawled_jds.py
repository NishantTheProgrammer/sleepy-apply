#!/usr/bin/env python3
"""
Backfill and Enrich full Job Descriptions (JDs) for all 'career-crawled' jobs in MongoDB.
Fetches real JD content, responsibilities, requirements, and tech skills,
and recalculates user match scores.
"""
import sys
import os
import asyncio
import re

backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from playwright.async_api import async_playwright
from app.db.client import connect_db, get_db
from app.agents.job_matcher import JobMatcherAgent

SKILLS_VOCAB = [
    'Python', 'Java', 'JavaScript', 'TypeScript', 'C++', 'C#', 'Go', 'Rust', 'Ruby', 'PHP', 'Swift', 'Kotlin', 'Scala',
    'React', 'Next.js', 'Vue', 'Angular', 'Node.js', 'FastAPI', 'Django', 'Flask', 'Spring Boot', 'Express',
    'SQL', 'PostgreSQL', 'MySQL', 'MongoDB', 'Redis', 'Cassandra', 'Elasticsearch', 'DynamoDB',
    'AWS', 'Azure', 'GCP', 'Docker', 'Kubernetes', 'Terraform', 'Ansible', 'Linux', 'Unix', 'MacOS', 'Windows', 'Android', 'iOS',
    'Git', 'CI/CD', 'Jenkins', 'GitHub Actions', 'Jira', 'Confluence',
    'Bash', 'Shell', 'PowerShell', 'Datacenter', 'Networking', 'TCP/IP', 'VLAN', 'Routing', 'Switching', 'DNS', 'DHCP',
    'VMware', 'Proxmox', 'Virtualization', 'REST API', 'GraphQL', 'Microservices', 'Kafka', 'RabbitMQ',
    'Machine Learning', 'Deep Learning', 'PyTorch', 'TensorFlow', 'NLP', 'Computer Vision', 'LLM',
    'Selenium', 'Playwright', 'Cypress', 'PySpark', 'Databricks', 'Airflow', 'Snowflake', 'BigQuery'
]


async def main():
    await connect_db()
    db = get_db()
    matcher = JobMatcherAgent()
    users = await db.users.find({"is_active": True}).to_list(100)

    # Find jobs from career-crawled that have brief or placeholder descriptions (< 300 chars)
    cursor = db.jobs.find({"source": "career-crawled"})
    jobs_to_enrich = []
    async for j in cursor:
        jobs_to_enrich.append(j)

    print(f"\n🔍 Found {len(jobs_to_enrich)} career-crawled jobs in MongoDB. Enriching JDs...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for idx, job in enumerate(jobs_to_enrich, 1):
            job_id = job["_id"]
            title = job.get("title", "")
            comp = job.get("company", "")
            target_url = (job.get("application_url") or job.get("source_url") or "").strip()

            print(f"\n[{idx}/{len(jobs_to_enrich)}] 🏢 {comp} - {title}")
            print(f"     URL: {target_url[:80]}")

            if not target_url.startswith("http"):
                print("     ⚠️ Skipped: Invalid URL")
                continue

            try:
                await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(1500)

                extracted = await page.evaluate("""() => {
                    const selectors = [
                        '[data-automation-id="jobPostingDescription"]',
                        '[data-automation-id="job-posting-details"]',
                        '#content', '.posting-description', '.job-description',
                        '.job-details__content', '[class*="jobDescription"]',
                        '[class*="job-description"]', '[class*="JobDescription"]',
                        '[class*="job-details"]', '[class*="JobDetail"]',
                        '#job-description', '#job-details',
                        'article', 'main', '[role="main"]'
                    ];

                    let container = null;
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.innerText && el.innerText.trim().length > 150) {
                            container = el;
                            break;
                        }
                    }
                    if (!container) container = document.body;

                    return {
                        text: container ? container.innerText.trim() : ''
                    };
                }""")

                raw_text = extracted.get("text", "")
                if len(raw_text) > 150:
                    clean_lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
                    resp = []
                    req = []
                    current_sec = None

                    for line in clean_lines:
                        lower = line.lower()
                        if any(k in lower for k in ['responsibilit', 'what will you do', 'what you will do', 'duties', 'the role', 'key expectations']):
                            current_sec = 'resp'
                            continue
                        elif any(k in lower for k in ['desired experience', 'requirement', 'qualification', 'what you bring', 'what we are looking for', 'who you are', 'skills']):
                            current_sec = 'req'
                            continue
                        elif any(k in lower for k in ['who are we', 'about us', 'about the company', 'benefits', 'compensation', 'perks', 'how we hire']):
                            current_sec = None
                            continue

                        if current_sec == 'resp' and 8 <= len(line) <= 350:
                            resp.append(line.lstrip('•-* ').strip())
                        elif current_sec == 'req' and 8 <= len(line) <= 350:
                            req.append(line.lstrip('•-* ').strip())

                    # Technical skills
                    found_skills = set(job.get("required_skills", []))
                    for s in SKILLS_VOCAB:
                        pattern = r'(?<![a-zA-Z0-9])' + re.escape(s) + r'(?![a-zA-Z0-9])'
                        if re.search(pattern, raw_text, re.IGNORECASE):
                            found_skills.add(s)

                    skills_list = sorted(list(found_skills))[:15]

                    # Clean markdown formatted description
                    formatted_jd = (
                        f"### {title}\n\n"
                        f"**Company**: {comp} | **Location**: {job.get('location', 'India')}\n\n"
                        f"#### Overview & Job Description\n\n"
                        f"{raw_text[:3500].strip()}\n"
                    )

                    update_fields = {
                        "description": formatted_jd,
                        "required_skills": skills_list,
                        "requirements": req[:15],
                        "responsibilities": resp[:15],
                        "enriched": True,
                    }

                    await db.jobs.update_one({"_id": job_id}, {"$set": update_fields})
                    print(f"     ✅ Saved full JD: {len(raw_text)} chars | {len(skills_list)} skills | {len(resp)} responsibilities | {len(req)} requirements")

                    # Recompute match scores with updated skills & requirements
                    for u in users:
                        try:
                            await matcher.match_user_and_job(
                                user_id=str(u["_id"]),
                                job_id=str(job_id),
                                use_ai_reasoning=False,
                            )
                        except Exception:
                            pass

                else:
                    print(f"     ⚠️ Page content too short ({len(raw_text)} chars). Skipped.")

            except Exception as e:
                print(f"     ❌ Error fetching JD: {e}")

        await browser.close()

    print("\n🎉 JD enrichment complete for all career-crawled jobs in MongoDB!\n")


if __name__ == "__main__":
    asyncio.run(main())

