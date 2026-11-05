import re
from typing import Iterable, Any
from bson import ObjectId


async def get_unique_user_selected_roles(db, user_id: str | ObjectId | None = None) -> list[str]:
    """
    Retrieves the exact, unique role titles selected by users from db.profiles.
    
    Extracts strictly from:
      - profile.target_role (the role the user explicitly selected/typed)
      - profile.job_preferences.jobTitles / profile.jobPreferences.jobTitles (user preference titles)
    
    No static/hardcoded role lists or if/else role branching.
    """
    query: dict[str, Any] = {}
    if user_id:
        try:
            query["user_id"] = ObjectId(user_id) if isinstance(user_id, str) else user_id
        except Exception:
            query["user_id"] = user_id

    cursor = db.profiles.find(
        query,
        {
            "target_role": 1,
            "job_preferences.jobTitles": 1,
            "jobPreferences.jobTitles": 1,
        },
    )

    unique_roles: list[str] = []
    seen: set[str] = set()

    def _add(role_val: Any):
        if not role_val or not isinstance(role_val, str):
            return
        clean = role_val.strip()
        if clean and len(clean) >= 2 and clean.lower() not in seen:
            seen.add(clean.lower())
            unique_roles.append(clean)

    async for doc in cursor:
        _add(doc.get("target_role"))
        for t in (doc.get("job_preferences", {}).get("jobTitles") or []):
            _add(t)
        for t in (doc.get("jobPreferences", {}).get("jobTitles") or []):
            _add(t)

    return unique_roles


def format_roles_for_search_query(roles: Iterable[str]) -> list[str]:
    """
    Formats the user's selected roles into clean search queries for job boards.
    
    Removes parenthetical formatting (e.g. '(Node.js & React)') so external
    search APIs (LinkedIn, Indeed, Naukri) do not fail with syntax errors,
    while preserving the exact unique roles chosen by the users.
    
    No static mappings or hardcoded role keywords.
    """
    search_queries: list[str] = []
    seen: set[str] = set()

    for r in roles:
        if not r or not isinstance(r, str):
            continue
        trimmed = r.strip()
        if not trimmed:
            continue

        # Clean title without parenthetical annotations
        without_parens = re.sub(r"\(.*?\)", "", trimmed).strip(" -:,/|")
        # Tech / specialization inside parentheses if present e.g. "Node.js & React"
        inside_parens = re.findall(r"\((.*?)\)", trimmed)

        candidates = [without_parens, trimmed]
        for ip in inside_parens:
            # Clean and split parts if multiple
            ip_clean = re.sub(r"\s+", " ", ip).strip()
            if ip_clean and len(ip_clean) >= 2:
                candidates.append(ip_clean)

        for cand in candidates:
            c_clean = re.sub(r"\s+", " ", cand).strip(" -:,/|")
            if c_clean and len(c_clean) >= 2 and c_clean.lower() not in seen:
                seen.add(c_clean.lower())
                search_queries.append(c_clean)

    return search_queries


# Backward compatibility alias
expand_role_to_search_keywords = format_roles_for_search_query
