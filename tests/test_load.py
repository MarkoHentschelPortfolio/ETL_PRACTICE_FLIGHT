"""Tests for load module"""

import pytest
import pandas as pd
from src.load import save_to_sqlite, read_from_sqlite, get_table_info


def test_save_to_sqlite(sample_records, tmp_database):
    """Test saving DataFrame to SQLite"""
    df = pd.DataFrame(sample_records)
    save_to_sqlite(df, tmp_database, table_name='foods', if_exists='replace')
    
    # Verify table exists and has correct data
    df_read = read_from_sqlite(tmp_database, 'foods')
    assert len(df_read) == 3


def test_save_empty_dataframe_raises(tmp_database):
    """Test that saving empty DataFrame raises error"""
    df = pd.DataFrame()
    with pytest.raises(ValueError):
        save_to_sqlite(df, tmp_database, table_name='foods')


def test_read_from_sqlite(sample_records, tmp_database):
    """Test reading data from SQLite"""
    df = pd.DataFrame(sample_records)
    save_to_sqlite(df, tmp_database, table_name='foods', if_exists='replace')
    
    df_read = read_from_sqlite(tmp_database, 'foods')
    assert len(df_read) == 3
    assert 'name' in df_read.columns


def test_get_table_info(sample_records, tmp_database):
    """Test getting table information"""
    df = pd.DataFrame(sample_records)
    save_to_sqlite(df, tmp_database, table_name='foods', if_exists='replace')
    
    info = get_table_info(tmp_database, 'foods')
    assert info['table'] == 'foods'
    assert len(info['columns']) == 4
    assert 'name' in info['columns']
