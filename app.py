"""
DataPulse - Main Application Entry Point

A Streamlit-based data cleaning and optimization application with:
- File upload (CSV/Excel with multiple sheets)
- Database relationship diagram (Mermaid.js ER)
- Anomaly detection (Text + Numeric)
- Data profiling (metadata and preview)

All backend code is written in English with comprehensive inline documentation.
"""

from src.app import DataPulseApp


def main():
    """Main application entry point."""
    app = DataPulseApp()
    app.run()


if __name__ == "__main__":
    main()
