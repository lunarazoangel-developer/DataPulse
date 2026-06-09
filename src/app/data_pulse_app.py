"""
DataPulseApp - Main Application Class

This module contains the main DataLion application class that manages
all UI rendering and business logic in an object-oriented manner.

All code, variables, and inline documentation are written in English.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from typing import Dict, List, Any

from ..data_loader import DataLoader
from ..schema_analyzer import SchemaAnalyzer
from ..quality_audit import TextAnomalyDetector, NumericAnomalyDetector
from ..ai_enricher import AIPayloadBuilder


class DataPulseApp:
    """
    Main application class for DataPulse data cleaning tool.

    This class manages:
    - Session state initialization
    - File loading and processing
    - UI rendering for all tabs
    - Anomaly detection and categorization

    Attributes:
        APP_NAME: Application name constant
    """

    APP_NAME = "DataPulse"

    def __init__(self):
        """Initialize the DataLion application."""
        self._initialize_session_state()
        self._apply_custom_css()

    def _initialize_session_state(self):
        """Initialize all required session state variables."""
        if 'data_dict' not in st.session_state:
            st.session_state.data_dict = {}

        if 'schema_analyzer' not in st.session_state:
            st.session_state.schema_analyzer = SchemaAnalyzer()

        if 'relationships' not in st.session_state:
            st.session_state.relationships = []

        if 'files_loaded' not in st.session_state:
            st.session_state.files_loaded = False

        if 'text_threshold' not in st.session_state:
            st.session_state.text_threshold = 80.0

        if 'iqr_multiplier' not in st.session_state:
            st.session_state.iqr_multiplier = 1.5

        if 'zscore_threshold' not in st.session_state:
            st.session_state.zscore_threshold = 3.0

        if 'anomaly_results' not in st.session_state:
            st.session_state.anomaly_results = None

        if 'anomaly_cache_key' not in st.session_state:
            st.session_state.anomaly_cache_key = None

        if 'ai_payload' not in st.session_state:
            st.session_state.ai_payload = None

        if 'green_anomalies' not in st.session_state:
            st.session_state.green_anomalies = None

        if 'sensitive_columns' not in st.session_state:
            st.session_state.sensitive_columns = {}

    def _apply_custom_css(self):
        """Apply custom CSS for dark blue modern theme."""
        st.markdown("""
            <style>
            .stApp { background-color: #0D1B2A; }
            .stMarkdown, .stText, p, div { color: #E0E6ED !important; }
            h1, h2, h3, h4 { color: #4A90D9 !important; }
            section[data-testid="stSidebar"] { background-color: #1B2838; }
            .stButton > button[kind="primary"] {
                background-color: #1E3A5F;
                color: #E0E6ED;
                border: 1px solid #4A90D9;
            }
            .stButton > button[kind="primary"]:hover {
                background-color: #2E5A8F;
                border-color: #6AB0F9;
            }
            .stButton > button {
                background-color: #1B2838;
                color: #E0E6ED;
                border: 1px solid #3A5A7F;
            }
            .streamlit-expanderHeader {
                background-color: #1B2838;
                color: #E0E6ED;
            }
            [data-testid="stMetricValue"] { color: #4A90D9 !important; }
            [data-testid="stMetric"] {
                background-color: #1B2838;
                padding: 10px;
                border-radius: 5px;
                border: 1px solid #3A5A7F;
            }
            [data-testid="stMetricLabel"] { color: #A0AEB8 !important; }
            .stJson {
                background-color: #1B2838;
                padding: 15px;
                border-radius: 5px;
                border: 1px solid #3A5A7F;
            }
            pre { background-color: #1B2838 !important; border: 1px solid #3A5A7F; }
            .streamlit-expanderContent { background-color: #0D1B2A; }
            hr { border-color: #3A5A7F; }
            </style>
        """, unsafe_allow_html=True)

    def run(self):
        """Main application entry point."""
        st.set_page_config(
            page_title=self.APP_NAME,
            page_icon="🦁",
            layout="wide"
        )

        uploaded_files = self._render_sidebar()

        if uploaded_files and not st.session_state.files_loaded:
            self._load_files(uploaded_files)

        if st.session_state.files_loaded:
            self._render_main_content()
        else:
            self._render_welcome()

    def _render_sidebar(self):
        """Render the sidebar with file upload and controls."""
        st.sidebar.title(self.APP_NAME)
        st.sidebar.markdown("---")

        uploaded_files = st.sidebar.file_uploader(
            label="Upload Data Files",
            type=['csv', 'xlsx', 'xls'],
            accept_multiple_files=True,
            help="Upload CSV or Excel files. Excel files with multiple sheets are supported."
        )

        if st.session_state.files_loaded:
            st.sidebar.markdown("---")
            if st.sidebar.button("Clear All Data", type="secondary"):
                st.session_state.data_dict = {}
                st.session_state.relationships = []
                st.session_state.files_loaded = False
                st.session_state.sensitive_columns = {}
                st.rerun()

        return uploaded_files

    def _load_files(self, uploaded_files):
        """Load uploaded files into session state."""
        if not uploaded_files:
            return

        progress_bar = st.progress(0)
        status_text = st.empty()

        loader = DataLoader()
        loaded_data = {}
        total_files = len(uploaded_files)

        status_text.text("Loading files...")

        for i, uploaded_file in enumerate(uploaded_files):
            progress = int((i / total_files) * 100)
            progress_bar.progress(progress)
            status_text.text(f"Loading {uploaded_file.name}...")

            try:
                file_data = loader.load_single_file(uploaded_file)
                loaded_data.update(file_data)
            except Exception as e:
                st.error(f"Error loading {uploaded_file.name}: {e}")

        progress_bar.progress(100)
        status_text.text(f"Loaded {len(loaded_data)} table(s) successfully!")

        st.session_state.data_dict = loaded_data
        st.session_state.files_loaded = True
        st.session_state.anomaly_results = None
        st.session_state.anomaly_cache_key = None
        st.session_state.ai_payload = None
        st.session_state.green_anomalies = None

        analyzer = st.session_state.schema_analyzer
        relationships = analyzer.detect_relationships(loaded_data)
        st.session_state.relationships = relationships

        sensitive_cols = DataLoader.detect_sensitive_columns(loaded_data)
        st.session_state.sensitive_columns = sensitive_cols

        progress_bar.empty()
        status_text.empty()

    def _render_welcome(self):
        """Render welcome screen when no files are loaded."""
        st.title(f"Welcome to {self.APP_NAME} 🦁")
        st.markdown("""
        ### Your Intelligent Data Cleaning Assistant
        
        **Get started:**
        1. Upload your data files (CSV or Excel) using the sidebar
        2. Explore the database relationships in the Ecosystem Hub tab
        3. Review anomalies and configure detection settings in the Anomaly Report tab
        4. Export clean data with AI-generated payloads
        
        ---
        
        **Features:**
        - 🔗 Database Relationship Visualization (Mermaid.js ER Diagrams)
        - 🚦 Traffic Light Anomaly Detection (RED/YELLOW/GREEN)
        - 🔒 Column Security Configuration
        - 📦 AI-Ready Payload Generation
        """)

    def _render_main_content(self):
        """Render main content with tabs."""
        tabs = st.tabs([
            "🔗 Database Relationships",
            "🚦 Anomaly Report",
            "📊 Data Profiler"
        ])

        with tabs[0]:
            self._render_ecosystem_hub()

        with tabs[1]:
            self._render_anomaly_report()

        with tabs[2]:
            self._render_data_profiler()

    def _render_ecosystem_hub(self):
        """Render Tab 1: Database Relationships with charts."""
        st.subheader("Ecosystem Blueprint & Data Distribution")

        if not st.session_state.files_loaded or not st.session_state.data_dict:
            st.info("Please upload data files to view the ecosystem blueprint.")
            return

        analyzer = st.session_state.schema_analyzer
        data_dict = st.session_state.data_dict

        st.markdown("### 📊 Data Distribution Overview")

        type_distribution = analyzer.get_data_type_distribution(data_dict)
        null_statistics = analyzer.get_null_statistics(data_dict)

        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            st.markdown("#### Data Type Distribution")
            if not type_distribution.empty:
                fig_pie = px.pie(
                    type_distribution,
                    values='count',
                    names='data_type',
                    title="Column Data Types",
                    color_discrete_sequence=px.colors.qualitative.Set2
                )
                fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("No data type information available.")

        with chart_col2:
            st.markdown("#### Data Health (Null Percentage)")
            if not null_statistics.empty:
                color_map = {'Good': '#22c55e', 'Needs Attention': '#eab308', 'Critical': '#ef4444'}
                fig_bar = px.bar(
                    null_statistics,
                    x='table_name',
                    y='null_percentage',
                    color='health_status',
                    title="Null Values per Table",
                    labels={'null_percentage': 'Null %', 'table_name': 'Table'},
                    color_discrete_map=color_map
                )
                fig_bar.add_hline(y=5, line_dash="dash", line_color="green", annotation_text="5% threshold")
                fig_bar.add_hline(y=20, line_dash="dash", line_color="red", annotation_text="20% threshold")
                st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.info("No null statistics available.")

        st.markdown("---")
        st.markdown("### 🔗 Entity-Relationship Diagram")

        relationships = st.session_state.relationships

        if relationships:
            st.markdown(f"**Detected {len(relationships)} relationship(s) between tables**")
            with st.expander("View Relationship Details"):
                rel_df = pd.DataFrame(relationships)
                st.dataframe(rel_df, use_container_width=True, hide_index=True)
        else:
            st.warning("No relationships detected between tables.")

        mermaid_code = analyzer.generate_mermaid_er_diagram(relationships)

        if mermaid_code:
            try:
                from streamlit_mermaid import st_mermaid
                st_mermaid(mermaid_code, height=500)
            except ImportError:
                st.code(mermaid_code, language="mermaid")
                st.info("Install streamlit-mermaid for better visualization")

    def _render_anomaly_report(self):
        """Render Tab 2: Anomaly Report with traffic light system."""
        st.subheader("Initial Over-Sensitive Report")

        if not st.session_state.files_loaded or not st.session_state.data_dict:
            st.info("Please upload data files first.")
            return

        data_dict = st.session_state.data_dict

        self._render_security_configuration(data_dict)
        self._render_detection_settings()
        self._render_anomaly_results()

    def _render_security_configuration(self, data_dict):
        """Render column security configuration section."""
        st.markdown("### 🔒 Column Security Configuration")
        st.markdown("*Mark columns as sensitive/private to exclude from AI processing.*")

        table_names = list(data_dict.keys())

        if 'security_selected_table' not in st.session_state:
            st.session_state.security_selected_table = table_names[0] if table_names else None

        selected_table_security = st.selectbox(
            label="Select Table for Security Configuration",
            options=table_names,
            index=table_names.index(st.session_state.security_selected_table) if st.session_state.security_selected_table in table_names else 0,
            key="security_table_selector_tab2"
        )

        st.session_state.security_selected_table = selected_table_security

        with st.form(key="security_form"):
            if selected_table_security:
                df = data_dict[selected_table_security]
                columns = list(df.columns)
                current_sensitive = st.session_state.sensitive_columns.get(selected_table_security, [])

                selected_sensitive = st.multiselect(
                    label="Select Sensitive/Private Columns",
                    options=columns,
                    default=current_sensitive,
                    key="sensitive_multiselect_tab2",
                    help="Select columns containing personal, confidential, or private information"
                )

                submitted = st.form_submit_button("💾 Save Security Configuration", type="primary")

                if submitted:
                    st.session_state.sensitive_columns[selected_table_security] = selected_sensitive
                    st.success(f"Saved! {len(selected_sensitive)} column(s) marked as sensitive.")
                    st.session_state.anomaly_results = None

                auto_detected = DataLoader.detect_sensitive_columns({selected_table_security: df}).get(selected_table_security, [])
                manually_marked = [col for col in current_sensitive if col not in auto_detected]

                col1, col2 = st.columns(2)
                with col1:
                    if auto_detected:
                        st.markdown(f"**Auto-detected:** {', '.join(auto_detected)}")
                with col2:
                    if manually_marked:
                        st.markdown(f"**Manually marked:** {', '.join(manually_marked)}")

    def _render_detection_settings(self):
        """Render detection settings section."""
        st.markdown("---")
        st.markdown("### ⚙️ Detection Settings")

        with st.form(key="settings_form"):
            col1, col2, col3 = st.columns(3)

            with col1:
                text_threshold = st.slider(
                    label="Text Similarity Threshold (%)",
                    min_value=50,
                    max_value=100,
                    value=int(st.session_state.text_threshold),
                    step=5,
                    key="text_threshold_slider",
                    help="Minimum similarity percentage. Lower = more strict."
                )

            with col2:
                iqr_multiplier = st.slider(
                    label="IQR Multiplier",
                    min_value=0.5,
                    max_value=3.0,
                    value=st.session_state.iqr_multiplier,
                    step=0.1,
                    key="iqr_slider",
                    help="Lower = more outliers detected."
                )

            with col3:
                zscore_threshold = st.slider(
                    label="Z-Score Threshold",
                    min_value=1.0,
                    max_value=5.0,
                    value=st.session_state.zscore_threshold,
                    step=0.1,
                    key="zscore_slider",
                    help="Lower = more outliers detected."
                )

            submitted_settings = st.form_submit_button("✅ Apply Settings", type="primary")

            if submitted_settings:
                st.session_state.text_threshold = float(text_threshold)
                st.session_state.iqr_multiplier = iqr_multiplier
                st.session_state.zscore_threshold = zscore_threshold
                st.session_state.anomaly_results = None
                st.success("Settings applied! Running detection...")

        current_cache_key = (
            st.session_state.text_threshold,
            st.session_state.iqr_multiplier,
            st.session_state.zscore_threshold,
            len(st.session_state.data_dict)
        )

        needs_refresh = (
            st.session_state.anomaly_results is None or
            st.session_state.anomaly_cache_key != current_cache_key
        )

        st.markdown(f"**Current:** Text: {st.session_state.text_threshold}% | IQR: {st.session_state.iqr_multiplier} | Z-Score: {st.session_state.zscore_threshold}")

        if needs_refresh:
            with st.spinner("Running anomaly detection..."):
                all_results = self._run_anomaly_detection()
                st.session_state.anomaly_results = all_results
                st.session_state.anomaly_cache_key = current_cache_key
        else:
            all_results = st.session_state.anomaly_results

    def _run_anomaly_detection(self):
        """Run anomaly detection on all loaded data."""
        text_detector = TextAnomalyDetector(
            similarity_threshold=st.session_state.text_threshold,
            min_frequency=5
        )

        numeric_detector = NumericAnomalyDetector(
            iqr_multiplier=st.session_state.iqr_multiplier,
            zscore_threshold=st.session_state.zscore_threshold
        )

        all_results = {}
        total_tables = len(st.session_state.data_dict)

        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, (table_name, df) in enumerate(st.session_state.data_dict.items()):
            progress = int((i / total_tables) * 100)
            progress_bar.progress(progress)
            status_text.text(f"Analyzing {table_name}...")

            text_results = text_detector.detect_all_columns(df)
            numeric_results = numeric_detector.detect_all_columns(df, method='both')

            if text_results or numeric_results:
                all_results[table_name] = {
                    'text': text_results,
                    'numeric': numeric_results
                }

        progress_bar.progress(100)
        status_text.text("Analysis complete!")
        progress_bar.empty()
        status_text.empty()

        return all_results

    def _render_anomaly_results(self):
        """Render anomaly detection results."""
        all_results = st.session_state.anomaly_results

        has_text_anomalies = any(r['text'] for r in all_results.values())
        has_numeric_anomalies = any(r['numeric'] for r in all_results.values())

        if not has_text_anomalies and not has_numeric_anomalies:
            st.success("No anomalies detected with current settings!")
            st.markdown("""
            **Tips:**
            - Lower the Text Similarity Threshold to catch more text variations
            - Lower the IQR Multiplier to detect more numeric outliers
            - Lower the Z-Score Threshold to detect more statistical outliers
            """)
            return

        categorized = self._categorize_by_severity(all_results)

        red_count = sum(len(item['data']) for item in categorized['red'])
        yellow_count = sum(len(item['data']) for item in categorized['yellow'])
        green_count = sum(len(item['data']) for item in categorized['green'])

        st.markdown("### 🚦 Traffic Light Summary")
        summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
        with summary_col1:
            st.metric("🔴 RED", red_count)
        with summary_col2:
            st.metric("🟡 YELLOW", yellow_count)
        with summary_col3:
            st.metric("🟢 GREEN", green_count)
        with summary_col4:
            st.metric("Total Anomalies", red_count + yellow_count + green_count)

        traffic_light_report = {
            'red': categorized.get('red', []),
            'yellow': categorized.get('yellow', []),
            'green': categorized.get('green', [])
        }

        self._render_payload_preview(traffic_light_report, categorized)
        self._render_anomaly_details(categorized)

    def _categorize_by_severity(self, all_results: dict) -> dict:
        """Categorize anomalies by severity level (RED, YELLOW, GREEN)."""
        categorized = {'red': [], 'yellow': [], 'green': []}

        for table_name, results in all_results.items():
            if results.get('text'):
                for col_name, detection_results in results['text'].items():
                    if not detection_results:
                        continue

                    for det_type in ['fuzzy', 'low_frequency', 'case_inconsistency', 'whitespace']:
                        if det_type in detection_results and not detection_results[det_type].empty:
                            df = detection_results[det_type].copy()
                            df['table'] = table_name
                            df['column'] = col_name
                            df['detection_type'] = det_type

                            for severity in ['red', 'yellow', 'green']:
                                severity_df = df[df['severity'] == severity]
                                if not severity_df.empty:
                                    categorized[severity].append({
                                        'table': table_name,
                                        'column': col_name,
                                        'detection_type': det_type,
                                        'data': severity_df
                                    })

            if results.get('numeric'):
                for col_name, anomaly_df in results['numeric'].items():
                    if anomaly_df.empty:
                        continue

                    df = anomaly_df.copy()
                    df['table'] = table_name
                    df['column'] = col_name

                    for severity in ['red', 'yellow', 'green']:
                        severity_df = df[df['severity'] == severity]
                        if not severity_df.empty:
                            categorized[severity].append({
                                'table': table_name,
                                'column': col_name,
                                'detection_type': 'numeric',
                                'data': severity_df
                            })

        return categorized

    def _render_payload_preview(self, traffic_light_report, categorized):
        """Render AI payload preview section."""
        payload_builder = AIPayloadBuilder()

        preview_payload = payload_builder.generate_preview_payload(
            data_dict=st.session_state.data_dict,
            traffic_light_report=traffic_light_report,
            sensitive_columns=st.session_state.sensitive_columns,
            relationships=st.session_state.relationships,
            max_sample_rows=10,
            include_green=True
        )

        payload_summary = payload_builder.generate_summary(
            data_dict=st.session_state.data_dict,
            sensitive_columns=st.session_state.sensitive_columns,
            traffic_light_report=traffic_light_report
        )

        with st.expander("🔍 Preview Data Package for AI (Transparency & Security Hub)", expanded=False):
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("Tables", payload_summary['total_tables'])
            with col2:
                st.metric("RED", payload_summary['red_anomalies'])
            with col3:
                st.metric("YELLOW", payload_summary['yellow_anomalies'])
            with col4:
                st.metric("GREEN", payload_summary['green_anomalies'])
            with col5:
                st.metric("Redacted", payload_summary['redacted_columns'])

            st.markdown("---")
            st.markdown("#### 📦 Complete Payload JSON")
            import json
            st.json(preview_payload)

        st.markdown("### 📥 Export Options")

        col1, col2 = st.columns(2)

        with col1:
            import json
            payload_json = json.dumps(preview_payload, indent=2, default=str)
            st.download_button(
                label="📦 Generate AI Payload File (JSON)",
                data=payload_json,
                file_name="ai_payload.json",
                mime="application/json",
                type="primary"
            )

        with col2:
            if categorized.get('green'):
                green_dataframes = []
                for item in categorized['green']:
                    df = item['data'].copy()
                    df['table_name'] = item['table']
                    df['column_name'] = item['column']
                    green_dataframes.append(df)

                combined = pd.concat(green_dataframes, ignore_index=True)
                csv = combined.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="📊 Export GREEN Anomalies (CSV)",
                    data=csv,
                    file_name="green_anomalies.csv",
                    mime="text/csv",
                    help="Export GREEN anomalies for manual review"
                )

    def _render_anomaly_details(self, categorized):
        """Render detailed anomaly tables."""
        st.markdown("---")
        st.markdown("### 🔍 Anomaly Details")

        if categorized['red']:
            st.markdown("### 🔴 RED Alerts - Ready for AI Processing")
            st.markdown("*High-confidence issues that the AI can automatically fix.*")

            for i, item in enumerate(categorized['red']):
                with st.expander(f"📋 {item['table']} - {item['column']} ({len(item['data'])} issues)"):
                    df_display = item['data'].copy()
                    sensitive_cols = st.session_state.sensitive_columns.get(item['table'], [])
                    if sensitive_cols:
                        for col in sensitive_cols:
                            if col in df_display.columns:
                                df_display[col] = '[REDACTED]'
                    st.dataframe(df_display, use_container_width=True, hide_index=True)
        else:
            st.info("No RED alerts found.")

        st.markdown("---")
        if categorized['yellow']:
            st.markdown("### 🟡 Yellow Alerts - Needs AI Context")
            st.markdown("*Moderate issues requiring contextual information for AI analysis.*")

            for i, item in enumerate(categorized['yellow']):
                with st.expander(f"📋 {item['table']} - {item['column']} ({len(item['data'])} issues)"):
                    df_display = item['data'].copy()
                    sensitive_cols = st.session_state.sensitive_columns.get(item['table'], [])
                    if sensitive_cols:
                        for col in sensitive_cols:
                            if col in df_display.columns:
                                df_display[col] = '[REDACTED]'
                    st.dataframe(df_display, use_container_width=True, hide_index=True)
        else:
            st.info("No YELLOW alerts found.")

        st.markdown("---")
        if categorized['green']:
            st.markdown("### 🟢 Green Alerts - Human Review")
            st.markdown("*Low-severity issues for manual review.*")

            for i, item in enumerate(categorized['green']):
                with st.expander(f"📋 {item['table']} - {item['column']} ({len(item['data'])} issues)"):
                    df_display = item['data'].copy()
                    sensitive_cols = st.session_state.sensitive_columns.get(item['table'], [])
                    if sensitive_cols:
                        for col in sensitive_cols:
                            if col in df_display.columns:
                                df_display[col] = '[REDACTED]'
                    st.dataframe(df_display, use_container_width=True, hide_index=True)
        else:
            st.info("No GREEN alerts found.")

    def _render_data_profiler(self):
        """Render Tab 3: Data Profiler with metadata."""
        st.subheader("Data Profiler")

        if not st.session_state.files_loaded or not st.session_state.data_dict:
            st.info("Please upload data files first.")
            return

        data_dict = st.session_state.data_dict
        table_names = list(data_dict.keys())

        selected_table = st.selectbox(
            label="Select Table to Profile",
            options=table_names,
            key="profiler_table_selector"
        )

        if selected_table:
            df = data_dict[selected_table]

            st.markdown(f"### 📋 {selected_table} Overview")

            metadata_col1, metadata_col2, metadata_col3, metadata_col4 = st.columns(4)
            with metadata_col1:
                st.metric("Rows", f"{len(df):,}")
            with metadata_col2:
                st.metric("Columns", len(df.columns))
            with metadata_col3:
                memory_mb = df.memory_usage(deep=True).sum() / 1024 / 1024
                st.metric("Memory (MB)", f"{memory_mb:.2f}")
            with metadata_col4:
                null_total = df.isnull().sum().sum()
                st.metric("Null Values", f"{null_total:,}")

            st.markdown("#### Column Details")
            column_details = []
            for col in df.columns:
                column_details.append({
                    'Column': col,
                    'Type': str(df[col].dtype),
                    'Nulls': df[col].isnull().sum(),
                    'Unique': df[col].nunique(),
                    'Sample': str(df[col].dropna().iloc[0])[:50] if df[col].notna().any() else 'N/A'
                })

            details_df = pd.DataFrame(column_details)
            st.dataframe(details_df, use_container_width=True, hide_index=True)

            st.markdown("#### Data Preview")
            st.dataframe(df.head(50), use_container_width=True)
