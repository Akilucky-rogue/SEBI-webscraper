#!/usr/bin/env python3
"""
SEBI Recognised Intermediaries — Bulk Downloader
=================================================
Scrapes all intermediary datasets from SEBI's recognised intermediaries page.
Uses async HTTP to download all datasets in parallel.

Strategy:
1. Scrape the main page to dynamically extract all intmId values + names
2. POST to IntmExportAction.do for each ID (mimicking the form submit)
3. Save files with proper names derived from Content-Disposition headers
4. Validate all downloads for completeness
"""

import asyncio
import httpx
import os
import re
import sys
import time
import json
from pathlib import Path
from datetime import datetime

# ─── Configuration ────────────────────────────────────────────────────────────

SEBI_PAGE_URL = "https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognised=yes"
DOWNLOAD_URL = "https://www.sebi.gov.in/sebiweb/other/IntmExportAction.do"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Referer": "https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognised=yes",
    "Origin": "https://www.sebi.gov.in",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Form data that the page submits (hidden fields)
FORM_DATA = {
    "loginflag": "0",
    "searchValue": "",
    "type": "0",
    "search": "",
    "regNo": "",
    "intmId": "-1",
    "loginEmail": "",
    "loginPassword": "",
    "ckvalue": "1",
    "cap_login": "",
    "moduleNo": "-1",
    "moduleId": "",
    "link": "",
    "yourName": "",
    "friendName": "",
    "friendEmail": "",
    "mailmessage": "",
    "cap_email": "",
}

MAX_CONCURRENT = 5       # Conservative concurrency to avoid overwhelming SEBI
TIMEOUT_SECONDS = 60     # Per-request timeout
MIN_FILE_SIZE = 500      # Minimum bytes to consider a valid file
RETRY_ATTEMPTS = 3       # Retries per failed download
RETRY_DELAY = 2          # Seconds between retries


# ─── Step 1: Dynamic ID Extraction ───────────────────────────────────────────

def extract_intermediary_ids(html: str) -> list[dict]:
    """
    Parse the SEBI page HTML to extract all intmId values, names, and counts.
    Uses the exporttoexcel('ID') onclick pattern from download buttons.
    Also extracts the title from the corresponding link.
    """
    intermediaries = []

    # Extract IDs from download button onclick handlers
    export_ids = re.findall(r"exporttoexcel\('(\d+)'\)", html)

    # Extract ID-to-name mapping from the detail links
    id_name_map = {}
    pattern = r'doRecognisedFpi=yes&intmId=(\d+)"[^>]*title="([^"]+)"'
    for intm_id, title in re.findall(pattern, html):
        # Clean the title — remove date brackets
        clean_name = re.sub(r'\s*\[.*?\]\s*$', '', title).strip()
        id_name_map[intm_id] = clean_name

    # Extract counts
    count_pattern = r'id="intm_(\d+)"[^>]*data-value="(\d+)"'
    id_count_map = {}
    for sr_no, count in re.findall(count_pattern, html):
        id_count_map[sr_no] = int(count)

    # Build the final list using export IDs (these are the actual downloadable ones)
    for idx, intm_id in enumerate(export_ids, 1):
        name = id_name_map.get(intm_id, f"Unknown_ID_{intm_id}")
        count = id_count_map.get(str(idx), -1)
        intermediaries.append({
            "intm_id": int(intm_id),
            "sr_no": idx,
            "name": name,
            "count": count,
        })

    return intermediaries


# ─── Step 2: Async Downloader ────────────────────────────────────────────────

async def download_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    intm: dict,
    out_dir: str,
) -> dict:
    """Download a single intermediary dataset. Returns result dict."""
    intm_id = intm["intm_id"]
    result = {
        "intm_id": intm_id,
        "name": intm["name"],
        "success": False,
        "file_path": None,
        "file_size": 0,
        "filename": None,
        "error": None,
        "attempts": 0,
    }

    async with semaphore:
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            result["attempts"] = attempt
            try:
                r = await client.post(
                    f"{DOWNLOAD_URL}?intmId={intm_id}",
                    data=FORM_DATA,
                    timeout=TIMEOUT_SECONDS,
                )

                if r.status_code != 200:
                    result["error"] = f"HTTP {r.status_code}"
                    if attempt < RETRY_ATTEMPTS:
                        await asyncio.sleep(RETRY_DELAY * attempt)
                    continue

                content_type = r.headers.get("content-type", "")
                content_disp = r.headers.get("content-disposition", "")

                # Reject HTML error pages
                if "text/html" in content_type and len(r.content) < 5000:
                    result["error"] = f"Got HTML response ({len(r.content)} bytes)"
                    if attempt < RETRY_ATTEMPTS:
                        await asyncio.sleep(RETRY_DELAY * attempt)
                    continue

                # Check minimum file size
                if len(r.content) < MIN_FILE_SIZE:
                    result["error"] = f"File too small ({len(r.content)} bytes)"
                    if attempt < RETRY_ATTEMPTS:
                        await asyncio.sleep(RETRY_DELAY * attempt)
                    continue

                # Extract filename from Content-Disposition header
                filename = None
                if content_disp:
                    fname_match = re.search(r'filename\s*=\s*"?([^";\n]+)"?', content_disp)
                    if fname_match:
                        filename = fname_match.group(1).strip()

                # Fallback filename
                if not filename:
                    ext = ".xls" if "excel" in content_type else ".bin"
                    safe_name = re.sub(r'[^\w\s-]', '', intm["name"])[:80]
                    safe_name = re.sub(r'\s+', '_', safe_name)
                    filename = f"{safe_name}{ext}"

                # Sanitize filename — remove chars illegal on filesystems
                filename = filename.replace('/', '-').replace('\\', '-')
                filename = re.sub(r'[<>:"|?*]', '', filename)

                # Save the file
                file_path = os.path.join(out_dir, filename)
                with open(file_path, "wb") as f:
                    f.write(r.content)

                result["success"] = True
                result["file_path"] = file_path
                result["file_size"] = len(r.content)
                result["filename"] = filename
                print(f"  ✓ [{intm_id:>3}] {intm['name'][:60]:<60} → {filename} ({len(r.content):,} bytes)")
                break

            except httpx.TimeoutException:
                result["error"] = f"Timeout (attempt {attempt})"
                if attempt < RETRY_ATTEMPTS:
                    await asyncio.sleep(RETRY_DELAY * attempt)
            except Exception as e:
                result["error"] = f"{type(e).__name__}: {e}"
                if attempt < RETRY_ATTEMPTS:
                    await asyncio.sleep(RETRY_DELAY * attempt)

        if not result["success"]:
            print(f"  ✗ [{intm_id:>3}] {intm['name'][:60]:<60} → FAILED: {result['error']}")

    return result


async def download_all(intermediaries: list[dict], out_dir: str) -> list[dict]:
    """Download all intermediary datasets concurrently."""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async with httpx.AsyncClient(
        headers=HEADERS,
        follow_redirects=True,
        timeout=TIMEOUT_SECONDS,
    ) as client:
        tasks = [
            download_one(client, semaphore, intm, out_dir)
            for intm in intermediaries
        ]
        results = await asyncio.gather(*tasks)

    return results


# ─── Step 3: Validation & Reporting ──────────────────────────────────────────

def validate_and_report(intermediaries: list[dict], results: list[dict], out_dir: str):
    """Validate downloads and print a summary report."""
    total = len(intermediaries)
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]

    total_bytes = sum(r["file_size"] for r in successful)

    print("\n" + "=" * 80)
    print("DOWNLOAD SUMMARY")
    print("=" * 80)
    print(f"  Total intermediary types:  {total}")
    print(f"  Successfully downloaded:   {len(successful)}")
    print(f"  Failed:                    {len(failed)}")
    print(f"  Total data downloaded:     {total_bytes:,} bytes ({total_bytes / (1024*1024):.1f} MB)")
    print(f"  Output directory:          {out_dir}")

    if failed:
        print(f"\n  FAILED DOWNLOADS:")
        for r in failed:
            print(f"    ID {r['intm_id']:>3}: {r['name'][:50]} — {r['error']}")

    # List all downloaded files
    print(f"\n  DOWNLOADED FILES:")
    for r in sorted(successful, key=lambda x: x["intm_id"]):
        print(f"    ID {r['intm_id']:>3}: {r['filename']} ({r['file_size']:,} bytes)")

    # Save manifest
    manifest = {
        "download_date": datetime.now().isoformat(),
        "total_types": total,
        "successful": len(successful),
        "failed": len(failed),
        "total_bytes": total_bytes,
        "intermediaries": [
            {
                "intm_id": r["intm_id"],
                "name": r["name"],
                "success": r["success"],
                "filename": r["filename"],
                "file_size": r["file_size"],
                "error": r["error"],
            }
            for r in results
        ],
    }

    manifest_path = os.path.join(out_dir, "_manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\n  Manifest saved: {manifest_path}")

    return len(failed) == 0


# ─── Main ────────────────────────────────────────────────────────────────────

async def main(out_dir: str = None):
    if out_dir is None:
        out_dir = os.path.join("data", "sebi", "raw")

    os.makedirs(out_dir, exist_ok=True)

    print("=" * 80)
    print("SEBI Recognised Intermediaries — Bulk Downloader")
    print("=" * 80)

    # Step 1: Fetch the page and extract IDs
    print("\n[1/3] Fetching SEBI page and extracting intermediary IDs...")
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        r = await client.get(SEBI_PAGE_URL)

    if r.status_code != 200:
        print(f"ERROR: Failed to fetch SEBI page (HTTP {r.status_code})")
        sys.exit(1)

    intermediaries = extract_intermediary_ids(r.text)
    print(f"  Found {len(intermediaries)} intermediary types to download")

    if not intermediaries:
        print("ERROR: No intermediary IDs found. Page structure may have changed.")
        sys.exit(1)

    for intm in intermediaries:
        count_str = f"({intm['count']:,} records)" if intm['count'] > 0 else ""
        print(f"    ID {intm['intm_id']:>3}: {intm['name'][:65]} {count_str}")

    # Step 2: Download all
    print(f"\n[2/3] Downloading {len(intermediaries)} datasets (concurrency={MAX_CONCURRENT})...")
    start_time = time.time()
    results = await download_all(intermediaries, out_dir)
    elapsed = time.time() - start_time
    print(f"\n  Download phase completed in {elapsed:.1f}s")

    # Step 3: Validate
    print(f"\n[3/3] Validating downloads...")
    all_ok = validate_and_report(intermediaries, results, out_dir)

    if all_ok:
        print("\n✓ All downloads completed successfully!")
    else:
        print("\n⚠ Some downloads failed. Check the report above.")

    return results


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(main(out))
