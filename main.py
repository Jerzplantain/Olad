from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# River for online learning
from river import anomaly

# --- Database setup ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "vehicle_data.db")
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Allowed sensors / specs ---
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

# Define static spec thresholds (for ESP32 alerting and server fallback)
SENSOR_SPECS = {
    "Battery voltage": (11.5, 14.5),
    "Fuel trim": (-10, 10),
    "Alternator output": (13, 15),
    "Misfire count": (0, 5),
    "Engine RPMs": (800, 6000),
    "Engine run time": (0, 7200),  # seconds
    "Coolant temperature": (70, 105),
    "Engine oil temperature": (70, 120),
    "Transmission oil temperature": (70, 120)
}

# --- Database table ---
class SensorDataDB(Base):
    __tablename__ = "sensor_data"
    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(String, index=True)
    sensor = Column(String)
    value = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)
    anomaly_score = Column(Float, default=None)
    alert = Column(Integer, default=0)  # 0 = normal, 1 = out-of-spec

Base.metadata.create_all(bind=engine)

# --- FastAPI app ---
app = FastAPI(title="Vehicle Sensor API with Alerts & Adaptive AI")

# --- River model per vehicle (simple dictionary to hold multiple vehicle models) ---
vehicle_models = {}

def get_vehicle_model(vehicle_id):
    if vehicle_id not in vehicle_models:
        # Each vehicle gets a separate online anomaly detector
        vehicle_models[vehicle_id] = anomaly.HalfSpaceTrees(seed=42)
    return vehicle_models[vehicle_id]

# --- Pydantic model ---
class SensorData(BaseModel):
    vehicle_id: str
    sensor: str
    value: float
    timestamp: datetime = datetime.utcnow()

# --- Home route ---
@app.get("/")
def home():
    return {"message": "Server Running. Go to /docs for API docs or /data to see all sensor readings."}

# --- Endpoint to receive sensor data ---
@app.post("/sensor")
def receive_data(data: SensorData):
    if data.sensor not in ALLOWED_SENSORS:
        raise HTTPException(status_code=400, detail=f"Sensor '{data.sensor}' not allowed.")

    # Check static spec alert
    min_val, max_val = SENSOR_SPECS[data.sensor]
    alert = int(data.value < min_val or data.value > max_val)

    # Adaptive anomaly scoring via River
    model = get_vehicle_model(data.vehicle_id)
    features = {data.sensor: data.value}
    anomaly_score = model.score_one(features)
    model.learn_one(features)

    # Save to DB
    db = SessionLocal()
    entry = SensorDataDB(
        vehicle_id=data.vehicle_id,
        sensor=data.sensor,
        value=data.value,
        timestamp=data.timestamp,
        anomaly_score=anomaly_score,
        alert=alert
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    db.close()

    return {
        "status": "ok",
        "message": "Data stored",
        "id": entry.id,
        "alert": bool(alert),
        "anomaly_score": anomaly_score
    }

# --- Endpoint to get all stored data ---
@app.get("/data")
def get_data():
    db = SessionLocal()
    entries = db.query(SensorDataDB).all()
    db.close()
    return {
        "data": [
            {
                "vehicle_id": e.vehicle_id,
                "sensor": e.sensor,
                "value": e.value,
                "timestamp": e.timestamp,
                "anomaly_score": e.anomaly_score,
                "alert": bool(e.alert)
            }
            for e in entries
        ]
    }

# --- Stats endpoint including anomaly scores and alert counts ---
@app.get("/stats/{vehicle_id}")
def get_vehicle_stats(vehicle_id: str):
    db = SessionLocal()
    results = (
        db.query(
            SensorDataDB.sensor,
            func.min(SensorDataDB.value).label("min"),
            func.max(SensorDataDB.value).label("max"),
            func.avg(SensorDataDB.value).label("average"),
            func.avg(SensorDataDB.anomaly_score).label("avg_anomaly_score"),
            func.sum(SensorDataDB.alert).label("alert_count")
        )
        .filter(SensorDataDB.vehicle_id == vehicle_id)
        .group_by(SensorDataDB.sensor)
        .all()
    )
    db.close()

    stats = {}
    for sensor, min_val, max_val, avg_val, avg_score, alert_count in results:
        stats[sensor] = {
            "min": round(min_val, 2),
            "max": round(max_val, 2),
            "average": round(avg_val, 2),
            "average_anomaly_score": round(avg_score, 4) if avg_score is not None else None,
            "alerts": int(alert_count)
        }
    return {"vehicle_id": vehicle_id, "stats": stats}
]]]
