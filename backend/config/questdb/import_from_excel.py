#!/usr/bin/env python3
"""
Import sensor data from Excel file into QuestDB.

Usage:
    python3 import_from_excel.py sensor_data.xlsx
    python3 import_from_excel.py sensor_data.xlsx --validate
    python3 import_from_excel.py sensor_data.xlsx --dry-run

Excel format required:
    sensor_id | sensor_type | latitude | longitude | pm10 | pm25 | no2 | timestamp
    F001      | fixed       | 44.5026  | 26.0821   | 35.2 | 20.1 | 28  | 2025-01-03 10:00:00
"""

import sys
import argparse
import pandas as pd
import psycopg2
from datetime import datetime
from typing import Dict, List, Tuple

# QuestDB connection
DB_CONFIG = {
    'host': 'localhost',
    'port': 8812,
    'user': 'admin',
    'password': 'quest',
    'dbname': 'qdb'
}

REQUIRED_COLUMNS = [
    'sensor_id',
    'sensor_type', 
    'latitude',
    'longitude',
    'pm10',
    'pm25',
    'no2',
    'timestamp'
]


class ExcelImporter:
    """Import sensor data from Excel to QuestDB."""
    
    def __init__(self, excel_path: str, dry_run: bool = False):
        self.excel_path = excel_path
        self.dry_run = dry_run
        self.errors = []
        self.warnings = []
        
    def validate_excel_format(self, df: pd.DataFrame) -> bool:
        """Validate Excel file has required columns and correct data types."""
        print("\n[1] Validating Excel format...")
        
        # Check columns
        missing_cols = set(REQUIRED_COLUMNS) - set(df.columns)
        if missing_cols:
            self.errors.append(f"Missing columns: {missing_cols}")
            return False
        
        print(f" All required columns present: {len(REQUIRED_COLUMNS)}")
        
        # Check sensor_type values
        valid_types = {'fixed', 'mobile'}
        invalid_types = set(df['sensor_type'].unique()) - valid_types
        if invalid_types:
            self.errors.append(f"Invalid sensor_type values: {invalid_types}")
            return False
        
        print(f"Sensor types valid: {df['sensor_type'].value_counts().to_dict()}")
        
        # Check coordinate ranges (Bucharest bounds)
        lat_range = (44.35, 44.50)
        lon_range = (26.00, 26.20)
        
        out_of_bounds = df[
            (df['latitude'] < lat_range[0]) | (df['latitude'] > lat_range[1]) |
            (df['longitude'] < lon_range[0]) | (df['longitude'] > lon_range[1])
        ]
        
        if len(out_of_bounds) > 0:
            self.warnings.append(
                f"{len(out_of_bounds)} readings outside Bucharest bounds "
                f"(lat {lat_range}, lon {lon_range})"
            )
            print(f"Warning: {self.warnings[-1]}")
        else:
            print(f"All coordinates within Bucharest bounds")
        
        # Check for negative pollution values
        negative_pm10 = df[df['pm10'] < 0]
        negative_pm25 = df[df['pm25'] < 0]
        negative_no2 = df[df['no2'] < 0]
        
        if len(negative_pm10) > 0 or len(negative_pm25) > 0 or len(negative_no2) > 0:
            self.errors.append("Found negative pollution values (invalid)")
            return False
        
        print(f"All pollution values non-negative")
        
        # Check timestamp format
        try:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            print(f"Timestamps parsed successfully")
            print(f"Time range: {df['timestamp'].min()} to {df['timestamp'].max()}")
        except Exception as e:
            self.errors.append(f"Invalid timestamp format: {e}")
            return False
        
        return True
    
    def load_excel(self) -> pd.DataFrame:
        """Load and validate Excel file."""
        print(f"\nLoading Excel file: {self.excel_path}")
        
        try:
            df = pd.read_excel(self.excel_path)
            print(f" Loaded {len(df)} rows")
            
            if not self.validate_excel_format(df):
                return None
            
            return df
            
        except FileNotFoundError:
            self.errors.append(f"File not found: {self.excel_path}")
            return None
        except Exception as e:
            self.errors.append(f"Error loading Excel: {e}")
            return None
    
    def insert_to_questdb(self, df: pd.DataFrame) -> int:
        """Insert data into QuestDB."""
        if self.dry_run:
            print("\n[DRY RUN] Would insert to QuestDB:")
            print(df.head(10))
            return len(df)
        
        print("\n[2] Inserting to QuestDB...")
        
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()
            
            inserted = 0
            batch_size = 100
            
            for i in range(0, len(df), batch_size):
                batch = df.iloc[i:i+batch_size]
                
                for _, row in batch.iterrows():
                    cur.execute("""
                        INSERT INTO sensor_readings 
                        (sensor_id, sensor_type, latitude, longitude, pm10, pm25, no2, timestamp)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        row['sensor_id'],
                        row['sensor_type'],
                        float(row['latitude']),
                        float(row['longitude']),
                        float(row['pm10']),
                        float(row['pm25']),
                        float(row['no2']),
                        row['timestamp']
                    ))
                    inserted += 1
                
                conn.commit()
                print(f"  Inserted {inserted}/{len(df)} rows...", end='\r')
            
            print(f"\nSuccessfully inserted {inserted} readings")
            
            # Verify insertion
            cur.execute("SELECT COUNT(*) FROM sensor_readings")
            total = cur.fetchone()[0]
            print(f"Total readings in database: {total}")
            
            cur.close()
            conn.close()
            
            return inserted
            
        except Exception as e:
            self.errors.append(f"Database insertion error: {e}")
            return 0
    
    def generate_summary(self, df: pd.DataFrame):
        """Generate summary statistics."""
        print("IMPORT SUMMARY")
        
        print(f"\nTotal readings: {len(df)}")
        print(f"Unique sensors: {df['sensor_id'].nunique()}")
        
        print("\nBy sensor type:")
        type_counts = df.groupby('sensor_type').size()
        for sensor_type, count in type_counts.items():
            print(f"  {sensor_type:10s}: {count:4d} readings")
        
        print("\nPollution statistics:")
        stats = df[['pm10', 'pm25', 'no2']].describe()
        print(stats.round(2))
        
        print("\nTime range:")
        print(f"  First reading: {df['timestamp'].min()}")
        print(f"  Last reading:  {df['timestamp'].max()}")
        print(f"  Duration:      {df['timestamp'].max() - df['timestamp'].min()}")
        
        if self.warnings:
            print("\nWARNINGS:")
            for warning in self.warnings:
                print(f"  - {warning}")

    def run(self) -> bool:
        """Execute import process."""
        print("EXCEL TO QUESTDB IMPORT")
        
        # Load and validate
        df = self.load_excel()
        if df is None:
            self.print_errors()
            return False
        
        # Show summary
        self.generate_summary(df)
        
        # Insert to database
        if not self.dry_run:
            inserted = self.insert_to_questdb(df)
            if inserted == 0:
                self.print_errors()
                return False
        
        print("Import completed successfully!")
        return True
    
    def print_errors(self):
        """Print all errors."""
        if self.errors:
            print("\nERRORS:")
            for error in self.errors:
                print(f"  - {error}")
            print()


def main():
    parser = argparse.ArgumentParser(
        description='Import sensor data from Excel to QuestDB',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 import_from_excel.py sensor_data.xlsx
  python3 import_from_excel.py sensor_data.xlsx --validate --dry-run
  python3 import_from_excel.py /path/to/data.xlsx

Excel format:
  sensor_id | sensor_type | latitude | longitude | pm10 | pm25 | no2 | timestamp
  F001      | fixed       | 44.5026  | 26.0821   | 35.2 | 20.1 | 28  | 2025-01-03 10:00
        """
    )
    
    parser.add_argument('excel_file', help='Path to Excel file')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Validate without inserting to database')
    parser.add_argument('--validate', action='store_true',
                       help='Run validation only (implies --dry-run)')
    
    args = parser.parse_args()
    
    dry_run = args.dry_run or args.validate
    
    importer = ExcelImporter(args.excel_file, dry_run=dry_run)
    success = importer.run()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
