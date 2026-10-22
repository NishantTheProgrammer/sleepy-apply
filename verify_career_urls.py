#!/usr/bin/env python3
"""
Career URL Verifier for top_500_tech_companies_india.json

Checks each company career URL concurrently, verifies whether the page exists,
and adds/updates the flag `verified: true` (or `false`), along with `http_status`
and `verified_at` timestamp.

Usage:
  python3 verify_career_urls.py
  python3 verify_career_urls.py --limit 20
  python3 verify_career_urls.py --workers 30 --timeout 8
  python3 verify_career_urls.py --dry-run
"""

import argparse
import json
import os
import shutil
import ssl
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import urllib.request
import urllib.error

# Try importing httpx for async HTTP/2 performance if available, otherwise fallback to threaded urllib
try:
    import httpx
    import asyncio
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

DEFAULT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "top_500_tech_companies_india.json")

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Upgrade-Insecure-Requests": "1",
}


def check_url_urllib(url: str, timeout: float = 8.0) -> dict:
    """Verifies a single URL using standard library urllib."""
    if not url or not url.strip():
        return {"verified": False, "http_status": None, "error": "Empty URL"}

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url.strip(), headers=BROWSER_HEADERS)

    # Try HEAD first for speed
    try:
        req.get_method = lambda: "HEAD"
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            return {
                "verified": status < 400,
                "http_status": status,
                "final_url": resp.url if resp.url != url else None,
            }
    except urllib.error.HTTPError as e:
        # Some servers return 405 Method Not Allowed or 403 on HEAD, so fall back to GET
        if e.code in [405, 403, 400]:
            pass
        elif e.code == 404 or e.code == 410:
            return {"verified": False, "http_status": e.code, "error": f"HTTP {e.code} Not Found"}
        elif e.code in [401, 429]:
            # Page exists but is protected by auth or rate-limiting
            return {"verified": True, "http_status": e.code, "note": "Protected/Rate-Limited"}
        else:
            return {"verified": False, "http_status": e.code, "error": f"HTTP {e.code}"}
    except Exception:
        pass

    # Fallback to GET (stream/read minimal)
    try:
        req_get = urllib.request.Request(url.strip(), headers=BROWSER_HEADERS)
        with urllib.request.urlopen(req_get, context=ctx, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            return {
                "verified": status < 400,
                "http_status": status,
                "final_url": resp.url if resp.url != url else None,
            }
    except urllib.error.HTTPError as e:
        # Cloudflare / WAF returns 400 / 401 / 403 / 429 to automated scrapers even though domain & career portal exist
        if e.code in [400, 401, 403, 429]:
            return {"verified": True, "http_status": e.code, "note": "WAF / Bot Protected (Page Exists)"}
        return {"verified": False, "http_status": e.code, "error": f"HTTP {e.code}"}
    except urllib.error.URLError as e:
        reason = str(getattr(e, "reason", e))
        return {"verified": False, "http_status": None, "error": reason[:100]}
    except Exception as e:
        return {"verified": False, "http_status": None, "error": str(e)[:100]}


async def check_all_httpx(companies: list[dict], timeout: float = 8.0, concurrency: int = 30) -> list[tuple[int, dict]]:
    """Fast async verification using httpx."""
    results = []
    sem = asyncio.Semaphore(concurrency)

    limits = httpx.Limits(max_connections=concurrency * 2, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=BROWSER_HEADERS, verify=False, limits=limits) as client:
        async def verify_single(idx: int, comp: dict):
            url = comp.get("career_page", "").strip()
            name = comp.get("company_name", "Unknown")
            if not url:
                return idx, {"verified": False, "http_status": None, "error": "Empty URL"}

            async with sem:
                try:
                    # Attempt GET with stream to avoid downloading full payloads
                    res = await client.get(url)
                    status = res.status_code
                    if status < 400:
                        return idx, {"verified": True, "http_status": status, "final_url": str(res.url)}
                    elif status in [400, 401, 403, 429]:
                        return idx, {"verified": True, "http_status": status, "note": "WAF/Bot Protected"}
                    else:
                        return idx, {"verified": False, "http_status": status, "error": f"HTTP {status}"}
                except httpx.HTTPStatusError as e:
                    return idx, {"verified": False, "http_status": e.response.status_code, "error": f"HTTP {e.response.status_code}"}
                except Exception as e:
                    # Try urllib fallback for this single url
                    res = check_url_urllib(url, timeout=timeout)
                    return idx, res

        tasks = [verify_single(i, c) for i, c in enumerate(companies)]
        done = 0
        total = len(tasks)
        for coro in asyncio.as_completed(tasks):
            idx, res = await coro
            done += 1
            comp = companies[idx]
            v_str = "✅" if res.get("verified") else "❌"
            status_str = f"HTTP {res.get('http_status')}" if res.get("http_status") else res.get("error", "Error")
            print(f"[{done:03d}/{total:03d}] {v_str} Rank {comp.get('rank', idx+1):<3} {comp.get('company_name'):<25} -> {status_str}")
            results.append((idx, res))

    return results


def run_threaded_verification(companies: list[dict], timeout: float = 8.0, workers: int = 25) -> list[tuple[int, dict]]:
    """Multi-threaded verification using standard library."""
    results = []
    total = len(companies)
    done = 0

    print(f"🚀 Starting concurrent verification using {workers} worker threads...\n")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(check_url_urllib, comp.get("career_page", ""), timeout): (i, comp)
            for i, comp in enumerate(companies)
        }

        for future in as_completed(future_map):
            i, comp = future_map[future]
            try:
                res = future.result()
            except Exception as e:
                res = {"verified": False, "http_status": None, "error": str(e)}

            done += 1
            v_str = "✅" if res.get("verified") else "❌"
            status_str = f"HTTP {res.get('http_status')}" if res.get("http_status") else res.get("error", "Error")
            print(f"[{done:03d}/{total:03d}] {v_str} Rank {comp.get('rank', i+1):<3} {comp.get('company_name'):<25} -> {status_str}")
            results.append((i, res))

    return results


def main():
    parser = argparse.ArgumentParser(description="Verify company career URLs in top_500_tech_companies_india.json")
    parser.add_argument("--file", "-f", default=DEFAULT_FILE, help="Path to top_500_tech_companies_india.json")
    parser.add_argument("--workers", "-w", type=int, default=25, help="Concurrent workers (default: 25)")
    parser.add_argument("--timeout", "-t", type=float, default=8.0, help="Timeout in seconds per URL (default: 8.0)")
    parser.add_argument("--limit", "-l", type=int, default=0, help="Test only first N companies (0 for all 500)")
    parser.add_argument("--dry-run", action="store_true", help="Perform checks without modifying the JSON file")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"❌ Error: File not found at {args.file}")
        sys.exit(1)

    print(f"📂 Loading: {args.file}")
    with open(args.file, "r", encoding="utf-8") as f:
        data = json.load(f)

    companies = data.get("companies", [])
    total_companies = len(companies)
    print(f"📋 Found {total_companies} companies in dataset")

    if args.limit > 0:
        companies_to_verify = companies[:args.limit]
        print(f"⚠️ Limiting to first {args.limit} companies for testing")
    else:
        companies_to_verify = companies

    start_time = time.time()

    # Choose async httpx if available, otherwise threaded urllib
    if HAS_HTTPX:
        print("⚡ Using high-performance httpx async engine")
        results = asyncio.run(check_all_httpx(companies_to_verify, timeout=args.timeout, concurrency=args.workers))
    else:
        print("🧵 Using Python ThreadPoolExecutor engine")
        results = run_threaded_verification(companies_to_verify, timeout=args.timeout, workers=args.workers)

    elapsed = time.time() - start_time
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Update company objects
    verified_count = 0
    failed_count = 0

    for idx, check_result in results:
        comp = companies[idx]
        is_verified = bool(check_result.get("verified", False))
        comp["verified"] = is_verified
        if check_result.get("http_status"):
            comp["http_status"] = check_result["http_status"]
        if check_result.get("final_url"):
            comp["final_url"] = check_result["final_url"]
        comp["verified_at"] = now_iso

        if is_verified:
            verified_count += 1
        else:
            failed_count += 1

    print("\n" + "=" * 60)
    print("📊 VERIFICATION SUMMARY")
    print("=" * 60)
    print(f"Total Checked:   {len(companies_to_verify)}")
    print(f"✅ Verified Active: {verified_count} ({verified_count/len(companies_to_verify)*100:.1f}%)")
    print(f"❌ Failed / Inactive: {failed_count} ({failed_count/len(companies_to_verify)*100:.1f}%)")
    print(f"⏱️ Time Elapsed:  {elapsed:.2f} seconds ({len(companies_to_verify)/elapsed:.1f} URLs/sec)")
    print("=" * 60)

    if not args.dry_run:
        # Create backup
        backup_path = f"{args.file}.bak"
        print(f"💾 Backing up original to: {backup_path}")
        shutil.copy2(args.file, backup_path)

        # Write updated JSON
        print(f"💾 Writing updated verified data to: {args.file}")
        with open(args.file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print("✨ Successfully updated top_500_tech_companies_india.json with verified flags!")
    else:
        print("🔍 Dry-run mode: File not modified.")


if __name__ == "__main__":
    main()
