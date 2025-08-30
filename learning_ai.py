import sqlite3
from datetime import datetime
from river import anomaly, preprocessing
import time

# Database file
DB_FILE = "vehicle_data.db"

# New sensor list
SENSORS = [
    "Battery voltage",
    "Fuel trim",
    "Alternator output",
    "Misfire count",
    "Engine RPMs",
    "Engine run time",
    "Coolant temperature",
    "Engine oil temperature",
    "Transmission oil temperature"
]

# Create a model for each vehicle and each sensor
vehicle_models = {}

# Function to fetch new data from DB
def fetch_data():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, vehicle_id, sensor, value FROM sensor_data WHERE anomaly_score IS NULL ORDER BY timestamp ASC")
    rows = c.fetchall()
    conn.close()
    return rows

# Function to update anomaly score in DB
def update_score(row_id, score):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE sensor_data SET anomaly_score=? WHERE id=?", (score, row_id))
    conn.commit()
    conn.close()

# Initialize models
def get_model(vehicle_id, sensor):
    if vehicle_id not in vehicle_models:
        vehicle_models[vehicle_id] = {}
    if sensor not in vehicle_models[vehicle_id]:
        # Use z-score + HalfSpaceTrees for anomaly detection
        vehicle_models[vehicle_id][sensor] = preprocessing.StandardScaler() | anomaly.HalfSpaceTrees(seed=42, n_trees=25, height=5)
    return vehicle_models[vehicle_id][sensor]

print("Starting online learning for vehicle sensors...")

while True:
    rows = fetch_data()
    if not rows:
        time.sleep(2)
        continue

    for row_id, vehicle_id, sensor, value in rows:
        if sensor not in SENSORS:
            # Skip any sensors not in our defined list
            continue

        model = get_model(vehicle_id, sensor)
        x = {"value": value}
        score = model.score_one(x)
        model.learn_one(x)

        # Update anomaly score in DB
        update_score(row_id, float(score))

        print(f"[{vehicle_id}] {sensor}={value} | anomaly_score={score:.4f}")
    
    # Small delay to prevent busy loop
    time.sleep(1)
