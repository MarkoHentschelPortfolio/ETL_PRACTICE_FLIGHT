"""Tests for transform module"""

import pytest
import pandas as pd
from src.transform import (
    list_to_dataframe, standardize_columns, remove_duplicates, 
    handle_missing_values, get_data_quality_report
)


def test_list_to_dataframe(sample_records):
    """Test converting list to DataFrame"""
    df = list_to_dataframe(sample_records)
    assert len(df) == 3
    assert 'name' in df.columns


def test_standardize_columns():
    """Test column name standardization"""
    df = pd.DataFrame({
        'Product Name': [1, 2],
        'Unit Price': [1.5, 2.0],
        'Category-Type': ['A', 'B']
    })
    df_std = standardize_columns(df)
    assert 'product_name' in df_std.columns
    assert 'unit_price' in df_std.columns
    assert 'category_type' in df_std.columns


def test_remove_duplicates():
    """Test removing duplicate rows"""
    df = pd.DataFrame({
        'id': [1, 2, 2, 3],
        'name': ['A', 'B', 'B', 'C']
    })
    df_clean = remove_duplicates(df)
    assert len(df_clean) == 3


def test_handle_missing_values():
    """Test handling missing values"""
    df = pd.DataFrame({
        'id': [1, 2, 3],
        'value': [1.0, None, 3.0]
    })
    df_clean = handle_missing_values(df, strategy='drop')
    assert len(df_clean) == 2


def test_get_data_quality_report(sample_records):
    """Test data quality report generation"""
    df = list_to_dataframe(sample_records)
    report = get_data_quality_report(df)
    
    assert report['total_rows'] == 3
    assert report['total_columns'] == 4
    assert report['duplicates'] == 0
    assert 'id' in report['columns']
