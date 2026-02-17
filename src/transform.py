"""Transform module: Clean and normalize data using pandas"""

import json
import logging
import pandas as pd
import hashlib
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime


logger = logging.getLogger(__name__)


class DataTransformer:
    """Handle data transformations with configurable settings."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize transformer with optional config.
        
        Args:
            config: Configuration dict with fill_map, dtype_map, etc.
        """
        self.config = config or {}
        self.fill_map = self.config.get('fill_map', {})
        self.dtype_map = self.config.get('dtype_map', {})
        self.exclude_cols = self.config.get('exclude_cols', [])
        logger.info(f"DataTransformer initialized with config keys: {list(self.config.keys())}")
    
    def load_from_json(self, filepath: str) -> pd.DataFrame:
        """Load data from JSON file, handling nested structures."""
        try:
            with open(filepath, 'r') as f:
                content = json.load(f)
            
            # Unwrap metadata wrapper if exists
            if isinstance(content, dict) and 'data' in content:
                data = content['data']
            else:
                data = content
            
            # Handle API response format
            if isinstance(data, dict):
                # If it's a dict with 'data' key (common API format)
                if 'data' in data:
                    data = data['data']
                # If it's a single record, wrap in list
                elif not any(isinstance(v, list) for v in data.values()):
                    data = [data]
            
            # Convert to DataFrame
            if isinstance(data, list):
                df = pd.json_normalize(data)  # Handles nested dicts
            else:
                df = pd.DataFrame([data])
            
            logger.info(f"Loaded {len(df)} records from {filepath}")
            return df
            
        except Exception as e:
            logger.error(f"Failed to load {filepath}: {e}")
            raise
    
    def standardize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardize column names."""
        df = df.copy()
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_').str.replace('-', '_').str.replace('.', '_')
        logger.info(f"Standardized columns: {list(df.columns)}")
        return df
    
    def drop_columns(self, df: pd.DataFrame, columns: Optional[List[str]] = None) -> pd.DataFrame:
        """Drop specified columns from DataFrame."""
        df = df.copy()
        columns = columns or self.exclude_cols
        
        if columns:
            # Only drop columns that actually exist
            cols_to_drop = [c for c in columns if c in df.columns]
            if cols_to_drop:
                df = df.drop(columns=cols_to_drop)
                logger.info(f"Dropped {len(cols_to_drop)} columns: {cols_to_drop}")
        
        return df
    
    def remove_duplicates(self, df: pd.DataFrame, subset: Optional[List[str]] = None, keep: str = 'first') -> pd.DataFrame:
        """Remove duplicate rows."""
        df = df.copy()
        before = len(df)
        df = df.drop_duplicates(subset=subset, keep=keep) # type: ignore
        logger.info(f"Removed {before - len(df)} duplicates")
        return df
    
    def handle_missing_values(self, df: pd.DataFrame, strategy: str = 'fill_value') -> pd.DataFrame:
        """Handle missing values using config fill_map."""
        df = df.copy()
        before = int(df.isnull().sum().sum())
        
        if strategy == 'drop':
            df = df.dropna()
        elif strategy == 'fill_value' and self.fill_map:
            valid_map = {col: val for col, val in self.fill_map.items() if col in df.columns}
            df = df.fillna(value=valid_map)
        
        after = int(df.isnull().sum().sum())
        logger.info(f"Handled missing: {before} → {after} nulls")
        return df
    
    def apply_dtypes(self, df: pd.DataFrame, errors: str = 'coerce') -> pd.DataFrame:
        """Apply dtype conversions using config dtype_map."""
        df = df.copy()
        
        for col, target in self.dtype_map.items():
            if col not in df.columns:
                continue
            
            try:
                t = str(target).lower()
                
                if t in ('int', 'int64', 'integer'):
                    df[col] = pd.to_numeric(df[col], errors=errors).astype('Int64') # pyright: ignore[reportCallIssue, reportArgumentType]
                elif t in ('float', 'float64'):
                    df[col] = pd.to_numeric(df[col], errors=errors).astype('Float64') # pyright: ignore[reportCallIssue, reportArgumentType]
                elif 'datetime' in t or t in ('date', 'timestamp'):
                    # Try common date formats first, then fall back to auto-detection
                    df[col] = pd.to_datetime(
                        df[col], 
                        errors=errors, # type: ignore
                        format='mixed',  # Handles multiple formats automatically
                        utc=False
                    ) # pyright: ignore[reportCallIssue]
                elif t in ('string', 'str'):
                    df[col] = df[col].astype('string')
                else:
                    df[col] = df[col].astype(target)
                
                logger.info(f"Converted {col} to {target}")
            except Exception as e:
                logger.warning(f"Failed to convert {col} to {target}: {e}")
        
        return df
    
    def add_metadata(
        self, 
        df: pd.DataFrame, 
        exclude_cols: Optional[List[str]] = None,
        hash_algorithm: str = 'sha256'
    ) -> pd.DataFrame:
        """
        Add metadata columns: meta_load_date and meta_row_hash.
        
        Args:
            df: Input DataFrame
            exclude_cols: Columns to exclude from hash calculation (e.g., timestamps)
            hash_algorithm: Hash algorithm to use ('md5', 'sha256', 'sha1')
            
        Returns:
            DataFrame with metadata columns
        """
        df = df.copy()
        
        # Add load timestamp
        df['meta_load_date'] = datetime.now()
        
        # Determine columns to hash
        exclude_cols = exclude_cols or []
        hash_cols = [c for c in df.columns if c not in exclude_cols and not c.startswith('meta_')]
        
        # Generate row hash
        def generate_row_hash(row, algorithm='sha256'):
            """Generate deterministic hash for a row."""
            # Convert row to string, handling nulls and converting to string
            row_string = '|'.join([
                str(val) if pd.notna(val) else 'NULL' 
                for val in row[hash_cols]
            ])
            
            # Create hash
            if algorithm == 'md5':
                hash_obj = hashlib.md5(row_string.encode('utf-8'))
            elif algorithm == 'sha1':
                hash_obj = hashlib.sha1(row_string.encode('utf-8'))
            else:  # default sha256
                hash_obj = hashlib.sha256(row_string.encode('utf-8'))
            
            return hash_obj.hexdigest()
        
        df['meta_row_hash'] = df.apply(
            lambda row: generate_row_hash(row, hash_algorithm), 
            axis=1
        )
        
        logger.info(f"Added metadata: meta_load_date and meta_row_hash (algorithm: {hash_algorithm})")
        return df
    
    def transform(self, df: pd.DataFrame, add_metadata: bool = True) -> pd.DataFrame:
        """
        Run full transformation pipeline.
        
        Args:
            df: Input DataFrame
            add_metadata: Whether to add metadata columns (default: True)
            
        Returns:
            Transformed DataFrame
        """
        df = self.standardize_columns(df)
        df = self.drop_columns(df)  # Drop excluded columns early
        df = self.remove_duplicates(df)
        df = self.handle_missing_values(df)
        df = self.apply_dtypes(df)
        
        if add_metadata:
            # Exclude 'id' column (surrogate key that changes per extraction)
            # from hash calculation to enable proper duplicate detection
            df = self.add_metadata(df, exclude_cols=['id'])
        
        logger.info(f"Transformation complete: {len(df)} rows")
        return df
    
    def get_quality_report(self, df: pd.DataFrame) -> dict:
        """Generate data quality report."""
        return {
            'total_rows': len(df),
            'total_columns': len(df.columns),
            'duplicates': df.duplicated().sum(),
            'missing_values': df.isnull().sum().sum(),
            'missing_percentage': (df.isnull().sum().sum() / (len(df) * len(df.columns)) * 100) if len(df) > 0 else 0,
            'columns': list(df.columns),
            'dtypes': df.dtypes.to_dict(),
        }

