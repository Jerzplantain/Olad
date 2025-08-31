# dashboard.py
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import random
from supabase import create_client

# --- Supabase config ---
SUPABASE_URL = "https://zhrlppnknfjxhwhfsdxd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpocmxwcG5rbmZqeGh3aGZzZHhkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTY1NjY3NjIsImV4cCI6MjA3MjE0Mjc2Mn0.EVrzx09YwDglwFUCjS3hKbrg2Wdy1hjSPV1gWxnN_yU"  # Use anon key for read-only dashboard
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

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

# --- Fetch from Supabase ---
def fetch_data():
    try:
        response = (
            supabase.table("sensor_data")
            .select("vehicle_id, sensor, value, timestamp")
            .order("timestamp", desc=False)
            .limit(500)  # pull latest 500
            .execute()
        )
        if response.data:
            return pd.DataFrame(response.data)
        else:
            return generate_demo_data()
    except Exception as e:
        st.warning(f"⚠️ Could not fetch data from Supabase. Showing demo data. ({e})")
        return generate_demo_data()

df = fetch_data()

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
