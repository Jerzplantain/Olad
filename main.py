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
    alert = int(data.value < min_val or data.v_
