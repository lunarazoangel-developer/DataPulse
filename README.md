# DataPulse

Intelligent data cleaning and anomaly detection application with AI-ready payload generation.

## Architecture

- **Frontend**: Next.js (React) + Tailwind CSS
- **Backend**: FastAPI (Python) + Polars

## Features

- **File Upload**: Support for CSV and Excel files (including multi-sheet Excel)
- **Database Relationships**: Mermaid.js ER diagrams to visualize table relationships
- **Anomaly Detection**: Traffic light system (RED/YELLOW/GREEN) for text and numeric data
- **Advanced Discrepancy Detection**: Format validation, duplicates, type mismatches, date anomalies, cardinality, domain rules
- **Column Profiling**: Auto-generated metrics (completeness, uniqueness, null %, type, recommendations) per column
- **Column Security**: Auto-detect and mark sensitive columns (PII, passwords, etc.)
- **AI Payload Generation**: Export sanitized JSON payloads for AI processing (with size estimate)
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
```

### Frontend

```bash
cd frontend
npm install
```

## Usage

### Running the Backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`

### Running the Frontend

```bash
cd frontend
npm run dev
```

The application will open in your browser at `http://localhost:3000`

## How to Use

1. **Upload Data**: Use the upload form to upload CSV or Excel files
2. **Explore Relationships**: View database relationships in the Dashboard tab
3. **Configure Security**: Mark sensitive columns in the Anomaly Report tab
4. **Adjust Detection**: Use sliders to tune anomaly detection sensitivity
5. **Review Anomalies**: See traffic light results (RED/YELLOW/GREEN)
6. **Export**: Download AI-ready JSON payload (size estimate shown next to the button)

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/files/upload` | Upload data files |
| GET | `/api/files/tables` | Get list of loaded tables |
| DELETE | `/api/files/clear` | Clear all data |
| GET | `/api/analyze/relationships` | Get table relationships |
| GET | `/api/analyze/schema` | Get schema analysis |
| POST | `/api/analyze/anomalies` | Run anomaly detection (returns categorized anomalies + column profiles + timings) |
| GET | `/api/payload/sensitive-columns` | Get sensitive columns |
| POST | `/api/payload/sensitive-columns` | Update sensitive columns |
| GET | `/api/payload/size` | Estimate AI payload size in bytes/human format |
| GET | `/api/payload/preview` | Preview AI payload (summary mode, max 5 examples per anomaly) |
| GET | `/api/payload/download` | Download AI payload JSON (summary mode) |

## Project Structure

```
datapulse/
├── backend/                    # FastAPI + Polars
│   ├── main.py               # Entry point
│   ├── requirements.txt      # Python dependencies
│   ├── api/
│   │   ├── routes/
│   │   │   ├── files.py     # File upload endpoints
│   │   │   ├── analyze.py   # Analysis endpoints
│   │   │   └── payload.py   # Payload generation + size
│   │   └── session.py       # In-memory data store
│   ├── core/
│   │   ├── data_loader.py           # CSV/Excel loading
│   │   ├── schema_analyzer.py       # Relationship detection
│   │   ├── quality_audit.py         # Text/numeric anomaly detection
│   │   ├── quality_audit_helpers.py # Format/regex/date/domain rules
│   │   ├── discrepancy_profiler.py  # 9 discrepancy detectors + column profiler
│   │   └── ai_enricher.py           # AI payload builder (summary/full mode)
│   └── data/                # Uploaded files storage
├── frontend/                  # Next.js + Tailwind
│   ├── app/
│   │   ├── page.tsx        # Upload page
│   │   └── dashboard/      # Dashboard views
│   ├── components/           # UI components
│   └── lib/                # Utilities
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

Sensitive columns (detected or manually marked) are:
- Excluded from AI payload schemas
- Redacted as `"[REDACTED]"` in sample data
- Not sent to AI for processing

## License

MIT License
