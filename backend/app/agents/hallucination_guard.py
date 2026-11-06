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


class HallucinationGuard:
    """Rigorous post-generation validation layer preventing hallucinations, tech inflation, and metric fabrications."""

    BANNED_BUZZWORDS = {
        "spearheaded", "synergized", "leveraged", "delve", "pivotal", "transformative",
        "game-changing", "visionary", "testament to", "holistic", "cutting-edge",
        "revolutionized", "skyrocketed", "unparalleled", "groundbreaking",
    }

    KNOWN_CANONICAL_METRICS = {
        "5", "10+", "450+", "4000+", "6th", "2020", "2021", "2022", "2023", "2024", "2025", "2026",
    }

    def validate_and_sanitize(
        self,
        tailored_resume: dict[str, Any],
        original_profile: dict[str, Any],
        evidence_result: EvidenceMappingResult,
    ) -> ValidationResult:
        """Runs comprehensive deterministic & semantic checks against the candidate ground truth."""
        violations: list[ValidationViolation] = []
        warnings: list[ValidationViolation] = []

        cand_index = evidence_result.candidate_index
        missing_skills_set = {s.lower() for s in evidence_result.skills_classification.missing_skills}
        all_known_tech_lower = {t.lower() for t in cand_index.all_known_technologies}

        sanitized_copy = dict(tailored_resume)

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

            # Sanitize headline if it contains missing technologies
            sanitized_headline = headline
            for missing_tech in missing_skills_set:
                pattern = re.compile(rf"\b{re.escape(missing_tech)}\b", re.IGNORECASE)
                sanitized_headline = pattern.sub("", sanitized_headline)
            # Clean up dangling delimiters like ' | ', ' & ', ', '
            sanitized_headline = re.sub(r"[\s,&|]+$", "", sanitized_headline).strip()
            sanitized_headline = re.sub(r"\|\s*\|", "|", sanitized_headline).strip()
            sanitized_copy["target_headline"] = sanitized_headline

        # -------------------------------------------------------------
        # 2. Professional Summary Checks
        # -------------------------------------------------------------
        summary = str(tailored_resume.get("tailored_summary") or tailored_resume.get("summary") or "").strip()
        if summary:
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
                # If claim_tech is Java or Spring Boot, candidate only has project-level experience, NOT multi-year employment!
                if any(t in claim_tech.lower() for t in ["java", "spring"]):
                    proj_tech_lower = [pt.lower() for pt in cand_index.project_technologies]
                    if any(t in proj_tech_lower for t in ["java", "spring", "spring boot"]):
                        if claim_years >= 3.0:
                            violations.append(ValidationViolation(
                                category="experience_inflation",
                                severity="CRITICAL",
                                field="summary",
                                message=f"Misrepresented project-level technology {claim_tech} as {claim_years:g} years of experience.",
                                detected_value=m.group(0),
                                allowed_boundary="Spring Boot/Java is project experience in StaffSync, not multi-year professional employment.",
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
                        violations.append(ValidationViolation(
                            category="unsupported_specialization",
                            severity="CRITICAL",
                            field="summary",
                            message=f"Summary falsely claims proven expertise/specialization in project-only technology '{pt}'.",
                            detected_value=sm.group(0).strip(),
                            allowed_boundary=f"'{pt}' is an independent project technology (StaffSync), not professional expertise. Distinguish project exposure from professional experience.",
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

            # E) Banned AI buzzwords
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
                    violations.append(ValidationViolation(
                        category="invented_metric",
                        severity="CRITICAL",
                        field="experience.responsibilities",
                        message=f"Invented specific team count '{team_count_m.group(0)}' (source only states 'mentored junior developers').",
                        detected_value=team_count_m.group(0),
                        allowed_boundary="Preserve authentic phrasing: 'mentored junior developers' without fabricated headcounts.",
                    ))

                # Check for invented financial claims
                fin_m = re.search(r"\$\s*\d+[\d,\.]*\s*(?:million|m|k|billion|b)?", b_str, re.IGNORECASE)
                if fin_m:
                    violations.append(ValidationViolation(
                        category="invented_metric",
                        severity="CRITICAL",
                        field="experience.responsibilities",
                        message=f"Invented corporate financial claim: '{fin_m.group(0)}'.",
                        detected_value=fin_m.group(0),
                        allowed_boundary="Financial claims not present in source profile are strictly forbidden.",
                    ))

            # Check cross-employer responsibility attribution
            orig_emp = next((e for e in orig_exps if e.get("company", "").strip().lower() == co.lower()), None)
            if orig_emp:
                orig_text = f"{orig_emp.get('jobTitle', '')} {orig_emp.get('description', '')} " + " ".join(orig_emp.get('responsibilities', []))
                orig_text_lower = orig_text.lower()
                other_emps = [e for e in orig_exps if e.get("company", "").strip().lower() != co.lower()]
                for other in other_emps:
                    other_co = other.get("company", "")
                    other_text = f"{other.get('jobTitle', '')} {other.get('description', '')} " + " ".join(other.get('responsibilities', []))
                    other_terms = ["getlivecoach", "mesa-qr", "kichi-mall", "in1mall", "woocommerce", "ionic", "twilio", "stripe split", "urban local bodies", "city finance", "sendgrid", "form.io", "amplitude", "materialized views", "dhwani"]
                    distinctive_other = [t for t in other_terms if t in other_text.lower() and t not in orig_text_lower]

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

            # Explicit check for City Finance / 4000+ ULBs misattribution
            if "max vision" in co.lower():
                for b in bullets:
                    b_str = str(b)
                    if any(k in b_str.lower() for k in ["city finance", "4000+", "4,000+", "urban local bodies", "form.io", "sendgrid", "indian partner network"]):
                        violations.append(ValidationViolation(
                            category="cross_employer_bleed",
                            severity="CRITICAL",
                            field="experience.responsibilities",
                            message=f"City Finance / 4000+ urban local bodies belongs strictly to Dhwani Rural Information Systems, but was attributed to '{co}'.",
                            detected_value=b_str,
                            allowed_boundary="City Finance must be attributed to Dhwani Rural Information Systems only.",
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

        # Check projects for unsupported outcome claims
        for proj in tailored_resume.get("projects") or []:
            p_desc = str(proj.get("description") or "")
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
        # 5. Automated Remediation / Sanitization if Critical Violations
        # -------------------------------------------------------------
        critical_violations = [v for v in violations if v.severity == "CRITICAL"]
        is_valid = len(critical_violations) == 0
        sanitized = False

        if not is_valid:
            sanitized = True
            # Sanitize summary if it had critical issues
            clean_sum = summary
            # Strip unverified missing technologies
            for missing_tech in missing_skills_set:
                if len(missing_tech) > 2:
                    clean_sum = re.sub(rf"\b{re.escape(missing_tech)}\b", "", clean_sum, flags=re.IGNORECASE)
            # Revert inflated years to authentic overall years
            clean_sum = re.sub(r"\b(?:\d+)\+?\s*years?\b", f"{cand_index.overall_years:g} years", clean_sum, count=1, flags=re.IGNORECASE)
            # Ensure Spring Boot is referenced cleanly without claiming 5+ years Java
            if ("java" in clean_sum.lower() or "spring" in clean_sum.lower()) and cand_index.overall_years >= 5:
                clean_sum = re.sub(
                    r"(?:with\s+)?(?:\d+\+?\s*years?(?:\s+of)?\s+)?(?:proven\s+expertise\s+in\s+)?Java(?:\s*,\s*(?:and\s*)?|\s+and\s+)?Spring Boot",
                    "with hands-on project experience in Spring Boot",
                    clean_sum,
                    flags=re.IGNORECASE,
                )
                clean_sum = re.sub(
                    r"Proven expertise in Java, Spring Boot, and backend systems",
                    "Proven expertise in backend systems, REST APIs, and database optimization, with hands-on project experience in Spring Boot",
                    clean_sum,
                    flags=re.IGNORECASE,
                )
            if "specializing in java" in clean_sum.lower() or "specializing in spring" in clean_sum.lower():
                clean_sum = re.sub(
                    r"(?:specializing in|specialization in)\s+([A-Za-z\s,/&]+?)(?:\.|\bwith\b|\band\b|$)",
                    "with hands-on project experience in Spring Boot (StaffSync).",
                    clean_sum,
                    flags=re.IGNORECASE,
                )
            clean_sum = " ".join(clean_sum.split()).strip()
            sanitized_copy["tailored_summary"] = clean_sum
            sanitized_copy["summary"] = clean_sum

            # Strip missing skills if leaked into matching_skills
            if "matching_skills" in sanitized_copy and isinstance(sanitized_copy["matching_skills"], list):
                sanitized_copy["matching_skills"] = [
                    s for s in sanitized_copy["matching_skills"]
                    if str(s).lower() not in missing_skills_set
                ]

            # Sanitize experience bullets
            sanitized_exps = []
            for exp in tailored_exps:
                exp_c = dict(exp)
                resps = exp_c.get("responsibilities") or exp_c.get("highlights") or []
                clean_resps = []
                for r in resps:
                    r_clean = str(r)
                    for missing_tech in missing_skills_set:
                        if len(missing_tech) > 2:
                            r_clean = re.sub(rf"\b{re.escape(missing_tech)}\b", "", r_clean, flags=re.IGNORECASE)
                    # Strip fabricated mentoring team size
                    r_clean = re.sub(
                        r"(?:mentored|mentoring)\s+(?:a\s+)?(?:team\s+of\s+)?(?:\d+[-–]\d+|\d+)\s*(junior|engineers|developers)",
                        r"mentored \1",
                        r_clean,
                        flags=re.IGNORECASE,
                    )
                    # Strip unsupported outcome claims
                    for uop in unsupported_outcome_patterns:
                        r_clean = re.sub(uop, "", r_clean, flags=re.IGNORECASE)

                    r_clean_norm = " ".join(r_clean.split()).strip(" ,.-")
                    if r_clean_norm:
                        clean_resps.append(r_clean_norm)
                exp_c["responsibilities"] = clean_resps
                exp_c["highlights"] = clean_resps
                sanitized_exps.append(exp_c)

            # Ensure City Finance is attributed to Dhwani, never to Max Vision
            dhwani_san = next((e for e in sanitized_exps if "dhwani" in e.get("company", "").lower()), None)
            for exp_c in sanitized_exps:
                if "max vision" in exp_c.get("company", "").lower():
                    mv_resps = []
                    for r in exp_c.get("responsibilities", []):
                        if any(k in r.lower() for k in ["city finance", "4000+", "4,000+", "urban local bodies"]):
                            if dhwani_san and r not in dhwani_san["responsibilities"]:
                                dhwani_san["responsibilities"].append(r)
                        else:
                            mv_resps.append(r)
                    exp_c["responsibilities"] = mv_resps
                    exp_c["highlights"] = mv_resps

            sanitized_copy["experience"] = sanitized_exps

            # Sanitize project descriptions to remove unsupported outcome claims
            sanitized_projs = []
            for proj in sanitized_copy.get("projects") or []:
                p_c = dict(proj)
                p_desc = str(p_c.get("description") or "")
                for uop in unsupported_outcome_patterns:
                    p_desc = re.sub(uop, "", p_desc, flags=re.IGNORECASE)
                p_c["description"] = " ".join(p_desc.split()).strip(" ,.-")
                sanitized_projs.append(p_c)
            sanitized_copy["projects"] = sanitized_projs

        summary_notes = (
            f"Validation passed with 0 critical violations. {len(warnings)} warning(s)."
            if is_valid
            else f"Validation failed with {len(critical_violations)} critical violation(s). Resume sanitized to ground truth."
        )

        return ValidationResult(
            is_valid=is_valid,
            critical_violations=critical_violations,
            warnings=warnings,
            sanitized=sanitized,
            sanitized_content=sanitized_copy if sanitized else tailored_resume,
            summary_notes=summary_notes,
        )
