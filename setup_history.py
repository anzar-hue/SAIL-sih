import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sail_database.db')

# Columns added after the first version of this table. Existing databases are
# upgraded in place, so running this file (or starting app.py) is always safe.
EXTRA_COLUMNS = {
    "created_at": "TEXT",
    "port": "TEXT",
    "tonnage": "REAL",
    "event_keyword": "TEXT",
    "predicted_landed_per_tonne": "REAL",   # full landed cost (material + freight + bunker + demurrage + storage)
    "window_start": "TEXT",
    "window_end": "TEXT",
    "suggested_date": "TEXT",
    "notify_after": "TEXT",                 # suggested date + 7 days: when the "enter actual price" notice appears
    "notify_dismissed": "INTEGER DEFAULT 0",
    "calibration_factor": "REAL DEFAULT 1.0",  # correction that was applied when this prediction was made
    # extra charges entered with the prediction (percent of the predicted cost)
    "origin_tax_pct": "REAL", "india_tax_pct": "REAL", "sea_route_pct": "REAL", "other_pct": "REAL",
    "insurance_pct": "REAL", "incoterm": "TEXT", "extras_total_pct": "REAL", "predicted_extras_per_tonne": "REAL",
    # what actually happened after the purchase
    "actual_port_labour": "REAL", "actual_docking": "REAL", "actual_anchoring": "REAL", "actual_cleaning": "REAL",
    "actual_other_charges": "REAL", "actual_extra_charges_total": "REAL",
    "incident_cost": "REAL",                # loss / fine amount, INR
    "realized_risks": "TEXT",               # comma-separated incident codes
}


def setup_history_table(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # predicted_cost_per_tonne / actual_cost_per_tonne = purchase (material) price in INR per tonne
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS prediction_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_date TEXT,
        delivery_date TEXT,
        cargo_type TEXT,
        origin TEXT,
        predicted_cost_per_tonne REAL,
        actual_cost_per_tonne REAL,
        variance_percent REAL,
        status TEXT DEFAULT 'PENDING'
    )
    ''')

    existing = {row[1] for row in cursor.execute("PRAGMA table_info(prediction_history)")}
    for name, ddl in EXTRA_COLUMNS.items():
        if name not in existing:
            cursor.execute(f"ALTER TABLE prediction_history ADD COLUMN {name} {ddl}")

    conn.commit()
    conn.close()


if __name__ == '__main__':
    setup_history_table()
    print("Prediction History table is ready in sail_database.db")