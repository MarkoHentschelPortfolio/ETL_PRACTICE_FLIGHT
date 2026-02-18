import sys
import os
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.extract import APIExtractor, save_raw_data
from src.transform import DataTransformer
from src.load import save_to_sqlite
from src.process import FlightAnalyticsProcessor
from config.config import DATA_CONFIGS
from datetime import datetime

# Load environment variables
load_dotenv()

# Setup class instances for each step of the ETL pipeline
extraction_date = (datetime.now()).strftime("%Y%m%d")
extractor = APIExtractor(
    base_url="https://api.aviationstack.com/v1",
    max_retries=1
)

processor = FlightAnalyticsProcessor(
    staging_db='data/staging/airtraffic.sqlite',
    analytics_db='data/processed/flights_analytics.sqlite'
)

#setup params for dimensions and facts - facts will need one key per day, dimensions can be used over multiple days without hitting API limits as they have fewer records
params_dim_data = {
    'access_key': os.getenv('AVIATION_API_KEY_DIM'),
}
    
params_fact_data = {
    'access_key': os.getenv('AVIATION_API_KEY_FACT'), #daily reset needed for flights data due to API limits
}

for source_name, config in DATA_CONFIGS.items():
    try:
        # EXTRACT

        params = params_fact_data if source_name in ['flights'] else params_dim_data
        
        # Use offset pagination for flights (API has 100-record limit per request)
        if source_name == 'flights':
            # Fetch up to 1000 flight records using offset pagination
            data = extractor.fetch_offset_paginated(
                endpoint=config['endpoint'],
                params=params,
                limit=100,  # API max per request
                max_records=10000  # Total records to fetch, api limit is 100 calls per month -> 10k records per api key -> 43 keys per day
            )
            # This line wraps the flights list in a dictionary with a 'data' key to match the expected format. Without it, the transformer would fail because it wouldn't find the 'data' key when processing the saved JSON file.
            data = {'data': data}
        else:
            # Single request for other endpoints
            params['limit'] = config['limit']
            data = extractor.fetch(config['endpoint'], params=params)
        
        save_raw_data(data, f"data/raw/{source_name}_{extraction_date}.json")
        
        # TRANSFORM - Clean and normalize data as preparation for loading and analytics
        transformer = DataTransformer(config=config)
        df = transformer.load_from_json(f"data/raw/{source_name}_{extraction_date}.json")
        df = transformer.transform(df)  # Runs full pipeline
        
        # Quality check
        report = transformer.get_quality_report(df)
        print(f"✓ {source_name}: {report['total_rows']} rows, {report['missing_values']} nulls")
        
        # LOAD -- with partitioned upsert for flights (much faster for large tables!)
        if source_name == 'flights':
            save_to_sqlite(df, config['db_path'], table_name=config['table_name'], 
                          upsert=True, partition_column='flight_date')
        else:
            save_to_sqlite(df, config['db_path'], table_name=config['table_name'], upsert=True)
        print(f"✓ Saved to {config['table_name']} table\n")
        
    except Exception as e:
        print(f"✗ Failed {source_name}: {e}")


# PROCESS - Generate analytics usecase from staged data with calculated metrics (e.g. flight distances, delays, etc.)
print("\n=== PROCESSING ANALYTICS ===")
try:
    df_analytics = processor.run()
    print(f"✓ Generated {len(df_analytics)} flight performance records\n")
except Exception as e:
    print(f"✗ Failed analytics processing: {e}\n")
