# SEBI Recognised Intermediaries Scraper — User Manual

## What This Tool Does

This script downloads all intermediary datasets from SEBI's Recognised Intermediaries page at `https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognised=yes`. It dynamically detects every intermediary category listed on the page, downloads each dataset as an `.xls` file, and validates the results. No browser automation or manual interaction is needed.

As of April 2026, the page lists 37 intermediary types covering 35,000+ registered entities including Stock Brokers, AIFs, FPIs, Mutual Funds, Portfolio Managers, Research Analysts, Merchant Bankers, and more.

---

## Prerequisites

### 1. Python 3.10+

The script uses `asyncio`, type hints with `list[dict]`, and other modern Python features. Check your version:

```bash
python3 --version
```

If you're on Windows:

```cmd
python --version
```

### 2. Install httpx

The only external dependency is `httpx`, an async HTTP client. Install it via pip:

```bash
pip install httpx
```

On some systems (e.g., Ubuntu/Debian with system Python), you may need:

```bash
pip install httpx --break-system-packages
```

Or use a virtual environment (recommended):

```bash
python3 -m venv venv
source venv/bin/activate        # macOS/Linux
venv\Scripts\activate           # Windows
pip install httpx
```

### 3. Internet Access

The script needs to reach `www.sebi.gov.in` over HTTPS. No VPN or special network config is needed — SEBI's site is publicly accessible.

### 4. No Authentication Required

The SEBI download endpoint does not require login, session tokens, or API keys. The script sends the same form data that a browser would when clicking the download button.

---

## File Structure

After cloning or copying, you should have:

```
Sebi/
  sebi_scraper.py                  # The scraper script
  data/sebi/raw/                   # Downloaded files (created on first run)
    *.xls                          # One XLS file per intermediary type
    _manifest.json                 # Download metadata and results log
```

---

## Usage

### Basic Run (Default Output Directory)

```bash
python3 sebi_scraper.py
```

This downloads all files into `data/sebi/raw/` relative to where you run the command.

### Custom Output Directory

```bash
python3 sebi_scraper.py /path/to/your/output/folder
```

The directory is created automatically if it doesn't exist.

### Windows

```cmd
python sebi_scraper.py
python sebi_scraper.py C:\Users\YourName\Downloads\sebi_data
```

---

## What Happens When You Run It

The script runs in three phases:

### Phase 1 — ID Discovery

The script fetches the SEBI Recognised Intermediaries HTML page and parses it to extract every `intmId` (the internal identifier SEBI uses for each intermediary category). It also extracts the human-readable name and record count for each type. This means you never need to hardcode IDs — if SEBI adds a new category, the script picks it up automatically.

### Phase 2 — Async Download

For each discovered ID, the script sends a POST request to SEBI's export endpoint:

```
POST https://www.sebi.gov.in/sebiweb/other/IntmExportAction.do?intmId={ID}
```

This is the same request a browser makes when you click the download icon on the page. Up to 5 downloads run concurrently (configurable). Each download retries up to 3 times on failure with exponential backoff.

### Phase 3 — Validation & Manifest

After all downloads complete, the script checks that each file is a valid binary (not an HTML error page) and exceeds the minimum size threshold. It prints a summary table and writes `_manifest.json` with full metadata.

---

## Sample Output

```
================================================================================
SEBI Recognised Intermediaries — Bulk Downloader
================================================================================

[1/3] Fetching SEBI page and extracting intermediary IDs...
  Found 37 intermediary types to download
    ID  16: Registered Alternative Investment Funds (1,857 records)
    ID  30: Registered Stock Brokers in equity segment (4,942 records)
    ...

[2/3] Downloading 37 datasets (concurrency=5)...
  ✓ [ 16] Registered Alternative Investment Funds  → ...Apr 02 2026.xls (889,856 bytes)
  ✓ [ 30] Registered Stock Brokers in equity seg.  → ...Apr 02 2026.xls (1,946,112 bytes)
  ...

  Download phase completed in 48.2s

[3/3] Validating downloads...

================================================================================
DOWNLOAD SUMMARY
================================================================================
  Total intermediary types:  37
  Successfully downloaded:   37
  Failed:                    0
  Total data downloaded:     15,028,224 bytes (14.3 MB)

✓ All downloads completed successfully!
```

---

## Configuration

All tunable parameters are constants at the top of the script. Edit them directly:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `MAX_CONCURRENT` | `5` | Number of simultaneous downloads. Increase for speed, decrease if you get rate-limited or timeouts. |
| `TIMEOUT_SECONDS` | `60` | Per-request timeout in seconds. The FPI dataset (~4.8 MB) can be slow — keep this at 60+ seconds. |
| `MIN_FILE_SIZE` | `500` | Minimum response size (bytes) to accept as a valid file. Responses smaller than this are treated as errors. |
| `RETRY_ATTEMPTS` | `3` | Number of times to retry a failed download before giving up. |
| `RETRY_DELAY` | `2` | Base delay between retries (seconds). Multiplied by the attempt number for exponential backoff. |

---

## Output Files

### XLS Files

Each downloaded file is named using the `Content-Disposition` header from SEBI's server, which looks like:

```
Registered Stock Brokers in equity segment as on Apr 02 2026.xls
```

The files are in legacy `.xls` format (OLE2/BIFF), not `.xlsx`. They can be opened with Microsoft Excel, LibreOffice Calc, Google Sheets, or read programmatically with Python libraries like `xlrd`, `pandas`, or `openpyxl` (after conversion).

### Reading XLS Files in Python

```python
import pandas as pd

# Read a single file
df = pd.read_excel("data/sebi/raw/Merchant Bankers as on Apr 02 2026.xls")
print(df.head())

# Read all files into a dict
import os, glob

data = {}
for f in glob.glob("data/sebi/raw/*.xls"):
    name = os.path.basename(f).replace(".xls", "")
    data[name] = pd.read_excel(f)
    print(f"{name}: {len(data[name])} rows")
```

Requires: `pip install pandas xlrd openpyxl`

### Manifest File (_manifest.json)

A JSON file recording the results of each run:

```json
{
  "download_date": "2026-04-03T13:06:42.123456",
  "total_types": 37,
  "successful": 37,
  "failed": 0,
  "total_bytes": 15028224,
  "intermediaries": [
    {
      "intm_id": 16,
      "name": "Registered Alternative Investment Funds",
      "success": true,
      "filename": "Registered Alternative Investment Funds as on Apr 02 2026.xls",
      "file_size": 889856,
      "error": null
    },
    ...
  ]
}
```

---

## Troubleshooting

### "No intermediary IDs found"

SEBI may have changed the HTML structure. Open the page in a browser and check whether the download buttons still use `exporttoexcel('ID')` in their `onclick` attribute. If the pattern has changed, update the regex in `extract_intermediary_ids()`.

### Timeouts on Large Files

The FPI dataset (ID 29) is ~4.8 MB and can take 30+ seconds to download. If you see timeout errors for large files, increase `TIMEOUT_SECONDS` to 90 or 120.

### Rate Limiting / Connection Refused

SEBI's server occasionally throttles rapid requests. If you see many failures, reduce `MAX_CONCURRENT` from 5 to 2 or 3. The script already uses exponential backoff between retries.

### "File too small" Errors

Some intermediary categories may temporarily return empty responses from SEBI. Re-run the script — the retry logic usually handles transient issues. If a specific ID consistently fails, check if that category has been removed from the SEBI page.

### FileNotFoundError with Special Characters

If a filename contains characters illegal on your OS (like `/` on Linux/macOS or `?` on Windows), the script sanitizes them by replacing with `-`. This was a known issue fixed in the current version. If you encounter it, make sure you have the latest `sebi_scraper.py`.

### Running on Windows

Windows users should use `python` instead of `python3`. The script is cross-platform and works on Windows, macOS, and Linux without modification.

---

## How the Reverse Engineering Works

For reference, here is how the download mechanism was discovered. You don't need to know this to use the scraper, but it's useful for maintenance.

SEBI's page has a JavaScript function in `/js/other.js`:

```javascript
function exporttoexcel(id) {
    document.otherForm.action = "../other/IntmExportAction.do?intmId=" + id;
    document.otherForm.submit();
}
```

Each download button calls `exporttoexcel('16')`, `exporttoexcel('30')`, etc. This submits the page's main form via POST to the export endpoint. The form contains hidden fields (login flags, search params, etc.) that the server expects but doesn't actually validate — they just need to be present.

The script mimics this exact behavior: it sends a POST to `IntmExportAction.do?intmId=X` with the same form fields. No session cookie, CSRF token, or authentication is needed.

---

## Scheduling Regular Downloads

To keep your dataset current, run the scraper on a schedule. SEBI updates most datasets daily.

### Linux/macOS (cron)

```bash
# Run every day at 7 AM
crontab -e
0 7 * * * cd /path/to/Sebi && python3 sebi_scraper.py >> scraper.log 2>&1
```

### Windows (Task Scheduler)

Create a basic task that runs:

```
Program: python
Arguments: C:\path\to\Sebi\sebi_scraper.py
Start in: C:\path\to\Sebi
```

Set the trigger to daily at your preferred time.

---

## Extending the Script

### Merge All Datasets

To combine all downloaded files into one consolidated DataFrame:

```python
import pandas as pd
import glob, os

frames = []
for f in sorted(glob.glob("data/sebi/raw/*.xls")):
    df = pd.read_excel(f)
    df["_source_file"] = os.path.basename(f)
    frames.append(df)

combined = pd.concat(frames, ignore_index=True)
combined.to_excel("data/sebi/all_intermediaries.xlsx", index=False)
```

### Load into a Database

```python
import sqlite3
combined.to_sql("intermediaries", sqlite3.connect("sebi.db"), if_exists="replace", index=False)
```

### Track Changes Over Time

Run the scraper daily to a date-stamped folder:

```bash
python3 sebi_scraper.py "data/sebi/$(date +%Y-%m-%d)"
```

Then diff successive days to find newly registered or deregistered intermediaries.
