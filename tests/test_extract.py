"""Tests for extract module"""

import pytest
from src.extract import fetch_api_data
import json
from pathlib import Path


def test_list_to_dataframe_basic(sample_records):
    """Test converting list of dicts to DataFrame"""
    import pandas as pd
    df = pd.DataFrame(sample_records)
    assert len(df) == 3
    assert list(df.columns) == ['id', 'name', 'price', 'category']


def test_fetch_api_data_exists():
    """Test that fetch_api_data function exists and is callable"""
    assert callable(fetch_api_data)


def test_save_raw_data(sample_records, tmp_path):
    """Test saving raw data to JSON file"""
    from src.extract import save_raw_data
    
    filepath = tmp_path / 'test_data.json'
    save_raw_data(sample_records, str(filepath))
    
    assert filepath.exists()
    with open(filepath) as f:
        data = json.load(f)
    assert len(data) == 3
