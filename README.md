# DataPulse

A Streamlit-based intelligent data cleaning and anomaly detection application with AI-ready payload generation.

## Features

- **File Upload**: Support for CSV and Excel files (including multi-sheet Excel)
- **Database Relationships**: Mermaid.js ER diagrams to visualize table relationships
- **Anomaly Detection**: Traffic light system (RED/YELLOW/GREEN) for text and numeric data
- **Column Security**: Auto-detect and mark sensitive columns (PII, passwords, etc.)
- **AI Payload Generation**: Export sanitized JSON payloads for AI processing

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/datapulse.git
cd datapulse

# Create virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Requirements

- Python 3.8+
- Streamlit
- Pandas
- Plotly
- streamlit-mermaid (optional, for ER diagrams)

Install all dependencies:

```bash
pip install streamlit pandas plotly openpyxl python-levenshtein
pip install streamlit-mermaid  # Optional
```

## Usage

```bash
streamlit run app.py
```

The application will open in your browser at `http://localhost:8501`.

## How to Use

1. **Upload Data**: Use the sidebar to upload CSV or Excel files
2. **Explore Relationships**: View database relationships in the "Database Relationships" tab
3. **Configure Security**: Mark sensitive columns in the "Anomaly Report" tab
4. **Adjust Detection**: Use sliders to tune anomaly detection sensitivity
5. **Review Anomalies**: See traffic light results (RED/YELLOW/GREEN)
6. **Export**: Download AI-ready JSON payloads

## Project Structure

```
datapulse/
├── app.py                    # Main entry point
├── src/
│   ├── app/
│   │   ├── __init__.py
│   │   └── data_pulse_app.py # Main application class
│   ├── data_loader.py        # File loading utilities
│   ├── schema_analyzer.py   # Relationship detection & ER diagrams
│   ├── quality_audit.py     # Anomaly detection
│   └── ai_enricher.py       # AI payload generation
├── .streamlit/
│   └── config.toml          # Streamlit configuration
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
