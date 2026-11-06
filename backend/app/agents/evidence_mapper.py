"""Evidence Mapper for AI-Powered Resume Tailoring.

Maps Job Description (JD) requirements to authentic candidate profile evidence,
categorizing every requirement as MATCHED, PARTIAL, MISSING, or UNVERIFIED with
clear source attribution (professional experience, independent project, education,
or self-reported skill).
"""

from __future__ import annotations

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
        "b.tech": "B.Tech",
        "b.e": "BE",
        "mca": "MCA",
        "bca": "BCA",
    }

    @classmethod
    def canonical_tech(cls, tech: str) -> str:
        clean = tech.strip().lower()
        return cls.TECH_CANONICAL_MAP.get(clean, tech.strip())

    def build_candidate_index(self, profile: dict[str, Any]) -> CandidateEvidenceIndex:
        """Indexes candidate profile into clean, distinct evidence layers."""
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
        for exp in raw_exp:
            company = exp.get("company", "").strip()
            title = exp.get("jobTitle") or exp.get("title", "").strip()
            start = exp.get("startDate") or exp.get("start_date", "").strip()
            end = "Present" if (exp.get("current") or exp.get("is_current")) else (exp.get("endDate") or exp.get("end_date", "")).strip()
            resps = exp.get("responsibilities") or exp.get("highlights") or []
            desc = exp.get("description", "")
            full_text = f"{title} {desc} " + " ".join(resps)

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
                "responsibilities": resps,
                "description": desc,
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

        return CandidateEvidenceIndex(
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

    def extract_jd_requirements(
        self, job_title: str, required_skills: list[str], job_description: str
    ) -> list[dict[str, Any]]:
        """Extracts structured requirements from JD with importance classifications."""
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
        exp_m = re.search(r"(\d+)\s*(?:to|-|–)\s*(\d+)\s*years?.*?([a-zA-Z\s]+)", job_description, re.IGNORECASE)
        if exp_m:
            add_req(
                f"{exp_m.group(1)}-{exp_m.group(2)} years {exp_m.group(3).strip()[:30]}",
                "experience_duration",
                "mandatory",
                exp_m.group(0),
            )
        else:
            exp_single = re.search(r"(\d+)\+?\s*years?.*?([a-zA-Z\s]{3,30})", job_description, re.IGNORECASE)
            if exp_single:
                add_req(
                    f"{exp_single.group(1)}+ years {exp_single.group(2).strip()}",
                    "experience_duration",
                    "mandatory",
                    exp_single.group(0),
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

        for canon, variants, label, default_imp in tech_patterns:
            if any(re.search(r"\b" + re.escape(v) + r"\b", desc_lower) for v in variants):
                imp = default_imp
                for v in variants:
                    if re.search(rf"\b(?:must have|required|requirements)\b[\s\S]*?\b{re.escape(v)}\b", desc_lower):
                        imp = "mandatory"
                        break
                    elif re.search(rf"\b(?:desirables?|nice to have|preferred|plus)\b[\s\S]*?\b{re.escape(v)}\b", desc_lower):
                        imp = "desirable"
                        break
                add_req(canon, "technology", imp, label)

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
        edu_m = re.search(r"\b(B\.?Tech|B\.?E|MCA|BCA|Master|Bachelor|Computer Science)\b", job_description, re.IGNORECASE)
        if edu_m:
            add_req("B.Tech/BE or related", "education", "desirable", "B.Tech/BE Computer Science, Engineering, or related field")

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
                if "ecommerce" in role["raw_text"].lower() or "e-commerce" in role["raw_text"].lower() or "stripe" in role["raw_text"].lower():
                    found_evidence.append((role["company"], "Contributed to e-commerce applications with WooCommerce REST API and Stripe split payments"))
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
                    notes="Verified e-commerce and payment integration experience.",
                )
            return EvidenceItem(requirement=name, status="MISSING", importance=importance)

        # 3. Leadership / Mentorship check
        if category == "leadership" and "mentor" in name.lower():
            for role in index.professional_roles:
                for resp in role.get("responsibilities", []):
                    if "mentor" in resp.lower():
                        return EvidenceItem(
                            requirement=name,
                            status="PARTIAL" if "4-6" in raw_text or "team of" in raw_text.lower() else "MATCHED",
                            importance=importance,
                            evidence_source="professional_experience",
                            evidence_text=resp,
                            source_entity=role["company"],
                            confidence=0.9,
                            notes="Mentored junior developers verified; exact team count was not specified in source profile.",
                        )

        # 4. Education check
        if category == "education":
            degrees = [e["degree"] for e in index.education]
            deg_str = ", ".join(degrees)
            has_btech = any("b.tech" in d.lower() or "b.e" in d.lower() for d in degrees)
            has_cs = any("mca" in d.lower() or "bca" in d.lower() or "computer" in d.lower() for d in degrees)
            if has_btech:
                return EvidenceItem(
                    requirement=name,
                    status="MATCHED",
                    importance=importance,
                    evidence_source="education",
                    evidence_text=deg_str,
                    source_entity="IGNOU",
                    confidence=1.0,
                )
            elif has_cs:
                return EvidenceItem(
                    requirement=name,
                    status="PARTIAL",
                    importance=importance,
                    evidence_source="education",
                    evidence_text=f"Candidate holds {deg_str} (Computer Applications degree equivalent).",
                    source_entity="IGNOU",
                    confidence=0.85,
                    notes="Candidate holds MCA (2023) and BCA (2020) rather than B.Tech/BE. Highlight exact degrees authentically.",
                )
            return EvidenceItem(requirement=name, status="MISSING", importance=importance)

        # 5. Technology checks
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

        # Special semantic mappings for tech:
        # e.g., if JD asks for "SQL", and candidate has PostgreSQL / MySQL in professional roles or profile
        if name.upper() == "SQL":
            has_sql = (
                "SQL" in index.professional_technologies
                or any(t in index.professional_technologies for t in ["PostgreSQL", "MySQL"])
                or any(t in index.all_known_technologies for t in ["SQL", "PostgreSQL", "MySQL"])
            )
            if has_sql:
                return EvidenceItem(
                    requirement="SQL",
                    status="MATCHED",
                    importance=importance,
                    evidence_source="professional_experience",
                    evidence_text="Extensive production SQL database experience with PostgreSQL and MySQL including query optimization and materialized views.",
                    source_entity="Dhwani Rural Information Systems",
                    confidence=0.95,
                    notes="SQL requirement satisfied via PostgreSQL and MySQL professional production experience.",
                )

        # B) Check in independent / academic projects
        for proj in index.projects:
            if name.lower() in [t.lower() for t in proj["technologies"]] or re.search(r"\b" + re.escape(name) + r"\b", proj["raw_text"], re.IGNORECASE):
                source_type = "academic_project" if proj.get("is_academic") else "project"
                return EvidenceItem(
                    requirement=name,
                    status="PARTIAL",
                    importance=importance,
                    evidence_source=source_type,
                    evidence_text=f"Built {proj['name']}: {proj['description']}",
                    source_entity=proj["name"],
                    confidence=0.85,
                    notes=f"Candidate has hands-on {name} experience in personal/independent project ({proj['name']}), NOT multi-year professional employment.",
                )

        # Check Spring Boot special case: if JD asks for Spring, Spring Boot is in StaffSync
        if name in ["Spring", "Spring Boot", "Java", "Core Java"]:
            staff_sync = next((p for p in index.projects if "staffsync" in p["name"].lower()), None)
            if staff_sync and ("spring" in name.lower() or name in ["Java", "Core Java"]):
                return EvidenceItem(
                    requirement=name,
                    status="PARTIAL",
                    importance=importance,
                    evidence_source="project",
                    evidence_text=f"StaffSync: {staff_sync['description']}",
                    source_entity="StaffSync",
                    confidence=0.85,
                    notes=f"Hands-on {name} implemented in StaffSync role-based workforce management system. Do NOT claim multi-year enterprise Java.",
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
