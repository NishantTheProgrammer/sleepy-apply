import asyncio
import html
import re
import html2text
from app.db.client import connect_db, get_db

h = html2text.HTML2Text()
h.ignore_links = False
h.ignore_images = True
h.body_width = 0
h.protect_links = True
h.unicode_snob = True
h.skip_internal_links = True

async def migrate():
    await connect_db()
    db = get_db()
    cursor = db.jobs.find()
    count = 0
    async for j in cursor:
        desc = j.get("description", "")
        if not desc:
            continue
        if "<" in desc or "&" in desc:
            unescaped = html.unescape(html.unescape(desc))
            converted = h.handle(unescaped)
            cleaned = re.sub(r"\n\s*\n\s*\n+", "\n\n", converted).strip()
            if cleaned and cleaned != desc:
                await db.jobs.update_one({"_id": j["_id"]}, {"$set": {"description": cleaned}})
                count += 1
    print(f"Successfully processed jobs with html2text! Updated {count} jobs.")

if __name__ == "__main__":
    asyncio.run(migrate())
