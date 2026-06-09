"""
Data Loader Module

This module handles the ingestion of data files (CSV and Excel) into pandas DataFrames.
It supports single file uploads, batch uploads, and Excel files with multiple sheets.

All methods use caching to prevent re-reading from disk on every Streamlit interaction.
"""

import io
from typing import Dict, Union, List
import pandas as pd
import streamlit as st


class DataLoader:
    """
    A class responsible for ingesting data files and returning unified DataFrames.

    Supported formats:
    - CSV files (.csv)
    - Excel files (.xlsx, .xls) with support for multiple sheets

    The class uses st.cache_data to ensure files are only read from disk once,
    then served from memory during subsequent interactions.
    """

    def __init__(self):
        """Initialize the DataLoader."""
        self.supported_csv_extensions = ['.csv']
        self.supported_excel_extensions = ['.xlsx', '.xls']

    def _is_csv(self, filename: str) -> bool:
        """Check if the file is a CSV based on extension."""
        return any(filename.lower().endswith(ext) for ext in self.supported_csv_extensions)

    def _is_excel(self, filename: str) -> bool:
        """Check if the file is an Excel file based on extension."""
        return any(filename.lower().endswith(ext) for ext in self.supported_excel_extensions)

    @staticmethod
    @st.cache_data(show_spinner=False)
    def _load_csv_cached(file_content: bytes, filename: str) -> pd.DataFrame:
        """
        Load a CSV file from bytes into a DataFrame.

        This method is cached to prevent re-reading from disk.

        Args:
            file_content: The raw bytes of the CSV file
            filename: The original filename (used for encoding detection)

        Returns:
            pd.DataFrame: The loaded data
        """
        # Try different encodings to handle various CSV formats
        encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']

        for encoding in encodings:
            try:
                df = pd.read_csv(io.BytesIO(file_content), encoding=encoding)
                return df
            except UnicodeDecodeError:
                continue
            except Exception:
                break

        # Fallback: try with error handling
        df = pd.read_csv(io.BytesIO(file_content), encoding='utf-8', errors='ignore')
        return df

    @staticmethod
    @st.cache_data(show_spinner=False)
    def _load_excel_cached(file_content: bytes, filename: str) -> Dict[str, pd.DataFrame]:
        """
        Load an Excel file from bytes into a dictionary of DataFrames (one per sheet).

        This method is cached to prevent re-reading from disk.
        Supports multiple sheets per Excel file.

        Args:
            file_content: The raw bytes of the Excel file
            filename: The original filename

        Returns:
            Dict[str, pd.DataFrame]: Dictionary with sheet names as keys and DataFrames as values
        """
        result = {}

        # Read all sheets from the Excel file
        excel_file = pd.ExcelFile(io.BytesIO(file_content))

        for sheet_name in excel_file.sheet_names:
            try:
                df = pd.read_excel(excel_file, sheet_name=sheet_name)
                # Create a unique key: filename_sheetname
                key = f"{filename}::{sheet_name}"
                result[key] = df
            except Exception as e:
                # Log error but continue with other sheets
                print(f"Error loading sheet '{sheet_name}' from {filename}: {e}")

        return result

    def load_single_file(self, uploaded_file) -> Dict[str, pd.DataFrame]:
        """
        Load a single uploaded file (CSV or Excel) and return a dictionary of DataFrames.

        For Excel files with multiple sheets, returns a dictionary with keys like:
        {"filename::Sheet1": df1, "filename::Sheet2": df2, ...}

        For CSV files, returns {"filename": df}.

        Args:
            uploaded_file: A Streamlit UploadedFile object

        Returns:
            Dict[str, pd.DataFrame]: Dictionary of loaded DataFrames
        """
        filename = uploaded_file.name
        file_content = uploaded_file.read()

        result = {}

        if self._is_csv(filename):
            df = self._load_csv_cached(file_content, filename)
            result[filename] = df

        elif self._is_excel(filename):
            sheet_dict = self._load_excel_cached(file_content, filename)
            result.update(sheet_dict)

        else:
            raise ValueError(f"Unsupported file format: {filename}")

        return result

    def load_multiple_files(self, uploaded_files: List) -> Dict[str, pd.DataFrame]:
        """
        Load multiple uploaded files and return a unified dictionary of DataFrames.

        This method handles batch uploads of CSV and Excel files.
        For Excel files, each sheet becomes a separate entry with the key format:
        "filename::sheetname"

        Args:
            uploaded_files: List of Streamlit UploadedFile objects

        Returns:
            Dict[str, pd.DataFrame]: Unified dictionary with filename (or filename::sheet) as keys
                                    and DataFrames as values
        """
        result = {}

        for uploaded_file in uploaded_files:
            try:
                file_data = self.load_single_file(uploaded_file)
                result.update(file_data)
            except Exception as e:
                print(f"Error loading file {uploaded_file.name}: {e}")

        return result

    @staticmethod
    def detect_sensitive_columns(data_dict: Dict[str, pd.DataFrame]) -> Dict[str, List[str]]:
        """
        Automatically detect potentially sensitive columns based on common naming patterns.

        This method scans column names across all DataFrames and identifies columns
        that may contain personal or sensitive information. These columns are
        pre-marked as sensitive for security review.

        Args:
            data_dict: Dictionary with table names as keys and DataFrames as values

        Returns:
            Dict[str, List[str]]: Dictionary mapping table names to lists of sensitive column names
        """
        # Keywords that indicate potentially sensitive data
        SENSITIVE_KEYWORDS = [
            'email', 'phone', 'tel', 'mobile', 'cell',
            'salary', 'wage', 'income', 'payment', 'credit',
            'password', 'secret', 'key', 'token', 'auth',
            'ssn', 'social', 'national_id', 'passport',
            'address', 'zip', 'postal', 'dob', 'birth',
            'gender', 'race', 'religion', 'political',
            'account', 'iban', 'card', 'cvv',
            'name', 'first_name', 'last_name', 'full_name'
        ]

        sensitive_columns = {}

        for table_name, df in data_dict.items():
            table_sensitive = []

            for col in df.columns:
                col_lower = col.lower()

                # Check if column name contains any sensitive keyword
                for keyword in SENSITIVE_KEYWORDS:
                    if keyword in col_lower:
                        table_sensitive.append(col)
                        break

            if table_sensitive:
                sensitive_columns[table_name] = table_sensitive

        return sensitive_columns
