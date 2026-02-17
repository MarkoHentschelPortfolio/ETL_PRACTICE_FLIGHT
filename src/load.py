"""Load module: Save data to AWS S3 bucket"""

import logging
import pandas as pd
import boto3
from typing import Optional
from botocore.exceptions import ClientError
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def save_to_sqlite(
    df: pd.DataFrame, 
    database_path: str, 
    table_name: str, 
    if_exists: str = 'replace',
    upsert: bool = False,
    partition_column: Optional[str] = None,
    insert_new_only: bool = True
) -> None:
    """
    Save a pandas DataFrame into a local SQLite database table.

    Args:
        df: DataFrame to save
        database_path: Filesystem path to the SQLite database file
        table_name: Table name to write the data into
        if_exists: Behavior when the table exists: 'replace', 'append', or 'fail'
        upsert: If True, update existing rows based on meta_row_hash, insert new ones
        partition_column: Column to use for partitioning (e.g., 'flight_date') - only deletes within partition values
        insert_new_only: If True, only insert rows with hashes not in database (no updates, append-only)

    Raises:
        ValueError: If DataFrame is empty or meta_row_hash missing for upsert
        Exception: If the write operation fails
    """
    if df.empty:
        raise ValueError("Cannot save empty DataFrame")
    
    if (upsert or insert_new_only) and 'meta_row_hash' not in df.columns:
        raise ValueError("Upsert/insert_new_only requires 'meta_row_hash' column in DataFrame")

    try:
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(database_path)
        
        try:
            if insert_new_only:
                # INSERT NEW ONLY: Skip rows with existing hashes (append-only, no updates)
                df.head(0).to_sql(table_name, conn, if_exists='append', index=False)
                conn.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS idx_hash_{table_name} ON "{table_name}"(meta_row_hash)')
                
                # Get existing hashes from database (only need to check within partition if specified)
                if partition_column and partition_column in df.columns:
                    partition_values = df[partition_column].unique().tolist()
                    # Convert to strings if Timestamp objects (SQLite can't bind Timestamp)
                    partition_values = [str(v) if hasattr(v, 'isoformat') else v for v in partition_values]
                    placeholders = ','.join(['?' for _ in partition_values])
                    existing_hashes = pd.read_sql_query(
                        f'SELECT meta_row_hash FROM "{table_name}" WHERE {partition_column} IN ({placeholders})',
                        conn,
                        params=partition_values
                    )['meta_row_hash'].tolist()
                    logger.info(f"Found {len(existing_hashes)} existing hashes in partitions {partition_values[:5]}")
                else:
                    existing_hashes = pd.read_sql_query(
                        f'SELECT meta_row_hash FROM "{table_name}"',
                        conn
                    )['meta_row_hash'].tolist()
                    logger.info(f"Found {len(existing_hashes)} existing hashes in table")
                
                # Filter out rows that already exist
                df_new = df[~df['meta_row_hash'].isin(existing_hashes)]
                
                if len(df_new) == 0:
                    logger.info("No new rows to insert (all hashes already exist)")
                else:
                    # Insert only new rows
                    df_new.to_sql(table_name, conn, if_exists='append', index=False)
                    logger.info(f"Inserted {len(df_new)} new rows (skipped {len(df) - len(df_new)} existing)")
                
            elif upsert:
                # Create table with unique constraint on hash
                df.head(0).to_sql(table_name, conn, if_exists='append', index=False)
                conn.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS idx_hash_{table_name} ON "{table_name}"(meta_row_hash)')
                
                # Create index on partition column for faster deletes
                if partition_column and partition_column in df.columns:
                    conn.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_{partition_column} ON "{table_name}"({partition_column})')
                
                deleted_count = 0
                
                # PARTITIONED UPSERT: Only delete rows matching partition values (much faster!)
                if partition_column and partition_column in df.columns:
                    # Get unique partition values from incoming data
                    partition_values = df[partition_column].unique().tolist()
                    # Convert to strings if Timestamp objects (SQLite can't bind Timestamp)
                    partition_values = [str(v) if hasattr(v, 'isoformat') else v for v in partition_values]
                    
                    # HYBRID APPROACH: Delete rows within partition that match hashes
                    # This gives us speed of partitioning + accuracy of hash matching
                    hashes = df['meta_row_hash'].tolist()
                    batch_size = 999
                    
                    # First, narrow down by partition
                    partition_placeholders = ','.join(['?' for _ in partition_values[:999]])
                    
                    # Then delete by hash within those partitions
                    for i in range(0, len(hashes), batch_size):
                        hash_batch = hashes[i:i + batch_size]
                        hash_placeholders = ','.join(['?' for _ in hash_batch])
                        
                        # Delete rows that match BOTH partition AND hash
                        cursor = conn.execute(
                            f'DELETE FROM "{table_name}" WHERE {partition_column} IN ({partition_placeholders}) '
                            f'AND meta_row_hash IN ({hash_placeholders})',
                            partition_values[:999] + hash_batch
                        )
                        deleted_count += cursor.rowcount
                    
                    logger.info(f"Deleted {deleted_count} existing rows in partitions {partition_values[:5]}{'...' if len(partition_values) > 5 else ''} (hash-matched)")
                
                else:
                    # FULL UPSERT: Delete by hash (slower for large tables)
                    hashes = df['meta_row_hash'].tolist()
                    batch_size = 999
                    
                    for i in range(0, len(hashes), batch_size):
                        batch = hashes[i:i + batch_size]
                        placeholders = ','.join(['?' for _ in batch])
                        cursor = conn.execute(f'DELETE FROM "{table_name}" WHERE meta_row_hash IN ({placeholders})', batch)
                        deleted_count += cursor.rowcount
                    
                    if deleted_count > 0:
                        logger.info(f"Deleted {deleted_count} existing rows by hash")
                
                # Insert all rows
                df.to_sql(table_name, conn, if_exists='append', index=False)
                
                logger.info(f"Upserted {len(df)} rows to sqlite:///{database_path} table {table_name}")
            else:
                df.to_sql(table_name, conn, if_exists=if_exists, index=False) # type: ignore
                logger.info(f"Saved {len(df)} rows to sqlite:///{database_path} table {table_name} (if_exists={if_exists})")
        finally:
            conn.close()

    except Exception as e:
        logger.error(f"Failed to save DataFrame to SQLite {database_path} table {table_name}: {e}")
        raise


def save_to_s3(df: pd.DataFrame, bucket_name: str, key: str, 
               file_format: str = 'csv', region_name: Optional[str] = None) -> None:
    """
    Save DataFrame to AWS S3 bucket.
    
    Args:
        df: DataFrame to save
        bucket_name: S3 bucket name
        key: S3 object key (path/filename)
        file_format: File format ('csv' or 'parquet')
        region_name: AWS region name
        
    Raises:
        ValueError: If DataFrame is empty
        ClientError: If S3 operation fails
    """
    if df.empty:
        raise ValueError("Cannot save empty DataFrame")
    
    try:
        # Initialize S3 client
        s3_client = boto3.client('s3', region_name=region_name)
        
        # Convert DataFrame to bytes based on format
        if file_format.lower() == 'csv':
            buffer = df.to_csv(index=False).encode('utf-8')
        elif file_format.lower() == 'parquet':
            buffer = df.to_parquet(index=False)
        else:
            raise ValueError(f"Unsupported format: {file_format}")
        
        # Upload to S3
        s3_client.put_object(Bucket=bucket_name, Key=key, Body=buffer)
        
        logger.info(f"Saved {len(df)} rows to s3://{bucket_name}/{key} (format: {file_format})")
        
    except ClientError as e:
        logger.error(f"AWS S3 error: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to save data to S3: {e}")
        raise


def get_s3_object_info(bucket_name: str, key: str, region_name: Optional[str] = None) -> dict:
    """
    Get information about an object in S3 bucket.
    
    Args:
        bucket_name: S3 bucket name
        key: S3 object key
        region_name: AWS region name
        
    Returns:
        Dictionary with object information
    """
    try:
        # Initialize S3 client
        s3_client = boto3.client('s3', region_name=region_name)
        
        # Get object metadata
        response = s3_client.head_object(Bucket=bucket_name, Key=key)
        
        info = {
            'bucket': bucket_name,
            'key': key,
            'size': response['ContentLength'],
            'last_modified': response['LastModified'],
            'content_type': response.get('ContentType', 'unknown'),
        }
        
        logger.info(f"Object info for {key}: size={info['size']} bytes")
        return info
        
    except ClientError as e:
        logger.error(f"Failed to get S3 object info: {e}")
        raise


def read_from_s3(bucket_name: str, key: str, file_format: str = 'csv', 
                 region_name: Optional[str] = None) -> pd.DataFrame:
    """
    Read data from S3 object into DataFrame.
    
    Args:
        bucket_name: S3 bucket name
        key: S3 object key
        file_format: File format ('csv' or 'parquet')
        region_name: AWS region name
        
    Returns:
        DataFrame with S3 object data
    """
    try:
        # Initialize S3 client
        s3_client = boto3.client('s3', region_name=region_name)
        
        # Get object from S3
        response = s3_client.get_object(Bucket=bucket_name, Key=key)
        
        # Read based on format
        if file_format.lower() == 'csv':
            df = pd.read_csv(response['Body'])
        elif file_format.lower() == 'parquet':
            df = pd.read_parquet(response['Body'])
        else:
            raise ValueError(f"Unsupported format: {file_format}")
        
        logger.info(f"Read {len(df)} rows from s3://{bucket_name}/{key}")
        return df
        
    except ClientError as e:
        logger.error(f"Failed to read from S3: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to read from S3: {e}")
        raise
