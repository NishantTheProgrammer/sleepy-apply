import asyncio
import html
import re
from app.db.client import connect_db, get_db

def clean_html(html_str: str) -> str:
    if not html_str:
        return ""
    text = html.unescape(html_str)
    text = html.unescape(text)
    text = re.sub(r"</?(h[1-6]|div|p|tr|section|article)[^>]*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", "\n• ", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<(strong|b)[^>]*>(.*?)</\1>", r"**\2**", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()

async def migrate():
    await connect_db()
    db = get_db()
    cursor = db.jobs.find()
    count = 0
    async for j in cursor:
        desc = j.get("description", "")
        if "&lt;" in desc or "<div" in desc or "<p" in desc or "&quot;" in desc or "&#39;" in desc:
            cleaned = clean_html(desc)
            await db.jobs.update_one({"_id": j["_id"]}, {"$set": {"description": cleaned}})
            count += 1
    print(f"Successfully cleaned {count} job descriptions in MongoDB!")

if __name__ == "__main__":
    asyncio.run(migrate())
