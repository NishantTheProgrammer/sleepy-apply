import re
from typing import Iterable


def expand_role_to_search_keywords(roles: Iterable[str]) -> list[str]:
    """
    Expands candidate target roles and job preference titles into clean, high-yield
    search phrases for job portals (LinkedIn, Indeed, Naukri, and career sites).
    
    Examples:
      'Senior Full Stack Engineer (Node.js & React)' ->
        ['Senior Full Stack Engineer', 'Node.js Developer', 'React Developer', 'Full Stack Developer', 'Full Stack Engineer']
      'Senior Quality Engineer' ->
        ['Senior Quality Engineer', 'Quality Engineer', 'SDET', 'QA Automation Engineer']
      'Senior ETL tester' ->
        ['Senior ETL tester', 'ETL Tester', 'ETL QA', 'Data QA']
    """
    expanded: list[str] = []
    seen: set[str] = set()

    def _add(kw: str):
        k = re.sub(r"\s+", " ", str(kw or "")).strip(" -:,/|()[]{}")
        if k and len(k) >= 2 and k.lower() not in seen:
            seen.add(k.lower())
            expanded.append(k)

    for role in roles:
        if not role or not isinstance(role, str) or not role.strip():
            continue
        raw = role.strip()

        # 1. Cleaned full role (without parentheses or trailing punctuation)
        cleaned = re.sub(r"\(.*?\)", "", raw).strip(" -:,/|")
        if cleaned:
            _add(cleaned)

        # 2. Extract technical qualifiers inside parentheses e.g. (Node.js & React), (SDE-2), (Playwright/Selenium)
        inside_paren = re.findall(r"\((.*?)\)", raw)
        for ip in inside_paren:
            parts = re.split(r"[/&,]|(?:\band\b)", ip)
            for p in parts:
                p_clean = p.strip()
                if not p_clean or len(p_clean) < 2:
                    continue
                p_low = p_clean.lower()
                if any(t in p_low for t in ["node", "react", "python", "java", "golang", "go", "vue", "angular", "next"]):
                    _add(f"{p_clean} Developer")
                    _add(p_clean)
                elif any(t in p_low for t in ["playwright", "selenium", "cypress", "appium"]):
                    _add(f"{p_clean} Engineer")
                    _add(p_clean)
                elif "sde" in p_low:
                    _add(p_clean)
                else:
                    _add(p_clean)

        # 3. Derive standard industry role variants from the title
        cleaned_lower = cleaned.lower()
        if "full stack" in cleaned_lower or "fullstack" in cleaned_lower:
            _add("Full Stack Developer")
            _add("Full Stack Engineer")
        elif "backend" in cleaned_lower:
            _add("Backend Developer")
            _add("Backend Engineer")
        elif "frontend" in cleaned_lower:
            _add("Frontend Developer")
            _add("Frontend Engineer")
        elif "etl" in cleaned_lower:
            _add("ETL Tester")
            _add("ETL QA")
            _add("Data QA")
            _add("Data Engineer")
        elif any(q in cleaned_lower for q in ["sdet", "quality engineer", "qa automation", "test automation"]):
            _add("SDET")
            _add("Quality Engineer")
            _add("QA Automation Engineer")
        elif "devops" in cleaned_lower or "sre" in cleaned_lower or "cloud" in cleaned_lower:
            _add("DevOps Engineer")
            _add("Site Reliability Engineer")
            _add("Cloud Engineer")
        elif "machine learning" in cleaned_lower or "ai" in cleaned_lower:
            _add("Machine Learning Engineer")
            _add("AI Engineer")
        elif "software" in cleaned_lower or "developer" in cleaned_lower or "engineer" in cleaned_lower:
            _add("Software Engineer")
            _add("Software Developer")

    return expanded

