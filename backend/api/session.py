from typing import Dict, List
import polars as pl

data_store: Dict[str, Dict[str, pl.DataFrame]] = {}
file_paths: Dict[str, List[str]] = {}
sensitive_columns_store: Dict[str, Dict[str, List[str]]] = {}
relationships_store: Dict[str, List[Dict]] = {}
