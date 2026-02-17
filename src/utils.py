"""Utilities: Logging, config, and helper functions"""

import logging
import logging.handlers
from pathlib import Path
from datetime import datetime
from typing import Optional
import os
from dotenv import load_dotenv


def setup_logging(log_dir: str = 'logs', log_level: str = 'INFO') -> None:
    """
    Configure logging for the application.
    
    Args:
        log_dir: Directory to store log files
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Create logs directory
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    
    # Log file path
    log_file = Path(log_dir) / f"etl_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10*1024*1024, backupCount=5  # 10MB per file, keep 5 backups
    )
    file_handler.setFormatter(formatter)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    root_logger.info("Logging initialized")


def load_env_config() -> dict:
    """
    Load configuration from environment variables.
    
    Returns:
        Dictionary of environment configuration
    """
    load_dotenv(dotenv_path='config/.env')
    
    config = {
        'api_base_url': os.getenv('API_BASE_URL', 'https://api.example.com'),
        'api_endpoint': os.getenv('API_ENDPOINT', '/foods'),
        'api_timeout': int(os.getenv('API_TIMEOUT', '30')),
        'database_path': os.getenv('DATABASE_PATH', 'db/food_data.sqlite'),
        'log_level': os.getenv('LOG_LEVEL', 'INFO'),
    }
    
    return config


def validate_dataframe(df, required_columns: Optional[list] = None) -> bool:
    """
    Validate a DataFrame has required properties.
    
    Args:
        df: DataFrame to validate
        required_columns: List of required column names
        
    Returns:
        True if valid, False otherwise
    """
    if df is None or df.empty:
        logging.error("DataFrame is None or empty")
        return False
    
    if required_columns:
        missing = set(required_columns) - set(df.columns)
        if missing:
            logging.error(f"Missing required columns: {missing}")
            return False
    
    return True
