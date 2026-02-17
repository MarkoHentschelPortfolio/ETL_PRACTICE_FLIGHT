"""Test configuration and fixtures"""

import sys
import os
import pytest
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.fixture
def sample_records():
    """Sample API response data"""
    return [
        {'id': 1, 'name': 'Apple', 'price': 1.20, 'category': 'Fruit'},
        {'id': 2, 'name': 'Banana', 'price': 0.50, 'category': 'Fruit'},
        {'id': 3, 'name': 'Carrot', 'price': 0.75, 'category': 'Vegetable'},
    ]


@pytest.fixture
def tmp_database(tmp_path):
    """Temporary SQLite database path"""
    return str(tmp_path / 'test.sqlite')


@pytest.fixture
def tmp_log_dir(tmp_path):
    """Temporary logs directory"""
    return str(tmp_path / 'logs')
