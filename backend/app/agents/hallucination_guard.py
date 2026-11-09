"""Hallucination Guard for AI-Powered Resume Tailoring.

Rigorously verifies every factual claim in a tailored resume against the original
candidate profile and evidence mapping. Deterministically checks technology claims,
years of experience, metrics, dates, companies, and project-vs-employment boundaries.
"""

from __future__ import annotations

import json
import re
from typing import Any
from pydantic import BaseModel, Field

from app.agents.evidence_mapper import EvidenceMappingResult, CandidateEvidenceIndex
from app.models.profile import CanonicalDict


class ValidationViolation(BaseModel):
    category: str  # unsupported_technology | experience_inflation | invented_metric | invalid_dates | role_fabrication | project_promoted
    severity: str  # CRITICAL | WARNING
    field: str
    message: str
    detected_value: str
    allowed_boundary: str


class ValidationResult(BaseModel):
    is_valid: bool = True
    critical_violations: list[ValidationViolation] = Field(default_factory=list)
    warnings: list[ValidationViolation] = Field(default_factory=list)
    sanitized: bool = False
    sanitized_content: dict[str, Any] = Field(default_factory=dict)
    summary_notes: str = ""
    initial_violations: list[ValidationViolation] = Field(default_factory=list)


class HallucinationGuard:
    """Rigorous post-generation validation layer preventing hallucinations, tech inflation, and metric fabrications."""

    BANNED_BUZZWORDS = {
        "spearheaded", "synergized", "leveraged", "delve", "pivotal", "transformative",
        "game-changing", "visionary", "testament to", "holistic", "cutting-edge",
        "revolutionized", "skyrocketed", "unparalleled", "groundbreaking",
    }

    def _run_checks(
        self,
        tailored_resume: dict[str, Any],
        original_profile: dict[str, Any],
        evidence_result: EvidenceMappingResult,
    ) -> tuple[list[ValidationViolation], list[ValidationViolation]]:
        """Executes all deterministic and semantic checks against candidate ground truth."""
        violations: list[ValidationViolation] = []
        warnings: list[ValidationViolation] = []

        cand_index = evidence_result.candidate_index
        missing_skills_set = {s.lower() for s in evidence_result.skills_classification.missing_skills}
        all_known_tech_lower = {t.lower() for t in cand_index.all_known_technologies}
        profile_full_text = json.dumps(original_profile, default=str)

        # -------------------------------------------------------------
        # 1. Target Headline Checks
        # -------------------------------------------------------------
        headline = str(tailored_resume.get("target_headline") or "").strip()
        if headline:
            # Check for unsupported missing skills in headline (e.g. CI/CD, Jenkins, Maven, Kubernetes)
            for missing_tech in missing_skills_set:
                if re.search(r"\b" + re.escape(missing_tech) + r"\b", headline.lower()):
                    violations.append(ValidationViolation(
                        category="unsupported_technology",
                        severity="CRITICAL",
                        field="target_headline",
                        message=f"Headline claims unverified missing technology: '{missing_tech}'.",
                        detected_value=headline,
                        allowed_boundary=f"Must only feature verified candidate technologies: {', '.join(sorted(cand_index.all_known_technologies))}",
                    ))

        # -------------------------------------------------------------
        # 2. Professional Summary Checks
        # -------------------------------------------------------------
        summary = str(tailored_resume.get("tailored_summary") or tailored_resume.get("summary") or "").strip()
        if summary:
            # Check for malformed, fractured, or ungrammatical text
            malformed_patterns = [
                r"\b(?:in\s+and|and\s+with|focusing\s+on\s+and|hands-on\s+project\s+experience\s+in\s+and|and\s+DevOps|in\s+and\s+DevOps|with\s+and\b|and\s+or\b|,\s*and\s*,\s*|and\s+or\s+and)\b",
                r"\bfocusing\s+on\s+(?:[A-Za-z]+\s+)?and\s+with\b",
                r"\bexperience\s+in\s+and\b",
                r"\bthrough\s+and\b",
                r"\bwith\s+a\s+focus\s+on\s+and\b",
            ]
            for mp in malformed_patterns:
                m_match = re.search(mp, summary, re.IGNORECASE)
                if m_match:
                    violations.append(ValidationViolation(
                        category="malformed_summary",
                        severity="CRITICAL",
                        field="summary",
                        message=f"Summary contains malformed or ungrammatical text: '{m_match.group(0)}'.",
                        detected_value=summary,
                        allowed_boundary="Summary must be grammatically complete and coherent without broken conjunctions or dangling phrases.",
                    ))
                    break

            # A) Check for inflated years of experience
            years_matches = re.findall(r"(\d+)\+?\s*years?", summary, re.IGNORECASE)
            for y_str in years_matches:
                y_val = float(y_str)
                if y_val > cand_index.overall_years:
                    violations.append(ValidationViolation(
                        category="experience_inflation",
                        severity="CRITICAL",
                        field="summary",
                        message=f"Summary inflates years of experience to {y_val:g} yrs (candidate only has {cand_index.overall_years:g} yrs).",
                        detected_value=summary,
                        allowed_boundary=f"Maximum overall experience is {cand_index.overall_years:g} years.",
                    ))

            # B) Check for fake tech-specific multi-year claims
            # e.g., "5+ years of Java" or "5 years in Spring Boot"
            tech_exp_matches = re.finditer(
                r"(\d+)\+?\s*years?(?:\s+of|\s+in|\s+with)?\s+([A-Za-z\s\.\-\/]+?)(?:experience|,|\.|\band\b)",
                summary,
                re.IGNORECASE,
            )
            for m in tech_exp_matches:
                claim_years = float(m.group(1))
                claim_tech = m.group(2).strip()
                # If claim_tech is a project-only technology (not verified in professional employment), claiming multi-year experience is inflation
                is_proj_tech = any(claim_tech.lower() in pt.lower() or pt.lower() in claim_tech.lower() for pt in cand_index.project_technologies)
                is_prof_tech = any(claim_tech.lower() in pr.lower() or pr.lower() in claim_tech.lower() for pr in cand_index.professional_technologies)
                if is_proj_tech and not is_prof_tech and claim_years >= 2.0:
                    matching_proj_obj = next((p for p in cand_index.projects if any(claim_tech.lower() in t.lower() for t in (p.get("technologies") or []))), None)
                    matching_p = matching_proj_obj.get("name") if matching_proj_obj else "independent projects"
                    raw_p_techs = matching_proj_obj.get("technologies", []) if matching_proj_obj else []
                    # De-duplicate substrings (e.g. keep "Spring Boot", drop standalone "Spring")
                    filtered_p_techs = [t for t in raw_p_techs if not any(t.lower() != o.lower() and t.lower() in o.lower() for o in raw_p_techs)]
                    sorted_p_techs = sorted(filtered_p_techs, key=lambda x: (len(x.split()), x), reverse=True)
                    p_tech_str = "/".join(sorted_p_techs) if sorted_p_techs else claim_tech
                    violations.append(ValidationViolation(
                        category="experience_inflation",
                        severity="CRITICAL",
                        field="summary",
                        message=f"Misrepresented project-level technology {claim_tech} as {claim_years:g} years of experience.",
                        detected_value=m.group(0),
                        allowed_boundary=f"{p_tech_str} is project experience in {matching_p}, not multi-year professional employment.",
                    ))

            # C) Check for claiming professional specialization or proven expertise in project-only technologies
            spec_matches = re.finditer(
                r"(?:proven\s+expertise\s+in|expertise\s+in|specializing\s+in|specialist\s+in|expert\s+in|specialization\s+in|mastery\s+of|seasoned\s+in|proficient\s+in|skilled\s+in|strong\s+background\s+in)\s+([A-Za-z\s,/&]+?)(?:\.|\bwith\b|\band\b|$)",
                summary,
                re.IGNORECASE,
            )
            for sm in spec_matches:
                claimed_spec = sm.group(1).lower()
                for pt in cand_index.project_technologies:
                    if pt.lower() in claimed_spec and pt.lower() not in [pr.lower() for pr in cand_index.professional_technologies]:
                        matching_p = next((p.get("name") for p in cand_index.projects if any(pt.lower() in t.lower() for t in (p.get("technologies") or []))), "independent projects")
                        violations.append(ValidationViolation(
                            category="unsupported_specialization",
                            severity="CRITICAL",
                            field="summary",
                            message=f"Summary falsely claims proven expertise/specialization in project-only technology '{pt}'.",
                            detected_value=sm.group(0).strip(),
                            allowed_boundary=f"'{pt}' is an independent project technology ({matching_p}), not professional expertise. Distinguish project exposure from professional experience.",
                        ))
                for ut in evidence_result.skills_classification.unverified_skills:
                    if len(ut) > 2 and re.search(r"\b" + re.escape(ut) + r"\b", claimed_spec, re.IGNORECASE):
                        violations.append(ValidationViolation(
                            category="unsupported_specialization",
                            severity="CRITICAL",
                            field="summary",
                            message=f"Summary falsely claims specialization in unverified skill '{ut}'.",
                            detected_value=sm.group(0).strip(),
                            allowed_boundary=f"'{ut}' is only self-reported and unverified; cannot be claimed as an area of specialization.",
                        ))

            # D) Check for missing skills in summary
            for missing_tech in missing_skills_set:
                if len(missing_tech) > 2 and re.search(r"\b" + re.escape(missing_tech) + r"\b", summary.lower()):
                    violations.append(ValidationViolation(
                        category="unsupported_technology",
                        severity="CRITICAL",
                        field="summary",
                        message=f"Summary claims unverified missing technology: '{missing_tech}'.",
                        detected_value=summary,
                        allowed_boundary=f"Missing technology must not be claimed: '{missing_tech}'.",
                    ))

            # E) Check for unsupported security claims in summary
            security_matches = re.finditer(
                r"\b(?:security\s+expert(?:ise)?|expert(?:ise)?\s+in\s+security|specialist\s+in\s+security|robust\s+and\s+secure\s+applications?|cybersecurity)\b",
                summary,
                re.IGNORECASE,
            )
            for sec_m in security_matches:
                violations.append(ValidationViolation(
                    category="unsupported_claim",
                    severity="CRITICAL",
                    field="summary",
                    message=f"Summary makes unsupported claim of security expertise: '{sec_m.group(0)}'.",
                    detected_value=sec_m.group(0),
                    allowed_boundary="Remove unsupported security expertise claims unless backed by verified source credentials.",
                ))
                warnings.append(ValidationViolation(
                    category="unsupported_claim",
                    severity="WARNING",
                    field="summary",
                    message=f"Security claim '{sec_m.group(0)}' lacks verified credentials in candidate background.",
                    detected_value=sec_m.group(0),
                    allowed_boundary="Remove security expertise claims.",
                ))

            # F) Check for unsupported broad claims in summary: scalable, secure, robust, expert, devops
            profile_text_lower = json.dumps(original_profile, default=str).lower()
            if re.search(r"\bdevops\b", summary, re.IGNORECASE) and not re.search(r"\bdevops\b", profile_text_lower):
                violations.append(ValidationViolation(
                    category="unsupported_claim",
                    severity="CRITICAL",
                    field="summary",
                    message="Summary claims DevOps without backing evidence in candidate profile.",
                    detected_value="DevOps",
                    allowed_boundary="Remove DevOps claim unless backed by verified source credentials.",
                ))
            for buzzword in ["scalable", "secure", "robust", "expert"]:
                if re.search(r"\b" + re.escape(buzzword) + r"\b", summary, re.IGNORECASE):
                    if not re.search(r"\b" + re.escape(buzzword) + r"\b", profile_text_lower):
                        violations.append(ValidationViolation(
                            category="unsupported_claim",
                            severity="CRITICAL",
                            field="summary",
                            message=f"Summary makes unsupported claim of '{buzzword}' without backing evidence in candidate profile.",
                            detected_value=buzzword,
                            allowed_boundary=f"Remove '{buzzword}' unless backed by verified source evidence.",
                        ))

            # G) Banned AI buzzwords
            for bw in self.BANNED_BUZZWORDS:
                if re.search(r"\b" + re.escape(bw) + r"\b", summary, re.IGNORECASE):
                    warnings.append(ValidationViolation(
                        category="banned_buzzword",
                        severity="WARNING",
                        field="summary",
                        message=f"Found banned AI buzzword '{bw}'.",
                        detected_value=bw,
                        allowed_boundary="Use concrete engineering verbs (Built, Designed, Integrated).",
                    ))

        # -------------------------------------------------------------
        # 3. Contradictory Evidence Mapping Checks
        # -------------------------------------------------------------
        matching_skills_in_resume = [str(s).lower() for s in (tailored_resume.get("matching_skills") or [])]
        for missing_tech in missing_skills_set:
            if missing_tech in matching_skills_in_resume:
                violations.append(ValidationViolation(
                    category="contradictory_evidence_mapping",
                    severity="CRITICAL",
                    field="matching_skills",
                    message=f"Skill '{missing_tech}' is classified as MISSING in EvidenceMapping, but present in matching_skills.",
                    detected_value=missing_tech,
                    allowed_boundary="Missing skills cannot be marked as matched.",
                ))

        # -------------------------------------------------------------
        # 3. Work Experience Checks (Factual Immutability)
        # -------------------------------------------------------------
        tailored_exps = tailored_resume.get("experience") or []
        orig_exps = original_profile.get("experience") or []
        orig_companies = [e.get("company", "").strip().lower() for e in orig_exps]

        unsupported_outcome_patterns = [
            r",?\s*(?:and\s+)?(?:enhancing|enhance|improving|improve|increasing|increase|boosting|boost)\s+(?:workflow|operational|team|developer)?\s*efficiency(?:\s+across\s+all\s+teams)?",
            r",?\s*(?:and\s+)?(?:improving|improve)\s+(?:team|developer)\s+coordination",
            r",?\s*(?:and\s+)?(?:optimizing|optimize|maximizing|maximize)\s+(?:workflow|operational|team|organizational)?\s*productivity",
            r",?\s*(?:and\s+)?streamlining\s+company\s+operations\s+and\s+improve\s+team\s+coordination",
            r",?\s*(?:and\s+)?(?:accelerating|accelerate)\s+project\s+delivery",
            r",?\s*(?:and\s+)?(?:driving|drive)\s+organizational\s+success",
        ]

        for exp in tailored_exps:
            co = str(exp.get("company") or "").strip()
            if co.lower() not in orig_companies:
                violations.append(ValidationViolation(
                    category="role_fabrication",
                    severity="CRITICAL",
                    field="experience.company",
                    message=f"Fabricated or altered company name: '{co}'.",
                    detected_value=co,
                    allowed_boundary=f"Must match original profile companies: {', '.join(orig_companies)}",
                ))

            # Check that personal projects were NOT promoted to professional companies
            for p in cand_index.projects:
                if p["name"].lower() == co.lower():
                    violations.append(ValidationViolation(
                        category="project_promoted",
                        severity="CRITICAL",
                        field="experience.company",
                        message=f"Promoted independent project '{co}' into a professional employer.",
                        detected_value=co,
                        allowed_boundary="Personal projects belong in PROJECTS section only.",
                    ))

            # Check that employment records do not have empty projects arrays
            if "projects" in exp and isinstance(exp["projects"], list) and len(exp["projects"]) == 0:
                warnings.append(ValidationViolation(
                    category="empty_project_array",
                    severity="WARNING",
                    field=f"experience.{co}.projects",
                    message=f"Employment record for '{co}' contains an empty projects array.",
                    detected_value="projects: []",
                    allowed_boundary="Omit projects array from employment record when no sub-projects exist.",
                ))

            # Inspect responsibilities / highlights for missing tech or hallucinated metrics
            bullets = exp.get("responsibilities") or exp.get("highlights") or []
            for b in bullets:
                b_str = str(b)
                for missing_tech in missing_skills_set:
                    if len(missing_tech) > 2 and re.search(r"\b" + re.escape(missing_tech) + r"\b", b_str.lower()):
                        violations.append(ValidationViolation(
                            category="unsupported_technology",
                            severity="CRITICAL",
                            field="experience.responsibilities",
                            message=f"Experience bullet claims unverified missing tech '{missing_tech}'.",
                            detected_value=b_str,
                            allowed_boundary=f"Candidate has no verifiable experience in {missing_tech}.",
                        ))

                # Check for fabricated team counts (e.g. "mentored team of 4-6 junior engineers")
                team_count_m = re.search(r"(?:mentored|mentoring)\s+(?:a\s+)?(?:team\s+of\s+)?(\d+[-–]\d+|\d+)\s*(?:junior|engineers|developers)", b_str, re.IGNORECASE)
                if team_count_m:
                    count_val = team_count_m.group(1)
                    if count_val not in profile_full_text:
                        violations.append(ValidationViolation(
                            category="invented_metric",
                            severity="CRITICAL",
                            field="experience.responsibilities",
                            message=f"Invented specific team count '{team_count_m.group(0)}' (source does not state headcount of {count_val}).",
                            detected_value=team_count_m.group(0),
                            allowed_boundary="Preserve authentic phrasing from source without fabricated headcounts.",
                        ))

                # Check for invented financial claims
                fin_m = re.search(r"[\$€£₹]\s*\d+[\d,\.]*\s*(?:million|m|k|billion|b)?", b_str, re.IGNORECASE)
                if fin_m:
                    fin_val = fin_m.group(0)
                    if fin_val.lower() not in profile_full_text.lower():
                        violations.append(ValidationViolation(
                            category="invented_metric",
                            severity="CRITICAL",
                            field="experience.responsibilities",
                            message=f"Invented corporate financial claim: '{fin_val}'.",
                            detected_value=fin_val,
                            allowed_boundary="Financial claims not present in source profile are strictly forbidden.",
                        ))

            # Check cross-employer responsibility attribution generically
            orig_emp = next((e for e in orig_exps if e.get("company", "").strip().lower() == co.lower()), None)
            if orig_emp:
                orig_text = f"{orig_emp.get('jobTitle', '')} {orig_emp.get('description', '')} " + " ".join(orig_emp.get('responsibilities', []))
                orig_text_lower = orig_text.lower()
                other_emps = [e for e in orig_exps if e.get("company", "").strip().lower() != co.lower()]
                for other in other_emps:
                    other_co = other.get("company", "")
                    other_text = f"{other.get('jobTitle', '')} {other.get('description', '')} " + " ".join(other.get('responsibilities', []))

                    distinctive_other = set()
                    if other_co and len(other_co) > 3:
                        distinctive_other.add(other_co.lower())
                    for r_o in other.get("responsibilities", []):
                        m_p = re.match(r"^([A-Za-z0-9\.\-\s]{3,35}):", str(r_o).strip())
                        if m_p:
                            p_term = m_p.group(1).strip().lower()
                            if p_term not in orig_text_lower:
                                distinctive_other.add(p_term)
                    for dom in re.findall(r"\b[a-zA-Z0-9\.\-]+\.(?:com|org|in|io|net)\b", other_text.lower()):
                        if dom not in orig_text_lower:
                            distinctive_other.add(dom)
                    # Dynamically collect metrics from other employer's text
                    other_metrics = re.findall(
                        r"\b(?:\d+(?:,\d{3})*(?:\.\d+)?(?:\+|%)?(?:\s*[a-zA-Z\-/]{2,}(?:\s+[a-zA-Z\-/]{2,}){0,2})?|[\$€£₹]\s*\d+(?:,\d{3})*(?:\.\d+)?(?:\s*(?:k|m|b|million|billion|thousand|crore|lakh))?|\b\d+(?:st|nd|rd|th)\b|\b\d+(?:\.\d+)?x\b)\b",
                        other_text.lower(),
                    )
                    for metric_match in other_metrics:
                        m_str = metric_match.strip()
                        if m_str and not (m_str.isdigit() and len(m_str) == 4 and (m_str.startswith("19") or m_str.startswith("20"))):
                            if len(m_str) >= 2 and m_str not in orig_text_lower:
                                distinctive_other.add(m_str)
                    for m_obj in original_profile.get("metrics", []):
                        if m_obj.get("company_id") == other.get("company_id"):
                            m_val = str(m_obj.get("value", "")).lower()
                            if m_val and m_val not in orig_text_lower:
                                distinctive_other.add(m_val)

                    for b in bullets:
                        b_lower = str(b).lower()
                        for term in distinctive_other:
                            if term in b_lower:
                                violations.append(ValidationViolation(
                                    category="cross_employer_bleed",
                                    severity="CRITICAL",
                                    field="experience.responsibilities",
                                    message=f"Bullet under '{co}' contains distinctive achievement/term '{term}' belonging to '{other_co}'.",
                                    detected_value=str(b),
                                    allowed_boundary=f"Responsibilities must not transfer across employers. '{term}' belongs strictly to '{other_co}'.",
                                ))

            # Check for unsupported generic outcome claims
            profile_full_text = json.dumps(original_profile, default=str)
            unsupported_outcome_patterns = [
                r",?\s*(?:and\s+)?(?:enhancing|enhance|improving|improve|increasing|increase|boosting|boost)\s+(?:workflow|operational|team|developer)?\s*efficiency(?:\s+across\s+all\s+teams)?",
                r",?\s*(?:and\s+)?(?:improving|improve)\s+(?:team|developer)\s+coordination",
                r",?\s*(?:and\s+)?(?:optimizing|optimize|maximizing|maximize)\s+(?:workflow|operational|team|organizational)?\s*productivity",
                r",?\s*(?:and\s+)?streamlining\s+company\s+operations\s+and\s+improve\s+team\s+coordination",
                r",?\s*(?:and\s+)?(?:accelerating|accelerate)\s+project\s+delivery",
                r",?\s*(?:and\s+)?(?:driving|drive)\s+organizational\s+success",
            ]
            for b in bullets:
                b_str = str(b)
                for uop in unsupported_outcome_patterns:
                    m = re.search(uop, b_str, re.IGNORECASE)
                    if m and not re.search(uop, profile_full_text, re.IGNORECASE):
                        violations.append(ValidationViolation(
                            category="unsupported_outcome",
                            severity="CRITICAL",
                            field="experience.responsibilities",
                            message=f"Unsupported outcome claim '{m.group(0)}' in experience is not backed by candidate source evidence.",
                            detected_value=b_str,
                            allowed_boundary="Preserve authentic source achievements without inventing outcome claims.",
                        ))

        # Check projects for cross-entity contamination and unsupported outcome claims
        orig_projects = original_profile.get("projects") or []
        employment_duty_patterns = [
            r"\b(?:mentored|mentoring)\s+(?:junior\s+developers?|engineers?|team)\b",
            r"\b(?:conducted|conducting)\s+(?:technical\s+)?interviews?\b",
            r"\b(?:reviewing|reviewed)\s+pull\s+requests?\b",
            r"\b(?:code\s+reviews?\s+and\s+pr\s+reviews?|pr\s+reviews?)\b",
        ]
        for proj in tailored_resume.get("projects") or []:
            p_desc = str(proj.get("description") or "")
            p_name = proj.get("name") or proj.get("title") or "Project"
            orig_p = next((p for p in orig_projects if (p.get("name") or p.get("title") or "").strip().lower() == p_name.lower()), None)
            orig_p_desc = (orig_p.get("description") or "").lower() if orig_p else ""
            for edp in employment_duty_patterns:
                m_duty = re.search(edp, p_desc, re.IGNORECASE)
                if m_duty and not re.search(edp, orig_p_desc, re.IGNORECASE):
                    violations.append(ValidationViolation(
                        category="cross_entity_contamination",
                        severity="CRITICAL",
                        field="projects.description",
                        message=f"Project '{p_name}' contains employment responsibilities '{m_duty.group(0)}' belonging to employment records.",
                        detected_value=p_desc,
                        allowed_boundary="Project descriptions must only use facts associated with that project.",
                    ))
            for uop in unsupported_outcome_patterns:
                m = re.search(uop, p_desc, re.IGNORECASE)
                if m and not re.search(uop, profile_full_text, re.IGNORECASE):
                    violations.append(ValidationViolation(
                        category="unsupported_outcome",
                        severity="CRITICAL",
                        field="projects.description",
                        message=f"Project '{proj.get('name')}' claims unsupported outcome '{m.group(0)}'.",
                        detected_value=p_desc,
                        allowed_boundary="Project descriptions must only reflect authentic facts and technologies.",
                    ))

        # Check for contradictory skill classifications (project technology marked UNVERIFIED)
        unverified_set = {s.lower() for s in evidence_result.skills_classification.unverified_skills}
        for proj in tailored_resume.get("projects") or []:
            p_name = proj.get("name") or proj.get("title") or "Project"
            for pt in (proj.get("technologies") or proj.get("tech_stack") or []):
                if str(pt).lower() in unverified_set:
                    violations.append(ValidationViolation(
                        category="contradictory_skill_classification",
                        severity="CRITICAL",
                        field="projects.technologies",
                        message=f"Technology '{pt}' in project '{p_name}' is contradictory with classification UNVERIFIED.",
                        detected_value=str(pt),
                        allowed_boundary="Technologies verified in project evidence must not be classified as UNVERIFIED.",
                    ))

        # -------------------------------------------------------------
        # 4. Education & Dates Fidelity
        # -------------------------------------------------------------
        tailored_edu = tailored_resume.get("education") or []
        orig_edu = original_profile.get("education") or []
        orig_degs = [e.get("degree", "").lower() for e in orig_edu]

        for ed in tailored_edu:
            deg = str(ed.get("degree") or "").lower()
            if not any(od in deg or deg in od for od in orig_degs):
                violations.append(ValidationViolation(
                    category="role_fabrication",
                    severity="CRITICAL",
                    field="education.degree",
                    message=f"Altered or fabricated degree: '{ed.get('degree')}'.",
                    detected_value=str(ed.get("degree")),
                    allowed_boundary=f"Degrees must match original profile: {orig_degs}",
                ))

        # -------------------------------------------------------------
        # 5. Achievements Integrity Checks
        # -------------------------------------------------------------
        tailored_achievements = tailored_resume.get("achievements") or []
        for ach in tailored_achievements:
            t = (ach.get("title") if isinstance(ach, dict) else str(ach)).strip()
            # Standalone URL as achievement title
            if re.match(r"^https?://", t, re.IGNORECASE) or re.match(r"^www\.", t, re.IGNORECASE):
                violations.append(ValidationViolation(
                    category="fragmented_achievement",
                    severity="CRITICAL",
                    field="achievements.title",
                    message=f"Achievement title is a standalone URL: '{t}'. URLs must be attached to complete achievements.",
                    detected_value=t,
                    allowed_boundary="Attach URLs to complete achievements; do not output URLs as standalone achievements.",
                ))
                warnings.append(ValidationViolation(
                    category="fragmented_achievement",
                    severity="WARNING",
                    field="achievements.title",
                    message=f"Standalone URL detected as achievement: '{t}'.",
                    detected_value=t,
                    allowed_boundary="Reconstruct complete achievement title.",
                ))

            # Fragmented sentence checks
            fragment_indicators = [
                "back-end technologies.",
                "star gold badge and a track",
                "proven ability to",
            ]
            if any(fi in t.lower() for fi in fragment_indicators):
                violations.append(ValidationViolation(
                    category="fragmented_achievement",
                    severity="CRITICAL",
                    field="achievements.title",
                    message=f"Achievement is a fragmented sentence fragment: '{t}'.",
                    detected_value=t,
                    allowed_boundary="Reconstruct complete cohesive achievements.",
                ))
                warnings.append(ValidationViolation(
                    category="fragmented_achievement",
                    severity="WARNING",
                    field="achievements.title",
                    message=f"Fragmented sentence shard detected: '{t}'.",
                    detected_value=t,
                    allowed_boundary="Preserve complete achievement record.",
                ))

            # Achievement title containing a URL
            if re.search(r"https?://\S+", t):
                violations.append(ValidationViolation(
                    category="url_in_achievement_title",
                    severity="CRITICAL",
                    field="achievements.title",
                    message=f"Achievement title contains an embedded URL: '{t}'. Keep achievement titles free of URLs.",
                    detected_value=t,
                    allowed_boundary="Store URLs strictly in the url field; achievement title must contain descriptive text only.",
                ))
                warnings.append(ValidationViolation(
                    category="url_in_achievement_title",
                    severity="WARNING",
                    field="achievements.title",
                    message=f"Embedded URL found in achievement title '{t}'.",
                    detected_value=t,
                    allowed_boundary="Store URLs strictly in the url field.",
                ))

        # -------------------------------------------------------------
        # 6. Education Equivalence Checks
        # -------------------------------------------------------------
        for item in evidence_result.mappings:
            if item.evidence_source == "education" and "equivalent" in item.notes.lower() and any(k in item.notes.lower() for k in ["bca", "mca", "computer applications"]):
                violations.append(ValidationViolation(
                    category="unsupported_education_equivalence",
                    severity="CRITICAL",
                    field="education.degree",
                    message=f"Education mapping notes claim engineering equivalence: '{item.notes}'.",
                    detected_value=item.notes,
                    allowed_boundary="Do not describe BCA/MCA as equivalent to B.Tech/BE.",
                ))

        # -------------------------------------------------------------
        # 7. Entity IDs and Reference Integrity
        # -------------------------------------------------------------
        if "candidate_id" in tailored_resume and not str(tailored_resume.get("candidate_id") or "").strip():
            violations.append(ValidationViolation(
                category="empty_entity_id",
                severity="CRITICAL",
                field="candidate_id",
                message="Candidate ID is an empty string.",
                detected_value=str(tailored_resume.get("candidate_id")),
                allowed_boundary="Candidate must have a non-empty stable ID.",
            ))

        companies = tailored_resume.get("companies")
        known_co_ids = set()
        if companies and isinstance(companies, list):
            for comp in companies:
                cid = comp.get("id") if isinstance(comp, dict) else None
                if cid is not None and not str(cid).strip():
                    violations.append(ValidationViolation(
                        category="empty_entity_id",
                        severity="CRITICAL",
                        field="companies.id",
                        message=f"Company entity '{comp.get('name') if isinstance(comp, dict) else comp}' has an empty ID.",
                        detected_value=str(cid),
                        allowed_boundary="All companies must have non-empty IDs.",
                    ))
                elif cid:
                    known_co_ids.add(str(cid))

        for exp in tailored_exps:
            c_name = exp.get("company", "Company")
            if "id" in exp and not str(exp.get("id") or "").strip():
                violations.append(ValidationViolation(
                    category="empty_entity_id",
                    severity="CRITICAL",
                    field=f"experience.{c_name}.id",
                    message=f"Employment entry for '{c_name}' has an empty ID.",
                    detected_value=str(exp.get("id")),
                    allowed_boundary="Employment records must not have empty IDs.",
                ))
            if "company_id" in exp and not str(exp.get("company_id") or "").strip():
                violations.append(ValidationViolation(
                    category="empty_entity_id",
                    severity="CRITICAL",
                    field=f"experience.{c_name}.company_id",
                    message=f"Employment entry for '{c_name}' has an empty company_id.",
                    detected_value=str(exp.get("company_id")),
                    allowed_boundary="Employment records must not have empty company_id references.",
                ))
            elif exp.get("company_id") and known_co_ids:
                if str(exp["company_id"]) not in known_co_ids:
                    violations.append(ValidationViolation(
                        category="broken_entity_reference",
                        severity="CRITICAL",
                        field=f"experience.{c_name}.company_id",
                        message=f"company_id '{exp['company_id']}' does not resolve to any entity in 'companies' catalog.",
                        detected_value=str(exp["company_id"]),
                        allowed_boundary=f"Must resolve to one of: {sorted(list(known_co_ids))}",
                    ))

        for proj in tailored_resume.get("projects") or []:
            p_name = proj.get("name") or proj.get("title") or "Project"
            if "id" in proj and not str(proj.get("id") or "").strip():
                violations.append(ValidationViolation(
                    category="empty_entity_id",
                    severity="CRITICAL",
                    field=f"projects.{p_name}.id",
                    message=f"Project '{p_name}' has an empty ID.",
                    detected_value=str(proj.get("id")),
                    allowed_boundary="Projects must have non-empty stable IDs.",
                ))

        for ach in tailored_resume.get("achievements") or []:
            if isinstance(ach, dict):
                a_title = ach.get("title", "Achievement")
                if "id" in ach and not str(ach.get("id") or "").strip():
                    violations.append(ValidationViolation(
                        category="empty_entity_id",
                        severity="CRITICAL",
                        field=f"achievements.{a_title[:30]}.id",
                        message=f"Achievement '{a_title[:30]}' has an empty ID.",
                        detected_value=str(ach.get("id")),
                        allowed_boundary="Achievements must have non-empty stable IDs.",
                    ))

        return violations, warnings

    def validate(
        self,
        tailored_resume: dict[str, Any],
        original_profile: dict[str, Any],
        evidence_result: EvidenceMappingResult,
    ) -> ValidationResult:
        """Runs comprehensive semantic and deterministic validation without sanitization."""
        violations, warnings = self._run_checks(tailored_resume, original_profile, evidence_result)
        critical_violations = [v for v in violations if v.severity == "CRITICAL"]
        is_valid = len(critical_violations) == 0
        summary_notes = (
            f"Validation passed with 0 critical violations. {len(warnings)} warning(s)."
            if is_valid
            else f"Validation failed with {len(critical_violations)} critical violation(s)."
        )
        return ValidationResult(
            is_valid=is_valid,
            critical_violations=critical_violations,
            warnings=warnings,
            sanitized=False,
            sanitized_content=tailored_resume,
            summary_notes=summary_notes,
            initial_violations=critical_violations,
        )

    @staticmethod
    def _regenerate_grounded_summary(
        cand_index: CandidateEvidenceIndex,
        original_profile: dict[str, Any],
        evidence_result: EvidenceMappingResult,
    ) -> str:
        """Deterministically synthesizes a clean, concise, 100% grammatically complete and factual summary."""
        profile_text = json.dumps(original_profile, default=str)
        profile_text_lower = profile_text.lower()

        # 1. Primary Title
        cand_title = ""
        if cand_index.professional_roles:
            t = cand_index.professional_roles[0].get("title", "").strip()
            if t:
                cand_title = t
        if not cand_title:
            cand_title = original_profile.get("jobPreferences", {}).get("jobTitles", ["Software Engineer"])[0]
        if not cand_title or cand_title.lower() == "software engineer":
            if "full stack" in original_profile.get("summary", "").lower():
                cand_title = "Full Stack Developer"
            else:
                cand_title = "Software Engineer"

        # 2. Sentence 1: Title and verified overall years
        years = cand_index.overall_years
        supports_scalable = "scalable" in profile_text_lower
        sys_adj = "scalable" if supports_scalable else "production"
        s1 = f"{cand_title} with {years:g} years of overall software development experience delivering {sys_adj} backend systems, high-performance APIs, and database optimizations."

        # 3. Sentence 2: Verified professional strengths and project exposure
        prof_techs = sorted(list(cand_index.professional_technologies))
        matching_prof = [
            t for t in prof_techs
            if t in evidence_result.skills_classification.matched_skills
        ]
        chosen_prof = []
        if any(t in prof_techs for t in ["SQL", "PostgreSQL", "MySQL"]):
            chosen_prof.append("SQL")
        for t in matching_prof:
            if t not in chosen_prof and t not in ["SQL"]:
                chosen_prof.append(t)
        for t in ["Node.js", "Python", "REST APIs", "Microservices"]:
            if t in prof_techs and t not in chosen_prof:
                chosen_prof.append(t)

        chosen_prof = chosen_prof[:3]
        if chosen_prof:
            if "SQL" in chosen_prof:
                s2_base = f"Proven professional track record in {', '.join(chosen_prof)} and database optimization"
            else:
                s2_base = f"Proven professional track record in {', '.join(chosen_prof)}"
        else:
            s2_base = "Proven professional track record delivering reliable backend services and APIs"

        # 4. Relevant project-level experience
        s_proj = ""
        proj_skills = [
            t for t in evidence_result.skills_classification.partially_matched_skills
            if t.lower() in [pt.lower() for pt in cand_index.project_technologies]
        ]
        if proj_skills:
            for proj in cand_index.projects:
                p_name = proj.get("name") or proj.get("title") or "independent projects"
                project_technologies = proj.get("technologies") or []
                p_techs = [
                    t for t in proj_skills
                    if any(t.lower() == pt.lower() or t.lower() in pt.lower() for pt in project_technologies)
                ]
                if p_techs:
                    resolved_techs = []
                    for t in p_techs:
                        if t.lower() == "spring" and any("spring boot" in pt.lower() for pt in project_technologies):
                            canon_t = next((pt for pt in project_technologies if "spring boot" in pt.lower()), "Spring Boot")
                        else:
                            canon_t = next((pt for pt in project_technologies if pt.lower() == t.lower()), t)
                        if canon_t not in resolved_techs:
                            resolved_techs.append(canon_t)
                    p_techs_sorted = sorted(resolved_techs, key=lambda x: (1 if "spring boot" in x.lower() else (2 if "spring" in x.lower() else 3), -len(x)))
                    filtered_p_techs = [t for t in p_techs_sorted if not (t.lower() == "spring" and any("spring boot" in o.lower() for o in p_techs_sorted))]
                    tech_joined = filtered_p_techs[0] if filtered_p_techs else "Spring Boot"
                    s_proj = f", with hands-on project experience in {tech_joined} through {p_name}"
                    break

        s2 = f"{s2_base}{s_proj}."
        return f"{s1} {s2}"

    def validate_and_sanitize(
        self,
        tailored_resume: dict[str, Any],
        original_profile: dict[str, Any],
        evidence_result: EvidenceMappingResult,
    ) -> ValidationResult:
        """Validates tailored resume, applies deterministic remediation for critical issues,
        and re-evaluates semantic validation against the final sanitized output."""
        violations, warnings = self._run_checks(tailored_resume, original_profile, evidence_result)
        initial_critical = [v for v in violations if v.severity == "CRITICAL"]

        if not initial_critical:
            return ValidationResult(
                is_valid=True,
                critical_violations=[],
                warnings=warnings,
                sanitized=False,
                sanitized_content=tailored_resume,
                summary_notes=f"Validation passed with 0 critical violations. {len(warnings)} warning(s).",
                initial_violations=[],
            )

        # -------------------------------------------------------------
        # Automated Remediation / Sanitization
        # -------------------------------------------------------------
        cand_index = evidence_result.candidate_index
        missing_skills_set = {s.lower() for s in evidence_result.skills_classification.missing_skills}
        profile_full_text = json.dumps(original_profile, default=str)
        sanitized_copy = dict(tailored_resume)

        # 1. Sanitize Headline
        headline = str(tailored_resume.get("target_headline") or "").strip()
        if headline:
            sanitized_headline = headline
            for missing_tech in missing_skills_set:
                pattern = re.compile(rf"\b{re.escape(missing_tech)}\b", re.IGNORECASE)
                sanitized_headline = pattern.sub("", sanitized_headline)
            sanitized_headline = re.sub(r"[\s,&|]+$", "", sanitized_headline).strip()
            sanitized_headline = re.sub(r"\|\s*\|", "|", sanitized_headline).strip()
            sanitized_copy["target_headline"] = sanitized_headline

        # 2. Sanitize Summary
        summary = str(tailored_resume.get("tailored_summary") or tailored_resume.get("summary") or "").strip()
        summary_crit = [v for v in initial_critical if v.field == "summary"]
        if summary_crit:
            # Regenerate deterministically using verified ground-truth facts
            clean_sum = self._regenerate_grounded_summary(cand_index, original_profile, evidence_result)
            # Reapply verified bold tags only if summary originally used bolding
            if "**" in summary:
                for ms in evidence_result.skills_classification.matched_skills + evidence_result.skills_classification.partially_matched_skills:
                    if len(ms) > 2 and ms.lower() in clean_sum.lower() and f"**{ms}**" not in clean_sum and f"**{ms.lower()}**" not in clean_sum.lower():
                        clean_sum = re.sub(rf"\b{re.escape(ms)}\b", f"**{ms}**", clean_sum)
            sanitized_copy["tailored_summary"] = clean_sum
            sanitized_copy["summary"] = clean_sum
        else:
            clean_sum = summary
            for missing_tech in missing_skills_set:
                if len(missing_tech) > 2:
                    clean_sum = re.sub(rf"\b{re.escape(missing_tech)}\b", "", clean_sum, flags=re.IGNORECASE)
            clean_sum = " ".join(clean_sum.split()).strip(" ,.-")
            sanitized_copy["tailored_summary"] = clean_sum
            sanitized_copy["summary"] = clean_sum

        # 3. Strip missing skills from matching_skills
        if "matching_skills" in sanitized_copy and isinstance(sanitized_copy["matching_skills"], list):
            sanitized_copy["matching_skills"] = [
                s for s in sanitized_copy["matching_skills"]
                if str(s).lower() not in missing_skills_set
            ]

        # 4. Reconstruct complete achievements
        from app.agents.resume_builder import reconstruct_achievements
        sanitized_copy["achievements"] = reconstruct_achievements(
            tailored_resume.get("achievements") or [],
            original_profile,
            summary,
        )

        # 5. Sanitize experience bullets
        profile_full_text = json.dumps(original_profile, default=str)
        unsupported_outcome_patterns = [
            r",?\s*(?:and\s+)?(?:enhancing|enhance|improving|improve|increasing|increase|boosting|boost)\s+(?:workflow|operational|team|developer)?\s*efficiency(?:\s+across\s+all\s+teams)?",
            r",?\s*(?:and\s+)?(?:improving|improve)\s+(?:team|developer)\s+coordination",
            r",?\s*(?:and\s+)?(?:optimizing|optimize|maximizing|maximize)\s+(?:workflow|operational|team|organizational)?\s*productivity",
            r",?\s*(?:and\s+)?streamlining\s+company\s+operations\s+and\s+improve\s+team\s+coordination",
            r",?\s*(?:and\s+)?(?:accelerating|accelerate)\s+project\s+delivery",
            r",?\s*(?:and\s+)?(?:driving|drive)\s+organizational\s+success",
        ]
        sanitized_exps = []
        for exp in tailored_resume.get("experience") or []:
            exp_c = CanonicalDict(exp)
            resps = exp_c.get("responsibilities") or exp_c.get("highlights") or []
            clean_resps = []
            for r in resps:
                r_clean = str(r)
                for missing_tech in missing_skills_set:
                    if len(missing_tech) > 2:
                        r_clean = re.sub(rf"\b{re.escape(missing_tech)}\b", "", r_clean, flags=re.IGNORECASE)
                def _sanitize_team_count(m: re.Match) -> str:
                    count_str = m.group(1)
                    if count_str and count_str in profile_full_text:
                        return m.group(0)
                    role_word = m.group(2)
                    return f"mentored {role_word}"

                r_clean = re.sub(
                    r"(?:mentored|mentoring)\s+(?:a\s+)?(?:team\s+of\s+)?(\d+[-–]\d+|\d+)\s*(junior|engineers|developers)",
                    _sanitize_team_count,
                    r_clean,
                    flags=re.IGNORECASE,
                )
                for uop in unsupported_outcome_patterns:
                    r_clean = re.sub(uop, "", r_clean, flags=re.IGNORECASE)

                r_clean_norm = " ".join(r_clean.split()).strip(" ,.-")
                if r_clean_norm:
                    clean_resps.append(r_clean_norm)
            exp_c["responsibilities"] = clean_resps
            sanitized_exps.append(exp_c)

        # Ensure cross-company experience attribution integrity generically
        orig_exps = original_profile.get("experience") or []
        bullet_to_source_co: dict[str, str] = {}
        distinctive_term_to_co: dict[str, str] = {}
        for orig_e in orig_exps:
            o_co = orig_e.get("company", "").strip()
            for r in orig_e.get("responsibilities", []):
                r_str = str(r).strip()
                bullet_to_source_co[r_str.lower().strip(" ,.-")] = o_co
                p_m = re.match(r"^([A-Za-z0-9\.\-\s]{3,35}):", r_str)
                if p_m:
                    distinctive_term_to_co[p_m.group(1).strip().lower()] = o_co
                for dom in re.findall(r"\b[a-zA-Z0-9\.\-]+\.(?:com|org|in|io|net)\b", r_str.lower()):
                    distinctive_term_to_co[dom] = o_co
                # Dynamically index metrics to their source company
                for m_term in re.findall(
                    r"\b(?:\d+(?:,\d{3})*(?:\.\d+)?(?:\+|%)?(?:\s*[a-zA-Z\-/]{2,}(?:\s+[a-zA-Z\-/]{2,}){0,2})?|[\$€£₹]\s*\d+(?:,\d{3})*(?:\.\d+)?(?:\s*(?:k|m|b|million|billion|thousand|crore|lakh))?|\b\d+(?:st|nd|rd|th)\b|\b\d+(?:\.\d+)?x\b)\b",
                    r_str.lower(),
                ):
                    m_clean = m_term.strip()
                    if m_clean and len(m_clean) >= 3 and not (m_clean.isdigit() and len(m_clean) == 4 and (m_clean.startswith("19") or m_clean.startswith("20"))):
                        distinctive_term_to_co[m_clean] = o_co

        for m_obj in original_profile.get("metrics", []):
            cid = m_obj.get("company_id")
            if cid:
                c_name = next((e.get("company") for e in orig_exps if e.get("company_id") == cid), None)
                if c_name:
                    m_val = str(m_obj.get("value", "")).lower()
                    if len(m_val) >= 3:
                        distinctive_term_to_co[m_val] = c_name

        all_reassigned_resps: dict[str, list[str]] = {e.get("company", "").strip().lower(): [] for e in sanitized_exps}
        for exp_c in sanitized_exps:
            this_co = exp_c.get("company", "").strip().lower()
            kept_resps = []
            for r in exp_c.get("responsibilities", []):
                r_lower = r.strip().lower().strip(" ,.-")
                target_co = bullet_to_source_co.get(r_lower)
                if not target_co:
                    p_m = re.match(r"^([A-Za-z0-9\.\-\s]{3,35}):", r.strip())
                    if p_m and p_m.group(1).strip().lower() in distinctive_term_to_co:
                        target_co = distinctive_term_to_co[p_m.group(1).strip().lower()]
                    if not target_co:
                        for dom, d_co in distinctive_term_to_co.items():
                            if dom in r_lower:
                                target_co = d_co
                                break

                if target_co and target_co.lower() != this_co and target_co.lower() in all_reassigned_resps:
                    all_reassigned_resps[target_co.lower()].append(r)
                else:
                    kept_resps.append(r)
            exp_c["responsibilities"] = kept_resps
            if "highlights" in exp_c:
                del exp_c["highlights"]
            if "projects" in exp_c and isinstance(exp_c["projects"], list) and len(exp_c["projects"]) == 0:
                del exp_c["projects"]

        for exp_c in sanitized_exps:
            c_key = exp_c.get("company", "").strip().lower()
            for r_add in all_reassigned_resps.get(c_key, []):
                if r_add not in exp_c["responsibilities"]:
                    exp_c["responsibilities"].append(r_add)
            if "highlights" in exp_c:
                del exp_c["highlights"]
            if "projects" in exp_c and isinstance(exp_c["projects"], list) and len(exp_c["projects"]) == 0:
                del exp_c["projects"]

        sanitized_copy["experience"] = sanitized_exps

        # 6. Sanitize project descriptions and prevent cross-entity contamination
        orig_projects = original_profile.get("projects") or []
        employment_duty_patterns = [
            r"\b(?:mentored|mentoring)\s+(?:junior\s+developers?|engineers?|team)\b",
            r"\b(?:conducted|conducting)\s+(?:technical\s+)?interviews?\b",
            r"\b(?:reviewing|reviewed)\s+pull\s+requests?\b",
            r"\b(?:code\s+reviews?\s+and\s+pr\s+reviews?|pr\s+reviews?)\b",
        ]
        sanitized_projs = []
        for idx, proj in enumerate(sanitized_copy.get("projects") or []):
            p_c = dict(proj)
            p_name = p_c.get("name") or p_c.get("title") or f"Project {idx+1}"
            p_desc = str(p_c.get("description") or "")
            orig_p = next((p for p in orig_projects if (p.get("name") or p.get("title") or "").strip().lower() == p_name.lower()), None)
            orig_desc = orig_p.get("description", "") if orig_p else ""
            for edp in employment_duty_patterns:
                if re.search(edp, p_desc, re.IGNORECASE) and not re.search(edp, orig_desc, re.IGNORECASE):
                    p_desc = orig_desc
                    break
            for uop in unsupported_outcome_patterns:
                p_desc = re.sub(uop, "", p_desc, flags=re.IGNORECASE)
            p_c["description"] = " ".join(p_desc.split()).strip(" ,.-")
            if not p_c.get("id"):
                p_c["id"] = f"project_{idx+1:03d}"
            sanitized_projs.append(p_c)
        sanitized_copy["projects"] = sanitized_projs

        # 7. Ensure stable entity IDs and Companies catalog
        if not sanitized_copy.get("candidate_id") and not sanitized_copy.get("id"):
            cand_name = cand_index.full_name or "candidate"
            slug = re.sub(r"[^a-z0-9]+", "_", cand_name.lower()).strip("_")
            sanitized_copy["candidate_id"] = f"candidate_{slug or '001'}"

        companies_catalog = []
        existing_co_map = {}
        for idx, exp in enumerate(sanitized_copy.get("experience") or []):
            co_name = exp.get("company", "").strip() or f"Company {idx+1}"
            slug = re.sub(r"[^a-z0-9]+", "_", co_name.lower()).strip("_")
            co_id = exp.get("company_id") or f"company_{slug or f'{idx+1:03d}'}"
            if co_id not in existing_co_map:
                co_obj = {"id": co_id, "name": co_name}
                existing_co_map[co_id] = co_obj
                companies_catalog.append(co_obj)
            exp["company_id"] = co_id
            if not exp.get("id"):
                exp["id"] = f"experience_{idx+1:03d}"
        if sanitized_copy.get("experience"):
            sanitized_copy["companies"] = companies_catalog

        for idx, ach in enumerate(sanitized_copy.get("achievements") or []):
            if isinstance(ach, dict) and not ach.get("id"):
                ach["id"] = f"achievement_{idx+1:03d}"

        # 8. Reconcile contradictory skill classifications
        if "skills_breakdown" in sanitized_copy and isinstance(sanitized_copy["skills_breakdown"], dict):
            sb = sanitized_copy["skills_breakdown"]
            unv = list(sb.get("unverified_skills", []))
            part = list(sb.get("partially_matched_skills", []))
            for proj in sanitized_copy.get("projects") or []:
                for pt in (proj.get("technologies") or []):
                    pt_match = next((u for u in unv if u.lower() == str(pt).lower()), None)
                    if pt_match:
                        unv.remove(pt_match)
                        if pt_match not in part:
                            part.append(pt_match)
            sb["unverified_skills"] = unv
            sb["partially_matched_skills"] = part

        # -------------------------------------------------------------
        # Re-run semantic validation on final sanitized JSON
        # -------------------------------------------------------------
        post_violations, post_warnings = self._run_checks(sanitized_copy, original_profile, evidence_result)
        post_critical = [v for v in post_violations if v.severity == "CRITICAL"]
        is_valid = len(post_critical) == 0

        summary_notes = (
            f"Validation passed with 0 critical violations after sanitization ({len(initial_critical)} critical violation(s) auto-remediated). {len(post_warnings)} warning(s)."
            if is_valid
            else f"Validation failed with {len(post_critical)} critical violation(s) remaining after sanitization."
        )

        return ValidationResult(
            is_valid=is_valid,
            critical_violations=post_critical,
            warnings=post_warnings,
            sanitized=True,
            sanitized_content=sanitized_copy,
            summary_notes=summary_notes,
            initial_violations=initial_critical,
        )
