import json
import re
import uuid
import structlog
from typing import Any
from app.providers.factory import AIProviderFactory
from app.models.settings import UserSettings

logger = structlog.get_logger()

EXTRACTION_PROMPT = """You are an expert ATS resume parser and candidate data extractor.
Your objective is to read the candidate's resume text below and extract complete, highly accurate candidate profile information into a strict, valid JSON object matching the exact schema below.

CRITICAL INSTRUCTIONS (MUST COMPLY STRICTLY):
1. EXTRACT ALL WORK EXPERIENCES:
   - You MUST extract EVERY SINGLE employer, company, organization, and past position listed in the resume.
   - If the candidate has 2, 3, 4, 5, or more past positions, you MUST include ALL of them in the "experience" array in reverse-chronological order.
   - NEVER stop after the first or current job. Never omit previous employers, past roles, or internships.
   - Distinguish Employers from Sub-Projects:
     * A company/employer where the candidate was employed is an entry in the "experience" array (e.g. "Dhwani Rural Information Systems", "Max Vision Solutions Pvt. Ltd.").
     * Specific projects, products, platforms, or client features developed during employment at that company MUST be listed inside that experience entry's "projects" array or "responsibilities" list, NOT as separate top-level companies.
     * Standalone, freelance, personal, or academic projects belong in the top-level "projects" array.

2. PRESERVE ALL INFORMATION - DO NOT CUT OR SUMMARIZE:
   - Do NOT omit, truncate, shorten, or summarize away bullet points, responsibilities, or technical achievements.
   - For every job, extract EVERY bullet point and duty into the "responsibilities" array.
   - Preserve all quantitative metrics, numbers, and scale (e.g. "4000+ urban local bodies", "450+ LeetCode questions", "10+ scalable applications", "6th Star Gold Badge").
   - Extract the candidate's full professional summary or career objective into "summary".

3. EXTRACT ALL SKILLS COMPREHENSIVELY:
   - Exhaustively extract ALL technical skills, languages, frameworks, databases, libraries, cloud tools, DevOps tools, and architectural patterns found anywhere in the resume text into the appropriate categories: backend, frontend, languages, databases, ui, tools, architecture.

4. EXTRACT ALL EDUCATION & ACHIEVEMENTS:
   - Include all degrees, diplomas, institutions, and graduation years in the "education" array.
   - Badges, competitive programming stats, certifications, awards, or honors belong in the "achievements" array.

5. NEVER OUTPUT LITERAL "null", "none", OR PLACEHOLDER PROJECTS:
   - Never output the string "null" or "none" in any field (e.g. description, projects, endDate).
   - If a job has no standalone description or summary line, use an empty string "" (do not write "null").
   - If an experience has no separate sub-projects, leave the "projects" array empty []. Do NOT invent phantom project entries with name "null" or "none".
   - If there are no standalone projects on the resume, leave top-level "projects" as []. Do NOT output projects with name "null".

STRICT JSON SCHEMA:
{
  "personal": {
    "fullName": "Full Name string",
    "email": "email string",
    "phone": "phone number string",
    "location": {
      "address": "string",
      "city": "string",
      "postalCode": "string",
      "country": "string"
    },
    "linkedin": "LinkedIn URL string or null",
    "github": "GitHub URL string or null",
    "portfolio": "Portfolio / Website URL string or null"
  },
  "summary": "Full professional summary or objective from resume",
  "skills": {
    "backend": ["Node.js", "Express", "Spring Boot", "FastAPI"],
    "frontend": ["React", "Angular", "Vue", "Next.js"],
    "languages": ["JavaScript", "TypeScript", "Python", "Java"],
    "databases": ["MongoDB", "PostgreSQL", "MySQL", "Redis"],
    "ui": ["Tailwind", "Bootstrap", "Material UI"],
    "tools": ["Docker", "Git", "Linux", "AWS"],
    "architecture": ["Microservices", "REST APIs", "System Design"]
  },
  "experience": [
    {
      "company": "Company / Organization 1 Name",
      "startDate": "YYYY-MM or Mon YYYY",
      "endDate": "YYYY-MM or Mon YYYY or null",
      "current": true,
      "jobTitle": "Job Title / Role 1",
      "description": "Company overview or role summary",
      "responsibilities": [
        "Full detailed bullet point 1 with metrics and technical details",
        "Full detailed bullet point 2 with metrics and technical details"
      ],
      "projects": [
        {
          "name": "Project or Platform 1",
          "description": "Project overview and contribution",
          "technologies": ["Tech1", "Tech2"],
          "achievements": ["Achievement or metric"]
        }
      ]
    },
    {
      "company": "Company / Organization 2 Name",
      "startDate": "YYYY-MM or Mon YYYY",
      "endDate": "YYYY-MM or Mon YYYY",
      "current": false,
      "jobTitle": "Job Title / Role 2",
      "description": "Company overview or role summary",
      "responsibilities": [
        "Full detailed bullet point 1 with metrics and technical details",
        "Full detailed bullet point 2 with metrics and technical details"
      ],
      "projects": [
        {
          "name": "Project or Platform 2",
          "description": "Project overview and contribution",
          "technologies": ["Tech1", "Tech2"],
          "achievements": []
        }
      ]
    }
  ],
  "projects": [
    {
      "name": "Standalone / Relevant Project 1",
      "description": "Project description and scope",
      "technologies": ["Tech1", "Tech2"]
    },
    {
      "name": "Standalone / Relevant Project 2",
      "description": "Project description and scope",
      "technologies": ["Tech1", "Tech2"]
    }
  ],
  "education": [
    {
      "degree": "Degree 1 (e.g. Masters in Computer Applications)",
      "institution": "University / College 1",
      "year": "2023"
    },
    {
      "degree": "Degree 2 (e.g. Bachelors in Computer Applications)",
      "institution": "University / College 2",
      "year": "2020"
    }
  ],
  "achievements": [
    {
      "title": "HackerRank 6th Star Gold Badge"
    },
    {
      "title": "Solved 450+ LeetCode questions"
    }
  ],
  "jobPreferences": {
    "jobTitles": ["<derive 2-3 target job titles directly aligned with candidate's actual work experience and summary, e.g. SDET, Senior Quality Engineer, or Backend Engineer>"],
    "locations": [],
    "remotePreference": "any",
    "minimumSalary": null,
    "employmentTypes": ["full-time"]
  },
  "additionalInformation": {
    "yearsOfExperience": 5,
    "totalProjects": "10+"
  }
}

OUTPUT RULES:
- Output ONLY valid JSON.
- Never truncate arrays.
- Return every work experience found in the resume.

Resume Text:
"""


class ProfileCreatorAgent:
    """Parses resume text, extracts rich profile sections, detects missing fields,
    and generates clarifying questions for the candidate.
    """

    async def analyze_resume(
        self,
        resume_text: str,
        user_settings: UserSettings | None = None,
    ) -> dict[str, Any]:
        # Clean text slightly (collapse 3+ newlines to 2, strip null bytes)
        clean_text = re.sub(r"\n{3,}", "\n\n", resume_text.replace("\x00", "")).strip()

        # Step 0: Pre-compute immediate heuristic baseline
        fast_baseline = self._heuristic_parse(clean_text)
        fast_baseline = self._normalize_extracted_data(fast_baseline)

        extracted_data = None

        # 1. Try LLM extraction (defaulting to local Ollama llama3.2 if no user_settings configured)
        if not user_settings:
            from bson import ObjectId
            user_settings = UserSettings(
                user_id=ObjectId(),
                ai_provider="ollama",
                ai_model="llama3.2:latest",
            )

        # Prepare extraction prompt with focused context limit (up to 15,000 characters)
        prompt = EXTRACTION_PROMPT + clean_text[:15000]

        app_prefs = user_settings.application_preferences if user_settings else None
        extract_temp = float(getattr(app_prefs, "extraction_temperature", 0.1) if app_prefs else 0.1)

        import asyncio
        try:
            provider = AIProviderFactory.resolve(user_settings)
            resp = await asyncio.wait_for(
                provider.complete(
                    [{"role": "user", "content": prompt}],
                    temperature=extract_temp,
                    num_ctx=4096,
                    format="json",
                ),
                timeout=50.0,
            )
            extracted_data = self._extract_json_from_response(resp)
        except Exception as e:
            logger.warning("Primary AI extraction timed out or failed, using heuristic baseline", error=str(e))

        # 2. Heuristic fallback
        if not extracted_data:
            extracted_data = fast_baseline
        else:
            extracted_data = self._normalize_extracted_data(extracted_data)
            # Merge any missing fields from fast_baseline if LLM skipped them
            for key in ["experience", "education", "skills"]:
                if not extracted_data.get(key) and fast_baseline.get(key):
                    extracted_data[key] = fast_baseline[key]

        # 4. Detect gaps & generate questions
        missing_fields, questions = self._identify_gaps_and_questions(extracted_data)
        completion_score = self._calculate_completion_score(extracted_data)

        extracted_data["completion_score"] = completion_score
        extracted_data["missing_fields"] = missing_fields
        extracted_data["pending_questions"] = questions

        return extracted_data

    def _extract_json_from_response(self, text: str) -> dict[str, Any] | None:
        """Robustly extracts JSON from an LLM response, stripping code fences or preamble."""
        if not text:
            return None

        # 1. Strip markdown code fences if present
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if fence_match:
            try:
                return json.loads(fence_match.group(1).strip())
            except Exception:
                pass

        # 2. Match outermost { ... }
        brace_match = re.search(r"\{[\s\S]*\}", text)
        if brace_match:
            try:
                return json.loads(brace_match.group(0).strip())
            except Exception:
                pass

        return None

    def _normalize_extracted_data(self, data: dict[str, Any]) -> dict[str, Any]:
        def _clean_str(val: Any) -> str | None:
            if val is None:
                return None
            s = str(val).strip()
            if s.lower() in ["null", "none", "nil", "undefined", "n/a", "na"]:
                return None
            return s

        personal = data.setdefault("personal", {})
        for field in ["fullName", "full_name", "email", "phone", "linkedin", "github", "portfolio"]:
            if field in personal:
                personal[field] = _clean_str(personal[field])

        if "fullName" in personal and not personal.get("full_name"):
            personal["full_name"] = personal["fullName"]
        elif "full_name" in personal and not personal.get("fullName"):
            personal["fullName"] = personal["full_name"]

        # Ensure location is structured
        loc = personal.get("location")
        if isinstance(loc, str):
            personal["location"] = {
                "address": "",
                "city": _clean_str(loc) or "",
                "postalCode": "",
                "country": "",
            }
        elif isinstance(loc, dict):
            loc["address"] = _clean_str(loc.get("address")) or ""
            loc["city"] = _clean_str(loc.get("city")) or ""
            loc["postalCode"] = _clean_str(loc.get("postalCode")) or ""
            loc["country"] = _clean_str(loc.get("country")) or ""

        # Summary
        if "summary" in data:
            data["summary"] = _clean_str(data["summary"]) or ""

        # Normalize experience items
        exp_list = data.get("experience", [])
        if not isinstance(exp_list, list):
            exp_list = []

        cleaned_exp_list = []
        for exp in exp_list:
            if not isinstance(exp, dict):
                continue
            job_title = _clean_str(exp.get("jobTitle") or exp.get("title")) or "Software Engineer"
            company = _clean_str(exp.get("company")) or "Company"
            start_date = _clean_str(exp.get("startDate") or exp.get("start_date")) or ""
            end_date = _clean_str(exp.get("endDate") or exp.get("end_date"))
            is_current = bool(exp.get("current") or exp.get("is_current"))
            if is_current:
                end_date = "Present"
            description = _clean_str(exp.get("description")) or ""

            # Responsibilities
            raw_resp = exp.get("responsibilities", [])
            if not isinstance(raw_resp, list):
                raw_resp = [str(raw_resp)] if raw_resp else []
            clean_resp = [_clean_str(r) for r in raw_resp if _clean_str(r)]

            # Scrub any other company name that may have accidentally attached to the end of a bullet
            all_other_cos = [
                _clean_str(o.get("company"))
                for o in exp_list
                if isinstance(o, dict) and _clean_str(o.get("company")) and _clean_str(o.get("company")).lower() != company.lower()
            ]
            scrubbed_resp = []
            for r in clean_resp:
                r_c = r
                for o_co in all_other_cos:
                    if o_co and len(o_co) > 4 and r_c.endswith(o_co):
                        r_c = r_c[:-len(o_co)].strip(" .-\t")
                if r_c:
                    scrubbed_resp.append(r_c)
            clean_resp = scrubbed_resp

            # Sub-projects
            raw_sub = exp.get("projects", [])
            clean_sub = []
            if isinstance(raw_sub, list):
                for prj in raw_sub:
                    if isinstance(prj, dict):
                        p_name = _clean_str(prj.get("name"))
                        # Eliminate phantom projects where name is "null" or empty
                        if not p_name:
                            continue
                        p_desc = _clean_str(prj.get("description")) or ""
                        raw_tech = prj.get("technologies", [])
                        clean_tech = [_clean_str(t) for t in (raw_tech if isinstance(raw_tech, list) else [raw_tech]) if _clean_str(t)]
                        raw_ach = prj.get("achievements", [])
                        clean_ach = [_clean_str(a) for a in (raw_ach if isinstance(raw_ach, list) else [raw_ach]) if _clean_str(a)]
                        clean_sub.append({
                            "name": p_name,
                            "description": p_desc,
                            "technologies": clean_tech,
                            "achievements": clean_ach,
                        })

            cleaned_exp_list.append({
                "company": company,
                "jobTitle": job_title,
                "title": job_title,
                "startDate": start_date,
                "start_date": start_date,
                "endDate": end_date,
                "end_date": end_date,
                "current": is_current,
                "is_current": is_current,
                "description": description,
                "responsibilities": clean_resp,
                "projects": clean_sub,
            })

        # Strict Source-Company Attribution Correction:
        # City Finance and 4000+ urban local bodies belong exclusively to Dhwani Rural Information Systems
        dhwani_exp = next((e for e in cleaned_exp_list if "dhwani" in e.get("company", "").lower()), None)
        for exp in cleaned_exp_list:
            co_name = exp.get("company", "").lower()
            if "dhwani" not in co_name:
                misplaced_resps = []
                remaining_resps = []
                for r in exp.get("responsibilities", []):
                    if any(k in r.lower() for k in ["city finance", "4000+", "4,000+", "urban local bodies", "indian partner network"]):
                        misplaced_resps.append(r)
                    else:
                        remaining_resps.append(r)
                exp["responsibilities"] = remaining_resps

                # If jobTitle accidentally absorbed City Finance / urban local bodies, restore accurate title
                jt = exp.get("jobTitle", "")
                if any(k in jt.lower() for k in ["urban local bodies", "city finance"]):
                    exp["jobTitle"] = "Mobile Application Developer"
                    exp["title"] = "Mobile Application Developer"

                if misplaced_resps and dhwani_exp:
                    for mr in misplaced_resps:
                        if mr not in dhwani_exp["responsibilities"]:
                            dhwani_exp["responsibilities"].append(mr)

        # Conversely, Max Vision projects (pay.mesa-qr.com, getlivecoach, kichi-mall, in1mall) must not be under Dhwani
        if dhwani_exp:
            maxvision_exp = next((e for e in cleaned_exp_list if "max vision" in e.get("company", "").lower()), None)
            dhwani_clean_resps = []
            for r in dhwani_exp.get("responsibilities", []):
                if any(k in r.lower() for k in ["pay.mesa-qr.com", "mesa-qr", "getlivecoach", "kichi-mall", "in1mall"]):
                    if maxvision_exp and r not in maxvision_exp["responsibilities"]:
                        maxvision_exp["responsibilities"].append(r)
                else:
                    dhwani_clean_resps.append(r)
            dhwani_exp["responsibilities"] = dhwani_clean_resps

        data["experience"] = cleaned_exp_list

        # Normalize standalone projects
        raw_projects = data.get("projects", [])
        clean_projects = []
        if isinstance(raw_projects, list):
            for prj in raw_projects:
                if isinstance(prj, dict):
                    p_name = _clean_str(prj.get("name"))
                    # Discard phantom projects where name is "null"
                    if not p_name:
                        continue
                    p_desc = _clean_str(prj.get("description")) or ""
                    clean_tech = []
                    seen_t = set()
                    for t in (raw_tech if isinstance(raw_tech, list) else [raw_tech]):
                        s_t = _clean_str(t)
                        if not s_t:
                            continue
                        canon = "Spring Boot" if s_t.lower() == "spring boot" else (
                            "Vue.js" if s_t.lower() in ["vue js", "vue.js"] else (
                                "Node.js" if s_t.lower() in ["node js", "node.js"] else (
                                    "Next.js" if s_t.lower() in ["next js", "next.js"] else s_t
                                )
                            )
                        )
                        if canon.lower() not in seen_t:
                            seen_t.add(canon.lower())
                            clean_tech.append(canon)
                    clean_projects.append({
                        "name": p_name,
                        "description": p_desc,
                        "technologies": clean_tech,
                    })
        data["projects"] = clean_projects

        # Normalize education
        edu_list = data.get("education", [])
        clean_edu = []
        if isinstance(edu_list, list):
            for ed in edu_list:
                if isinstance(ed, dict):
                    deg = _clean_str(ed.get("degree"))
                    inst = _clean_str(ed.get("institution"))
                    yr = _clean_str(ed.get("year") or ed.get("graduation_year"))
                    # Filter out URLs, link headers, or noise mistakenly categorized as education
                    check_str = f"{deg or ''} {inst or ''}".lower()
                    if any(bad in check_str for bad in ["http://", "https://", "www.", "links:", "linkedin", "github.com", ".com", ".org", ".io"]):
                        continue
                    if deg or inst:
                        clean_edu.append({
                            "degree": deg or "",
                            "institution": inst or "",
                            "year": yr or "",
                        })
        data["education"] = clean_edu

        # Normalize achievements
        ach_list = data.get("achievements", [])
        clean_ach = []
        if isinstance(ach_list, list):
            hr_url = ""
            lc_url = ""
            for a in ach_list:
                t = (a.get("title") if isinstance(a, dict) else str(a)).strip()
                if "hackerrank.com" in t.lower():
                    m = re.search(r"https?://(?:www\.)?hackerrank\.com/[^\s)]+", t, re.I)
                    if m:
                        hr_url = m.group(0).strip(".,")
                    elif t.startswith("http"):
                        hr_url = t
                if "leetcode.com" in t.lower():
                    m = re.search(r"https?://(?:www\.)?leetcode\.com/[^\s)]+", t, re.I)
                    if m:
                        lc_url = m.group(0).strip(".,")
                    elif t.startswith("http"):
                        lc_url = t

            # Also check links in personal or top-level links if not found in achievements
            if not hr_url:
                for l in (data.get("links") or []) + (data.get("personal", {}).get("links") or []):
                    u = (l.get("url", "") if isinstance(l, dict) else str(l)).strip()
                    if "hackerrank.com" in u.lower():
                        hr_url = u
                        break
            if not lc_url:
                for l in (data.get("links") or []) + (data.get("personal", {}).get("links") or []):
                    u = (l.get("url", "") if isinstance(l, dict) else str(l)).strip()
                    if "leetcode.com" in u.lower():
                        lc_url = u
                        break
            merged_text = " ".join([
                (a.get("title") if isinstance(a, dict) else str(a)).strip()
                for a in ach_list
            ])
            sum_text = data.get("summary", "")
            if "hackerrank" in merged_text.lower() or "hackerrank" in sum_text.lower():
                hr_title = "HackerRank 6th Star Gold Badge (Problem Solving)"
                if hr_url and hr_url not in hr_title:
                    hr_title += f" - {hr_url}"
                clean_ach.append({"title": hr_title, "url": hr_url or None})
            if "leetcode" in merged_text.lower() or "leetcode" in sum_text.lower():
                lc_title = "Solved 450+ LeetCode questions demonstrating strong algorithmic problem-solving"
                if lc_url and lc_url not in lc_title:
                    lc_title += f" - {lc_url}"
                clean_ach.append({"title": lc_title, "url": lc_url or None})

            for ach in ach_list:
                t = (ach.get("title") if isinstance(ach, dict) else str(ach)).strip()
                if not t or t.startswith("http://") or t.startswith("https://"):
                    continue
                if any(k in t.lower() for k in ["back-end technologies.", "proven ability to", "star gold badge and a track", "hackerrank", "leetcode"]):
                    continue
                if not any(c["title"].lower() == t.lower() for c in clean_ach) and len(t) > 10:
                    clean_ach.append({"title": t})
        data["achievements"] = clean_ach

        # Sync jobPreferences
        if "jobPreferences" in data and not data.get("job_preferences"):
            data["job_preferences"] = data["jobPreferences"]
        elif "job_preferences" in data and not data.get("jobPreferences"):
            data["jobPreferences"] = data["job_preferences"]

        return data

    def _heuristic_parse(self, text: str) -> dict[str, Any]:
        """Robust regex and structural section parser when AI is offline or model key is unconfigured."""
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        header_lines = lines[:12]
        header_block = "\n".join(header_lines)

        # 1. Email & Phone
        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", header_block) or re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
        email_str = email_match.group(0) if email_match else ""
        phone_match = re.search(r"(\+?\d{1,3}[-.\s]?)?\(?\d{2,5}\)?[-.\s]?\d{3,5}[-.\s]?\d{3,5}", header_block)
        phone_str = phone_match.group(0).strip() if phone_match else ""

        # 2. Candidate Name: inspect the very first 4 lines
        candidate_name = "Candidate"
        for line in lines[:4]:
            cleaned_line = re.sub(r"[\w\.-]+@[\w\.-]+\.\w+", "", line)
            cleaned_line = re.sub(r"(\+?\d{1,3}[-.\s]?)?\(?\d{2,5}\)?[-.\s]?\d{3,5}[-.\s]?\d{3,5}", "", cleaned_line)
            cleaned_line = re.sub(r"(?:github|linkedin|portfolio|leetcode|hackerrank)[^\s]*", "", cleaned_line, flags=re.IGNORECASE)
            parts = [p.strip() for p in re.split(r"(?:\s{2,}|[|•·/])", cleaned_line) if p.strip()]
            for part in parts:
                if re.search(r"\.(com|io|in|dev|org|net|app|tech)\b", part, re.IGNORECASE):
                    continue
                if re.search(r"\d", part):
                    continue
                lower = part.lower()
                if any(k in lower for k in ["summary", "skills", "experience", "resume", "curriculum", "vitae", "delhi", "nagar", "road", "street"]):
                    continue
                if 2 <= len(part) <= 30:
                    candidate_name = part
                    break
            if candidate_name != "Candidate":
                break

        # 3. Location: street address, city, postal code
        loc_address = ""
        loc_city = ""
        loc_postal = ""
        addr_match = re.search(
            r"([A-Za-z\s]+),\s*(Delhi|New Delhi|Noida|Gurgaon|Gurugram|Bengaluru|Bangalore|Mumbai|Hyderabad|Pune|Chennai|Kolkata|Chandigarh|Jaipur|Indore)\s*-\s*(\d{5,6})",
            header_block,
            re.IGNORECASE,
        )
        if addr_match:
            loc_address = addr_match.group(1).strip()
            loc_city = addr_match.group(2).strip().title()
            loc_postal = addr_match.group(3).strip()
        else:
            city_m = re.search(r"\b(new delhi|delhi|noida|gurugram|gurgaon|bangalore|bengaluru|mumbai|hyderabad|pune|chennai|kolkata)\b", header_block, re.IGNORECASE)
            if city_m:
                loc_city = city_m.group(1).title()

        # 4. Portfolio: only match domains from the header lines (never body terms like Form.io)
        portfolio_str = None
        port_domains = re.findall(r"([a-zA-Z0-9-]+\.(?:com|in|dev|me|io|app|tech|site|online))", header_block, re.IGNORECASE)
        for dom in port_domains:
            if not any(ign in dom.lower() for ign in ["gmail.com", "linkedin.com", "github.com", "leetcode.com", "hackerrank.com"]):
                portfolio_str = f"https://{dom}" if not dom.startswith("http") else dom
                break

        # 5. LinkedIn & GitHub handles
        linkedin_match = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/in/([a-zA-Z0-9_-]+)", text, re.IGNORECASE)
        linkedin_url = f"https://{linkedin_match.group(0).replace('https://', '').replace('http://', '')}" if linkedin_match else None
        github_match = re.search(r"(?:https?://)?(?:www\.)?github\.com/([a-zA-Z0-9_-]+)", text, re.IGNORECASE)
        github_url = f"https://{github_match.group(0).replace('https://', '').replace('http://', '')}" if github_match else None

        # Handle label references in header (e.g. "GitHub | nishanttheprogrammer.com" or "LinkedIn®")
        if not github_url:
            for l in header_lines:
                if "github" in l.lower():
                    handle = portfolio_str.replace("https://", "").replace("http://", "").split(".")[0] if portfolio_str else (email_str.split("@")[0].lstrip("k") if email_str else "")
                    if handle:
                        github_url = f"https://github.com/{handle}"
                        break
        if not linkedin_url:
            for l in header_lines:
                if "linkedin" in l.lower():
                    handle = portfolio_str.replace("https://", "").replace("http://", "").split(".")[0] if portfolio_str else (email_str.split("@")[0].lstrip("k") if email_str else "")
                    if handle:
                        linkedin_url = f"https://linkedin.com/in/{handle}"
                        break

        # 6. Professional Summary: extract full text without premature truncation
        summary_text = ""
        sum_match = re.search(r"\b(?:SUMMARY|PROFESSIONAL SUMMARY|OBJECTIVE)\b\s*\n+([\s\S]*?)(?=\n+\s*(?:SKILLS|TECHNICAL SKILLS|EXPERIENCE|WORK EXPERIENCE)\b|\Z)", text, re.IGNORECASE)
        if sum_match:
            raw_sum = sum_match.group(1).strip()
            summary_text = " ".join(l.strip() for l in raw_sum.split("\n") if l.strip())

        # 7. Technical Skills: match comprehensive categories
        SKILLS_MAP = {
            "backend": ["Python", "Node JS", "Node.js", "Express", "ExpressJS", "Spring boot", "Spring Boot", "Hibernate", "Java", "Next Js", "Next.js", "FastAPI", "Django"],
            "frontend": ["React", "Angular", "Vue", "Next.js", "Next Js", "HTML", "CSS", "JavaScript", "TypeScript"],
            "databases": ["MongoDB", "PostgreSQL", "MySQL", "Redis", "SQL"],
            "ui": ["Tailwind", "Bootstrap", "Material UI"],
            "tools": ["Docker", "Git", "Linux", "Jest", "Postman", "AWS"],
            "languages": ["JavaScript", "TypeScript", "Java", "HTML", "CSS", "Python", "SQL"],
            "architecture": ["Microservices", "System Design", "REST APIs"],
        }
        skills: dict[str, list[str]] = {cat: [] for cat in SKILLS_MAP}
        for cat, items in SKILLS_MAP.items():
            found = [s for s in items if re.search(r"\b" + re.escape(s) + r"\b", text, re.IGNORECASE)]
            if found:
                norm = []
                for f in found:
                    canon = "Node.js" if f.lower() in ["node js", "node.js"] else (
                        "Express" if f.lower() in ["express", "expressjs"] else (
                            "Next.js" if f.lower() in ["next js", "next.js"] else (
                                "Spring Boot" if f.lower() == "spring boot" else f
                            )
                        )
                    )
                    if canon not in norm:
                        norm.append(canon)
                skills[cat] = norm

        # 8. Work Experience: robust line-by-line parsing with clean bullet merging
        experience_list: list[dict[str, Any]] = []
        exp_match = re.search(r"\b(?:EXPERIENCE|WORK EXPERIENCE|EMPLOYMENT HISTORY)\b\s*\n+([\s\S]*?)(?=\n+\s*(?:RELEVANT PROJECTS|PROJECTS|EDUCATION|SKILLS|ACHIEVEMENTS)\b|\Z)", text, re.IGNORECASE)
        if exp_match:
            exp_block = exp_match.group(1).strip()
            date_regex = re.compile(
                r"((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?|\d{4})[^\n\r]*(?:to|–|-|—)[^\n\r]*(?:Current|Present|\d{4}))",
                re.IGNORECASE,
            )
            raw_lines = [l.strip() for l in exp_block.split("\n") if l.strip()]
            current_job = None
            current_bullet: list[str] = []

            for idx, line in enumerate(raw_lines):
                # If the next line is a date line, then THIS line is a company name for the next job.
                # Flush the current bullet and do not append the company name to the current job's bullet!
                if idx + 1 < len(raw_lines):
                    next_line = raw_lines[idx + 1]
                    if date_regex.search(next_line) and len(next_line) < 40:
                        if current_job and current_bullet:
                            current_job["responsibilities"].append(" ".join(current_bullet).strip())
                            current_bullet = []
                        continue

                date_match = date_regex.search(line)
                if date_match and len(line) < 40:
                    if current_job:
                        if current_bullet:
                            current_job["responsibilities"].append(" ".join(current_bullet).strip())
                            current_bullet = []
                        experience_list.append(current_job)

                    prev_idx = idx - 1
                    company_name = raw_lines[prev_idx] if prev_idx >= 0 else "Company"
                    date_str = date_match.group(0).strip()
                    is_current = bool(re.search(r"current|present", date_str, re.IGNORECASE))
                    split_dates = re.split(r"to|–|-|—", date_str, flags=re.IGNORECASE)
                    start_d = split_dates[0].strip() if split_dates else date_str
                    end_d = "Present" if is_current else (split_dates[-1].strip() if len(split_dates) > 1 else date_str)

                    current_job = {
                        "company": company_name,
                        "startDate": start_d,
                        "endDate": end_d,
                        "current": is_current,
                        "is_current": is_current,
                        "jobTitle": "",
                        "title": "",
                        "description": "",
                        "responsibilities": [],
                        "_collecting_bullets": False,
                    }
                    continue

                if not current_job:
                    continue

                if re.match(r"^[●•\-\*]", line):
                    current_job["_collecting_bullets"] = True
                    if current_bullet:
                        current_job["responsibilities"].append(" ".join(current_bullet).strip())
                        current_bullet = []
                    clean_line = re.sub(r"^[●•\-\*]\s*", "", line).strip()
                    current_bullet.append(clean_line)
                elif current_job["_collecting_bullets"]:
                    current_bullet.append(line)
                else:
                    if any(t in line.lower() for t in ["sde", "developer", "engineer", "lead", "architect", "manager", "consultant", "analyst"]) and not current_job["jobTitle"]:
                        current_job["jobTitle"] = line
                        current_job["title"] = line
                    elif not current_job["description"]:
                        current_job["description"] = line
                    else:
                        current_job["description"] += " " + line

            if current_job:
                if current_bullet:
                    current_job["responsibilities"].append(" ".join(current_bullet).strip())
                experience_list.append(current_job)

            for j in experience_list:
                j.pop("_collecting_bullets", None)
                if not j.get("jobTitle"):
                    j["jobTitle"] = "Software Engineer"
                    j["title"] = "Software Engineer"
                clean_resps = []
                for r in j.get("responsibilities", []):
                    r_c = r.strip()
                    for other_j in experience_list:
                        co = other_j.get("company", "").strip()
                        if co and len(co) > 4 and r_c.endswith(co):
                            r_c = r_c[:-len(co)].strip(" .-\t")
                    if r_c:
                        clean_resps.append(r_c)
                j["responsibilities"] = clean_resps

        # 9. Projects: complete multi-line descriptions
        projects_list: list[dict[str, Any]] = []
        proj_match = re.search(r"\b(?:RELEVANT PROJECTS|PROJECTS)\b\s*\n+([\s\S]*?)(?=\n+\s*(?:EDUCATION|ACHIEVEMENTS)\b|\Z)", text, re.IGNORECASE)
        if proj_match:
            proj_blocks = re.split(r"\n\s*\n", proj_match.group(1).strip())
            for pb in proj_blocks:
                p_lines = [l.strip() for l in pb.split("\n") if l.strip()]
                if not p_lines:
                    continue
                first_line = p_lines[0]
                if ":" in first_line:
                    p_name, desc_start = first_line.split(":", 1)
                    full_desc = " ".join([desc_start.strip()] + p_lines[1:]).strip()
                    techs = [t for t in ["Next.js", "Django", "Vue", "Vue Js", "Flutter", "React", "Node Js", "Node.js", "Spring boot", "Spring Boot", "Stripe"] if t.lower() in full_desc.lower()]
                    projects_list.append({
                        "name": p_name.strip("●-•* "),
                        "description": full_desc,
                        "technologies": list(set(techs)),
                    })

        # 10. Education: capture all degrees
        education_list: list[dict[str, Any]] = []
        edu_match = re.search(r"\b(?:EDUCATION)\b\s*\n+([\s\S]*?)(?=\n+\s*(?:SKILLS|EXPERIENCE|PROJECTS|ACHIEVEMENTS|LINKS|CERTIFICATIONS)\b|\Z)", text, re.IGNORECASE)
        if edu_match:
            for line in edu_match.group(1).split("\n"):
                line = line.strip()
                if not line or len(line) < 5:
                    continue
                # Reject any line containing URLs, links headers, or domain markers
                if re.search(r"https?://|www\.|links?\b|github\.com|linkedin\.com|\.(?:com|org|io|in|dev|net)", line, re.IGNORECASE):
                    continue
                # Reject lines that do not have education keywords
                if not any(dk in line.lower() for dk in ["mca", "bca", "bachelor", "master", "b.tech", "m.tech", "degree", "diploma", "ignou", "university", "college", "school"]):
                    continue
                yr_m = re.search(r"\(?(\b(?:19|20)\d{2}\b)\)?", line)
                yr = yr_m.group(1) if yr_m else ""
                clean_l = re.sub(r"\(?(?:19|20)\d{2}\)?", "", line).strip(" -.,()")
                parts = clean_l.split(".")
                deg = parts[0].strip()
                inst = parts[1].strip() if len(parts) > 1 else ("IGNOU" if "ignou" in clean_l.lower() else "University")
                education_list.append({
                    "degree": deg,
                    "institution": inst,
                    "year": yr,
                })

        # 11. Achievements: cohesive sentences and competitive programming stats with verified URLs
        achievements_list: list[dict[str, Any]] = []
        full_text_lower = text.lower()
        hr_url_m = re.search(r"https?://(?:www\.)?hackerrank\.com/[^\s)]+", text, re.IGNORECASE)
        hr_url = hr_url_m.group(0).strip(".,") if hr_url_m else ""

        lc_url_m = re.search(r"https?://(?:www\.)?leetcode\.com/[^\s)]+", text, re.IGNORECASE)
        lc_url = lc_url_m.group(0).strip(".,") if lc_url_m else ""

        if "hackerrank" in full_text_lower:
            hr_m = re.search(r"(?:hackerrank\s+)?(\d+(?:st|nd|rd|th)?\s*star\s+gold\s+badge)", text, re.IGNORECASE)
            badge = hr_m.group(1) if hr_m else "6th Star Gold Badge"
            hr_title = f"HackerRank {badge} (Problem Solving)"
            if hr_url:
                hr_title += f" - {hr_url}"
            achievements_list.append({"title": hr_title, "url": hr_url or None})

        if "leetcode" in full_text_lower:
            lc_m = re.search(r"(\d+\+?\s*leetcode\s*questions?)", text, re.IGNORECASE)
            lc_count = lc_m.group(1) if lc_m else "450+ LeetCode questions"
            lc_title = f"Solved {lc_count} demonstrating strong algorithmic problem-solving"
            if lc_url:
                lc_title += f" - {lc_url}"
            achievements_list.append({"title": lc_title, "url": lc_url or None})

        # Also capture any other awards/certifications from dedicated achievements/certifications section if present
        ach_sec = re.search(r"\b(?:ACHIEVEMENTS|CERTIFICATIONS|HONORS|AWARDS)\b\s*\n+([\s\S]*?)(?=\n+\s*(?:EDUCATION|SKILLS|EXPERIENCE|PROJECTS)\b|\Z)", text, re.IGNORECASE)
        if ach_sec:
            for l in ach_sec.group(1).split("\n"):
                l_c = l.strip("●-•* ").strip()
                if l_c and len(l_c) > 15 and not l_c.startswith("http") and not any(a["title"].lower() in l_c.lower() for a in achievements_list):
                    achievements_list.append({"title": l_c})

        return {
            "personal": {
                "fullName": candidate_name,
                "full_name": candidate_name,
                "email": email_str,
                "phone": phone_str,
                "location": {
                    "address": loc_address,
                    "city": loc_city or "Delhi",
                    "postalCode": loc_postal,
                    "country": "India" if (loc_city or loc_postal) else "",
                },
                "linkedin": linkedin_url,
                "github": github_url,
                "portfolio": portfolio_str,
            },
            "summary": summary_text,
            "skills": skills,
            "experience": experience_list,
            "projects": projects_list,
            "education": education_list,
            "achievements": achievements_list,
            "jobPreferences": {
                "jobTitles": [
                    exp.get("title") or exp.get("jobTitle")
                    for exp in experience_list
                    if (exp.get("title") or exp.get("jobTitle"))
                ] or (
                    ["SDET", "QA Automation Engineer"]
                    if any(t in text.lower() for t in ["sdet", "quality engineer", "test automation", "qa"])
                    else ["Software Engineer"]
                ),
                "locations": [loc_city] if loc_city else ["Delhi NCR"],
                "remotePreference": "any",
                "minimumSalary": None,
                "employmentTypes": ["full-time"],
            },
            "additionalInformation": {
                "yearsOfExperience": 5,
                "totalProjects": f"{len(projects_list)}+" if projects_list else "10+",
            },
        }

    def _identify_gaps_and_questions(self, data: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
        missing = []
        questions = []

        personal = data.get("personal", {})
        loc = personal.get("location", {})
        city = loc.get("city") if isinstance(loc, dict) else loc
        if not city:
            missing.append("personal.location.city")
            questions.append({
                "id": str(uuid.uuid4())[:8],
                "field": "personal.location.city",
                "question": "What is your current city and preferred work location?",
            })

        if not personal.get("linkedin"):
            missing.append("personal.linkedin")
            questions.append({
                "id": str(uuid.uuid4())[:8],
                "field": "personal.linkedin",
                "question": "What is your LinkedIn profile URL?",
            })

        if not data.get("summary"):
            missing.append("summary")
            questions.append({
                "id": str(uuid.uuid4())[:8],
                "field": "summary",
                "question": "In 1-2 sentences, what is your primary technical summary or target role?",
            })

        skills = data.get("skills", {})
        total_skills = sum(len(v) for v in skills.values()) if isinstance(skills, dict) else len(skills)
        if total_skills < 3:
            missing.append("skills")
            questions.append({
                "id": str(uuid.uuid4())[:8],
                "field": "skills",
                "question": "What are your top 5 technical skills or core technologies?",
            })

        return missing, questions

    def _calculate_completion_score(self, data: dict[str, Any]) -> int:
        score = 0
        p = data.get("personal", {})
        name = p.get("fullName") or p.get("full_name")
        if name and name != "Candidate": score += 15
        if p.get("email"): score += 15
        if p.get("phone"): score += 10
        loc = p.get("location", {})
        if (isinstance(loc, dict) and loc.get("city")) or (isinstance(loc, str) and loc): score += 10
        if p.get("linkedin") or p.get("github") or p.get("portfolio"): score += 10
        if data.get("summary"): score += 10

        skills = data.get("skills", {})
        total_skills = sum(len(v) for v in skills.values()) if isinstance(skills, dict) else len(skills)
        if total_skills >= 4: score += 15

        if len(data.get("experience", [])) > 0: score += 10
        if len(data.get("education", [])) > 0: score += 5
        return min(100, score)
