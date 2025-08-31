from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
from river import anomaly
from supabase import create_client
import anyio
import os

# --- Supabase setup ---
SUPABASE_URL = "https://zhrlppnknfjxhwhfsdxd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpocmxwcG5rbmZqeGh3aGZzZHhkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTY1NjY3NjIsImV4cCI6MjA3MjE0Mjc2Mn0.EVrzx09YwDglwFUCjS3hKbrg2Wdy1hjSPV1gWxnN_yU"  # service_role
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
app = FastAPI(title="Vehicle Sensor API with Supabase & Alerts")

# --- Pydantic model ---
class SensorData(BaseModel):
    vehicle_id: str
    sensor: str
    value: float
    timestamp: datetime = datetime.utcnow()

# --- Home route ---
@app.get("/")
def home():
    return {"message": "Server running with Supabase. Use /sensor to POST data and /data to GET all readings."}

# --- Async helper for Supabase insert ---
async def supabase_insert(data: dict):
    return await anyio.to_thread.run_sync(lambda: supabase.table("sensor_data").insert(data).execute())

# --- Endpoint to receive sensor data ---
@app.post("/sensor")
async def receive_data(data: SensorData):
    if data.sensor not in ALLOWED_SENSORS:
        raise HTTPException(status_code=400, detail=f"Sensor '{data.sensor}' not allowed.")

    # Static threshold alert
    min_val, max_val = SENSOR_SPECS[data.sensor]
    alert = int(data.value < min_val or data.value > max_val)

    # Adaptive anomaly scoring
    model = get_vehicle_model(data.vehicle_id)
    features = {data.sensor: data.value}
    anomaly_score = model.score_one(features)
    model.learn_one(features)

    # Push to Supabase safely in thread
    response = await supabase_insert({
        "vehicle_id": data.vehicle_id,
        "sensor": data.sensor,
        "value": data.value,
        "timestamp": data.timestamp.isoformat(),
        "alert": alert,
        "anomaly_score": anomaly_score
    })

    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=str(response.data))

    return {
        "status": "ok",
        "message": "Data stored in Supabase",
        "alert": bool(alert),
        "anomaly_score": anomaly_score
    }

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
        sensor_values = [d["value"] for d in data if d["sensor"] == sensor]
        anomaly_scores = [d["anomaly_score"] for d in data if d["sensor"] == sensor and d["anomaly_score"] is not None]
        alerts = [d["alert"] for d in data if d["sensor"] == sensor]

        if sensor_values:
            stats[sensor] = {
                "min": round(min(sensor_values), 2),
                "max": round(max(sensor_values), 2),
                "average": round(sum(sensor_values)/len(sensor_values), 2),
                "average_anomaly_score": round(sum(anomaly_scores)/len(anomaly_scores), 4) if anomaly_scores else None,
                "alerts": sum(alerts)
            }

    return {"vehicle_id": vehicle_id, "stats": stats}
