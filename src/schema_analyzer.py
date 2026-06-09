"""
Schema Analyzer Module

This module provides functionality for analyzing data schemas across multiple DataFrames,
detecting relationships between tables based on shared column names, and generating
Mermaid.js ER diagrams for visualization.

All backend code is written in English with comprehensive documentation.
"""

from typing import Dict, List, Tuple
import pandas as pd


class SchemaAnalyzer:
    """
    A class for analyzing column schemas across multiple DataFrames and detecting relationships.

    The analyzer automatically identifies connections between tables based on:
    - Exact column name matches
    - Column names containing relational keywords (id, key, code, customer_id, etc.)

    Attributes:
        RELATIONAL_KEYWORDS: List of keywords that indicate potential foreign key relationships
    """

    # Keywords that indicate potential relational columns
    RELATIONAL_KEYWORDS = [
        'id', 'key', 'code', 'customer_id', 'user_id', 'order_id',
        'product_id', 'category_id', 'country_id', 'city_id',
        'employee_id', 'supplier_id', 'inventory_id', 'transaction_id',
        'invoice_id', 'payment_id', 'shipment_id', 'address_id',
        'region_id', 'department_id', 'manager_id', 'parent_id'
    ]

    def __init__(self):
        """Initialize the SchemaAnalyzer."""
        self.column_index: Dict[str, set] = {}
        self.data_dict: Dict[str, pd.DataFrame] = {}

    def scan_columns(self, data_dict: Dict[str, pd.DataFrame]) -> Dict[str, set]:
        """
        Scan column names across all active DataFrames in memory.

        Builds an index mapping each unique column name to the set of tables
        that contain that column.

        Args:
            data_dict: Dictionary with table names as keys and DataFrames as values

        Returns:
            Dict[str, set]: Dictionary mapping column names to sets of table names
        """
        self.data_dict = data_dict
        self.column_index = {}

        for table_name, df in data_dict.items():
            # Get column names (normalize to lowercase for case-insensitive matching)
            columns = set(col.lower() for col in df.columns)

            for col in columns:
                if col not in self.column_index:
                    self.column_index[col] = set()
                self.column_index[col].add(table_name)

        return self.column_index

    def _is_relational_column(self, column_name: str) -> bool:
        """
        Check if a column name indicates a potential relational key.

        Args:
            column_name: The column name to check

        Returns:
            bool: True if the column is a relational key
        """
        col_lower = column_name.lower()

        # Check if column name contains any relational keyword
        for keyword in self.RELATIONAL_KEYWORDS:
            if keyword in col_lower:
                return True

        return False

    def detect_relationships(self, data_dict: Dict[str, pd.DataFrame]) -> List[Dict]:
        """
        Automatically detect relationships between tables based on shared columns.

        Creates connection links when two or more tables share a column that:
        - Has the exact same name
        - Contains relational keywords (id, key, code, etc.)

        Args:
            data_dict: Dictionary with table names as keys and DataFrames as values

        Returns:
            List[Dict]: List of relationship dictionaries, each containing:
                - source: Source table name
                - target: Target table name
                - column: The shared column name
                - relationship_type: Type of relationship detected
        """
        # Scan columns first
        self.scan_columns(data_dict)

        relationships = []

        # Check each column for multiple tables
        for column_name, tables in self.column_index.items():
            if len(tables) >= 2:
                # This column exists in multiple tables - potential relationship
                is_relational = self._is_relational_column(column_name)

                # Create relationships between all pairs of tables
                table_list = list(tables)
                for i in range(len(table_list)):
                    for j in range(i + 1, len(table_list)):
                        relationship = {
                            'source': table_list[i],
                            'target': table_list[j],
                            'column': column_name,
                            'relationship_type': 'relational_key' if is_relational else 'shared_column'
                        }
                        relationships.append(relationship)

        return relationships

    def generate_mermaid_er_diagram(self, relationships: List[Dict]) -> str:
        """
        Generate a Mermaid.js ER diagram string representing the database structure.

        Creates an entity-relationship diagram where:
        - Each table is represented as an entity with its columns
        - Relationships are shown with connecting lines labeled by shared columns

        Args:
            relationships: List of relationship dictionaries from detect_relationships()

        Returns:
            str: Mermaid.js ER diagram code
        """
        if not self.data_dict:
            return "erDiagram\n    EMPTY"

        # Build table definitions
        table_definitions = []
        table_relationships = []
        processed_rels = set()

        # Process each table
        for table_name, df in self.data_dict.items():
            # Sanitize table name for Mermaid (replace special chars)
            safe_table_name = self._sanitize_name(table_name)

            # Build column list - use simplified format
            columns = []
            for col in df.columns:
                col_type = str(df[col].dtype)
                # Simplify dtype for display
                if 'int' in col_type:
                    col_type = 'INT'
                elif 'float' in col_type:
                    col_type = 'FLOAT'
                elif 'datetime' in col_type:
                    col_type = 'DATETIME'
                elif 'object' in col_type:
                    col_type = 'VARCHAR'
                else:
                    col_type = 'TYPE'

                columns.append(f"    {col} {col_type}")

            if columns:
                table_def = f'    {safe_table_name} {{\n{"".join(columns)}\n    }}'
            else:
                table_def = f'    {safe_table_name}'
            table_definitions.append(table_def)

        # Process relationships
        for rel in relationships:
            source = self._sanitize_name(rel['source'])
            target = self._sanitize_name(rel['target'])
            column = rel['column']

            # Create unique key to avoid duplicates
            rel_key = tuple(sorted([source, target]))
            if rel_key in processed_rels:
                continue
            processed_rels.add(rel_key)

            # Use simple relationship syntax
            rel_line = f'    {source} ||--||{target} : "{column}"'
            table_relationships.append(rel_line)

        # Combine into Mermaid ER diagram
        mermaid_lines = ["erDiagram"]

        # Add table definitions
        for definition in table_definitions:
            mermaid_lines.append(definition)

        # Add relationships
        for rel_line in table_relationships:
            mermaid_lines.append(rel_line)

        return "\n".join(mermaid_lines)

    def _sanitize_name(self, name: str) -> str:
        """
        Sanitize a table/column name for use in Mermaid.js diagram.

        Args:
            name: The original name

        Returns:
            str: Sanitized name safe for Mermaid syntax
        """
        # Replace spaces and special characters with underscores
        safe = name.replace(' ', '_').replace('-', '_').replace('.', '_')
        # Remove any characters that might break Mermaid
        safe = ''.join(c if c.isalnum() or c == '_' else '_' for c in safe)
        # Ensure it doesn't start with a number
        if safe and safe[0].isdigit():
            safe = 'T_' + safe
        return safe

    def get_table_metadata(self, table_name: str, df: pd.DataFrame) -> Dict:
        """
        Get comprehensive metadata for a specific table.

        Args:
            table_name: The name of the table
            df: The DataFrame to analyze

        Returns:
            Dict: Metadata including shape, column types, and preview
        """
        metadata = {
            'table_name': table_name,
            'shape': df.shape,
            'row_count': df.shape[0],
            'column_count': df.shape[1],
            'columns': list(df.columns),
            'dtypes': df.dtypes.astype(str).to_dict(),
            'preview': df.head(10),
            'null_counts': df.isnull().sum().to_dict(),
            'memory_usage': df.memory_usage(deep=True).sum()
        }

        return metadata

    def get_data_type_distribution(self, data_dict: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        Analyze and return the distribution of data types across all tables.

        This method aggregates column data types from all uploaded DataFrames
        to provide a high-level view of the data ecosystem composition.

        Args:
            data_dict: Dictionary with table names as keys and DataFrames as values

        Returns:
            pd.DataFrame: DataFrame with columns 'data_type' and 'count'
        """
        type_counts = {}

        for table_name, df in data_dict.items():
            for col_name, dtype in df.dtypes.items():
                # Simplify dtype for grouping
                dtype_str = str(dtype)
                if 'int' in dtype_str:
                    simplified = 'INTEGER'
                elif 'float' in dtype_str:
                    simplified = 'FLOAT'
                elif 'object' in dtype_str:
                    simplified = 'STRING'
                elif 'datetime' in dtype_str:
                    simplified = 'DATETIME'
                elif 'bool' in dtype_str:
                    simplified = 'BOOLEAN'
                else:
                    simplified = 'OTHER'

                type_counts[simplified] = type_counts.get(simplified, 0) + 1

        # Convert to DataFrame
        result_df = pd.DataFrame([
            {'data_type': dtype, 'count': count}
            for dtype, count in type_counts.items()
        ])

        if not result_df.empty:
            result_df = result_df.sort_values('count', ascending=False).reset_index(drop=True)

        return result_df

    def get_null_statistics(self, data_dict: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        Calculate null/missing value statistics for each table.

        This method computes the percentage of null values per table
        to assess overall data health.

        Args:
            data_dict: Dictionary with table names as keys and DataFrames as values

        Returns:
            pd.DataFrame: DataFrame with columns 'table_name', 'total_cells',
                         'null_cells', 'null_percentage', 'health_status'
        """
        results = []

        for table_name, df in data_dict.items():
            total_cells = df.shape[0] * df.shape[1]
            null_cells = df.isnull().sum().sum()
            null_percentage = (null_cells / total_cells * 100) if total_cells > 0 else 0

            # Determine health status based on null percentage
            if null_percentage < 5:
                health_status = 'Good'
            elif null_percentage < 20:
                health_status = 'Needs Attention'
            else:
                health_status = 'Critical'

            results.append({
                'table_name': table_name,
                'total_cells': total_cells,
                'null_cells': null_cells,
                'null_percentage': round(null_percentage, 2),
                'health_status': health_status,
                'row_count': df.shape[0],
                'column_count': df.shape[1]
            })

        return pd.DataFrame(results)
