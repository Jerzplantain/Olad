from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# --- Database setup ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "vehicle_data.db")
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Allowed PIDs / sensors ---
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

# --- Database table ---
class SensorDataDB(Base):
    __tablename__ = "sensor_data"
    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(String, index=True)
    sensor = Column(String)
    value = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)
    anomaly_score = Column(Float, default=None)

Base.metadata.create_all(bind=engine)

# --- FastAPI app ---
app = FastAPI(title="Vehicle Sensor API")

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
    # Validate sensor
    if data.sensor not in ALLOWED_SENSORS:
        raise HTTPException(status_code=400, detail=f"Sensor '{data.sensor}' not allowed.")
    
    db = SessionLocal()
    entry = SensorDataDB(
        vehicle_id=data.vehicle_id,
        sensor=data.sensor,
        value=data.value,
        timestamp=data.timestamp,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    db.close()
    return {"status": "ok", "message": "Data stored", "id": entry.id}

# --- Endpoint to get all stored data with anomaly scores ---
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
                "anomaly_score": e.anomaly_score
            }
            for e in entries
        ]
    }

# --- Stats endpoint including anomaly scores ---
@app.get("/stats/{vehicle_id}")
def get_vehicle_stats(vehicle_id: str):
    db = SessionLocal()
    results = (
        db.query(
            SensorDataDB.sensor,
            func.min(SensorDataDB.value).label("min"),
            func.max(SensorDataDB.value).label("max"),
            func.avg(SensorDataDB.value).label("average"),
            func.avg(SensorDataDB.anomaly_score).label("avg_anomaly_score")
        )
        .filter(SensorDataDB.vehicle_id == vehicle_id)
        .group_by(SensorDataDB.sensor)
        .all()
    )
    db.close()

    stats = {}
    for sensor, min_val, max_val, avg_val, avg_score in results:
        stats[sensor] = {
            "min": round(min_val, 2),
            "max": round(max_val, 2),
            "average": round(avg_val, 2),
            "average_anomaly_score": round(avg_score, 4) if avg_score is not None else None
        }
    return {"vehicle_id": vehicle_id, "stats": stats}
