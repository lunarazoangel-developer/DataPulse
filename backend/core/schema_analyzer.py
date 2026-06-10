from typing import Dict, List
import polars as pl


class SchemaAnalyzer:
    RELATIONAL_KEYWORDS = [
        'id', 'key', 'code', 'customer_id', 'user_id', 'order_id',
        'product_id', 'category_id', 'country_id', 'city_id',
        'employee_id', 'supplier_id', 'inventory_id', 'transaction_id',
        'invoice_id', 'payment_id', 'shipment_id', 'address_id',
        'region_id', 'department_id', 'manager_id', 'parent_id'
    ]

    def __init__(self):
        self.column_index: Dict[str, set] = {}
        self.data_dict: Dict[str, pl.DataFrame] = {}

    def scan_columns(self, data_dict: Dict[str, pl.DataFrame]) -> Dict[str, set]:
        self.data_dict = data_dict
        self.column_index = {}

        for table_name, df in data_dict.items():
            columns = set(col.lower() for col in df.columns)

            for col in columns:
                if col not in self.column_index:
                    self.column_index[col] = set()
                self.column_index[col].add(table_name)

        return self.column_index

    def _is_relational_column(self, column_name: str) -> bool:
        col_lower = column_name.lower()

        for keyword in self.RELATIONAL_KEYWORDS:
            if keyword in col_lower:
                return True

        return False

    def detect_relationships(self, data_dict: Dict[str, pl.DataFrame]) -> List[Dict]:
        self.scan_columns(data_dict)

        relationships = []

        for column_name, tables in self.column_index.items():
            if len(tables) >= 2:
                is_relational = self._is_relational_column(column_name)

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
        if not self.data_dict or len(self.data_dict) == 0:
            return "erDiagram\n    EMPTY"

        table_definitions = []
        table_relationships = []
        processed_rels = set()

        for table_name, df in self.data_dict.items():
            safe_table_name = self._sanitize_name(table_name)

            columns = []
            schema = df.schema
            for col in df.columns:
                col_type = str(schema[col])
                col_type_lower = col_type.lower()
                col_lower = col.lower()
                if 'int' in col_type_lower:
                    col_type = 'INT'
                elif 'float' in col_type_lower:
                    col_type = 'FLOAT'
                elif 'bool' in col_type_lower:
                    col_type = 'BOOLEAN'
                elif 'datetime' in col_type_lower or 'date' in col_type_lower or 'date' in col_lower or ('time' in col_lower and 'dwell' not in col_lower):
                    col_type = 'DATETIME'
                elif 'utf8' in col_type_lower or 'str' in col_type_lower:
                    col_type = 'VARCHAR'
                else:
                    col_type = 'TYPE'

                columns.append(f"    {col} {col_type}")

            if columns:
                table_def = f'    {safe_table_name} {{\n{"".join(columns)}\n    }}'
            else:
                table_def = f'    {safe_table_name}'
            table_definitions.append(table_def)

        for rel in relationships:
            source = self._sanitize_name(rel['source'])
            target = self._sanitize_name(rel['target'])

            rel_key = tuple(sorted([source, target]))
            if rel_key in processed_rels:
                continue
            processed_rels.add(rel_key)

            rel_line = f'    {source} ||--||{target} : "{rel["column"]}"'
            table_relationships.append(rel_line)

        mermaid_lines = ["erDiagram"]

        for definition in table_definitions:
            mermaid_lines.append(definition)

        for rel_line in table_relationships:
            mermaid_lines.append(rel_line)

        return "\n".join(mermaid_lines)

    def _sanitize_name(self, name: str) -> str:
        safe = name.replace(' ', '_').replace('-', '_').replace('.', '_')
        safe = ''.join(c if c.isalnum() or c == '_' else '_' for c in safe)
        if safe and safe[0].isdigit():
            safe = 'T_' + safe
        return safe

    def get_table_metadata(self, table_name: str, df: pl.DataFrame) -> Dict:
        metadata = {
            'table_name': table_name,
            'shape': (df.height, df.width),
            'row_count': df.height,
            'column_count': df.width,
            'columns': df.columns,
            'dtypes': {col: str(df[col].dtype) for col in df.columns},
            'preview': df.head(10).to_dicts(),
            'null_counts': {col: df[col].null_count() for col in df.columns},
            'memory_usage': df.estimated_size()
        }

        return metadata

    def get_data_type_distribution(self, data_dict: Dict[str, pl.DataFrame]) -> Dict:
        type_counts = {}

        for table_name, df in data_dict.items():
            for col_name, dtype in zip(df.columns, df.dtypes):
                dtype_str = str(dtype)
                if 'int' in dtype_str:
                    simplified = 'INTEGER'
                elif 'float' in dtype_str:
                    simplified = 'FLOAT'
                elif 'str' in dtype_str:
                    simplified = 'STRING'
                elif 'datetime' in dtype_str:
                    simplified = 'DATETIME'
                elif 'bool' in dtype_str:
                    simplified = 'BOOLEAN'
                else:
                    simplified = 'OTHER'

                type_counts[simplified] = type_counts.get(simplified, 0) + 1

        result = [
            {'data_type': dtype, 'count': count}
            for dtype, count in type_counts.items()
        ]

        result.sort(key=lambda x: x['count'], reverse=True)

        return result

    def get_null_statistics(self, data_dict: Dict[str, pl.DataFrame]) -> List[Dict]:
        results = []

        for table_name, df in data_dict.items():
            total_cells = df.height * df.width
            null_cells = sum(df[col].null_count() for col in df.columns)
            null_percentage = (null_cells / total_cells * 100) if total_cells > 0 else 0

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
                'row_count': df.height,
                'column_count': df.width
            })

        return results
