# ETL Practice Project

A Python-based ETL (Extract, Transform, Load) practice project for aviation data that demonstrates:
- Extracting data from REST APIs with pagination support
- Transforming data using pandas with advanced features (nested JSON normalization, hash-based deduplication, column filtering)
- Loading data to SQLite with multiple insert strategies (upsert, insert-new-only, append)
- Processing staged data into analytics-ready datasets with business logic (Haversine distance calculations, route aggregations)
- Processing multiple data sources with config-driven pipeline
- Class-based architecture for reusable, testable components
- Performance optimization for large-scale data (10K+ records)

## Project Structure

```
etl_practice/
├── src/                    # Source code (extract, transform, load, process)
│   ├── __init__.py
│   ├── config.py          # Data source configurations (fill maps, dtype maps, paths)
│   ├── extract.py         # API extraction functions
│   ├── transform.py       # Data transformation: handle_missing_values, apply_dtype_map, etc.
│   ├── load.py            # Load: save_to_sqlite, save_to_s3, read_from_s3
│   ├── process.py         # Analytics processing: FlightAnalyticsProcessor, haversine distance
│   ├── main.py            # Config-driven ETL + analytics pipeline
│   └── utils.py           # Utilities (logging, config, etc.)
├── data/
│   ├── raw/               # Raw API data (JSON files)
│   ├── processed/         # Analytics-ready data (flights_analytics.sqlite)
│   └── staging/           # Staging area (airtraffic.sqlite database)
├── config/                # Configuration files and templates
├── tests/                 # Unit tests
├── logs/                  # Application logs
├── scripts/               # Helper scripts
├── docs/                  # Documentation
├── .gitignore
├── README.md
├── requirements.txt
└── setup.py
```

## Quick Start

### Prerequisites
- Python 3.8+

### Installation

```bash
cd etl_practice

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Running the ETL Pipeline

```bash
python -m src.main
```

This executes the complete data pipeline:
1. **Extract**: Fetch data from aviationstack.com API
2. **Transform**: Clean, normalize, and deduplicate data
3. **Load**: Save to staging database with upsert logic
4. **Process**: Generate flight analytics with distance calculations

### Running Tests

```bash
pytest tests/ -v

# With coverage
pytest tests/ --cov=src --cov-report=html
```

## Configuration

1. Copy `config/config.yaml.example` to `config/config.yaml`
2. Update with your API endpoint, database settings, and AWS S3 credentials
3. Set environment variables for sensitive data (API keys, AWS credentials, database passwords)

## Project Features

### Extract
- **API Integration**: Fetch data from aviationstack.com REST API with error handling and retry logic
- **Pagination Support**: `fetch_offset_paginated()` handles API limits (100 records/request) by making multiple requests
- **Raw Data Storage**: Save API responses as JSON for data lineage and debugging

### Transform
- **Nested JSON Handling**: `pd.json_normalize()` flattens nested structures (e.g., `departure.iata` → `departure_iata`)
- **Hash-based Deduplication**: `add_metadata()` generates `meta_row_hash` for change detection
  - Excludes API surrogate keys (`id`) from hash to ensure consistency across extractions
  - Excludes metadata columns (`meta_load_date`, `meta_row_hash`) from hash calculation
- **Column Filtering**: `drop_columns()` removes unwanted fields using `exclude_cols` config pattern
- **Column Standardization**: `standardize_columns()` normalizes names (lowercase, dots/spaces → underscores)
- **Data Quality Reporting**: `get_quality_report()` provides row counts, null counts, and validation metrics

### Load - Multiple Insert Strategies
- **INSERT-NEW-ONLY** (default): Append-only approach, skips rows with existing hashes
  - Use for: Immutable data that never changes after initial insert
  - Performance: Fast (query existing hashes, filter, insert)
  - Example: Historical flight records, audit trails
  
- **UPSERT**: Delete matching rows, then insert (supports updates)
  - Use for: Mutable data that changes over time
  - Performance: Partitioned mode with hash matching for accuracy + speed
  - Example: Flight status updates (scheduled → active → landed)
  
- **APPEND**: Simple append without duplicate checking
  - Use for: When duplicates are acceptable or handled elsewhere
  - Performance: Fastest (no checks)

### Performance Optimizations
- **Partitioned Operations**: Filter by date/partition before hash matching (constant 0.5s vs 8+ min at 10M rows)
- **Batched Deletes**: Process in 999-row chunks to respect SQLite parameter limits
- **Indexes**: Automatic creation on `meta_row_hash` and partition columns for faster lookups

### Config-Driven Pipeline
- Centralized configurations in `config/config.py` per dataset
- `exclude_cols`: Pattern for filtering unwanted columns (timezones, live tracking data, etc.)
- `fill_map` and `dtype_map`: Column-specific transformations
- Supports both dimension (slowly changing) and fact (rapidly changing) data patterns

### Process - Analytics Generation
- **FlightAnalyticsProcessor**: Class-based analytics processing from staged data
- **Haversine Distance Calculation**: Vectorized calculation of straight-line distances between airports
  - Aggregates flight performance by route and date
  - Calculates total delay metrics and flight counts
  - Generates `straightline_distance_km` for each departure-arrival pair
- **Analytics Output**: `f_flight_performance` table in processed database
- **Class-Based Design**: Configurable database paths, reusable components, easy testing

## Example Usage

### Complete ETL Pipeline (Recommended)

```bash
python src/main.py
```

This processes all configured data sources:
- **airlines** (13,166 records) - dimension data
- **aircraft_types** (313 records) - dimension data  
- **airports** (6,685 records) - dimension data
- **airplanes** (19,095 records) - dimension data
- **flights** (10,000 records) - fact data with pagination
- **Analytics** - flight performance aggregated by route with distance calculations

### Using Individual Components

```python
from src.extract import APIExtractor
from src.transform import DataTransformer
from src.load import save_to_sqlite
from config.config import DATA_CONFIGS

# EXTRACT with pagination
extractor = APIExtractor(base_url="https://api.aviationstack.com/v1")
params = {'access_key': 'YOUR_KEY'}

# For large datasets - use offset pagination
flights_data = extractor.fetch_offset_paginated(
    endpoint='flights',
    params=params,
    limit=100,           # API max per request
    max_records=10000    # Total to fetch
)

# TRANSFORM
config = DATA_CONFIGS['flights']
transformer = DataTransformer(config=config)
df = transformer.load_from_json('data/raw/flights_20260212.json')
df = transformer.transform(df)  # Full pipeline: normalize → filter → hash → standardize

# LOAD - Choose your strategy
# Option 1: INSERT-NEW-ONLY (default, append-only)
save_to_sqlite(df, 'data/staging/airtraffic.sqlite', table_name='flights',
               partition_column='flight_date')  # Only inserts new hashes

# Option 2: UPSERT (for data that changes)
save_to_sqlite(df, 'data/staging/airtraffic.sqlite', table_name='flights',
               upsert=True, partition_column='flight_date')

# Option 3: APPEND (no duplicate checking)
save_to_sqlite(df, 'data/staging/airtraffic.sqlite', table_name='flights',
               if_exists='append')

# PROCESS - Generate analytics
from src.process import FlightAnalyticsProcessor

processor = FlightAnalyticsProcessor(
    staging_db='data/staging/airtraffic.sqlite',
    analytics_db='data/processed/flights_analytics.sqlite'
)
df_analytics = processor.run()
# Creates f_flight_performance table with route-level aggregations and distances
```

### Configuration Pattern

```python
# config/config.py
DATA_CONFIGS = {
    'flights': {
        'endpoint': 'flights',
        'limit': 100,
        'exclude_cols': [  # Columns to filter out
            'departure_timezone',
            'arrival_timezone', 
            'departure_runway',
            'arrival_runway',
            'live_updated_at',
            'codeshared_airline_name',
            # ... more unwanted columns
        ],
        'fill_map': {
            'flight_status': 'unknown',
            'departure_delay': 0,
        },
        'dtype_map': {
            'flight_date': 'string',
            'flight_status': 'string',
            'departure_delay': 'int',
        },
        'db_path': 'data/staging/airtraffic.sqlite',
        'table_name': 'flights'
    }
}
```

## Key Learnings & Design Decisions

### 1. Hash Calculation Strategy
**Problem**: Duplicate records appeared despite upsert logic because API surrogate keys (`id`) changed between extractions.

**Solution**: Exclude non-business columns from hash:
```python
df = self.add_metadata(df, exclude_cols=['id'])  # API's surrogate key
```

**Lesson**: Only include business-relevant columns in hash calculation. Exclude:
- API surrogate keys that change on every fetch
- Metadata columns (`meta_load_date`, `meta_row_hash`)
- System-generated timestamps

### 2. Nested JSON Handling
**Challenge**: Aviation API returns nested structures like:
```json
{
  "departure": {"iata": "JFK", "timezone": "America/New_York"},
  "arrival": {"iata": "LAX", "timezone": "America/Los_Angeles"}
}
```

**Solution**: `pd.json_normalize()` automatically flattens to:
```
departure_iata | departure_timezone | arrival_iata | arrival_timezone
JFK            | America/New_York   | LAX          | America/Los_Angeles
```

**Lesson**: pandas handles nested JSON elegantly - no custom parsing needed.

### 3. API Pagination
**Problem**: Aviation API limits responses to 100 records per request, but we need 10,000+ flights.

**Solution**: Implemented `fetch_offset_paginated()`:
```python
def fetch_offset_paginated(endpoint, params, limit=100, max_records=10000):
    all_data = []
    offset = 0
    while len(all_data) < max_records:
        params['offset'] = offset
        params['limit'] = limit
        response = fetch(endpoint, params)
        all_data.extend(response['data'])
        offset += limit
    return all_data
```

**Lesson**: Always check API documentation for pagination limits. Offset-based pagination is simple and reliable.

### 4. SQLite Parameter Limits
**Problem**: `sqlite3.ProgrammingError` when upserting 10,000 records - SQLite has a 999 parameter limit.

**Solution**: Batch DELETE operations:
```python
batch_size = 999
for i in range(0, len(hashes), batch_size):
    batch = hashes[i:i + batch_size]
    conn.execute(f'DELETE FROM table WHERE hash IN ({placeholders})', batch)
```

**Lesson**: SQLite's SQLITE_MAX_VARIABLE_NUMBER defaults to 999. Always batch large operations.

### 5. Scalability - Partitioned Operations
**Problem**: Hash-based upsert performance degrades with table size:
- 100K rows: 0.5s
- 1M rows: 30s
- 10M rows: 8+ minutes

**Solution**: Partition-first approach:
```python
# Instead of: DELETE WHERE hash IN (10000 hashes) -- scans entire table
# Use: DELETE WHERE flight_date IN ('2026-02-12') AND hash IN (10000 hashes)
```

**Performance**:
- Filters 10K rows (1 day) instead of 10M rows (entire table)
- Constant 0.5s regardless of total table size
- 96x faster at 10M row scale

**Lesson**: Always filter by partition/date before hash matching in large tables.

### 6. Timestamp Parameter Binding
**Problem**: `type 'Timestamp' is not supported` error when passing pandas Timestamp to SQLite.

**Solution**: Convert to strings before binding:
```python
partition_values = [str(v) if hasattr(v, 'isoformat') else v for v in partition_values]
```

**Lesson**: SQLite doesn't understand pandas Timestamp objects - convert to strings for parameter binding.

### 7. Insert Strategy Selection

| Strategy | Use Case | Performance | Updates Existing? |
|----------|----------|-------------|-------------------|
| **INSERT-NEW-ONLY** | Immutable data (historical records) | Fast (filter + insert) | No |
| **UPSERT** | Mutable data (status changes) | Medium (delete + insert) | Yes |
| **APPEND** | Audit trails, no deduplication | Fastest | N/A |

**Decision Tree**:
- Does the data change after initial load? → **UPSERT**
- Is it append-only/immutable? → **INSERT-NEW-ONLY**
- Are duplicates acceptable? → **APPEND**

**Lesson**: Choose the right strategy for your data mutability pattern to optimize performance.

### 8. Class-Based Architecture for Reusability

**Design Decision**: Refactored analytics processing from standalone functions to `FlightAnalyticsProcessor` class.

**Benefits**:
- **Consistency**: Matches existing patterns (`DataTransformer`, `APIExtractor`)
- **Configurability**: Database paths and table names as constructor parameters
- **Testability**: Easy to mock dependencies and unit test methods
- **Reusability**: Can instantiate multiple processors with different configurations
- **Maintainability**: Clear encapsulation of related functionality

**Pattern**:
```python
# Class-based approach (new)
processor = FlightAnalyticsProcessor(staging_db='...', analytics_db='...')
df = processor.run()

# vs Function-based approach (old)
df = load_flight_data('...')
df = process_flight_data(df)
save_analytics_data(df, '...')
```

**Lesson**: For multi-step pipelines with shared configuration, classes provide better organization and reusability than standalone functions.

## Data Pipeline Architecture

### Data Flow
```
1. EXTRACT → Raw JSON files (data/raw/)
   - API calls with pagination
   - One file per dataset per day
   
2. TRANSFORM → In-memory DataFrames
   - Normalize nested JSON structures
   - Filter unwanted columns
   - Standardize column names
   - Generate hash for deduplication
   
3. LOAD → SQLite database (data/staging/)
   - Insert-new-only (default)
   - Upsert with partitioning (optional)
   - Indexes on hash + partition columns
   
4. PROCESS → Analytics database (data/processed/)
   - Aggregate flight data by route and date
   - Calculate haversine distances between airports
   - Generate performance metrics (delays, flight counts)
   - Output to f_flight_performance table
```

### Current Data Volumes
- **airlines**: 13,166 records (dimension)
- **aircraft_types**: 313 records (dimension)
- **airports**: 6,685 records (dimension)
- **airplanes**: 19,095 records (dimension)
- **flights**: 10,000 records per run (fact data, 428,450 total available)
- **f_flight_performance**: 14,391 route aggregations (analytics output)

### API Integration
- **Provider**: aviationstack.com
- **Rate Limits**: 100 records per request, 100 requests per month per key
- **Strategy**: Use separate API keys for dimensions (low volume) vs facts (high volume)
- **Pagination**: Offset-based with automatic batching

## Transform Functions Reference

### add_metadata()
```python
# Generate hash for deduplication
df = add_metadata(df, exclude_cols=['id'])  # Exclude API surrogate keys
# Creates: meta_row_hash, meta_load_date
```

### drop_columns()
```python
# Filter unwanted columns using config
transformer = DataTransformer(config={
    'exclude_cols': ['departure_timezone', 'arrival_timezone', ...]
})
df = transformer.drop_columns(df)
```

### standardize_columns()
```python
# Normalize column names
df = standardize_columns(df)
# "Departure.IATA" → "departure_iata"
# "Flight Status" → "flight_status"
```

### handle_missing_values()
```python
# Fill with column-specific values
df = handle_missing_values(
	df, 
	strategy='fill_value',
	column_fill_map={'flight_status': 'unknown', 'delay': 0}
)
```

### apply_dtype_map()
```python
# Convert columns with intelligent coercion
df = apply_dtype_map(
	df,
	dtype_map={
		'flight_date': 'string',
		'departure_delay': 'int',
		'departure_scheduled': 'datetime',
	},
	errors='coerce',  # Convert invalid values to NA
	datetime_format_map={'departure_scheduled': '%Y-%m-%dT%H:%M:%S'}
)
```

## Process Functions Reference

### FlightAnalyticsProcessor

Class-based processor for generating flight analytics from staged data.

```python
from src.process import FlightAnalyticsProcessor

# Initialize with custom paths
processor = FlightAnalyticsProcessor(
    staging_db='data/staging/airtraffic.sqlite',
    analytics_db='data/processed/flights_analytics.sqlite',
    table_name='f_flight_performance'  # optional, defaults to f_flight_performance
)

# Run full analytics pipeline
df_analytics = processor.run()

# Or run individual steps
df = processor.load_flight_data()           # Load and aggregate from staging
df = processor.calculate_distances(df)      # Add haversine distances
processor.save_analytics(df)                # Save to analytics database
```

**Methods:**
- `load_flight_data()`: Aggregates flights by route and date with delay metrics
- `calculate_distances(df)`: Adds straight-line distance using Haversine formula
- `save_analytics(df)`: Saves processed data to analytics database
- `run()`: Executes full pipeline (load → calculate → save)

### Haversine Distance Calculation

Vectorized calculation of great-circle distance between two coordinate pairs.

```python
# Haversine formula implementation (vectorized for pandas)
distance_km = FlightAnalyticsProcessor.haversine_vectorize(
    lon1=df['dep_long'],    # Departure longitude
    lat1=df['dep_lat'],     # Departure latitude
    lon2=df['arr_long'],    # Arrival longitude
    lat2=df['arr_lat']      # Arrival latitude
)
# Returns: Series of distances in kilometers
```

**Formula**: Calculates straight-line distance on Earth's surface
- Converts coordinates to radians
- Uses Earth's radius: 6,371 km
- Returns: Distance in kilometers
- Use case: Route distance for performance analysis

**Analytics Output Schema:**
```
flight_date                 | Date of flights
departure_airport           | Departure airport name
arrival_airport            | Arrival airport name
total_delay_minutes        | Sum of arrival + departure delays
flights_count              | Number of flights on this route
straightline_distance_km   | Great-circle distance between airports
```

## Best Practices

### ETL Design
- **Idempotent Pipelines**: Use hash-based deduplication so re-running doesn't create duplicates
- **Partition Large Tables**: Filter by date/partition before hash operations for constant-time performance
- **Exclude System Columns from Hash**: Don't hash API surrogate keys, timestamps, or metadata
- **Batch Large Operations**: Respect SQLite's 999 parameter limit with batched deletes

### Data Quality
- Always validate null counts and row counts after transformation
- Use `get_quality_report()` to monitor data quality metrics
- Log all operations for debugging and audit trails
- Store raw JSON files for data lineage and reprocessing

### API Integration
- Check documentation for pagination limits and implement accordingly
- Use separate API keys for different data tiers (dimension vs fact)
- Implement retry logic for transient failures
- Save raw responses before transformation

### Performance
- Create indexes on hash columns and partition columns
- Use partitioned operations for tables > 1M rows
- Choose insert strategy based on data mutability:
  - Immutable data → INSERT-NEW-ONLY
  - Mutable data → UPSERT with partitioning
- Monitor performance as data grows and adjust partitioning strategy

### Configuration
- Centralize all dataset configs in `config/config.py`
- Use `exclude_cols` pattern for filtering unwanted columns
- Define `fill_map` and `dtype_map` per dataset
- Keep sensitive credentials in environment variables (not in config files)

### Development Workflow
- Always work within the virtual environment
- Run tests before committing changes (`pytest tests/ -v`)
- Use `.env` for local development (not committed to git)
- Keep raw data files out of version control (.gitignore)

## Troubleshooting

### Common Issues

**"Execution failed... type 'Timestamp' is not supported"**
- SQLite can't bind pandas Timestamp objects
- Solution: Convert to strings before parameter binding
```python
values = [str(v) if hasattr(v, 'isoformat') else v for v in values]
```

**"sqlite3.ProgrammingError: too many SQL variables"**
- SQLite has 999 parameter limit
- Solution: Batch operations into chunks of 999
```python
for i in range(0, len(items), 999):
    batch = items[i:i + 999]
    conn.execute(sql, batch)
```

**Slow upsert performance**
- Hash-only upsert scans entire table
- Solution: Add partition_column for date-based filtering
```python
save_to_sqlite(df, path, table, upsert=True, partition_column='flight_date')
```

**Duplicate records after upsert**
- API surrogate keys in hash calculation
- Solution: Exclude changing columns from hash
```python
df = add_metadata(df, exclude_cols=['id', 'updated_at'])
```

## License

MIT License
