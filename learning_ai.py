from datetime import datetime
from river import anomaly, preprocessing
import time
from supabase import create_client

# --- Supabase setup ---
SUPABASE_URL = "https://zhrlppnknfjxhwhfsdxd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpocmxwcG5rbmZqeGh3aGZzZHhkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTY1NjY3NjIsImV4cCI6MjA3MjE0Mjc2Mn0.EVrzx09YwDglwFUCjS3hKbrg2Wdy1hjSPV1gWxnN_yU"   # ⚠️ Use service_role key for updates
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Sensors we allow
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

# Models per vehicle/sensor
vehicle_models = {}

def get_model(vehicle_id, sensor):
    if vehicle_id not in vehicle_models:
        vehicle_models[vehicle_id] = {}
    if sensor not in vehicle_models[vehicle_id]:
        # Normalize then anomaly detect
        vehicle_models[vehicle_id][sensor] = (
            preprocessing.StandardScaler() | anomaly.HalfSpaceTrees(seed=42, n_trees=25, height=5)
        )
    return vehicle_models[vehicle_id][sensor]

# Fetch rows without anomaly_score
def fetch_data():
    response = (
        supabase.table("sensor_data")
        .select("id, vehicle_id, sensor, value")
        .is_("anomaly_score", None)
        .order("timestamp", desc=False)
        .limit(100)  # batch for efficiency
        .execute()
    )
    if response.data:
        return response.data
    return []

# Update anomaly_score in Supabase
def update_score(row_id, score):
    supabase.table("sensor_data").update({"anomaly_score": score}).eq("id", row_id).execute()

print("🚗 Starting online anomaly learning with Supabase...")

while True:
    rows = fetch_data()
    if not rows:
        time.sleep(2)
        continue

    for row in rows:
        row_id = row["id"]
        vehicle_id = row["vehicle_id"]
        sensor = row["sensor"]
        value = row["value"]

        if sensor not in SENSORS:
            continue

        model = get_model(vehicle_id, sensor)
        x = {"value": value}
        score = model.score_one(x)
        model.learn_one(x)

        update_score(row_id, float(score))
        print(f"[{vehicle_id}] {sensor}={value} | anomaly_score={score:.4f}")

    time.sleep(1)
