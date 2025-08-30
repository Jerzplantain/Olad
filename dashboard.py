# dashboard.py
import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import random

# Render server URL
SERVER_URL = "https://olad.onrender.com/data"

st.set_page_config(page_title="Vehicle Data Dashboard", layout="wide")
st.title("📊 Vehicle Sensor Data Dashboard")

# Function to generate fake demo data
def generate_demo_data():
    now = datetime.utcnow()
    data = []
    sensors = [
        "Battery voltage", "Fuel trim", "Alternator output", "Misfire count",
        "Engine RPMs", "Engine run time", "Coolant temperature",
        "Engine oil temperature", "Transmission oil temperature"
    ]
    for i in range(50):
        for s in sensors:
            data.append({
                "vehicle_id": "DemoCar",
                "sensor": s,
                "value": random.uniform(10, 100),
                "timestamp": now - timedelta(seconds=(50 - i) * 5)
            })
    return pd.DataFrame(data)

# Fetch data from Render API
try:
    response = requests.get(SERVER_URL, timeout=5)
    if response.status_code == 200:
        data = response.json()["data"]
        df = pd.DataFrame(data)
    else:
        st.warning("⚠️ Could not fetch data from API. Showing demo data.")
        df = generate_demo_data()
except Exception:
    st.warning("⚠️ API not reachable. Showing demo data.")
    df = generate_demo_data()

if not df.empty:
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])

    # Sidebar vehicle selection
    vehicle_ids = df["vehicle_id"].unique().tolist()
    selected_vehicle = st.sidebar.selectbox("Select Vehicle", ["All"] + vehicle_ids)

    if selected_vehicle != "All":
        df = df[df["vehicle_id"] == selected_vehicle]

    st.subheader("Raw Data Table")
    st.dataframe(df.tail(20))

    # Sensor line charts
    if "sensor" in df.columns and "value" in df.columns:
        st.subheader("Sensor Data Over Time")
        sensor_type = st.sidebar.selectbox("Select Sensor", df["sensor"].unique())
        df_sensor = df[df["sensor"] == sensor_type]
        st.line_chart(df_sensor.set_index("timestamp")["value"])

else:
    st.error("No data available.")
