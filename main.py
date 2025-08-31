from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
from river import anomaly
from supabase import create_client
import anyio
import os

# --- Supabase setup ---
SUPABASE_URL = "https://zhrlppnknfjxhwhfsdxd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpocmxwcG5rbmZqeGh3aGZzZHhkIiwicm9zZSI6ImFub24iLCJpYXQiOjE3NTY1NjY3NjIsImV4cCI6MjA3MjE0Mjc2Mn0.EVrzx09YwDglwFUCjS3hKbrg2Wdy1hjSPV1gWxnN_yU"  # service_role
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Allowed sensors and static thresholds ---
ALLOWED_SENSORS = [
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

SENSOR_SPECS = {
    "Battery voltage": (11.5, 14.5),
    "Fuel trim": (-10, 10),
    "Alternator output": (13, 15),
    "Misfire count": (0, 5),
    "Engine RPMs": (800, 6000),
    "Engine run time": (0, 7200),
    "Coolant temperature": (70, 105),
    "Engine oil temperature": (70, 120),
    "Transmission oil temperature": (70, 120)
}

# --- River models per vehicle ---
vehicle_models = {}

def get_vehicle_model(vehicle_id):
    if vehicle_id not in vehicle_models:
        vehicle_models[vehicle_id] = anomaly.HalfSpaceTrees(seed=42)
    return vehicle_models[vehicle_id]

# --- FastAPI app ---
app = FastAPI(title="Vehicle Sensor API with Supabase & Alerts (Wide Format)")

# --- Pydantic models ---
class SensorBatch(BaseModel):
    vehicle_id: str
    data: dict  # {"Battery voltage": 13.9, "Fuel trim": 2.1, ...}
    timestamp: datetime = datetime.utcnow()

# --- Home route ---
@app.get("/")
def home():
    return {"message": "Server running with Supabase. Use POST /sensor to send data and GET /data to fetch."}

# --- Async helper for Supabase insert ---
async def supabase_insert(data: dict):
    return await anyio.to_thread.run_sync(lambda: supabase.table("sensor_data").insert(data).execute())

# --- Endpoint to receive multiple sensors in one row ---
@app.post("/sensor")
async def receive_data(batch: SensorBatch):
    timestamp = batch.timestamp
    vehicle_id = batch.vehicle_id
    values = batch.data

    # Build row for Supabase
    row = {"vehicle_id": vehicle_id, "timestamp": timestamp.isoformat()}
    alerts = {}
    scores = {}

    model = get_vehicle_model(vehicle_id)

    for sensor, value in values.items():
        if sensor not in ALLOWED_SENSORS:
            continue

        # Threshold alert
        min_val, max_val = SENSOR_SPECS[sensor]
        alerts[sensor] = int(value < min_val or value > max_val)

        # Adaptive anomaly scoring
        features = {sensor: value}
        anomaly_score = model.score_one(features)
        model.learn_one(features)
        scores[sensor] = anomaly_score

        # Map sensor to DB column
        col_name = sensor.lower().replace(" ", "_")
        row[col_name] = value

    row["alert"] = alerts
    row["anomaly_score"] = scores

    response = await supabase_insert(row)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=str(response.data))

    return {"status": "ok", "inserted": row}

# --- Async helper for Supabase select ---
async def supabase_select(query):
    return await anyio.to_thread.run_sync(query)

# --- Endpoint to get all data ---
@app.get("/data")
async def get_data():
    response = await supabase_select(lambda: supabase.table("sensor_data").select("*").execute())
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=str(response.data))
    return {"data": response.data}

# --- Stats endpoint ---
@app.get("/stats/{vehicle_id}")
async def get_vehicle_stats(vehicle_id: str):
    response = await supabase_select(lambda: supabase.table("sensor_data").select("*").eq("vehicle_id", vehicle_id).execute())
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=str(response.data))

    data = response.data
    stats = {}
    for sensor in ALLOWED_SENSORS:
        col_name = sensor.lower().replace(" ", "_")
        sensor_values = [d[col_name] for d in data if d.get(col_name) is not None]
        alerts = [d["alert"].get(sensor, 0) for d in data if "alert" in d]
        anomaly_scores = [d["anomaly_score"].get(sensor) for d in data if "anomaly_score" in d and d["anomaly_score"].get(sensor) is not None]

        if sensor_values:
            stats[sensor] = {
                "min": round(min(sensor_values), 2),
                "max": round(max(sensor_values), 2),
                "average": round(sum(sensor_values)/len(sensor_values), 2),
                "average_anomaly_score": round(sum(anomaly_scores)/len(anomaly_scores), 4) if anomaly_scores else None,
                "alerts": sum(alerts)
            }

    return {"vehicle_id": vehicle_id, "stats": stats}
