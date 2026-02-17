"""Tests for utilities"""

import pytest
from src.utils import validate_dataframe, load_env_config
import pandas as pd


def test_validate_dataframe_valid(sample_records):
    """Test DataFrame validation with valid data"""
    df = pd.DataFrame(sample_records)
    assert validate_dataframe(df)


def test_validate_dataframe_empty():
    """Test DataFrame validation with empty DataFrame"""
    df = pd.DataFrame()
    assert not validate_dataframe(df)


def test_validate_dataframe_with_required_columns(sample_records):
    """Test DataFrame validation with required columns"""
    df = pd.DataFrame(sample_records)
    assert validate_dataframe(df, required_columns=['id', 'name'])


def test_validate_dataframe_missing_columns(sample_records):
    """Test DataFrame validation with missing columns"""
    df = pd.DataFrame(sample_records)
    assert not validate_dataframe(df, required_columns=['missing_col'])


def test_load_env_config():
    """Test environment config loading"""
    config = load_env_config()
    assert 'api_base_url' in config
    assert 'database_path' in config
    assert 'log_level' in config
