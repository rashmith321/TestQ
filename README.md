# LeetCode Profile Analyzer

Automated extraction of a public LeetCode profile's **Skills** (Fundamental, Intermediate, Advanced) and **Recent Activity** into a structured, downloadable JSON file, with a React dashboard on top of a FastAPI backend.

## Features

- Profile URL validation (`/u/<username>/` and legacy `/<username>/` forms) with clear errors for wrong sites, non-profile pages and malformed usernames, plus a live existence check.
- Skills extraction that keeps the three sections strictly separate and records each skill's name, slug, section and problems-solved count.
- Recent Activity extraction from two public lists, merged so every record carries every field LeetCode exposes (id, status, language, time), then enriched with difficulty.
- Run-time detection of LeetCode's server cap on Recent Activity (see *How pagination actually works*), plus tested cursor and offset paginators for sources that do paginate.
- Data cleaning: UTC ISO-8601 timestamps, deduplication by submission id (or problem + time + status + language), and repeated attempts at the same problem kept as separate records.
- Honest status reporting: `completed`, `partially_completed` or `failed`, with per-section status, error list, field-coverage counts and a plain statement of how much history the data covers.
- Background jobs with progress polling, a JSON download, and the raw API responses saved separately for debugging.
- 67 offline automated tests (no live LeetCode calls).

## Technology stack

Backend: Python 3.10+, FastAPI, Pydantic v2, Requests, BeautifulSoup4, optional Playwright. Frontend: React 18, Vite 5, plain CSS (light and dark). Storage: JSON files in `backend/output/`.

## Architecture

```
React UI ──POST /api/analyze──▶ FastAPI ──▶ JobManager (thread pool)
   ▲  poll GET /api/jobs/{id}                 │
   │                                          ▼
   └──GET /api/download/{file}        analyzer.run_analysis
                                          │
           ┌──────────────┬───────────────┼──────────────────┐
           ▼              ▼               ▼                  ▼
   profile_validator  skills_scraper  activity_scraper   data_processor
           │              │   │           │  └─ pagination_handler
           └──────────────┴───┴─ leetcode_client (GraphQL, retries, throttling)
                              └─ html_fallback (BeautifulSoup, __NEXT_DATA__)
                                                         ▼
                                                 json_generator ──▶ output/*.json
```

## Folder structure

```
leetcode-profile-analyzer/
├── backend/
│   ├── main.py                  FastAPI app and routes
│   ├── config.py                settings (env variables)
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── scraper/
│   │   ├── leetcode_client.py   HTTP/GraphQL client: retries, 429, 403, throttling
│   │   ├── queries.py           GraphQL documents (undocumented API, see Limitations)
│   │   ├── profile_validator.py URL parsing, username extraction, existence check
│   │   ├── skills_scraper.py    Fundamental / Intermediate / Advanced
│   │   ├── activity_scraper.py  Recent Activity, merge, difficulty lookup
│   │   ├── pagination_handler.py limit-probe, cursor and offset strategies
│   │   ├── html_fallback.py     BeautifulSoup parser for the profile page
│   │   ├── browser_fallback.py  optional Playwright client
│   │   └── exceptions.py        typed errors mapped to HTTP statuses
│   ├── services/
│   │   ├── analyzer.py          orchestration and status rules
│   │   ├── data_processor.py    cleaning and normalisation
│   │   ├── json_generator.py    document building, atomic writes, safe downloads
│   │   └── job_manager.py       background jobs and progress
│   ├── models/schemas.py        Pydantic models (API + JSON document)
│   ├── scripts/inspect_leetcode.py  live check of the data sources
│   ├── output/                  generated JSON (raw/ holds raw responses)
│   └── tests/                   pytest suite and fixtures
├── frontend/
│   ├── index.html, package.json, vite.config.js
│   └── src/ (App.jsx, main.jsx, styles.css, pages/, components/, services/api.js)
├── requirements.txt             points to backend/requirements.txt
├── .gitignore
└── README.md
```

## Installation and running on Windows

Prerequisites: Python 3.10 or newer (`py --version`) and Node.js 18 or newer (`node --version`).

### Backend (Command Prompt or PowerShell)

```bat
cd leetcode-profile-analyzer\backend
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

If PowerShell refuses to run `activate`, run this once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

Check it: open http://127.0.0.1:8000/api/health. Interactive API docs are at http://127.0.0.1:8000/docs.

### Frontend (a second terminal)

```bat
cd leetcode-profile-analyzer\frontend
npm install
npm run dev
```

Open http://localhost:5173. The Vite dev server forwards `/api` to the backend on port 8000.

### Verify the live data sources first (recommended)

LeetCode's data endpoints are undocumented and can change. Before relying on the app, run:

```bat
cd leetcode-profile-analyzer\backend
.venv\Scripts\activate
python scripts\inspect_leetcode.py <a_public_username>
python scripts\inspect_leetcode.py <a_public_username> --save
```

It reports whether each query works, which fields come back, how many Recent Activity records LeetCode returns for limits of 10, 20, 50 and 100, and whether the profile HTML embeds skills data. `--save` stores the responses in `tests/fixtures/live/` for building regression tests.

### Run the tests

```bat
cd leetcode-profile-analyzer\backend
.venv\Scripts\activate
pytest -v
```

## Using the app

Paste a profile URL such as `https://leetcode.com/u/username/` and choose **Analyze profile**. A progress bar shows each stage. When the job finishes, the dashboard shows the status of each section, skill counts, the activity difficulty mix, the three skill columns and the Recent Activity table (filterable by status). **Download JSON** saves `username_leetcode_data.json`.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Backend availability |
| POST | `/api/validate` | Body `{"profile_url": "..."}`. Returns username and canonical URL, or 400 |
| POST | `/api/analyze` | Body `{"profile_url": "..."}`. Validates immediately (400 on a bad URL), then returns **202** with `job_id` and `status_url` |
| GET | `/api/jobs/{job_id}` | `status` (`queued`, `running`, `done`, `error`), `progress` 0–100, `stage`, `log`, and when done `result` and `download_filename`; on failure `error` with `code` and `message` |
| GET | `/api/download/{filename}` | The JSON file as an attachment. Only names matching `*_leetcode_data.json` inside `output/` are served |

Error codes: `invalid_url` (400), `profile_not_found` (404), `rate_limited` (429), `access_blocked` (503), `network_error` (504), `structure_changed`, `graphql_error`, `analysis_failed` (502). Errors from the background job appear in the job's `error` field with the same codes.

Example with curl:

```bat
curl -X POST http://127.0.0.1:8000/api/analyze -H "Content-Type: application/json" -d "{\"profile_url\":\"https://leetcode.com/u/username/\"}"
curl http://127.0.0.1:8000/api/jobs/<job_id>
```

## JSON output

Abridged example (values are illustrative):

```json
{
  "profile": { "username": "example_user", "profile_url": "https://leetcode.com/u/example_user/", "real_name": null },
  "skills": {
    "fundamentals": [
      { "skill_name": "Array", "skill_slug": "array", "category": "fundamentals", "source_section": "Fundamental", "problems_solved": 58 }
    ],
    "intermediate": [],
    "advanced": []
  },
  "recent_activity": [
    {
      "problem_name": "Two Sum",
      "problem_slug": "two-sum",
      "problem_url": "https://leetcode.com/problems/two-sum/",
      "submission_id": "1234567890",
      "submission_date": "2026-11-20T14:03:11Z",
      "submission_timestamp": 1795183391,
      "status": "Accepted",
      "language": "python3",
      "difficulty": "Easy",
      "sources": ["recentSubmissionList", "recentAcSubmissionList"]
    }
  ],
  "metadata": {
    "total_skills": 1,
    "skills_by_category": { "fundamentals": 1, "intermediate": 0, "advanced": 0 },
    "total_activity_records": 1,
    "pages_processed": 4,
    "scraping_status": "completed",
    "scraped_at": "2026-11-23T10:00:00Z",
    "sections": {
      "skills": { "status": "completed", "source": "graphql:skillStats", "records": 1, "missing": [], "errors": [] },
      "recent_activity": { "status": "completed", "source": "graphql:recentSubmissionList+recentAcSubmissionList", "records": 1, "missing": [], "errors": [] }
    },
    "activity_sources": [
      { "name": "recentAcSubmissionList", "status": "completed", "records": 20, "batches": 2, "stop_reason": "server_cap_reached", "detected_cap": 20, "error": null }
    ],
    "history_coverage": "These are only the submissions LeetCode shows publicly in Recent Activity ...",
    "field_coverage": { "submission_id": 1, "submission_date": 1, "status": 1, "language": 1, "difficulty": 1, "problem_url": 1 },
    "data_source": "LeetCode's internal GraphQL endpoint ...",
    "requests_made": 7,
    "warnings": [],
    "errors": []
  }
}
```

Fields LeetCode does not expose are `null`, never guessed. `pages_processed` counts the requests made to the activity lists (batches), since LeetCode's public feed has no pages.

## How the data is obtained

The public profile page is a JavaScript app; the skills and Recent Activity are not in plain HTML but are loaded from `https://leetcode.com/graphql/`. The scraper calls the same queries the page does:

| Data | Query | Fields used |
|---|---|---|
| Profile exists | `matchedUser` | `username`, `profile.realName` |
| Skills | `matchedUser.tagProblemCounts` | `fundamental` / `intermediate` / `advanced` → `tagName`, `tagSlug`, `problemsSolved` |
| Accepted submissions | `recentAcSubmissionList(username, limit)` | `id`, `title`, `titleSlug`, `timestamp` |
| All recent submissions | `recentSubmissionList(username, limit)` | `title`, `titleSlug`, `timestamp`, `statusDisplay`, `lang` |
| Difficulty | `question(titleSlug)`, batched with aliases | `difficulty` |

If the skills query fails, the scraper falls back to parsing the profile HTML with BeautifulSoup and searching the embedded `__NEXT_DATA__` JSON. If LeetCode refuses plain HTTP requests, an optional Playwright client (`LCPA_BROWSER_FALLBACK=1`) retries from a real browser page; it stops if a challenge or CAPTCHA appears.

### How pagination actually works

LeetCode's public Recent Activity lists accept only a `limit`. There is no page number, offset or cursor, and the server caps the result. The `LimitProbePaginator` asks for 20, then 40, 80 and so on (up to `LCPA_ACTIVITY_MAX_LIMIT`) and stops when a bigger request returns nothing new. That stop is reported as `server_cap_reached` with the detected cap. Stopping at the app's own safety limit is reported as `max_limit_reached` and marks the section partial. `CursorPaginator` and `OffsetPaginator` are implemented and tested for sources that do paginate, but LeetCode offers no public endpoint that uses them.

## Known limitations

- **Not the full history.** Public Recent Activity is a short, capped feed (historically about 20 records per list). A user's complete submission history is available only to that user when logged in, and this tool does not log in.
- **Undocumented endpoint.** `leetcode.com/graphql/` is internal. Query and field names come from what the profile page has used and may change at any time; when they do, the affected section is reported as failed or partial with the GraphQL error, never filled with guesses. Re-check with `scripts/inspect_leetcode.py`.
- **Field gaps.** The all-status list has no submission id; the accepted list has no language. Records found only in one list have the other fields set to `null`, and `field_coverage` shows how many records have each field.
- **Development verification.** The project was built and tested in an environment without access to leetcode.com. All 67 tests pass against fixtures shaped like LeetCode's responses, and the full UI → API → JSON → download flow was exercised with a simulated server, but the live queries have not been run from that environment. Run the inspection script once before relying on the results.
- **Respectful use.** Requests are throttled (`LCPA_MIN_REQUEST_INTERVAL`, default 0.8 s), HTTP 429 is retried with backoff and `Retry-After`, and 403 or bot-check pages stop the job. Nothing tries to evade rate limits, logins or CAPTCHAs. Check LeetCode's terms of service for your use case.
- leetcode.cn is not supported (different site and API). Jobs are kept in memory and disappear when the backend restarts.

## Configuration

Environment variables (all optional): `LCPA_OUTPUT_DIR`, `LCPA_REQUEST_TIMEOUT` (15), `LCPA_MAX_RETRIES` (3), `LCPA_MIN_REQUEST_INTERVAL` (0.8), `LCPA_ACTIVITY_START_LIMIT` (20), `LCPA_ACTIVITY_MAX_LIMIT` (100), `LCPA_ACTIVITY_MAX_BATCHES` (4), `LCPA_DIFFICULTY_BATCH_SIZE` (10), `LCPA_SAVE_RAW` (true), `LCPA_BROWSER_FALLBACK` (false), `LCPA_CORS_ORIGINS`.

On Windows: `set LCPA_MIN_REQUEST_INTERVAL=1.5` (Command Prompt) or `$env:LCPA_MIN_REQUEST_INTERVAL="1.5"` (PowerShell) before starting uvicorn.

To use the browser fallback: `pip install playwright`, then `python -m playwright install chromium`, then set `LCPA_BROWSER_FALLBACK=1`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Can't reach the backend" in the UI | Start uvicorn on port 8000 from the `backend` folder |
| `ModuleNotFoundError: config` | Run uvicorn and pytest from inside `backend` |
| `access_blocked` | LeetCode refused the request or showed a browser check. Wait and retry, or try the optional browser fallback |
| `rate_limited` | Wait a few minutes; raise `LCPA_MIN_REQUEST_INTERVAL` |
| `graphql_error` / `structure_changed` | LeetCode changed its API. Run `scripts/inspect_leetcode.py` and update `scraper/queries.py` |
| Recent Activity has ~20 records | Expected: that is LeetCode's public cap (see `activity_sources[].detected_cap`) |
| Port 8000 or 5173 busy | `uvicorn main:app --port 8001` and change the target in `frontend/vite.config.js` |

## Future enhancements

Contest rating and badges, solved-count by difficulty, CSV export, a SQLite cache with per-profile history so repeated runs accumulate activity beyond the public cap over time, Redis-backed jobs for multiple workers, and comparison of several profiles.
