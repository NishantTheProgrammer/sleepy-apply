from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from bson import ObjectId
import structlog
from app.db.client import get_db
from app.models.company import CompanyGrade, ATSType
from app.db.seed_companies import seed_target_companies

router = APIRouter(prefix="/companies", tags=["companies"])
logger = structlog.get_logger()


class CreateCompanyRequest(BaseModel):
    name: str
    grade: CompanyGrade | str = "Tier-1"
    career_page: str
    ats_type: ATSType | str = "custom"
    board_token: str | None = None
    api_url: str | None = None
    industry: str | None = None
    location_hq: str | None = None
    is_active: bool = True


class UpdateCompanyRequest(BaseModel):
    name: str | None = None
    grade: CompanyGrade | str | None = None
    career_page: str | None = None
    ats_type: ATSType | str | None = None
    board_token: str | None = None
    api_url: str | None = None
    industry: str | None = None
    location_hq: str | None = None
    is_active: bool | None = None


@router.get("")
async def list_companies(
    grade: str | None = Query(default=None),
    ats_type: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
):
    """List target companies with optional filters and grade summary stats."""
    db = get_db()
    filter_query: dict = {}

    if grade:
        filter_query["grade"] = grade
    if ats_type:
        filter_query["ats_type"] = ats_type
    if is_active is not None:
        filter_query["is_active"] = is_active
    if search:
        filter_query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"industry": {"$regex": search, "$options": "i"}},
            {"location_hq": {"$regex": search, "$options": "i"}},
        ]

    total = await db.companies.count_documents(filter_query)

    cursor = db.companies.find(filter_query).sort([("grade", 1), ("name", 1)]).skip(skip).limit(limit)
    items = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        if doc.get("created_at") and hasattr(doc["created_at"], "isoformat"):
            doc["created_at"] = doc["created_at"].isoformat()
        if doc.get("updated_at") and hasattr(doc["updated_at"], "isoformat"):
            doc["updated_at"] = doc["updated_at"].isoformat()
        if doc.get("last_fetched_at") and hasattr(doc["last_fetched_at"], "isoformat"):
            doc["last_fetched_at"] = doc["last_fetched_at"].isoformat()
        items.append(doc)

    # Compute breakdown counts for fast UI tabs
    grade_counts = {
        "all": await db.companies.count_documents({}),
        "Tier-1": await db.companies.count_documents({"grade": "Tier-1"}),
        "Tier-2": await db.companies.count_documents({"grade": "Tier-2"}),
        "Tier-3": await db.companies.count_documents({"grade": "Tier-3"}),
        "Startup": await db.companies.count_documents({"grade": "Startup"}),
        "active": await db.companies.count_documents({"is_active": True}),
    }

    return {
        "items": items,
        "total": total,
        "grade_counts": grade_counts,
    }


@router.get("/{company_id}")
async def get_company(company_id: str):
    db = get_db()
    if not ObjectId.is_valid(company_id):
        raise HTTPException(status_code=400, detail="Invalid company ID")

    doc = await db.companies.find_one({"_id": ObjectId(company_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Company not found")

    doc["_id"] = str(doc["_id"])
    return doc


@router.post("", status_code=201)
async def create_company(body: CreateCompanyRequest):
    """Add a new company to the target companies collection."""
    db = get_db()
    clean_name = body.name.strip()
    existing = await db.companies.find_one({"name": {"$regex": f"^{clean_name}$", "$options": "i"}})
    if existing:
        raise HTTPException(status_code=409, detail=f"Company '{clean_name}' already exists in target list")

    now = datetime.now(timezone.utc)
    new_doc = {
        "name": clean_name,
        "grade": body.grade,
        "career_page": body.career_page.strip(),
        "ats_type": body.ats_type,
        "board_token": body.board_token.strip() if body.board_token else None,
        "api_url": body.api_url.strip() if body.api_url else None,
        "industry": body.industry.strip() if body.industry else None,
        "location_hq": body.location_hq.strip() if body.location_hq else None,
        "is_active": body.is_active,
        "total_jobs_fetched": 0,
        "last_fetched_at": None,
        "created_at": now,
        "updated_at": now,
    }

    res = await db.companies.insert_one(new_doc)
    new_doc["_id"] = str(res.inserted_id)
    return new_doc


@router.patch("/{company_id}")
async def update_company(company_id: str, body: UpdateCompanyRequest):
    db = get_db()
    if not ObjectId.is_valid(company_id):
        raise HTTPException(status_code=400, detail="Invalid company ID")

    update_fields: dict = {"updated_at": datetime.now(timezone.utc)}
    if body.name is not None:
        update_fields["name"] = body.name.strip()
    if body.grade is not None:
        update_fields["grade"] = body.grade
    if body.career_page is not None:
        update_fields["career_page"] = body.career_page.strip()
    if body.ats_type is not None:
        update_fields["ats_type"] = body.ats_type
    if body.board_token is not None:
        update_fields["board_token"] = body.board_token.strip() if body.board_token else None
    if body.api_url is not None:
        update_fields["api_url"] = body.api_url.strip() if body.api_url else None
    if body.industry is not None:
        update_fields["industry"] = body.industry.strip() if body.industry else None
    if body.location_hq is not None:
        update_fields["location_hq"] = body.location_hq.strip() if body.location_hq else None
    if body.is_active is not None:
        update_fields["is_active"] = body.is_active

    res = await db.companies.update_one({"_id": ObjectId(company_id)}, {"$set": update_fields})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Company not found")

    updated = await db.companies.find_one({"_id": ObjectId(company_id)})
    updated["_id"] = str(updated["_id"])
    return {"ok": True, "company": updated}


@router.delete("/{company_id}")
async def delete_company(company_id: str):
    db = get_db()
    if not ObjectId.is_valid(company_id):
        raise HTTPException(status_code=400, detail="Invalid company ID")

    res = await db.companies.delete_one({"_id": ObjectId(company_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Company not found")

    return {"ok": True, "message": "Company deleted"}


@router.post("/seed")
async def seed_companies(force: bool = False):
    """Seed or update target companies in MongoDB with verified metadata."""
    db = get_db()
    count = await seed_target_companies(db, force_overwrite=force)
    return {"ok": True, "message": f"Successfully processed {count} target companies in MongoDB"}
