import requests
import random
import time
from datetime import datetime

# FastAPI server URL
SERVER_URL = "http://192.168.68.129:8000/sensor"

# Example vehicle IDs
VEHICLES = ["CAR001", "CAR002"]

# New PIDs / sensors
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

# Function to generate realistic fake values for each sensor
def generate_fake_value(sensor):
    if sensor == "Battery voltage":
        return round(random.uniform(12.0, 14.5), 2)
    elif sensor == "Fuel trim":
        return round(random.uniform(-5.0, 5.0), 2)
    elif sensor == "Alternator output":
        return round(random.uniform(13.5, 14.8), 2)
    elif sensor == "Misfire count":
        return random.randint(0, 5)
    elif sensor == "Engine RPMs":
        return random.randint(800, 3500)
    elif sensor == "Engine run time":
        return random.randint(100, 50000)  # seconds
    elif sensor == "Coolant temperature":
        return random.randint(70, 100)  # °C
    elif sensor == "Engine oil temperature":
        return random.randint(60, 110)  # °C
    elif sensor == "Transmission oil temperature":
        return random.randint(60, 120)  # °C
    else:
        return 0

# Auto-run simulator
while True:
    for vehicle_id in VEHICLES:
        for sensor in SENSORS:
            value = generate_fake_value(sensor)
            data = {
                "vehicle_id": vehicle_id,
                "sensor": sensor,
                "value": value,
                "timestamp": datetime.utcnow().isoformat()
            }
            try:
                response = requests.post(SERVER_URL, json=data)
                if response.status_code == 200:
                    print(f"[{vehicle_id}] {sensor}={value} sent successfully.")
                else:
                    print(f"Error posting {sensor}: {response.status_code}")
            except Exception as e:
                print(f"Connection error: {e}")
    time.sleep(2)  # send every 2 seconds
