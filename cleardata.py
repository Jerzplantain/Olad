from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main import SensorDataDB, Base, DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

db = SessionLocal()
db.query(SensorDataDB).delete()
db.commit()
db.close()

print("All sensor data cleared.")
