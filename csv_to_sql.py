import sqlite3
import pandas as pd
import os

print("Booting SQL Migration...")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(BASE_DIR, 'sail_database.db')

conn = sqlite3.connect(DB_PATH)

try:
    print("Migrating Coal Data...")
    pd.read_csv(os.path.join(DATA_DIR, 'coal.csv')).to_sql('coking_coal', conn, if_exists='replace', index=False)
    
    print("Migrating Fuel Data...")
    pd.read_csv(os.path.join(DATA_DIR, 'rawfuel.csv')).to_sql('fuel_prices', conn, if_exists='replace', index=False)
    
    print("Migrating Port Volumes...")
    pd.read_csv(os.path.join(DATA_DIR, 'economic_raw_port_cargo_volume_india (1).csv')).to_sql('port_volumes', conn, if_exists='replace', index=False)
    
    print("Migrating Exchange Rates...")
    pd.read_csv(os.path.join(DATA_DIR, 'exchange_rate_india.csv')).to_sql('exchange_rates', conn, if_exists='replace', index=False)
    
    print("Migrating Weather Data (10,000 rows)...")
    pd.read_excel(os.path.join(DATA_DIR, 'member_3_weather_raw_10000_demo-1.xlsx')).to_sql('weather_observations', conn, if_exists='replace', index=False)

    print("\n[SUCCESS] All files converted to SQL! 'sail_database.db' is ready.")

except Exception as e:
    print(f"Error during migration: {e}")

finally:
    conn.close()