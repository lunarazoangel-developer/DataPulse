# DataPulse

Intelligent data cleaning and anomaly detection application with AI-ready payload generation.

## Architecture

- **Frontend**: Next.js (React) + Tailwind CSS
- **Backend**: FastAPI (Python) + Polars

## Features

- **File Upload**: Support for CSV and Excel files (including multi-sheet Excel)
- **Database Relationships**: Mermaid.js ER diagrams to visualize table relationships
- **Anomaly Detection**: Traffic light system (RED/YELLOW/GREEN) for text and numeric data
- **Column Security**: Auto-detect and mark sensitive columns (PII, passwords, etc.)
- **AI Payload Generation**: Export sanitized JSON payloads for AI processing

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
6. **Export**: Download AI-ready JSON payloads

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/files/upload` | Upload data files |
| GET | `/api/files/tables` | Get list of loaded tables |
| DELETE | `/api/files/clear` | Clear all data |
| GET | `/api/analyze/relationships` | Get table relationships |
| GET | `/api/analyze/schema` | Get schema analysis |
| POST | `/api/analyze/anomalies` | Run anomaly detection |
| GET | `/api/payload/sensitive-columns` | Get sensitive columns |
| POST | `/api/payload/sensitive-columns` | Update sensitive columns |
| GET | `/api/payload/preview` | Preview AI payload |
| GET | `/api/payload/download` | Download AI payload JSON |

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
│   │   │   └── payload.py   # Payload generation
│   │   └── session.py       # In-memory data store
│   ├── core/
│   │   ├── data_loader.py   # CSV/Excel loading
│   │   ├── schema_analyzer.py # Relationship detection
│   │   ├── quality_audit.py # Anomaly detection
│   │   └── ai_enricher.py  # Payload builder
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

### Text Anomalies
- Case inconsistency (e.g., "John" vs "john")
- Whitespace issues (e.g., " John " vs "John")
- Fuzzy duplicates (similar values)
- Low frequency values

### Numeric Anomalies
- IQR-based outliers
- Z-Score statistical outliers

## Traffic Light System

- **RED**: High-confidence issues ready for AI to fix
- **YELLOW**: Moderate issues requiring AI context
- **GREEN**: Low-severity issues for human review

## Security

Sensitive columns (detected or manually marked) are:
- Excluded from AI payload schemas
- Redacted as "[REDACTED]" in sample data
- Not sent to AI for processing

## License

MIT License
