"""Process module: Process staged data with business logic and transformations"""

import logging
import numpy as np
import pandas as pd
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Constants
EARTH_RADIUS_KM = 6371


class FlightAnalyticsProcessor:
    """Process flight data to create analytics-ready datasets."""
    
    def __init__(
        self,
        staging_db: str = 'data/staging/airtraffic.sqlite',
        analytics_db: str = 'data/processed/flights_analytics.sqlite',
        table_name: str = 'f_flight_performance'
    ):
        """
        Initialize the flight analytics processor.
        
        Args:
            staging_db: Path to staging SQLite database
            analytics_db: Path to analytics output database
            table_name: Name of output table
        """
        self.staging_db = staging_db
        self.analytics_db = analytics_db
        self.table_name = table_name
        logger.info(f"FlightAnalyticsProcessor initialized: {staging_db} → {analytics_db}")
    
    @staticmethod
    def haversine_vectorize(
        lon1: pd.Series, 
        lat1: pd.Series, 
        lon2: pd.Series, 
        lat2: pd.Series
    ) -> pd.Series:
        """
        Calculate straight-line distance between two lat/long points using Haversine formula.
        
        Args:
            lon1: Longitude of first point (degrees)
            lat1: Latitude of first point (degrees)
            lon2: Longitude of second point (degrees)
            lat2: Latitude of second point (degrees)
            
        Returns:
            Distance in kilometers
        """
        # Convert decimal degrees to radians and apply Haversine formula
        lon1, lat1, lon2, lat2 = map(np.radians, [lon1, lat1, lon2, lat2]) # type: ignore
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = np.sin(dlat/2.0)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2.0)**2
        c = 2 * np.arcsin(np.sqrt(a))
        return c * EARTH_RADIUS_KM # type: ignore
    
    def load_flight_data(self) -> pd.DataFrame:
        """
        Load and aggregate flight data from staging database.
        
        Returns:
            DataFrame with aggregated flight performance data
            
        Raises:
            sqlite3.Error: If database query fails
            ValueError: If no data is returned
        """
        query = '''
            SELECT 
                flight_date
                , ad.airport_name AS departure_airport
                , aa.airport_name AS arrival_airport
                , ad.longitude AS dep_long
                , ad.latitude AS dep_lat
                , aa.longitude AS arr_long
                , aa.latitude AS arr_lat
                , SUM(arrival_delay) + SUM(departure_delay) AS total_delay_minutes 
                , COUNT(*) AS flights_count
            FROM flights f
            LEFT JOIN airports ad 
                ON f.departure_iata = ad.iata_code 
            LEFT JOIN airports aa
                ON f.arrival_iata = aa.iata_code 
            WHERE 
                ad.airport_name IS NOT NULL 
                AND aa.airport_name IS NOT NULL
            GROUP BY 1, 2, 3
        '''
        
        logger.info(f"Loading flight data from {self.staging_db}")
        
        with sqlite3.connect(self.staging_db) as conn:
            df = pd.read_sql_query(query, conn)
        
        if df.empty:
            raise ValueError("No flight data returned from query")
        
        logger.info(f"Loaded {len(df)} flight route records")
        return df
    
    def calculate_distances(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate straight-line distances and clean up dataframe.
        
        Args:
            df: DataFrame with flight data including coordinates
            
        Returns:
            Processed DataFrame with distance calculations
        """
        logger.info("Calculating straight-line distances")
        
        df = df.copy()
        
        # Calculate distances between departure and arrival airports
        df['straightline_distance_km'] = self.haversine_vectorize(
            df['dep_long'], df['dep_lat'],
            df['arr_long'], df['arr_lat']
        )
        
        # Drop coordinate columns (no longer needed)
        df = df.drop(columns=['dep_long', 'dep_lat', 'arr_long', 'arr_lat'])
        
        logger.info(f"Processed {len(df)} records")
        return df
    
    def save_analytics(self, df: pd.DataFrame) -> None:
        """
        Save processed flight analytics to database.
        
        Args:
            df: Processed DataFrame to save
            
        Raises:
            sqlite3.Error: If database write fails
        """
        # Ensure output directory exists
        Path(self.analytics_db).parent.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Saving {len(df)} records to {self.analytics_db} table '{self.table_name}'")
        
        with sqlite3.connect(self.analytics_db) as conn:
            df.to_sql(self.table_name, conn, if_exists='replace', index=False)
        
        logger.info(f"Successfully saved analytics data")
    
    def run(self) -> pd.DataFrame:
        """
        Execute the full analytics processing pipeline.
        
        Returns:
            Processed DataFrame
            
        Raises:
            Exception: If any step in the pipeline fails
        """
        try:
            # Load data from staging
            df = self.load_flight_data()
            
            # Calculate metrics
            df = self.calculate_distances(df)
            
            # Save to analytics database
            self.save_analytics(df)
            
            logger.info("Flight analytics processing completed successfully")
            return df
            
        except Exception as e:
            logger.error(f"Failed to process flight analytics: {e}", exc_info=True)
            raise