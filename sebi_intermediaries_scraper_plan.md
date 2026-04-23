# SEBI Recognised Intermediaries — Bulk Downloader

## 1. Objective
Download **all intermediary datasets** from SEBI page:
https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognised=yes

Unlike AMFI:
- No filtering needed
- No pagination
- Only **iterate over IDs and download files**

---

## 2. Reverse Engineered Endpoint

### Download API
```
https://www.sebi.gov.in/sebiweb/other/IntmExportAction.do?intmId={ID}
```

Each row corresponds to one `intmId`.

Example:
- 16 → A specific intermediary dataset

---

## 3. Key Insight

You do NOT need:
- Browser automation
- Form submission
- Tokens (can be bypassed)

➡️ Only required:
- `intmId`

---

## 4. Strategy

### Step 1 — Collect all IDs
From UI:
- Each row has a download button
- Each maps to `intmId`

Two ways:

#### Option A (manual bootstrap)
Create list:
```
IDS = [1,2,3,...,50]
```

#### Option B (better)
Scrape page once → extract IDs from links

---

### Step 2 — Async download
For each ID:
```
GET IntmExportAction.do?intmId=X
```

---

## 5. Folder Structure

```
data/sebi/
  ├── raw/
  │     ├── 1.xlsx
  │     ├── 2.xlsx
  │     ├── 16.xlsx
```

---

## 6. Async Downloader (SEBI)

```python
# src/sebi_async.py

import asyncio
import httpx
import os

BASE_URL = "https://www.sebi.gov.in/sebiweb/other/IntmExportAction.do"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognised=yes"
}

OUT_DIR = "data/sebi/raw"
os.makedirs(OUT_DIR, exist_ok=True)

SEM = 20

async def fetch_id(client, sem, intm_id):
    async with sem:
        try:
            params = {"intmId": intm_id}
            r = await client.get(BASE_URL, params=params)

            if r.status_code == 200 and len(r.content) > 1000:
                path = f"{OUT_DIR}/{intm_id}.xlsx"
                with open(path, "wb") as f:
                    f.write(r.content)
                print(f"Saved {intm_id}")
            else:
                print(f"Skip {intm_id}")

        except Exception as e:
            print(f"Error {intm_id}: {e}")


async def run():
    sem = asyncio.Semaphore(SEM)

    ids = list(range(1, 60))  # adjust based on page

    async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:
        tasks = [fetch_id(client, sem, i) for i in ids]
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(run())
```

---

## 7. Notes

### ID Range
- Typically small (20–50)
- You can:
  - Hardcode
  - Or detect dynamically later

---

### No Pagination Needed
Each ID = full dataset

---

### File Types
Mostly:
- Excel
- Sometimes CSV

Handle generically via binary write

---

## 8. Performance

| Mode | Time |
|------|------|
| Sequential | ~1–2 min |
| Async | ~5–10 sec |

---

## 9. Future Enhancements

- Auto-detect `intmId` from HTML
- Merge all SEBI datasets
- Tag by intermediary type

---

## 10. Summary

You now have:

### AMFI
- PIN-based distributed scraping

### SEBI
- ID-based bulk dataset extraction


Both combined →
> **Complete financial intermediary intelligence layer**

---



---

# SEBI Recognised Intermediaries — Detailed Extraction Plan

## 1. Objective

Build a **robust, repeatable scraper** to download all datasets from:
https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognised=yes

Unlike AMFI, this is a **finite, ID-based extraction problem**.

Goal:
- Download all intermediary datasets
- Store them cleanly
- Ensure completeness (no missed IDs)

---

## 2. System Understanding (Critical)

### Page Behavior

The SEBI page displays:
- List of intermediary categories
- Each row has:
  - Name
  - Count
  - Download icon

Each download button maps to:

```
IntmExportAction.do?intmId=X
```

---

### Key Insight

> Each `intmId` represents a **complete dataset for one intermediary type**

No pagination. No filtering.

---

## 3. Reverse Engineered API

### Endpoint

```
GET https://www.sebi.gov.in/sebiweb/other/IntmExportAction.do?intmId={ID}
```

### Required Headers

```
User-Agent
Referer
```

No:
- Auth
- Tokens
- Session dependency (in practice)

---

## 4. Extraction Strategy

### Step 1 — Identify all valid IDs

#### Option A (Recommended initially)

Manually inspect page:
- Count number of rows (~20–40)
- IDs are sequential

Example:
```
1 → Registered AIF
2 → Stock Brokers Equity
...
```

---

#### Option B (Robust — later)

Scrape HTML:
- Extract all `intmId` from links
- Build dynamic ID list

---

### Step 2 — Download per ID

For each ID:

```
GET IntmExportAction.do?intmId=X
```

---

### Step 3 — Validate response

Check:
- Response size (> threshold)
- Status = 200

Reject:
- Empty files
- HTML error pages

---

### Step 4 — Store files

```
data/sebi/
  ├── raw/
  │     ├── 1.xlsx
  │     ├── 2.xlsx
  │     ├── 3.xlsx
```

---

## 5. Adaptive ID Discovery (Important)

Instead of fixed range:

### Logic

```
Loop IDs from 1 → N
Stop when consecutive failures exceed threshold
```

---

### Example Strategy

- Track valid responses
- Stop after 10 consecutive invalid IDs

---

## 6. Async Architecture

```
ID Generator → Async Queue → HTTP Requests → File Save
```

---

### Concurrency

| Parameter | Value |
|----------|------|
| Workers | 10–20 |
| Timeout | 30s |

---

## 7. Implementation Design

### Components

#### 1. ID Generator
- Generates sequential IDs
- Stops adaptively

#### 2. Downloader
- Async HTTP calls
- Saves binary

#### 3. Validator
- Checks file size

#### 4. Storage
- Writes to disk

---

## 8. Folder Structure

```
data/
  ├── sebi/
  │     ├── raw/
  │     │     ├── 1.xlsx
  │     │     ├── 2.xlsx
  │     │     ├── 16.xlsx
```

---

## 9. Data Characteristics

Each file contains:
- Full dataset of that intermediary type

Examples:
- Stock brokers
- AIFs
- Custodians

---

## 10. Edge Cases

### 1. Invalid ID

Returns:
- Small file
- HTML page

Solution:
- Filter by file size

---

### 2. Rate limiting

Unlikely, but:
- Add small concurrency control

---

### 3. File format variance

Some may be:
- XLSX
- CSV

Handle generically

---

## 11. Performance

| Mode | Time |
|------|------|
| Sequential | 1–2 min |
| Async | 5–15 sec |

---

## 12. Comparison with AMFI

| Feature | AMFI | SEBI |
|--------|------|------|
| Key | PIN | ID |
| Queries | Many | Few |
| Complexity | High | Low |
| Data structure | Fragmented | Pre-aggregated |

---

## 13. Validation Checklist

Ensure:

- All IDs covered
- File count matches UI rows
- File sizes reasonable
- No missing categories

---

## 14. Future Enhancements

(Not required now)

- Auto ID extraction from HTML
- Merge datasets
- Tag intermediary type
- Build unified schema

---

## 15. Final Summary

This system:

- Uses **direct endpoint access**
- Avoids UI automation
- Requires minimal logic
- Is highly stable


Combined with AMFI pipeline:

> You now control both **distribution layer (AMFI)** and **regulatory layer (SEBI)** datasets

---

**End of Document**

