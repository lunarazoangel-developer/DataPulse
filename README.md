# DataPulse

Intelligent data cleaning and anomaly detection application with AI-ready payload generation and an optional AI chat for discrepancy triage.

## Architecture

- **Frontend**: Next.js (React) + Tailwind CSS
- **Backend**: FastAPI (Python) + Polars
- **AI (beta)**: DeepSeek via OpenAI-compatible HTTP API

## Features

- **File Upload**: Support for CSV and Excel files (including multi-sheet Excel)
- **Persistent Database Storage**: Every upload becomes a timestamped folder under `backend/data/` (`YYYY-MM-DD_HH-MM-SS/`). All saved databases can be reopened, deleted, or listed from the home screen.
- **Database Relationships**: Mermaid.js ER diagrams to visualize table relationships
- **Anomaly Detection**: Traffic light system (RED/YELLOW/GREEN) for text and numeric data
- **Advanced Discrepancy Detection**: Format validation, duplicates, type mismatches, date anomalies, cardinality, domain rules
- **Column Profiling**: Auto-generated metrics (completeness, uniqueness, null %, type, recommendations) per column
- **Column Security**: Auto-detect and mark sensitive columns (PII, passwords, etc.)
- **AI Payload Generation**: Export sanitized JSON payloads for AI processing (with size estimate)
- **AI Analysis Tab (beta)**: Inline chat inside the dashboard that unlocks after a detection run. Sends the AI-ready report to DeepSeek and returns a structured **plan → approve → apply** flow with color-coded proposal cards and atomic CSV writes.
- **Branded UI**: Animated pulse-logo (ECG-style), pulse markers inside the RED/YELLOW/GREEN counters, custom-styled file picker, and a `btn-pulse` primary action button.
- **Sampling & Performance**: Optional row sampling for very large datasets, vectorized detection for fast execution
- **Detection Timing**: Per-detector timing breakdown for performance observability

## Installation

### Backend

```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set DEEPSEEK_API_KEY if you want the AI chat to work.
```

### Frontend

```bash
cd frontend
npm install
# .env.local is optional; NEXT_PUBLIC_API_URL defaults to http://localhost:8000
```

## Usage

### Running the Backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.

### Running the Frontend

```bash
cd frontend
npm run dev
```

The application will open in your browser at `http://localhost:3000`.

## How to Use

1. **Open a saved database or create a new one**: The home page lists every database saved under `backend/data/`. Click **Open** to reopen one, or upload files to create a brand-new database with a timestamp name.
2. **Explore Relationships**: View database relationships in the Database Relationships tab.
3. **Configure & Run Detection**: Open the Anomaly Report tab, adjust settings, and click **Run Detection**.
4. **Review Anomalies**: See traffic light results (RED/YELLOW/GREEN) with per-column counters that include a pulse marker in the severity color.
5. **AI Analysis (optional)**: Once at least one anomaly is found, a new **AI Analysis** tab unlocks next to the others. Click it to open the inline chat. The report is sent automatically to DeepSeek, which returns a structured plan. Approve / reject each card, then click **Aplicar cambios aprobados** (or type `continuar` in the chat) to apply them to the underlying tables.
6. **Export**: Download AI-ready JSON payload (size estimate shown next to the button).

### Storage Layout

```
backend/data/
└── 2026-06-11_14-30-45/        ← one folder per upload session
    ├── meta.json               ← { name, created_at, tables, file_count, total_rows }
    ├── users.csv
    └── products.xlsx
```

Clearing the in-memory session (`Clear` button) does NOT delete the folder on disk, so previously saved databases remain available to reopen.

## AI Chat Configuration (beta)

The AI tab requires a DeepSeek API key. Get one at <https://platform.deepseek.com/>, then edit `backend/.env`:

```bash
DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_API_URL=https://api.deepseek.com/v1/chat/completions
DEEPSEEK_TIMEOUT=60
```

> The model name is case-sensitive — DeepSeek only accepts the exact lowercase
> ids `deepseek-v4-flash` (faster, cheaper — recommended default) or
> `deepseek-v4-pro` (higher quality). Older aliases like `deepseek-chat` may
> still work on some accounts but are not the current recommended names.

Restart `uvicorn` after editing. The chat tab will then show a green "Ready" badge; if the key is missing it shows "Beta" and disables the input. The backend never exposes the key to the frontend.

## Plan → Approve → Apply Workflow (beta)

When the AI Analysis tab opens, the JSON report is sent to DeepSeek. The model is instructed to respond with a **structured plan** (a `summary` plus an array of `proposals`) rather than free-form text. The plan is rendered inside the chat as a stack of **color-coded cards**, one per proposal, ordered from highest to lowest risk.

Each card shows the proposed change, the affected `table.column`, the action, and a collapsible `params` block. The user can toggle two buttons per card:

- **✓ Aprobar** (default — green)
- **✕ Rechazar** (red)

Once at least one card is in the approved state, a sticky action panel appears with the button **Aplicar cambios aprobados (N)**. Typing `continuar` in the chat input also triggers the apply step. Approved changes are dispatched to `POST /api/ai/apply`, which mutates the in-memory Polars DataFrames, writes the new CSV files atomically (`.tmp` + `os.replace`) and refreshes `meta.json`. The response includes a per-proposal report of `rows_changed` and any errors. After a successful apply a banner offers **Re-detectar anomalías** (the user decides when to re-run the detectors — the workflow does not auto-re-run).

### Supported actions

| Action | Default risk | Description |
| --- | --- | --- |
| `strip_whitespace` | low | Trim leading/trailing whitespace |
| `normalize_case` | low | `lower` / `upper` / `title` |
| `fill_null` | low | Fill nulls and placeholders (`N/A`, `--`, `s/d`…) with a value |
| `replace_regex` | medium | `str.replace_all(pattern, replacement)` |
| `standardize_date` | medium | Try each `input_formats` entry and emit `target_format` |
| `clip_values` | medium | Clip numeric column to `[lower, upper]` |
| `cast_type` | high | Cast to `Int64`, `Float64`, `String`, `Boolean`, `Date`, `Datetime`, … |
| `drop_duplicates` | high | `df.unique(subset=…)` (subset optional) |
| `drop_rows` | high | `df.filter(~mask)` with `is_null`, `not_null`, `equals`, `not_equals`, `matches`, `between` |

Actions that would alter Excel files (`.xlsx`, `.xls`) are blocked at the apply step and reported as errors — re-upload the file as CSV to enable those changes.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/files/upload` | Upload files and create a new timestamped database |
| GET | `/api/files/tables` | Get tables in the current session (includes `database` name) |
| DELETE | `/api/files/clear` | Clear in-memory session (keeps saved databases on disk) |
| GET | `/api/databases` | List all saved databases under `backend/data/` |
| GET | `/api/databases/current` | Name of the currently active database |
| GET | `/api/databases/{name}` | Load a saved database into the session |
| DELETE | `/api/databases/{name}` | Permanently delete a saved database folder |
| GET | `/api/analyze/relationships` | Get table relationships |
| GET | `/api/analyze/schema` | Get schema analysis |
| POST | `/api/analyze/anomalies` | Run anomaly detection (returns categorized anomalies + column profiles + timings) |
| GET | `/api/payload/sensitive-columns` | Get sensitive columns |
| POST | `/api/payload/sensitive-columns` | Update sensitive columns |
| GET | `/api/payload/size` | Estimate AI payload size in bytes/human format |
| GET | `/api/payload/preview` | Preview AI payload (summary mode, max 5 examples per anomaly) |
| GET | `/api/payload/download` | Download AI payload JSON (summary mode) |
| GET | `/api/ai/status` | `{ available: bool, model: str }` for the AI chat |
| POST | `/api/ai/chat` | Send a message to the AI; body `{ payload, history, message? }`. Returns `{ message, summary, proposals }` so the UI can render the structured plan. Returns 503 if the key is missing. |
| POST | `/api/ai/apply` | Apply approved proposals. Body `{ database?, proposals: Proposal[] }`. Returns `{ database, applied[], skipped[], errors[], table_summaries[] }`. |

## Project Structure

```
datapulse/
├── backend/                         # FastAPI + Polars
│   ├── main.py                      # Entry point
│   ├── config.py                    # .env loader (DeepSeek, etc.)
│   ├── requirements.txt             # Python dependencies
│   ├── .env.example                 # Template for local secrets
│   ├── api/
│   │   ├── session.py               # In-memory data store
│   │   └── routes/
│   │       ├── files.py             # Upload / tables / clear
│   │       ├── databases.py         # List / open / delete saved DBs
│   │       ├── analyze.py           # Relationships / schema / anomalies
│   │       ├── payload.py           # AI payload builder + size estimate
│   │       └── ai.py                # DeepSeek chat proxy + /ai/apply (beta)
│   ├── ai/
│   │   ├── chat.py                  # DeepSeek client + structured prompt parser
│   │   └── actions.py               # Supported proposal actions + risk hints
│   ├── core/
│   │   ├── data_loader.py           # CSV/Excel loading
│   │   ├── data_transformer.py      # apply_proposal dispatcher (Polars)
│   │   ├── database_manager.py      # Timestamped-folder CRUD
│   │   ├── schema_analyzer.py       # Relationship detection
│   │   ├── quality_audit.py         # Text/numeric anomaly detection
│   │   ├── quality_audit_helpers.py # Format/regex/date/domain rules
│   │   ├── discrepancy_profiler.py  # 9 discrepancy detectors + column profiler
│   │   └── ai_enricher.py           # AI payload builder (summary/full mode)
│   └── data/                        # Saved databases (gitignored)
├── frontend/                        # Next.js + Tailwind
│   ├── app/
│   │   ├── page.tsx                 # Upload + saved databases home
│   │   └── dashboard/page.tsx       # 3 tabs: Relationships / Anomaly Report / AI Analysis
│   ├── components/
│   │   ├── PulseLogo.tsx            # Animated wordmark + ECG SVG
│   │   ├── PulseBar.tsx             # Reusable ECG line (full / compact)
│   │   ├── MermaidDiagram.tsx
│   │   └── ProposalCard.tsx         # AI plan card (approve / reject)
│   └── lib/
│       ├── api.ts                   # Typed axios helpers
│       └── proposals.ts             # Risk meta + helpers (sort, isContinuar…)
└── README.md
```

## Anomaly Detection Types

### Text Anomalies (TextAnomalyDetector)
- Case inconsistency (e.g., "John" vs "john") — **aggregated** with up to 5 examples per group
- Whitespace issues (e.g., " John " vs "John")
- Fuzzy duplicates (similar values, with **blocking by length/prefix** for scalability)
- Low frequency values — **aggregated** with up to 5 examples + total count

### Numeric Anomalies (NumericAnomalyDetector)
- IQR-based outliers
- Z-Score statistical outliers

### Discrepancy Detectors (DiscrepancyDetector)

All detectors are configurable via `AnalysisSettings` and run with try/except isolation (one failure does not stop the rest). Each anomaly is truncated to **5 examples** by default.

| Detector | Severity | Description |
|---|---|---|
| **Placeholder Null** | Yellow | Values like `"N/A"`, `"--"`, `"null"`, `"s/d"` in string columns |
| **Format Violation** | Red | Email/URL/UUID/IP/phone values that don't match the expected regex |
| **Inconsistent Date Format** | Red | Mixed date formats (ISO, US, EU) in the same column |
| **Type Mismatch** | Red | Strings that cannot be parsed in numeric/date columns |
| **Constant Column** | Green | Columns with a single unique value |
| **Low Variance** | Green | Numeric columns with coefficient of variation < 5% |
| **Date Anomaly** | Red/Yellow | Future dates (red) or dates before 1900 (yellow) |
| **High Cardinality** | Yellow | Columns with unique_ratio ≥ 0.9 (likely ID/PII) |
| **Domain Violation** | Red | Negative values in `age/price/qty`, out-of-range in `pct/ratio` (auto-inferred from column name) |
| **Duplicate Rows** | Red | Exact duplicates over full table or a logical subset |

## Performance Features

- **Vectorized detection** with Polars expressions (50k rows × 6 cols typically < 200ms).
- **Fuzzy matching blocking** by length bucket + first character for O(n×k) scaling instead of O(n²).
- **Optional sampling**: pass `sample_size` or `sample_fraction` to `/anomalies` for very large datasets.
- **Per-detector timing** returned in `discrepancy_timings_ms` for observability.
- **Resilient by design**: each detector is wrapped in try/except; a failure reports a `Detector Error` anomaly without breaking the response.

## Column Profiler

Every column in the analysis response gets a profile:

```json
{
  "column": "email",
  "dtype": "String",
  "total_count": 1000,
  "null_count": 12,
  "null_pct": 1.2,
  "unique_count": 850,
  "unique_ratio": 0.85,
  "completeness": 0.988,
  "is_constant": false,
  "is_likely_id": true,
  "detected_format": "email",
  "inferred_domain_rule": null,
  "severity": "green",
  "recommendations": ["Detected email format"]
}
```

## Traffic Light System

- **RED**: High-confidence issues ready for AI to fix
- **YELLOW**: Moderate issues requiring AI context
- **GREEN**: Low-severity issues for human review

## AI Payload (Summary Mode)

The download endpoint produces an **AI-ready JSON summary**:

```json
{
  "metadata": { "payload_mode": "summary", "max_samples_per_anomaly": 5, ... },
  "schemas": { "table_name": { "columns": [...], "redacted_columns": [...] } },
  "relationships": [...],
  "anomalies": {
    "red": [{ "table": ..., "column": ..., "detection_type": ..., "data": [max 5 entries] }],
    "yellow": [...],
    "green": [...]
  }
}
```

**Size estimate** is shown next to the Download button with color coding:
- Green: < 100 KB (ideal for AI)
- Yellow: 100 KB – 1 MB
- Red: ≥ 1 MB (consider sampling or filtering)

## Security

- Sensitive columns (detected or manually marked) are excluded from AI payload schemas and redacted as `"[REDACTED]"` in sample data.
- The DeepSeek API key is read from `backend/.env` on the server and never sent to the browser.
- All `.env` and `.env.local` files are gitignored; only `.env.example` is tracked.

## License

MIT License
