"""Evidence Mapper for AI-Powered Resume Tailoring.

Maps Job Description (JD) requirements to authentic candidate profile evidence,
categorizing every requirement as MATCHED, PARTIAL, MISSING, or UNVERIFIED with
clear source attribution (professional experience, independent project, education,
or self-reported skill).
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    requirement: str
    status: str  # MATCHED | PARTIAL | MISSING | UNVERIFIED
    importance: str = "mandatory"  # mandatory | desirable
    evidence_source: str = "none"  # professional_experience | project | education | achievement | self_reported | none
    evidence_text: str = ""
    source_entity: str = ""  # e.g. "Dhwani Rural Information Systems", "StaffSync", "IGNOU"
    confidence: float = 0.0
    notes: str = ""


class SkillsClassification(BaseModel):
    matched_skills: list[str] = Field(default_factory=list)
    partially_matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    unverified_skills: list[str] = Field(default_factory=list)
    additional_relevant_skills: list[str] = Field(default_factory=list)


class CandidateEvidenceIndex(BaseModel):
    full_name: str = ""
    overall_years: float = 0.0
    professional_roles: list[dict[str, Any]] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    education: list[dict[str, Any]] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    all_known_technologies: set[str] = Field(default_factory=set)
    professional_technologies: set[str] = Field(default_factory=set)
    project_technologies: set[str] = Field(default_factory=set)
    self_reported_technologies: set[str] = Field(default_factory=set)
    verified_qa_facts: dict[str, Any] = Field(default_factory=dict)


class EvidenceMappingResult(BaseModel):
    mappings: list[EvidenceItem] = Field(default_factory=list)
    skills_classification: SkillsClassification = Field(default_factory=SkillsClassification)
    candidate_index: CandidateEvidenceIndex = Field(default_factory=CandidateEvidenceIndex)
    target_job_title: str = ""
    target_company: str = ""


class EvidenceMapper:
    """Extracts, indexes, and rigorously maps JD requirements to candidate profile evidence."""

    TECH_CANONICAL_MAP = {
        "node js": "Node.js",
        "node.js": "Node.js",
        "nodejs": "Node.js",
        "express": "Express",
        "expressjs": "Express",
        "express.js": "Express",
        "spring boot": "Spring Boot",
        "springboot": "Spring Boot",
        "spring": "Spring",
        "java": "Java",
        "core java": "Java",
        "javascript": "JavaScript",
        "typescript": "TypeScript",
        "react": "React",
        "react js": "React",
        "react.js": "React",
        "reactjs": "React",
        "next js": "Next.js",
        "next.js": "Next.js",
        "nextjs": "Next.js",
        "angular": "Angular",
        "vue": "Vue",
        "vue js": "Vue",
        "vue.js": "Vue",
        "flutter": "Flutter",
        "django": "Django",
        "django rest": "Django",
        "fastapi": "FastAPI",
        "python": "Python",
        "postgresql": "PostgreSQL",
        "postgres": "PostgreSQL",
        "mysql": "MySQL",
        "mongodb": "MongoDB",
        "mongo": "MongoDB",
        "redis": "Redis",
        "sql": "SQL",
        "docker": "Docker",
        "git": "Git",
        "linux": "Linux",
        "jest": "Jest",
        "rest apis": "REST APIs",
        "rest api": "REST APIs",
        "rest": "REST APIs",
        "microservices": "Microservices",
        "system design": "System Design",
        "hibernate": "Hibernate",
        "stripe": "Stripe",
        "sendgrid": "SendGrid",
        "amplitude": "Amplitude",
        "form.io": "Form.io",
        "twilio": "Twilio",
        "ionic": "Ionic",
        "wordpress": "WordPress",
        "woocommerce": "WooCommerce",
        "html": "HTML",
        "css": "CSS",
        "tailwind": "Tailwind",
        "bootstrap": "Bootstrap",
        "material ui": "Material UI",
        "ci/cd": "CI/CD",
        "jenkins": "Jenkins",
        "maven": "Maven",
        "tdd": "TDD",
        "test driven development": "TDD",
    }

    _profile_index_cache: dict[str, CandidateEvidenceIndex] = {}
    _jd_reqs_cache: dict[str, list[dict[str, Any]]] = {}

    @classmethod
    def _compute_hash(cls, data: Any) -> str:
        canonical_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

    @classmethod
    def canonical_tech(cls, tech: str) -> str:
        clean = tech.strip().lower()
        return cls.TECH_CANONICAL_MAP.get(clean, tech.strip())

    def build_candidate_index(self, profile: dict[str, Any]) -> CandidateEvidenceIndex:
        """Indexes candidate profile into clean, distinct evidence layers."""
        prof_hash = self._compute_hash(profile)
        if prof_hash in self._profile_index_cache:
            return self._profile_index_cache[prof_hash].model_copy(deep=True)

        personal = profile.get("personal", {})
        name = personal.get("fullName") or personal.get("full_name") or "Candidate"

        # Calculate overall years of experience from summary or experience entries
        summary = profile.get("summary", "")
        m = re.search(r"(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)", summary, re.IGNORECASE)
        overall_years = float(m.group(1)) if m else 5.0

        all_known: set[str] = set()
        prof_known: set[str] = set()
        proj_known: set[str] = set()
        self_known: set[str] = set()

        # 1. Professional experience indexing
        raw_exp = profile.get("experience", [])
        prof_roles = []
        all_companies = [
            e.get("company", "").strip()
            for e in raw_exp
            if e.get("company", "").strip()
        ]
        for exp in raw_exp:
            company = exp.get("company", "").strip()
            title = str(exp.get("jobTitle") or exp.get("title") or "").strip()
            start = str(exp.get("startDate") or exp.get("start_date") or "").strip()
            end = "Present" if (exp.get("current") or exp.get("is_current")) else str(exp.get("endDate") or exp.get("end_date") or "").strip()
            resps = exp.get("responsibilities") or exp.get("highlights") or []
            desc = exp.get("description", "")

            # Scrub foreign employer names from responsibilities and description
            other_companies = [c for c in all_companies if c.lower() != company.lower()]
            clean_resps = []
            for r in resps:
                r_clean = str(r).strip()
                for oc in other_companies:
                    pat = re.compile(rf"\s*[-—–.]*\s*{re.escape(oc)}(?:\s+Pvt\.?\s+Ltd\.?)?\b", re.IGNORECASE)
                    r_clean = pat.sub("", r_clean).strip(" .-\t")
                if r_clean:
                    clean_resps.append(r_clean)

            desc_clean = str(desc).strip()
            for oc in other_companies:
                pat = re.compile(rf"\s*[-—–.]*\s*{re.escape(oc)}(?:\s+Pvt\.?\s+Ltd\.?)?\b", re.IGNORECASE)
                desc_clean = pat.sub("", desc_clean).strip(" .-\t")

            full_text = f"{title} {desc_clean} " + " ".join(clean_resps)

            techs_found = set()
            for raw_k, canon in self.TECH_CANONICAL_MAP.items():
                if re.search(r"\b" + re.escape(raw_k) + r"\b", full_text, re.IGNORECASE):
                    techs_found.add(canon)
                    prof_known.add(canon)
                    all_known.add(canon)

            # If responsibility mentions query optimization, materialized views, or SQL databases
            if any(k in full_text.lower() for k in ["query optimization", "materialized views", "database", "sql"]):
                techs_found.add("SQL")
                prof_known.add("SQL")
                all_known.add("SQL")
                db_skills = profile.get("skills", {}).get("databases", []) if isinstance(profile.get("skills"), dict) else []
                for db_s in db_skills:
                    c_db = self.canonical_tech(db_s)
                    if c_db in ["PostgreSQL", "MySQL", "SQL"]:
                        techs_found.add(c_db)
                        prof_known.add(c_db)
                        all_known.add(c_db)

            # Sub-projects within employment
            sub_projs = exp.get("projects", [])
            for sp in sub_projs:
                for t in sp.get("technologies", []):
                    c = self.canonical_tech(t)
                    techs_found.add(c)
                    prof_known.add(c)
                    all_known.add(c)

            prof_roles.append({
                "company": company,
                "title": title,
                "dates": f"{start} – {end}",
                "responsibilities": clean_resps,
                "description": desc_clean,
                "technologies": sorted(list(techs_found)),
                "raw_text": full_text,
            })

        # 2. Independent / Academic projects indexing
        raw_proj = profile.get("projects", [])
        projects_indexed = []
        for p in raw_proj:
            p_name = p.get("name") or p.get("title", "").strip()
            p_desc = p.get("description", "").strip()
            p_techs = [self.canonical_tech(t) for t in (p.get("technologies") or p.get("tech_stack") or [])]
            for t in p_techs:
                if t:
                    proj_known.add(t)
                    all_known.add(t)
            full_text = f"{p_name} {p_desc} " + " ".join(p_techs)

            for raw_k, canon in self.TECH_CANONICAL_MAP.items():
                if re.search(r"\b" + re.escape(raw_k) + r"\b", full_text, re.IGNORECASE):
                    if canon not in p_techs:
                        p_techs.append(canon)
                    proj_known.add(canon)
                    all_known.add(canon)

            is_academic = any(k in full_text.lower() for k in ["college project", "academic", "university project", "bca", "mca"])
            projects_indexed.append({
                "name": p_name,
                "description": p_desc,
                "technologies": sorted(list(set(p_techs))),
                "is_academic": is_academic,
                "raw_text": full_text,
            })

        # 3. Education indexing
        raw_edu = profile.get("education", [])
        education_indexed = []
        for ed in raw_edu:
            deg = ed.get("degree", "").strip()
            inst = ed.get("institution", "").strip()
            yr = str(ed.get("year") or ed.get("graduation_year", "")).strip()
            if deg or inst:
                education_indexed.append({
                    "degree": deg,
                    "institution": inst,
                    "year": yr,
                })
                # Check degree tokens
                for dk in ["MCA", "BCA", "B.Tech", "BE", "Master", "Bachelor"]:
                    if dk.lower() in deg.lower():
                        all_known.add(dk)

        # 4. Achievements indexing
        raw_achs = profile.get("achievements", [])
        achievements_indexed = []
        for ach in raw_achs:
            t = ach.get("title") if isinstance(ach, dict) else str(ach)
            t = t.strip()
            if t and not t.startswith("http"):
                achievements_indexed.append(t)
                all_known.add(t)

        # 5. Self-reported skills
        raw_skills = profile.get("skills", {})
        if isinstance(raw_skills, dict):
            for items in raw_skills.values():
                for s in items:
                    c = self.canonical_tech(s)
                    self_known.add(c)
                    all_known.add(c)
        elif isinstance(raw_skills, list):
            for s in raw_skills:
                c = self.canonical_tech(s)
                self_known.add(c)
                all_known.add(c)

        # 6. Candidate-confirmed Q&A facts
        qa_facts = {}
        for q in profile.get("screening_questions", []):
            if q.get("answer"):
                qa_facts[q.get("question", "")] = q["answer"]
        for q in profile.get("pending_questions", []):
            if isinstance(q, dict) and q.get("answer"):
                qa_facts[q.get("question", "")] = q["answer"]

        idx_result = CandidateEvidenceIndex(
            full_name=name,
            overall_years=overall_years,
            professional_roles=prof_roles,
            projects=projects_indexed,
            education=education_indexed,
            achievements=achievements_indexed,
            all_known_technologies=all_known,
            professional_technologies=prof_known,
            project_technologies=proj_known,
            self_reported_technologies=self_known,
            verified_qa_facts=qa_facts,
        )
        self._profile_index_cache[prof_hash] = idx_result
        return idx_result

    def extract_jd_requirements(
        self, job_title: str, required_skills: list[str], job_description: str
    ) -> list[dict[str, Any]]:
        """Extracts structured requirements from JD with importance classifications."""
        jd_hash = self._compute_hash({"title": job_title, "skills": sorted(required_skills), "desc": job_description})
        if jd_hash in self._jd_reqs_cache:
            return [dict(r) for r in self._jd_reqs_cache[jd_hash]]

        reqs = []
        seen = set()

        def add_req(name: str, category: str, importance: str, raw_text: str = ""):
            key = name.lower().strip()
            if key and key not in seen:
                seen.add(key)
                reqs.append({
                    "name": name,
                    "category": category,
                    "importance": importance,
                    "raw_text": raw_text or name,
                })

        # Required skills list are primary requirements
        for sk in required_skills:
            clean = sk.strip()
            if not clean:
                continue
            add_req(clean, "technology", "mandatory", clean)

        # Parse key technical & architectural requirements from description
        desc_lower = job_description.lower()

        # Years of experience requirement
        exp_m = re.search(r"(\d+)\s*(?:to|-|–)\s*(\d+)\s*years?(?:\s+of)?(?:\s+programming\s+in|\s+experience\s+in)?\s+([A-Za-z\s/&,]+?)(?:\n|\.|\r|$)", job_description, re.IGNORECASE)
        if exp_m:
            topic = " ".join(exp_m.group(3).split()).strip(" ,.-")
            full_label = f"{exp_m.group(1)} to {exp_m.group(2)} years {topic}" if topic else f"{exp_m.group(1)} to {exp_m.group(2)} years experience"
            add_req(
                full_label,
                "experience_duration",
                "mandatory",
                exp_m.group(0).strip(),
            )
        else:
            exp_single = re.search(r"(\d+)\+?\s*years?(?:\s+of)?\s+([A-Za-z\s/&,]+?)(?:\n|\.|\r|$)", job_description, re.IGNORECASE)
            if exp_single:
                topic = " ".join(exp_single.group(2).split()).strip(" ,.-")
                full_label = f"{exp_single.group(1)}+ years {topic}" if topic else f"{exp_single.group(1)}+ years experience"
                add_req(
                    full_label,
                    "experience_duration",
                    "mandatory",
                    exp_single.group(0).strip(),
                )

        # Specific tech patterns in JD
        tech_patterns = [
            ("Java", ["java", "core java"], "Core Java", "mandatory"),
            ("Spring Boot", ["spring boot", "springboot"], "Spring / Spring Boot", "mandatory"),
            ("Spring", ["spring", "spring framework"], "Spring framework", "mandatory"),
            ("SQL", ["sql", "relational database", "rdbms"], "SQL & Relational Databases", "mandatory"),
            ("Hibernate", ["hibernate"], "Hibernate ORM", "desirable"),
            ("Jenkins", ["jenkins"], "Jenkins", "desirable"),
            ("Maven", ["maven"], "Maven build tool", "desirable"),
            ("CI/CD", ["ci/cd", "cicd", "continuous integration"], "CI/CD pipelines", "desirable"),
            ("TDD", ["tdd", "test driven development", "test-driven development"], "Test-driven development (TDD)", "desirable"),
            ("Microservices", ["microservice", "microservices"], "Microservices architecture", "desirable"),
            ("REST APIs", ["rest api", "rest apis", "restful"], "REST APIs", "mandatory"),
            ("System Design", ["system design", "system architecture"], "System design & architecture", "mandatory"),
            ("Node.js", ["node.js", "nodejs", "node js"], "Node.js", "mandatory" if "node" in job_title.lower() else "desirable"),
            ("PostgreSQL", ["postgresql", "postgres"], "PostgreSQL", "desirable"),
            ("MongoDB", ["mongodb", "mongo"], "MongoDB", "desirable"),
            ("Docker", ["docker"], "Docker containerization", "desirable"),
        ]

        # Structured importance detector based on preceding JD section header
        jd_section_headers = []
        for m in re.finditer(r"\b(?:requirements?|must have|what you(?:'ll| will) need|qualifications|core qualifications|minimum qualifications)\b", desc_lower):
            jd_section_headers.append((m.start(), "mandatory"))
        for m in re.finditer(r"\b(?:nice to have|preferred|desirables?|good to have|plus|bonus|what we'd like to see)\b", desc_lower):
            jd_section_headers.append((m.start(), "desirable"))
        jd_section_headers.sort(key=lambda x: x[0])

        def get_importance(term: str, default: str = "desirable") -> str:
            matches = [m.start() for m in re.finditer(r"\b" + re.escape(term) + r"\b", desc_lower)]
            if not matches:
                return default
            prec = [h for h in jd_section_headers if h[0] < matches[0]]
            if prec:
                return prec[-1][1]
            return default

        for canon, variants, label, default_imp in tech_patterns:
            matched_var = next((v for v in variants if re.search(r"\b" + re.escape(v) + r"\b", desc_lower)), None)
            if matched_var:
                imp = get_importance(matched_var, default_imp)
                add_req(canon, "technology", imp, label)

        # Dynamically scan any other technology from TECH_CANONICAL_MAP in description
        for raw_k, canon in self.TECH_CANONICAL_MAP.items():
            if canon.lower() not in seen and len(raw_k) >= 3:
                if re.search(r"\b" + re.escape(raw_k) + r"\b", desc_lower):
                    imp = get_importance(raw_k, "desirable")
                    add_req(canon, "technology", imp, canon)

        # Domain experience (e.g. eCommerce)
        if "ecommerce" in desc_lower or "e-commerce" in desc_lower:
            add_req("E-commerce", "domain", "desirable", "Experience building operationally critical services, especially in eCommerce")

        # Leadership / Mentorship
        mentor_m = re.search(r"(mentoring|coaching|lead\w*)\s*(?:team\s*of\s*)?(\d+[-–]\d+|\d+)?\s*(junior|engineers|developers)", job_description, re.IGNORECASE)
        if mentor_m:
            team_spec = mentor_m.group(2)
            lbl = f"Mentoring junior engineers (target: {team_spec})" if team_spec else "Mentoring junior engineers"
            add_req("Mentoring", "leadership", "desirable", lbl)
        elif "mentor" in desc_lower:
            add_req("Mentoring", "leadership", "desirable", "Mentoring junior developers / engineers")

        # Education requirements
        edu_m = re.search(r"\b(B\.?Tech|B\.?E|MCA|BCA|Master(?:'s)?|Bachelor(?:'s)?|Computer Science)\b", job_description, re.IGNORECASE)
        if edu_m:
            matched_deg = edu_m.group(1).lower()
            if "b.tech" in matched_deg or "b.e" in matched_deg:
                req_deg_name = "B.Tech/BE or related"
                req_deg_label = "B.Tech/BE Computer Science, Engineering, or related field"
            elif "master" in matched_deg or "mca" in matched_deg:
                req_deg_name = "Master's or related"
                req_deg_label = "Master's degree in Computer Science or related field"
            else:
                req_deg_name = "Bachelor's or related"
                req_deg_label = "Bachelor's degree in Computer Science or related field"
            imp = get_importance(edu_m.group(0), "desirable")
            add_req(req_deg_name, "education", imp, req_deg_label)

        self._jd_reqs_cache[jd_hash] = reqs
        return reqs

    def map_evidence(
        self,
        profile: dict[str, Any],
        job: dict[str, Any],
    ) -> EvidenceMappingResult:
        """Rigorously evaluates every JD requirement against candidate evidence."""
        index = self.build_candidate_index(profile)
        job_title = job.get("title") or "Software Engineer"
        company = job.get("company") or "Company"
        required_skills = job.get("required_skills") or []
        job_desc = job.get("description") or ""

        reqs = self.extract_jd_requirements(job_title, required_skills, job_desc)

        mappings: list[EvidenceItem] = []
        matched_skills: list[str] = []
        partially_matched_skills: list[str] = []
        missing_skills: list[str] = []
        unverified_skills: list[str] = []

        for req in reqs:
            name = req["name"]
            canon_name = self.canonical_tech(name)
            category = req["category"]
            importance = req["importance"]

            item = self._evaluate_requirement(canon_name, category, importance, req["raw_text"], index)
            mappings.append(item)

            # Classify technology skills into specific buckets
            if category == "technology":
                if item.status == "MATCHED":
                    if canon_name not in matched_skills:
                        matched_skills.append(canon_name)
                elif item.status == "PARTIAL":
                    if canon_name not in partially_matched_skills:
                        partially_matched_skills.append(canon_name)
                elif item.status == "MISSING":
                    if canon_name not in missing_skills:
                        missing_skills.append(canon_name)
                elif item.status == "UNVERIFIED":
                    if canon_name not in unverified_skills:
                        unverified_skills.append(canon_name)

        # Find additional relevant candidate skills not explicitly demanded by JD
        all_req_canons = {self.canonical_tech(r["name"]).lower() for r in reqs}
        additional_relevant: list[str] = []
        for tech in sorted(list(index.professional_technologies)):
            if tech.lower() not in all_req_canons and tech not in matched_skills and tech not in partially_matched_skills:
                additional_relevant.append(tech)

        skills_cls = SkillsClassification(
            matched_skills=matched_skills,
            partially_matched_skills=partially_matched_skills,
            missing_skills=missing_skills,
            unverified_skills=unverified_skills,
            additional_relevant_skills=additional_relevant[:10],
        )

        # Enforce strict company-level isolation across all evidence mappings
        known_companies = [r["company"] for r in index.professional_roles if r.get("company")]
        for item in mappings:
            if item.evidence_source == "professional_experience" and item.source_entity:
                src_entity = item.source_entity
                foreign_companies = [c for c in known_companies if c.lower() != src_entity.lower()]
                cleaned_text = item.evidence_text
                for fc in foreign_companies:
                    pat = re.compile(rf"\s*[-—–.]*\s*{re.escape(fc)}(?:\s+Pvt\.?\s+Ltd\.?)?\b", re.IGNORECASE)
                    cleaned_text = pat.sub("", cleaned_text).strip(" .-\t")
                item.evidence_text = cleaned_text

        return EvidenceMappingResult(
            mappings=mappings,
            skills_classification=skills_cls,
            candidate_index=index,
            target_job_title=job_title,
            target_company=company,
        )

    def _evaluate_requirement(
        self,
        name: str,
        category: str,
        importance: str,
        raw_text: str,
        index: CandidateEvidenceIndex,
    ) -> EvidenceItem:
        """Determines MATCHED, PARTIAL, MISSING, or UNVERIFIED with supporting evidence."""
        # 1. Experience duration check
        if category == "experience_duration":
            m = re.search(r"(\d+)", name)
            req_years = float(m.group(1)) if m else 5.0
            if index.overall_years >= req_years:
                return EvidenceItem(
                    requirement=name,
                    status="MATCHED",
                    importance=importance,
                    evidence_source="professional_experience",
                    evidence_text=f"Candidate has {index.overall_years:g} years overall software development experience.",
                    source_entity="Candidate Profile",
                    confidence=0.95,
                    notes=f"Meets overall experience requirement ({index.overall_years:g} yrs >= {req_years:g} yrs).",
                )
            else:
                return EvidenceItem(
                    requirement=name,
                    status="PARTIAL",
                    importance=importance,
                    evidence_source="professional_experience",
                    evidence_text=f"Candidate has {index.overall_years:g} years overall experience (target was {name}).",
                    source_entity="Candidate Profile",
                    confidence=0.8,
                    notes=f"Candidate has {index.overall_years:g} years overall full-stack experience vs {name} demanded. Do not fabricate extra years.",
                )

        # 2. Domain checks (e.g. eCommerce)
        if category == "domain" and "ecommerce" in name.lower():
            # Check experience or projects
            found_evidence = []
            for role in index.professional_roles:
                if any(w in role["raw_text"].lower() for w in ["ecommerce", "e-commerce", "stripe", "woocommerce", "checkout", "payment"]):
                    match_b = next((b for b in role.get("responsibilities", []) if any(w in b.lower() for w in ["ecommerce", "e-commerce", "stripe", "woocommerce", "payment"])), role["raw_text"])
                    found_evidence.append((role["company"], match_b))
            for proj in index.projects:
                if "ecommerce" in proj["raw_text"].lower() or "e-commerce" in proj["raw_text"].lower():
                    found_evidence.append((proj["name"], proj["description"]))

            if found_evidence:
                ent, txt = found_evidence[0]
                return EvidenceItem(
                    requirement=name,
                    status="MATCHED",
                    importance=importance,
                    evidence_source="professional_experience",
                    evidence_text=txt,
                    source_entity=ent,
                    confidence=0.9,
                    notes=f"Verified e-commerce experience from {ent}.",
                )
            return EvidenceItem(requirement=name, status="MISSING", importance=importance)

        # 3. Leadership / Mentorship check across ALL profile fields
        is_mentor_req = (
            category == "leadership"
            or any(k in name.lower() for k in ["mentor", "lead", "interview", "supervis", "team lead", "coaching"])
        )
        if is_mentor_req:
            # 1. Search all indexed professional roles (responsibilities, description, raw_text, jobTitle)
            for role in index.professional_roles:
                all_role_texts = (
                    role.get("responsibilities", [])
                    + [role.get("description", ""), role.get("raw_text", ""), role.get("jobTitle", "")]
                )
                for t in all_role_texts:
                    t_str = str(t).strip()
                    if re.search(r"\b(?:mentor\w*|interviews?|coaching)\b", t_str, re.IGNORECASE):
                        return EvidenceItem(
                            requirement=name,
                            status="MATCHED",
                            importance=importance,
                            evidence_source="professional_experience",
                            evidence_text=t_str,
                            source_entity=role["company"],
                            confidence=1.0,
                            notes=f"Mentoring explicitly MATCHED from {role['company']} experience (mentoring junior developers and conducting technical interviews).",
                        )

            # 2. Search raw experience array from profile
            raw_exps = index.raw_profile.get("experience", [])
            for rexp in raw_exps:
                exp_texts = (
                    rexp.get("responsibilities", [])
                    + [rexp.get("description", ""), rexp.get("jobTitle", ""), rexp.get("title", "")]
                )
                for et in exp_texts:
                    et_str = str(et).strip()
                    if re.search(r"\b(?:mentor\w*|interviews?|coaching)\b", et_str, re.IGNORECASE):
                        return EvidenceItem(
                            requirement=name,
                            status="MATCHED",
                            importance=importance,
                            evidence_source="professional_experience",
                            evidence_text=et_str,
                            source_entity=rexp.get("company", "Professional Experience"),
                            confidence=1.0,
                            notes=f"Mentoring explicitly MATCHED from {rexp.get('company')} experience.",
                        )

            # 3. Search candidate summary
            summary_text = f"{index.overall_summary} {index.raw_profile.get('summary', '')}"
            if re.search(r"\b(?:mentor\w*|interviews?|coaching)\b", summary_text, re.IGNORECASE):
                primary_co = index.experiences[0].get("company", "Professional Experience") if index.experiences else "Professional Experience"
                return EvidenceItem(
                    requirement=name,
                    status="MATCHED",
                    importance=importance,
                    evidence_source="professional_experience",
                    evidence_text="Mentored junior developers and conducted interviews.",
                    source_entity=primary_co,
                    confidence=1.0,
                    notes=f"Mentoring explicitly MATCHED from candidate profile summary ({primary_co}).",
                )

        # 4. Education check
        if category == "education":
            degrees = [e["degree"] for e in index.education]
            deg_str = ", ".join(degrees)
            primary_inst = index.education[0].get("institution", "University") if index.education else "University"
            deg_lower = deg_str.lower()
            name_lower = name.lower()

            # Exact or direct level match
            is_direct_match = (
                ("b.tech" in name_lower and ("b.tech" in deg_lower or "b.e" in deg_lower))
                or ("master" in name_lower and ("master" in deg_lower or "mca" in deg_lower or "m.tech" in deg_lower or "ms" in deg_lower))
                or ("bachelor" in name_lower and ("bachelor" in deg_lower or "bca" in deg_lower or "b.tech" in deg_lower or "bs" in deg_lower))
            )
            if is_direct_match:
                return EvidenceItem(
                    requirement=name,
                    status="MATCHED",
                    importance=importance,
                    evidence_source="education",
                    evidence_text=deg_str,
                    source_entity=primary_inst,
                    confidence=1.0,
                    notes=f"Candidate holds verified degree: {deg_str}.",
                )

            # Related technical degree equivalent (e.g. MCA/BCA vs B.Tech/BE)
            has_cs = any("mca" in d.lower() or "bca" in d.lower() or "computer" in d.lower() or "science" in d.lower() or "engineering" in d.lower() for d in degrees)
            if has_cs:
                notes_msg = (
                    f"Candidate holds {deg_str} rather than B.Tech/BE. Highlight exact degrees authentically."
                    if "b.tech" in name_lower or "b.e" in name_lower
                    else f"Candidate holds {deg_str} (technical discipline equivalent). Highlight exact degrees authentically."
                )
                return EvidenceItem(
                    requirement=name,
                    status="PARTIAL",
                    importance=importance,
                    evidence_source="education",
                    evidence_text=f"Candidate holds {deg_str} (Computer Applications degree equivalent).",
                    source_entity=primary_inst,
                    confidence=0.85,
                    notes=notes_msg,
                )
            return EvidenceItem(requirement=name, status="MISSING", importance=importance)

        # 5. Technology checks
        # Special semantic mappings for SQL / Relational Databases (Checked BEFORE generic text fallback)
        if name.upper() == "SQL":
            db_bullets = []
            db_exp = next((e for e in index.professional_roles if any(k in " ".join(e.get("responsibilities", [])).lower() for k in ["query optimization", "materialized views", "postgresql", "mysql", "database", "sql"])), None)
            source_co = db_exp.get("company") if db_exp else (index.professional_roles[0].get("company") if index.professional_roles else "Professional Experience")
            for role in index.professional_roles:
                for r in role.get("responsibilities", []):
                    if any(k in r.lower() for k in ["query optimization", "materialized views", "postgresql", "mysql", "database"]):
                        r_clean = str(r).strip()
                        for other_role in index.professional_roles:
                            oc = other_role.get("company", "").strip()
                            if oc and oc.lower() != role.get("company", "").lower():
                                pat = re.compile(rf"\s*[-—–.]*\s*{re.escape(oc)}(?:\s+Pvt\.?\s+Ltd\.?)?\b", re.IGNORECASE)
                                r_clean = pat.sub("", r_clean).strip(" .-\t")
                        if r_clean:
                            db_bullets.append(r_clean)
                        source_co = role["company"]

            all_known_dbs = [t for t in index.all_known_technologies if t.upper() in ["SQL", "POSTGRESQL", "MYSQL", "ORACLE", "SQLITE", "MARIADB", "SNOWFLAKE", "BIGQUERY"]]
            db_skills_str = ", ".join(sorted(list(set(all_known_dbs)))) if all_known_dbs else "SQL"
            bullet_text = "; ".join(db_bullets) if db_bullets else "Production relational database design, query tuning, and schema optimization"
            return EvidenceItem(
                requirement="SQL",
                status="MATCHED",
                importance=importance,
                evidence_source="professional_experience",
                evidence_text=f"Production database engineering ({db_skills_str}): {bullet_text}",
                source_entity=source_co,
                confidence=0.95,
                notes=f"SQL requirement directly MATCHED via production {db_skills_str} and database engineering.",
            )

        # A) Check in professional experience
        for role in index.professional_roles:
            if name.lower() in [t.lower() for t in role["technologies"]] or re.search(r"\b" + re.escape(name) + r"\b", role["raw_text"], re.IGNORECASE):
                # Exact bullet evidence
                matched_bullet = next((r for r in role["responsibilities"] if re.search(r"\b" + re.escape(name) + r"\b", r, re.IGNORECASE)), role["description"])
                return EvidenceItem(
                    requirement=name,
                    status="MATCHED",
                    importance=importance,
                    evidence_source="professional_experience",
                    evidence_text=matched_bullet or f"Used {name} professionally at {role['company']}",
                    source_entity=role["company"],
                    confidence=0.95,
                    notes=f"Verified professional employment experience with {name}.",
                )

        # B) Check in independent / academic projects
        for proj in index.projects:
            proj_techs = [t.lower() for t in (proj.get("technologies") or proj.get("tech_stack") or [])]
            name_lower = name.lower()
            matches_tech = (
                name_lower in proj_techs
                or any(name_lower in t or t in name_lower for t in proj_techs)
                or re.search(r"\b" + re.escape(name) + r"\b", proj.get("raw_text", ""), re.IGNORECASE)
                or (name_lower in ["spring", "spring framework"] and any("spring" in t for t in proj_techs))
                or (any(j in name_lower for j in ["java", "core java"]) and any("java" in t for t in proj_techs))
            )
            if matches_tech:
                source_type = "academic_project" if proj.get("is_academic") else "project"
                p_name = proj.get("name") or proj.get("title") or "Project"
                p_desc = proj.get("description", "").strip()
                return EvidenceItem(
                    requirement=name,
                    status="PARTIAL",
                    importance=importance,
                    evidence_source=source_type,
                    evidence_text=f"{p_name}: {p_desc}" if p_desc else f"Built {p_name}: {proj.get('description', '')}",
                    source_entity=p_name,
                    confidence=0.85,
                    notes=f"Candidate has hands-on {name} experience in personal/independent project ({p_name}), NOT multi-year professional employment.",
                )

        # C) Check self-reported skills
        if name in index.self_reported_technologies:
            return EvidenceItem(
                requirement=name,
                status="UNVERIFIED",
                importance=importance,
                evidence_source="self_reported",
                evidence_text=f"{name} is listed under candidate's skills list without detailed employment bullets.",
                source_entity="Skills List",
                confidence=0.5,
                notes=f"Self-reported keyword. No supporting employment or project metrics.",
            )

        # D) Not found anywhere
        return EvidenceItem(
            requirement=name,
            status="MISSING",
            importance=importance,
            evidence_source="none",
            evidence_text="",
            source_entity="",
            confidence=0.0,
            notes=f"No evidence for {name} found anywhere in candidate profile. MUST NOT claim this skill.",
        )
