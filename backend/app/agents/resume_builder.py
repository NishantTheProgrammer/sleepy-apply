import os
import re
import json
import hashlib
from datetime import datetime, timezone
from typing import Any
import structlog
from bson import ObjectId

from app.db.client import get_db
from app.templates.default import DefaultATSResumeTemplate
from app.providers.factory import AIProviderFactory
from app.models.profile import CanonicalDict
from app.models.settings import UserSettings
from app.agents.evidence_mapper import EvidenceMapper, EvidenceMappingResult
from app.agents.hallucination_guard import HallucinationGuard, ValidationResult

logger = structlog.get_logger()

RESUME_TAILOR_PROMPT = """You are a senior technical hiring manager and staff engineer tailoring a candidate's resume for a specific software engineering role.
Your mission is to maximize ATS keyword alignment and technical credibility while keeping the output 100% authentic, grounded, and human-written.

TARGET JOB DETAILS:
- Target Role: {job_title}
- Target Company: {company}
- Key Required Skills: {required_skills}
- Job Description Context:
{job_description}

EVIDENCE MAPPING & FACTUAL BOUNDARIES (COMPLY STRICTLY):
1. VERIFIED MATCHED SKILLS (PROVEN IN CANDIDATE BACKGROUND):
{matched_skills_evidence}

2. PARTIALLY MATCHED & PROJECT-LEVEL SKILLS (STRICT ATTRIBUTION):
{partial_skills_evidence}
* RULE: If a technology is from an independent or academic project, describe it accurately as hands-on project experience. NEVER claim multi-year professional employment for project-only technologies!
* STRICT SUMMARY RULE: Any PARTIALLY MATCHED technology (e.g. from candidate's independent projects) is PROJECT-LEVEL experience only. NEVER claim "proven expertise in [Tech]" or seasoned professional background for project-only technologies. If mentioned in summary, you MUST state "Hands-on project experience in [Tech] through [Project Name]".

3. UNVERIFIED / MISSING JD REQUIREMENTS (DO NOT CLAIM):
{missing_skills_list}
* CRITICAL RULE: The candidate has ZERO verified evidence for these technologies. You MUST NOT claim them, put them in the headline, summary, experience highlights, or skills!

4. OVERALL EXPERIENCE GROUNDING:
- Candidate has {overall_years:g} years of overall software development experience.
- NEVER inflate experience (do not claim >{overall_years:g} years or copy JD years like 6-8 years).
- NEVER convert overall Full Stack experience into tech-specific experience (e.g. never say "{overall_years:g}+ years of Java developer").

5. LEADERSHIP, MENTORING & TEAM SIZES:
- Leadership, mentoring, technical interviews, and PR reviews belong strictly to the employer where they were performed. NEVER attach employment responsibilities to personal/independent projects.
- DO NOT invent team sizes (e.g. do NOT write "mentored team of 4-6 engineers" unless specifically stated in source notes). State authentic mentoring actions without headcounts.

6. EDUCATION FIDELITY:
- Candidate holds: {education_summary}.
- Do NOT alter degrees or claim B.Tech/BE.

7. BANNED AI BUZZWORDS:
- Do NOT use: "spearheaded", "synergized", "leveraged", "delve", "pivotal", "transformative", "game-changing", "visionary", "testament to", "holistic", "cutting-edge", or "revolutionized".
- Use concrete engineering action verbs: Built, Designed, Implemented, Refactored, Maintained, Optimized, Automated, Integrated, Migrated, Deployed, Resolved, Scaled.

8. GOOGLE X-Y-Z FORMULA (REALISTIC OUTCOMES):
- Format bullets following: Accomplished [X], as measured by [Y], by doing [Z].
- Use authentic metrics from candidate notes (e.g. "handling data for 4000+ urban local bodies", "10+ scalable applications", "solving 450+ LeetCode problems").
- NEVER invent corporate financial figures (e.g. "$40M revenue increase", "99.999% efficiency leap").
- NO UNSUPPORTED OUTCOME CLAIMS: Do NOT invent outcomes like "enhancing workflow efficiency", "improving team coordination", "boosting productivity", or "streamlining operations" unless that exact outcome is explicitly present in the source candidate profile. Keep descriptions strictly factual based on what was built and used.

Return ONLY a valid JSON object matching this exact schema:
{{
  "target_headline": "Professional Role Headline | Primary Verified Tech Stacks",
  "tailored_summary": "2-3 sentence impactful summary accurately reflecting overall experience and verified strengths with selective **bold** keywords",
  "tailored_experience": [
    {{
      "company": "Exact Company Name",
      "highlights": [
        "Action verb + technical accomplishment + realistic outcome with selective **bold** verified tech"
      ]
    }}
  ],
  "tailored_projects": [
    {{
      "name": "Exact Name of matching project from candidate's background",
      "technologies": ["matching", "technologies"],
      "description": "Realistic 1-2 sentence description highlighting verified tech and architecture"
    }}
  ]
}}
"""


def select_and_tailor_projects(
    raw_projects: list[dict],
    required_skills: list[str],
    matching_skills: list[str],
    job_title: str,
    company: str = "",
    max_projects: int = 3,
    filter_irrelevant: bool = True,
    ai_projects: list[dict] | None = None,
    bold_enabled: bool = True,
    candidate_experience: list[dict] | None = None,
) -> list[dict]:
    """Filter candidate personal projects to prioritize high-relevance projects while preserving authenticity."""
    if not raw_projects:
        return []

    authentic_map = {}
    for idx, p in enumerate(raw_projects):
        name = (p.get("name") or p.get("title") or "").strip()
        if name:
            authentic_map[name.lower()] = (idx, p)

    employment_duty_patterns = [
        r"\b(?:mentored|mentoring)\s+(?:junior\s+developers?|engineers?|team)\b",
        r"\b(?:conducted|conducting)\s+(?:technical\s+)?interviews?\b",
        r"\b(?:reviewing|reviewed)\s+pull\s+requests?\b",
        r"\b(?:code\s+reviews?\s+and\s+pr\s+reviews?|pr\s+reviews?)\b",
    ]

    # 1. Match AI-selected projects against authentic candidate projects
    if ai_projects and isinstance(ai_projects, list):
        matched_ai_projects = []
        used_auth_names = set()
        for aip in ai_projects:
            if not isinstance(aip, dict):
                continue
            aip_name = (aip.get("name") or aip.get("title") or "").strip()
            if not aip_name:
                continue

            matched_auth = None
            orig_idx = 0
            for auth_name, (idx, auth_p) in authentic_map.items():
                if auth_name in used_auth_names:
                    continue
                if auth_name in aip_name.lower() or aip_name.lower() in auth_name:
                    matched_auth = auth_p
                    orig_idx = idx
                    used_auth_names.add(auth_name)
                    break

            if matched_auth:
                proj_copy = dict(matched_auth)
                orig_desc = proj_copy.get("description", "")
                ai_desc = (aip.get("description") or "").strip()

                # Verify explicit source provenance: prevent employment duties from leaking into project descriptions
                has_duty_leak = any(
                    re.search(edp, ai_desc, re.IGNORECASE) and not re.search(edp, orig_desc, re.IGNORECASE)
                    for edp in employment_duty_patterns
                )
                desc_to_use = orig_desc if has_duty_leak or not ai_desc else ai_desc

                # Strip unsupported outcome claims
                unsupported_outcome_patterns = [
                    r",?\s*(?:enhancing|improving|increasing|boosting)\s+(?:workflow|operational|team|developer)?\s*efficiency(?:\s+and\s+team\s+coordination)?",
                    r",?\s*(?:and\s+)?improving\s+team\s+coordination",
                    r",?\s*(?:and\s+)?streamlining\s+company\s+operations\s+and\s+improve\s+team\s+coordination",
                    r",?\s*(?:optimizing|maximizing)\s+(?:workflow|operational|team)?\s*productivity",
                    r",?\s*(?:accelerating|driving)\s+(?:project\s+delivery|business\s+growth)",
                ]
                for uop in unsupported_outcome_patterns:
                    desc_to_use = re.sub(uop, "", desc_to_use, flags=re.IGNORECASE)
                desc_to_use = " ".join(desc_to_use.split()).strip(" ,.-")
                if not desc_to_use:
                    desc_to_use = orig_desc

                if bold_enabled and desc_to_use:
                    for ms in matching_skills:
                        if (
                            len(ms) > 2
                            and ms.lower() in desc_to_use.lower()
                            and f"**{ms}**" not in desc_to_use
                            and f"**{ms.lower()}**" not in desc_to_use.lower()
                        ):
                            pattern = re.compile(rf"\b{re.escape(ms)}\b", re.IGNORECASE)
                            desc_to_use = pattern.sub(f"**{ms}**", desc_to_use)

                proj_copy["description"] = desc_to_use
                if aip.get("technologies") and isinstance(aip["technologies"], list):
                    # Clean tech tags
                    clean_ai_tech = []
                    seen_t = set()
                    for t in aip["technologies"]:
                        c = str(t).strip()
                        if c and c.lower() not in seen_t:
                            seen_t.add(c.lower())
                            clean_ai_tech.append(c)
                    proj_copy["technologies"] = clean_ai_tech

                clean_ai_p = CanonicalDict({
                    "id": proj_copy.get("id") or f"project_{len(matched_ai_projects)+1:03d}",
                    "name": aip_name,
                    "description": desc_to_use,
                    "technologies": proj_copy.get("technologies") or [],
                })
                if proj_copy.get("url"):
                    clean_ai_p["url"] = proj_copy["url"]
                matched_ai_projects.append(clean_ai_p)
                if len(matched_ai_projects) >= max_projects:
                    break

        if matched_ai_projects:
            return matched_ai_projects

    # 2. Rule-based relevance scoring and filtering fallback
    job_words = [
        w.lower()
        for w in re.findall(r"\w+", f"{job_title} {company}")
        if len(w) > 2
        and w.lower()
        not in {
            "and", "the", "for", "with", "senior", "lead", "staff", "junior", "engineer", "developer", "specialist", "manager"
        }
    ]

    scored_projects = []
    for p in raw_projects:
        p_name = (p.get("name") or p.get("title") or "").strip()
        p_desc = (p.get("description") or "").strip()
        p_tech = [str(t).strip() for t in (p.get("technologies") or p.get("tech_stack") or [])]
        tech_str = " ".join(p_tech).lower()
        full_text = f"{p_name} {p_desc} {tech_str}".lower()

        score = 0
        for ms in matching_skills:
            ms_clean = ms.lower().strip()
            if not ms_clean:
                continue
            if ms_clean in tech_str:
                score += 5
            elif ms_clean in full_text:
                score += 2

        for rs in required_skills:
            rs_clean = rs.lower().strip()
            if not rs_clean:
                continue
            if rs_clean in tech_str:
                score += 4
            elif rs_clean in full_text:
                score += 2

        # Special boost for backend matching projects
        if "backend" in job_title.lower() or "java" in " ".join(required_skills).lower():
            if "spring" in full_text or "django" in full_text:
                score += 4
            if "node" in full_text and "api" in full_text:
                score += 3

        for jw in job_words:
            if jw in full_text:
                score += 2

        is_academic = any(
            ac in full_text
            for ac in ["college project", "academic project", "class project", "university project", "semester"]
        )
        if is_academic and len(raw_projects) > 2:
            score -= 3

        scored_projects.append((score, len(p_tech), len(p_desc), p))

    scored_projects.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)

    if filter_irrelevant:
        positive_scored = [sp[3] for sp in scored_projects if sp[0] > 0]
        if positive_scored:
            selected_raw = positive_scored[:max_projects]
        else:
            selected_raw = [sp[3] for sp in scored_projects[: min(2, max_projects)]]
    else:
        selected_raw = [sp[3] for sp in scored_projects[:max_projects]]

    final_projects = []
    for p in selected_raw:
        p_copy = dict(p)
        desc = p_copy.get("description", "")
        if bold_enabled and desc:
            for ms in matching_skills:
                if (
                    len(ms) > 2
                    and ms.lower() in desc.lower()
                    and f"**{ms}**" not in desc
                    and f"**{ms.lower()}**" not in desc.lower()
                ):
                    pattern = re.compile(rf"\b{re.escape(ms)}\b", re.IGNORECASE)
                    desc = pattern.sub(f"**{ms}**", desc)
            p_copy["description"] = desc

        p_name = p_copy.get("name") or p_copy.get("title") or "Project"
        p_techs = p_copy.get("technologies") or p_copy.get("tech_stack") or []
        clean_p = CanonicalDict({
            "id": p_copy.get("id") or f"project_{len(final_projects)+1:03d}",
            "name": p_name,
            "description": desc,
            "technologies": p_techs,
        })
        if p_copy.get("url"):
            clean_p["url"] = p_copy["url"]
        final_projects.append(clean_p)

    return final_projects


def preserve_and_prioritize_experience_bullets(
    company_name: str,
    original_bullets: list[str],
    ai_bullets: list[str] | None,
    matching_skills: list[str],
    missing_skills: list[str],
    job_title: str = "",
    company: str = "",
    job_description: str = "",
    bold_enabled: bool = True,
    all_other_companies: list[str] | None = None,
    all_other_bullets: list[str] | None = None,
) -> list[str]:
    """Preserves critical candidate technical accomplishments, metrics, and integrations,
    eliminates cross-employer attribution bleed, and prioritizes bullets based on JD relevance."""
    clean_orig_bullets = [str(b).strip() for b in (original_bullets or []) if str(b).strip()]

    # Extract distinctive identifiers from other employers to detect bleed generically
    other_co_list = [c.strip() for c in (all_other_companies or []) if c.strip() and c.strip().lower() != (company_name or "").strip().lower()]
    other_proj_prefixes = []
    other_domains = []
    for ob in (all_other_bullets or []):
        m = re.match(r"^([A-Za-z0-9\.\-\s]{3,35}):", ob.strip())
        if m:
            other_proj_prefixes.append(m.group(1).strip().lower())
        other_domains.extend(re.findall(r"\b[a-zA-Z0-9\.\-]+\.(?:com|org|in|io|net)\b", ob.lower()))

    # 1. Clean and filter AI bullets for cross-employer bleed
    valid_ai_bullets: list[str] = []
    if ai_bullets and isinstance(ai_bullets, list):
        for b in ai_bullets:
            b_str = str(b).strip()
            if not b_str:
                continue
            b_lower = b_str.lower()
            # Reject if it mentions another employer's company name
            if any(oco.lower() in b_lower for oco in other_co_list if len(oco) > 3):
                continue
            # Reject if it contains a project prefix/domain distinct to another employer and not in this company's original bullets
            orig_text_lower = " ".join(clean_orig_bullets).lower()
            if any(p in b_lower and p not in orig_text_lower for p in other_proj_prefixes):
                continue
            if any(d in b_lower and d not in orig_text_lower for d in other_domains):
                continue
            valid_ai_bullets.append(b_str)

    # 2. Information Restoration: Ensure critical candidate details are not omitted
    final_raw_bullets: list[str] = []
    if valid_ai_bullets:
        combined_ai_text = " ".join(valid_ai_bullets).lower()
        # Restore full original bullet if AI truncated or dropped technical accomplishments
        for b in valid_ai_bullets:
            b_words = set(re.findall(r"\b[a-z]{3,}\b", b.lower()))
            best_ob = None
            best_overlap = 0.0
            for ob in clean_orig_bullets:
                ob_words = set(re.findall(r"\b[a-z]{3,}\b", ob.lower()))
                if ob_words and b_words:
                    overlap = len(ob_words & b_words) / len(b_words)
                    if overlap > best_overlap:
                        best_overlap = overlap
                        best_ob = ob
            if best_ob and best_overlap >= 0.60 and len(best_ob) > len(b):
                final_raw_bullets.append(best_ob)
            else:
                final_raw_bullets.append(b)

        # Check every authentic original bullet of THIS company:
        # Restore critical metrics, integrations, leadership, and JD requirements missing from AI output
        for ob in clean_orig_bullets:
            ob_lower = ob.lower()
            has_metric = bool(re.search(r"\b(?:\d+(?:,\d{3})*(?:\.\d+)?(?:\+|%)?(?:\s*[a-zA-Z\-/]{2,}(?:\s+[a-zA-Z\-/]{2,}){0,2})?|[\$€£₹]\s*\d+(?:,\d{3})*(?:\.\d+)?|\b\d+(?:st|nd|rd|th)\b|\b\d+(?:\.\d+)?x\b)\b", ob_lower))
            matched_integs = [
                t for t in EvidenceMapper.TECH_CANONICAL_MAP.keys()
                if len(t) >= 4 and t in ob_lower and t not in combined_ai_text
            ]
            has_mentoring = bool(re.search(r"\b(?:mentor\w*|interviews?)\b", ob_lower))
            bullet_matching = [ms for ms in matching_skills if len(ms) > 2 and ms.lower() in ob_lower]

            if has_metric and not any(m in combined_ai_text for m in re.findall(r"\b\d+\+?", ob)):
                if ob not in final_raw_bullets:
                    final_raw_bullets.append(ob)
            elif has_mentoring and not any(k in combined_ai_text for k in ["mentor", "interview"]):
                if ob not in final_raw_bullets:
                    final_raw_bullets.append(ob)
            elif matched_integs:
                sentences = re.split(r"(?<=[.!?])\s+", ob)
                for integ in matched_integs:
                    if integ not in combined_ai_text:
                        matching_sent = next((s.strip() for s in sentences if integ in s.lower()), None)
                        if matching_sent:
                            p_prefix_m = re.match(r"^([A-Za-z0-9\.\-\s]{3,35}):", ob.strip())
                            if p_prefix_m:
                                prefix_term = p_prefix_m.group(1).lower()
                                target_idx = next((i for i, fb in enumerate(final_raw_bullets) if fb.lower().startswith(prefix_term)), None)
                                if target_idx is not None and matching_sent.lower() not in final_raw_bullets[target_idx].lower():
                                    final_raw_bullets[target_idx] = final_raw_bullets[target_idx].rstrip(" .") + ". " + matching_sent
                                    continue
                        if ob not in final_raw_bullets:
                            final_raw_bullets.append(ob)
            elif bullet_matching and not any(bm.lower() in combined_ai_text for bm in bullet_matching):
                if ob not in final_raw_bullets:
                    final_raw_bullets.append(ob)
    else:
        final_raw_bullets = list(clean_orig_bullets)

    # 3. Strip missing technologies, leaked company names, and bold verified matching technologies
    processed_bullets: list[str] = []
    # Dynamic leak patterns derived from other employers + corporate entity suffixes
    company_leak_patterns = [
        rf"\s*[-—–.]*\s*{re.escape(co)}(?:\s+Pvt\.?\s+Ltd\.?)?\b"
        for co in other_co_list
        if len(co) >= 3
    ]
    corp_suffix_pattern = re.compile(
        r"\s*[-—–.]*\s*([A-Z][a-zA-Z0-9\s]{2,40}?\s*(?:Pvt\.?\s+Ltd\.?|LLC|Inc\.?|Corp\.?|Ltd\.?))\b",
        re.IGNORECASE,
    )
    for bullet in final_raw_bullets:
        b_clean = bullet
        for clp in company_leak_patterns:
            b_clean = re.sub(clp, "", b_clean, flags=re.IGNORECASE).strip(" .-\t")
        m_corp = corp_suffix_pattern.search(b_clean)
        if m_corp:
            matched_co = m_corp.group(1).strip()
            if company_name and matched_co.lower() not in company_name.lower():
                b_clean = corp_suffix_pattern.sub("", b_clean).strip(" .-\t")
        for ms in missing_skills:
            if len(ms) > 2:
                b_clean = re.sub(rf"\b{re.escape(ms)}\b", "", b_clean, flags=re.IGNORECASE)

        if bold_enabled:
            for ms in matching_skills:
                if (
                    len(ms) > 2
                    and ms.lower() in b_clean.lower()
                    and f"**{ms}**" not in b_clean
                    and f"**{ms.lower()}**" not in b_clean.lower()
                ):
                    pattern = re.compile(rf"\b{re.escape(ms)}\b", re.IGNORECASE)
                    b_clean = pattern.sub(f"**{ms}**", b_clean)

        b_clean = " ".join(b_clean.split()).strip()
        if b_clean and b_clean not in processed_bullets:
            processed_bullets.append(b_clean)

    # 4. Relevance Prioritization (Reorder bullets based on target JD relevance)
    target_context = f"{job_title} {company} {job_description}".lower()

    # Domain keyword patterns extracted generically from target JD
    jd_words = {w for w in re.findall(r"\b[a-z]{4,}\b", target_context) if w not in {
        "with", "from", "that", "this", "have", "will", "your", "work", "join", "about",
        "role", "team", "year", "years", "must", "good", "plus", "such", "well", "able",
    }}

    def bullet_relevance_score(b_text: str) -> int:
        score = 0
        b_lower = b_text.lower()

        # Target matching skills (+5 each)
        for s in matching_skills:
            if len(s) > 2 and s.lower() in b_lower:
                score += 5

        # Direct JD term overlap (+2 per meaningful matching token)
        b_words = set(re.findall(r"\b[a-z]{4,}\b", b_lower))
        score += 2 * len(jd_words & b_words)

        # Backend / Database / Optimization domain (+4 each)
        if any(w in target_context for w in ["backend", "java", "sql", "database", "api", "query", "optimize"]):
            for kw in ["query optimization", "materialized views", "postgresql", "mysql", "sql", "rest apis", "rest api", "bulk upload", "performance"]:
                if kw in b_lower:
                    score += 4

        # E-commerce / Payment / Financial domain (+4 each)
        if any(w in target_context for w in ["ecommerce", "e-commerce", "payment", "billing", "critical services"]):
            for kw in ["stripe", "stripe split payment", "woocommerce", "e-commerce", "qr code", "payment"]:
                if kw in b_lower:
                    score += 4

        # Mentoring / Leadership domain (+3 each)
        if any(w in target_context for w in ["mentor", "lead", "leadership", "guide", "team"]):
            if "mentor" in b_lower or "interview" in b_lower:
                score += 3

        # Cloud / DevOps domain (+4 each)
        if any(w in target_context for w in ["cloud", "aws", "docker", "kubernetes", "ci/cd", "devops"]):
            for kw in ["docker", "kubernetes", "aws", "cloud", "ci/cd", "pipeline"]:
                if kw in b_lower:
                    score += 4

        return score

    processed_bullets.sort(key=bullet_relevance_score, reverse=True)
    return processed_bullets


def reconstruct_achievements(
    raw_achs: list[Any],
    profile: dict[str, Any],
    summary: str = "",
) -> list[dict[str, Any]]:
    """Generic structured achievement reconstruction:
    - Reassembles fragmented sentences and competitive programming stats.
    - Associates verified platform URLs to correct achievement titles.
    - Never creates standalone URL achievements.
    - Supports arbitrary platforms (HackerRank, LeetCode, Codeforces, Kaggle, GitHub, AWS, etc.).
    """
    clean_achs: list[dict[str, Any]] = []

    # 1. Catalog all verified profile URLs by platform domain
    platform_urls: dict[str, str] = {}
    url_pattern = re.compile(r"https?://(?:www\.)?([a-zA-Z0-9\-]+)\.(?:[a-zA-Z]{2,4})[^\s)]*", re.IGNORECASE)

    all_links_sources = []
    if profile.get("personal", {}).get("links"):
        all_links_sources.extend(profile["personal"]["links"])
    if profile.get("links"):
        all_links_sources.extend(profile["links"])
    for k in ["hackerrank", "leetcode", "github", "linkedin", "portfolio", "kaggle", "codeforces"]:
        val = profile.get("personal", {}).get(k) or profile.get(k)
        if val and isinstance(val, str) and val.startswith("http"):
            all_links_sources.append(val)

    # Also scan raw achievements for URLs
    for a in raw_achs or []:
        t = str(a.get("title") or "" if isinstance(a, dict) else a).strip()
        u = str(a.get("url") or "" if isinstance(a, dict) else "").strip()
        if u and u.startswith("http"):
            all_links_sources.append(u)
        m = url_pattern.search(t)
        if m:
            all_links_sources.append(m.group(0).strip(".,"))

    for l in all_links_sources:
        u_str = (l.get("url") if isinstance(l, dict) else str(l)).strip()
        m = url_pattern.search(u_str)
        if m:
            domain_key = m.group(1).lower()
            if domain_key not in platform_urls:
                platform_urls[domain_key] = m.group(0).strip(".,")

    # 2. Extract full candidate textual context for achievements
    raw_titles = []
    for a in raw_achs or []:
        t = (a.get("title") if isinstance(a, dict) else str(a)).strip()
        if not t.startswith("http://") and not t.startswith("https://"):
            raw_titles.append(t)
    full_ach_text = " ".join(raw_titles)
    full_cand_text = f"{full_ach_text} {profile.get('summary', '')} {summary}"

    # 3. Dynamic Platform Achievement Extraction
    # A) HackerRank
    if "hackerrank" in full_cand_text.lower():
        hr_m = re.search(r"(?:hackerrank\s+)?(\d+(?:st|nd|rd|th)?\s*star\s+gold\s+badge)", full_cand_text, re.IGNORECASE)
        badge = hr_m.group(1) if hr_m else "Gold Badge"
        hr_title = f"HackerRank {badge} (Problem Solving)"
        clean_achs.append({
            "title": hr_title,
            "url": platform_urls.get("hackerrank") or None,
            "source": "original_resume",
        })

    # B) LeetCode
    if "leetcode" in full_cand_text.lower():
        lc_m = re.search(r"(\d+\+?\s*leetcode\s*(?:questions?|problems?))", full_cand_text, re.IGNORECASE)
        lc_count = re.sub(r"problems?", "questions", lc_m.group(1), flags=re.IGNORECASE) if lc_m else "algorithmic questions"
        lc_title = f"Solved {lc_count} demonstrating strong algorithmic problem-solving"
        clean_achs.append({
            "title": lc_title,
            "url": platform_urls.get("leetcode") or None,
            "source": "original_resume",
        })

    # C) Codeforces
    if "codeforces" in full_cand_text.lower():
        cf_m = re.search(r"codeforces\s+((?:candidate\s+master|grandmaster|master|expert|\d+\+?\s*rating)(?:\s*\([^)]+\))?)", full_cand_text, re.IGNORECASE)
        cf_title = f"Codeforces {cf_m.group(1).strip()}" if cf_m else "Codeforces Competitive Programmer"
        clean_achs.append({
            "title": cf_title,
            "url": platform_urls.get("codeforces") or None,
            "source": "original_resume",
        })

    # D) Kaggle
    if "kaggle" in full_cand_text.lower():
        kg_m = re.search(r"kaggle\s+((?:grandmaster|master|expert)(?:\s*\([^)]+\))?)", full_cand_text, re.IGNORECASE)
        kg_title = f"Kaggle {kg_m.group(1).strip()}" if kg_m else "Kaggle Competitions Contributor"
        clean_achs.append({
            "title": kg_title,
            "url": platform_urls.get("kaggle") or None,
            "source": "original_resume",
        })

    # 4. Standalone / Other Verified Achievements & Certifications
    platform_keys = ["hackerrank", "leetcode", "codeforces", "kaggle"]
    for a in raw_achs or []:
        t = str(a.get("title") or "" if isinstance(a, dict) else a).strip()
        u = str(a.get("url") or "" if isinstance(a, dict) else "").strip() or None
        m_u = url_pattern.search(t)
        if m_u:
            u = u or m_u.group(0).strip(".,")
            t = url_pattern.sub("", t).strip(" -—–:|")

        if not t or t.startswith("http://") or t.startswith("https://"):
            continue
        if any(frag in t.lower() for frag in [
            "back-end technologies.",
            "proven ability to",
            "star gold badge and a track",
            "demonstrated proficiency in problem-solving",
        ]):
            continue
        if any(pk in t.lower() for pk in platform_keys):
            continue

        if not u:
            for p_key, p_url in platform_urls.items():
                if p_key in t.lower():
                    u = p_url
                    break
        if not u and "certified" in t.lower() and "credly" in platform_urls:
            u = platform_urls["credly"]

        if len(t) > 10 and not any(c["title"].lower() == t.lower() for c in clean_achs):
            clean_achs.append({
                "title": t,
                "url": u or None,
                "source": "original_resume",
            })

    for idx, ach in enumerate(clean_achs):
        if not ach.get("id"):
            ach["id"] = f"achievement_{idx+1:03d}"

    return clean_achs


class ResumeBuilderAgent:
    """Generates evidence-grounded, ATS-friendly tailored resumes and renders DOCX/PDF."""

    _llm_generation_cache: dict[str, dict[str, Any]] = {}

    def __init__(self):
        self.template = DefaultATSResumeTemplate()
        self.evidence_mapper = EvidenceMapper()
        self.hallucination_guard = HallucinationGuard()

    async def build_tailored_resume(
        self,
        user_id: str,
        job_id: str,
        user_settings: UserSettings | None = None,
        template: str | None = None,
    ) -> dict | None:
        db = get_db()
        profile = await db.profiles.find_one({"user_id": ObjectId(user_id)})
        job = await db.jobs.find_one({"_id": ObjectId(job_id)})

        if not profile or not job:
            logger.warning("Cannot tailor resume: profile or job not found", user_id=user_id, job_id=job_id)
            return None

        # 1. Rigorous JD-to-candidate evidence mapping
        evidence_result: EvidenceMappingResult = self.evidence_mapper.map_evidence(profile, job)
        cand_index = evidence_result.candidate_index
        skills_cls = evidence_result.skills_classification

        job_title = job.get("title") or "Software Engineer"
        company = job.get("company") or "Company"
        required_skills = job.get("required_skills", []) or []

        matching_skills = skills_cls.matched_skills
        partial_skills = skills_cls.partially_matched_skills
        missing_skills = skills_cls.missing_skills

        # All candidate skills list
        candidate_skills_list = []
        raw_skills = profile.get("skills", {})
        if isinstance(raw_skills, dict):
            for items in raw_skills.values():
                candidate_skills_list.extend(items)
        elif isinstance(raw_skills, list):
            candidate_skills_list.extend(raw_skills)

        # Load user settings if not passed
        if not user_settings:
            settings_doc = await db.user_settings.find_one({"user_id": ObjectId(user_id)})
            if settings_doc:
                try:
                    user_settings = UserSettings(**settings_doc)
                except Exception:
                    pass

        app_prefs = user_settings.application_preferences if user_settings else None
        tailor_temp = float(getattr(app_prefs, "tailoring_temperature", 0.15) if app_prefs else 0.15)
        max_bullets = int(getattr(app_prefs, "max_bullets_per_role", 4) if app_prefs else 4)
        bold_enabled = bool(getattr(app_prefs, "bold_matching_keywords", True) if app_prefs else True)
        filter_projects = bool(getattr(app_prefs, "filter_irrelevant_projects", True) if app_prefs else True)
        max_projects = int(getattr(app_prefs, "max_tailored_projects", 3) if app_prefs else 3)

        raw_projects = profile.get("projects", [])
        raw_experience = profile.get("experience", [])

        # Format evidence summaries for prompt
        matched_evidence_lines = []
        for m in evidence_result.mappings:
            if m.status == "MATCHED":
                matched_evidence_lines.append(f"- {m.requirement} ({m.source_entity}): {m.evidence_text}")
        matched_evidence_text = "\n".join(matched_evidence_lines) or "- Full stack development, REST APIs, SQL databases"

        partial_evidence_lines = []
        for m in evidence_result.mappings:
            if m.status == "PARTIAL":
                partial_evidence_lines.append(f"- {m.requirement} ({m.source_entity}): {m.evidence_text} [{m.notes}]")
        partial_evidence_text = "\n".join(partial_evidence_lines) or "None."

        missing_skills_text = ", ".join(missing_skills) if missing_skills else "None identified"
        education_summary = ", ".join([f"{e.get('degree')} from {e.get('institution')}" for e in profile.get("education", [])]) or "Computer Applications degree"

        target_headline = ""
        tailored_summary = ""
        tailored_experience = None
        tailored_projects = None
        ai_tailored = False

        if user_settings and user_settings.ai_provider:
            try:
                job_desc_raw = job.get("description") or ""
                job_desc_clean = " ".join(job_desc_raw.split())[:2000] if job_desc_raw else "Build robust backend architectures and collaborative microservices."

                prompt = RESUME_TAILOR_PROMPT.format(
                    job_title=job_title,
                    company=company,
                    required_skills=", ".join(required_skills[:12]) if required_skills else "relevant engineering skills",
                    job_description=job_desc_clean,
                    matched_skills_evidence=matched_evidence_text,
                    partial_skills_evidence=partial_evidence_text,
                    missing_skills_list=missing_skills_text,
                    overall_years=cand_index.overall_years,
                    education_summary=education_summary,
                )

                cache_key = hashlib.sha256(f"{prompt}:{tailor_temp}".encode("utf-8")).hexdigest()
                parsed = self._llm_generation_cache.get(cache_key)

                if not parsed:
                    provider = AIProviderFactory.resolve(user_settings)
                    resp = await provider.complete([{"role": "user", "content": prompt}], temperature=tailor_temp)
                    json_match = re.search(r"\{[\s\S]*\}", resp)
                    if json_match:
                        parsed = json.loads(json_match.group(0))
                        self._llm_generation_cache[cache_key] = parsed

                if parsed:
                    if parsed.get("target_headline"):
                        target_headline = parsed["target_headline"].strip()
                    if parsed.get("tailored_summary"):
                        cand_sum = parsed["tailored_summary"].strip()
                        # Generic project-only technology integrity: prevent claiming proven expertise in project-only tech
                        for prj in cand_index.projects:
                            p_name = prj.get("name") or prj.get("title") or "independent project"
                            p_techs = prj.get("technologies") or prj.get("tech_stack") or []
                            p_tech_only = [t for t in p_techs if t.lower() not in [pr.lower() for pr in cand_index.professional_technologies]]
                            if p_tech_only and any(t.lower() in cand_sum.lower() for t in p_tech_only):
                                sorted_techs = sorted(p_tech_only, key=lambda x: (len(x.split()), len(x)), reverse=True)
                                tech_joined = " and ".join(sorted_techs[:2])
                                tech_or = "|".join(re.escape(t) for t in sorted_techs)
                                cand_sum = re.sub(
                                    rf"\b(?:proven\s+expertise|expertise|specializ\w+|mastery|seasoned)\s+(?:in|with)\s+([A-Za-z\s,/&]*\b(?:{tech_or})\b[A-Za-z\s,/&]*)",
                                    f"hands-on project experience in {tech_joined} ({p_name})",
                                    cand_sum,
                                    flags=re.IGNORECASE,
                                )
                        tailored_summary = cand_sum
                        ai_tailored = True
                    if parsed.get("tailored_experience") and isinstance(parsed["tailored_experience"], list):
                        tailored_experience = parsed["tailored_experience"]
                    if parsed.get("tailored_projects") and isinstance(parsed["tailored_projects"], list):
                        tailored_projects = parsed["tailored_projects"]
            except Exception as e:
                logger.warning("AI resume tailoring failed, using rule-based synthesis", error=str(e))

        # ------------------------------------------------------------------
        # Deterministic Grounding & Headline Synthesis
        # ------------------------------------------------------------------
        # Construct verified headline without missing technologies (e.g. NEVER claim CI/CD)
        if not target_headline:
            verified_headline_tech = []
            for ms in matching_skills:
                if ms.lower() not in {m.lower() for m in missing_skills}:
                    verified_headline_tech.append(ms)

            # Add primary backend stack if missing
            for fallback_tech in ["Node.js", "PostgreSQL", "REST APIs", "SQL", "System Design"]:
                if fallback_tech in cand_index.all_known_technologies and fallback_tech not in verified_headline_tech:
                    verified_headline_tech.append(fallback_tech)

            # Note project-level tech appropriately
            tech_str = ", ".join(verified_headline_tech[:3])
            project_headline_suffix = ""
            for ps in sorted(partial_skills, key=lambda s: (len(s.split()), len(s)), reverse=True):
                matching_p = next(
                    (p for p in cand_index.projects if any(ps.lower() in t.lower() or t.lower() in ps.lower() for t in (p.get("technologies") or []))),
                    None,
                )
                if matching_p:
                    matching_p_techs = sorted(matching_p.get("technologies") or [], key=len, reverse=True)
                    p_tech = next((t for t in matching_p_techs if ps.lower() in t.lower() or t.lower() in ps.lower()), ps)
                    project_headline_suffix = f" & {p_tech} Projects"
                    break
            tech_str += project_headline_suffix
            target_headline = f"{job_title} | {tech_str}"

        # Strip any unverified missing skills that leaked into target_headline
        for ms in missing_skills:
            if len(ms) > 2:
                target_headline = re.sub(rf"\b{re.escape(ms)}\b", "", target_headline, flags=re.IGNORECASE)
        target_headline = re.sub(r"[\s,&|]+$", "", target_headline).strip()
        target_headline = re.sub(r"\|\s*\|", "|", target_headline).strip()

        # ------------------------------------------------------------------
        # Deterministic Summary Synthesis
        # ------------------------------------------------------------------
        if not ai_tailored or not tailored_summary:
            # 1. Candidate primary title from most recent professional role or headline
            primary_title = cand_index.professional_roles[0]["title"] if cand_index.professional_roles else (profile.get("target_headline") or "Software Engineer")
            if not primary_title or primary_title.lower() in ["company", "developer", "engineer"]:
                primary_title = "Software Engineer"

            # 2. Key professional stack: only technologies candidate used professionally in cand_index.professional_technologies
            prof_matching = [s for s in matching_skills if s.lower() in [pt.lower() for pt in cand_index.professional_technologies]]
            bold_prof = [f"**{s}**" for s in prof_matching[:4]]
            key_stack = ", ".join(bold_prof) if bold_prof else f"**{job_title}** core capabilities"

            # 3. Dynamically derive project-level technology note from candidate projects
            project_tech_note = ""
            if partial_skills and cand_index.projects:
                for ps in partial_skills[:2]:
                    matching_p = next(
                        (p for p in cand_index.projects if any(ps.lower() in t.lower() or t.lower() in ps.lower() for t in (p.get("technologies") or []))),
                        None,
                    )
                    if matching_p:
                        p_name = matching_p.get("name") or matching_p.get("title") or "independent project"
                        # Collect matching technologies from the project preferring specific (longer) names
                        proj_techs = sorted(matching_p.get("technologies") or [], key=len, reverse=True)
                        matched_techs = []
                        for s in partial_skills[:2]:
                            t_found = next((t for t in proj_techs if s.lower() in t.lower() or t.lower() in s.lower()), s)
                            if not any(t_found.lower() != m.lower() and t_found.lower() in m.lower() for m in matched_techs):
                                if t_found not in matched_techs:
                                    matched_techs.append(t_found)
                        matched_techs = sorted(matched_techs, key=lambda x: (len(x.split()), x), reverse=True)
                        proj_techs_formatted = " and ".join([f"**{s}**" for s in matched_techs])
                        project_tech_note = f" Hands-on project experience with {proj_techs_formatted} through **{p_name}**."
                        break

            # 4. Verified capabilities strictly substantiated by candidate's professional evidence text
            all_prof_text = " ".join(r.get("raw_text", "") for r in cand_index.professional_roles).lower()
            supported_caps = []
            if any(k in all_prof_text for k in ["api", "apis", "rest"]):
                supported_caps.append("high-performance APIs")
            if any(k in all_prof_text for k in ["database", "sql", "query optimization", "query tuning", "materialized views"]):
                supported_caps.append("database design & query tuning")
            if any(k in all_prof_text for k in ["microservice", "microservices"]):
                supported_caps.append("microservices architecture")
            if any(k in all_prof_text for k in ["scalable", "scalability", "scale"]):
                supported_caps.append("scalable systems")

            caps_phrase = f" Core expertise in {', '.join(supported_caps)}." if supported_caps else ""

            tailored_summary = (
                f"{primary_title} with **{cand_index.overall_years:g} years** of overall software development experience. "
                f"Proven professional track record developing with {key_stack}.{caps_phrase}{project_tech_note}"
            )

        # ------------------------------------------------------------------
        # Experience Highlights Assembly & Attribution Preservation
        # ------------------------------------------------------------------
        # Ensure cross-company attribution integrity in raw_experience generically
        all_companies_list = [e.get("company", "").strip() for e in raw_experience if e.get("company", "").strip()]
        all_exp_bullets_map = {
            e.get("company", "").strip(): (e.get("responsibilities") or e.get("highlights") or [])
            for e in raw_experience
        }

        # Index authentic bullets and their owning employer
        bullet_owner_map: dict[str, str] = {}
        project_prefix_owner_map: dict[str, str] = {}
        for exp in raw_experience:
            c_name = exp.get("company", "").strip()
            for r in (exp.get("responsibilities") or exp.get("highlights") or []):
                r_clean = str(r).strip()
                bullet_owner_map[r_clean.lower()] = c_name
                m = re.match(r"^([A-Za-z0-9\.\-\s]{3,35}):", r_clean)
                if m:
                    project_prefix_owner_map[m.group(1).strip().lower()] = c_name

        cleaned_raw_experience = []
        for exp in raw_experience:
            exp_c = dict(exp)
            this_co = exp_c.get("company", "").strip()
            exp_resps = exp_c.get("responsibilities") or exp_c.get("highlights") or []
            kept_resps = []
            for r in exp_resps:
                r_str = str(r).strip()
                r_lower = r_str.lower()
                m = re.match(r"^([A-Za-z0-9\.\-\s]{3,35}):", r_str)
                prefix = m.group(1).strip().lower() if m else None
                owner_co = bullet_owner_map.get(r_lower) or (project_prefix_owner_map.get(prefix) if prefix else None)
                if owner_co and owner_co.lower() != this_co.lower():
                    # Move to authentic owner
                    target_exp = next((e for e in raw_experience if e.get("company", "").strip().lower() == owner_co.lower()), None)
                    if target_exp:
                        target_resps = target_exp.get("responsibilities") or target_exp.get("highlights") or []
                        if r_str not in target_resps:
                            target_resps.append(r_str)
                            target_exp["responsibilities"] = target_resps
                else:
                    kept_resps.append(r)
            exp_c["responsibilities"] = kept_resps
            exp_c["highlights"] = kept_resps
            cleaned_raw_experience.append(exp_c)
        raw_experience = cleaned_raw_experience

        final_experience = []
        tailored_exp_map = {}
        if tailored_experience:
            for te in tailored_experience:
                if isinstance(te, dict) and te.get("company"):
                    co_name = te["company"].strip().lower()
                    tailored_exp_map[co_name] = te.get("highlights", [])

        companies_catalog = []
        company_slug_map = {}
        for idx, exp in enumerate(raw_experience):
            co_name = exp.get("company", "").strip() or f"Company {idx+1}"
            slug = re.sub(r"[^a-z0-9]+", "_", co_name.lower()).strip("_")
            co_id = exp.get("company_id") or f"company_{slug or f'{idx+1:03d}'}"
            if co_id not in company_slug_map:
                company_slug_map[co_id] = co_name
                companies_catalog.append({"id": co_id, "name": co_name})

        for idx, exp in enumerate(raw_experience):
            exp_copy = dict(exp)
            co_name = exp_copy.get("company", "").strip() or f"Company {idx+1}"
            co_key = co_name.lower()
            orig_bullets = exp_copy.get("responsibilities") or exp_copy.get("highlights") or []
            ai_exp_bullets = tailored_exp_map.get(co_key, [])

            slug = re.sub(r"[^a-z0-9]+", "_", co_name.lower()).strip("_")
            co_id = exp_copy.get("company_id") or f"company_{slug or f'{idx+1:03d}'}"

            other_cos = [c for c in all_companies_list if c.lower() != co_name.lower()]
            other_bs = []
            for oc in other_cos:
                other_bs.extend(all_exp_bullets_map.get(oc, []))

            processed_bullets = preserve_and_prioritize_experience_bullets(
                company_name=co_name,
                original_bullets=orig_bullets,
                ai_bullets=ai_exp_bullets,
                matching_skills=matching_skills,
                missing_skills=missing_skills,
                job_title=job_title,
                company=company,
                job_description=job.get("description", ""),
                bold_enabled=bold_enabled,
                all_other_companies=other_cos,
                all_other_bullets=other_bs,
            )

            exp_id = exp_copy.get("id") or f"experience_{idx+1:03d}"
            clean_exp_entry = CanonicalDict({
                "id": exp_id,
                "company_id": co_id,
                "company": co_name,
                "title": exp_copy.get("title") or exp_copy.get("jobTitle") or "Software Engineer",
                "start_date": exp_copy.get("start_date") or exp_copy.get("startDate") or "",
                "end_date": exp_copy.get("end_date") or exp_copy.get("endDate") or "",
                "is_current": bool(exp_copy.get("is_current", exp_copy.get("current", False))),
                "description": exp_copy.get("description", ""),
                "responsibilities": processed_bullets or exp_copy.get("responsibilities", []),
            })
            if exp_copy.get("projects"):
                clean_exp_entry["projects"] = exp_copy["projects"]
            final_experience.append(clean_exp_entry)

        # ------------------------------------------------------------------
        # Filter & Prioritize Matching Projects
        # ------------------------------------------------------------------
        final_projects = select_and_tailor_projects(
            raw_projects=raw_projects,
            required_skills=required_skills,
            matching_skills=matching_skills,
            job_title=job_title,
            company=company,
            max_projects=max_projects,
            filter_irrelevant=filter_projects,
            ai_projects=tailored_projects,
            bold_enabled=bold_enabled,
            candidate_experience=raw_experience,
        )

        # ------------------------------------------------------------------
        # Re-order and Categorize Skills
        # ------------------------------------------------------------------
        tailored_skills = {}
        if isinstance(raw_skills, dict):
            for cat, items in raw_skills.items():
                boosted = [s for s in items if s in matching_skills]
                others = [s for s in items if s not in matching_skills]
                tailored_skills[cat] = boosted + others
        elif isinstance(raw_skills, list):
            boosted = [s for s in raw_skills if s in matching_skills]
            others = [s for s in raw_skills if s not in matching_skills]
            tailored_skills = boosted + others

        selected_template_id = template or profile.get("selected_template") or "default"
        now = datetime.now(timezone.utc)

        personal_data = profile.get("personal", {})
        cand_name = personal_data.get("fullName") or personal_data.get("full_name") or "Candidate"
        cand_id = profile.get("candidate_id") or profile.get("id")
        if not cand_id:
            cand_slug = re.sub(r"[^a-z0-9]+", "_", cand_name.lower()).strip("_")
            cand_id = f"candidate_{cand_slug or '001'}"

        resume_content = {
            "candidate_id": cand_id,
            "job_id": str(job_id),
            "job_title": job_title,
            "company": company,
            "companies": companies_catalog,
            "target_headline": target_headline,
            "summary": tailored_summary,
            "tailored_summary": tailored_summary,
            "matching_skills": matching_skills,
            "missing_skills": missing_skills,
            "skills_breakdown": {
                "matched_skills": skills_cls.matched_skills,
                "partially_matched_skills": skills_cls.partially_matched_skills,
                "missing_skills": skills_cls.missing_skills,
                "unverified_skills": skills_cls.unverified_skills,
                "additional_relevant_skills": skills_cls.additional_relevant_skills,
            },
            "evidence_mappings": [m.model_dump() for m in evidence_result.mappings],
            "required_skills": required_skills,
            "personal": CanonicalDict({
                **{k: v for k, v in personal_data.items() if k != "fullName"},
                "full_name": cand_name,
            }),
            "skills": tailored_skills if tailored_skills else raw_skills,
            "experience": final_experience,
            "education": profile.get("education", []),
            "projects": final_projects,
            "achievements": reconstruct_achievements(profile.get("achievements", []), profile, tailored_summary),
            "template": selected_template_id,
            "generated_at": now.isoformat(),
        }

        # ------------------------------------------------------------------
        # Post-Generation Hallucination Guard Validation & Sanitization
        # Sequence:
        # 1. Generate output.
        # 2. Run deterministic validation.
        # 3. Sanitize or regenerate affected sections.
        # 4. Validate the final serialized JSON again.
        # 5. Set is_valid based on the final output, not the remediation attempt.
        # ------------------------------------------------------------------
        initial_val: ValidationResult = self.hallucination_guard.validate(
            tailored_resume=resume_content,
            original_profile=profile,
            evidence_result=evidence_result,
        )

        was_sanitized = False
        initial_critical = initial_val.critical_violations

        if not initial_val.is_valid or initial_val.warnings:
            val_result: ValidationResult = self.hallucination_guard.validate_and_sanitize(
                tailored_resume=resume_content,
                original_profile=profile,
                evidence_result=evidence_result,
            )
            was_sanitized = val_result.sanitized
            resume_content = val_result.sanitized_content

        final_serialized = json.loads(json.dumps(resume_content, default=str))
        final_val: ValidationResult = self.hallucination_guard.validate(
            tailored_resume=final_serialized,
            original_profile=profile,
            evidence_result=evidence_result,
        )

        final_is_valid = len(final_val.critical_violations) == 0
        resume_content["validation_report"] = {
            "is_valid": final_is_valid,
            "sanitized": was_sanitized,
            "critical_violations": [v.model_dump() for v in final_val.critical_violations],
            "warnings": [w.model_dump() for w in final_val.warnings],
            "summary": (
                f"Validation passed with 0 critical violations. {len(final_val.warnings)} warning(s)."
                if final_is_valid
                else f"Validation failed with {len(final_val.critical_violations)} critical violation(s)."
            ),
            "initial_violations": [v.model_dump() for v in initial_critical],
        }

        def _sanitize_for_mongo(obj):
            if isinstance(obj, ObjectId):
                return str(obj)
            if isinstance(obj, dict):
                return {k: _sanitize_for_mongo(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_sanitize_for_mongo(v) for v in obj]
            return obj

        resume_content = _sanitize_for_mongo(resume_content)

        # ------------------------------------------------------------------
        # Render Output Files (DOCX & PDF)
        # ------------------------------------------------------------------
        storage_dir = os.path.join(os.getcwd(), "storage", "resumes", str(user_id))
        os.makedirs(storage_dir, exist_ok=True)
        docx_path = os.path.join(storage_dir, f"resume_{job_id}_{selected_template_id}.docx")

        try:
            from app.templates.manager import render_docx_for_profile
            tailored_profile_context = {
                **profile,
                "target_headline": resume_content["target_headline"],
                "summary": resume_content["summary"],
                "skills": resume_content["skills"],
                "experience": resume_content["experience"],
                "projects": resume_content["projects"],
                "matching_skills": resume_content["matching_skills"],
            }
            docx_stream = render_docx_for_profile(selected_template_id, tailored_profile_context)
            with open(docx_path, "wb") as f:
                f.write(docx_stream.getvalue())
        except Exception as e:
            logger.error("Failed to render tailored resume DOCX", error=str(e), job_id=job_id)
            docx_path = None

        pdf_path = os.path.join(storage_dir, f"resume_{job_id}.pdf")
        try:
            self.template.render_pdf(resume_content, pdf_path)
        except Exception as e:
            logger.error("Failed to render resume PDF", error=str(e), job_id=job_id)
            pdf_path = None

        # ------------------------------------------------------------------
        # Store in db.resumes and db.job_matches (Never mutating db.profiles!)
        # ------------------------------------------------------------------
        resume_doc = {
            "user_id": ObjectId(user_id),
            "job_id": ObjectId(job_id),
            "template": selected_template_id,
            "content": resume_content,
            "pdf_path": pdf_path,
            "docx_path": docx_path,
            "generated_at": now.isoformat(),
        }
        res = await db.resumes.update_one(
            {"user_id": ObjectId(user_id), "job_id": ObjectId(job_id)},
            {"$set": resume_doc},
            upsert=True,
        )
        if res.upserted_id:
            resume_doc["_id"] = str(res.upserted_id)

        await db.job_matches.update_one(
            {"user_id": ObjectId(user_id), "job_id": ObjectId(job_id)},
            {
                "$set": {
                    "tailored_resume": resume_content,
                    "resume_generated_at": now.isoformat(),
                    "resume_docx_path": docx_path,
                },
                "$setOnInsert": {
                    "status": "pending",
                    "compatibility_score": 75,
                },
            },
            upsert=True,
        )

        logger.info(
            "Evidence-grounded tailored resume stored successfully",
            user_id=user_id,
            job_id=job_id,
            company=company,
            title=job_title,
            matched_skills_count=len(matching_skills),
            is_valid=final_is_valid,
        )
        return resume_doc
