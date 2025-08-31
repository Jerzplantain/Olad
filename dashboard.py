# dashboard.py
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from supabase import create_client

# --- Supabase config ---
SUPABASE_URL = "https://zhrlppnknfjxhwhfsdxd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpocmxwcG5rbmZqeGh3aGZzZHhkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTY1NjY3NjIsImV4cCI6MjA3MjE0Mjc2Mn0.EVrzx09YwDglwFUCjS3hKbrg2Wdy1hjSPV1gWxnN_yU"  # Use anon key for read-only dashboard
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="Vehicle Data Dashboard", layout="wide")
st.title("📊 Vehicle Sensor Data Dashboard")

# --- Function to generate demo data ---
def generate_demo_data():
    now = datetime.utcnow()
    data = []
    sensors = [
        "Battery voltage", "Fuel trim", "Alternator output", "Misfire count",
        "Engine RPMs", "Engine run time", "Coolant temperature",
        "Engine oil temperature", "Transmission oil temperature"
    ]
    for i in range(50):
        row = {"vehicle_id": "DemoCar", "timestamp": now - timedelta(seconds=(50 - i) * 5)}
        for s in sensors:
            row[s] = random.uniform(10, 100)
        data.append(row)
    return pd.DataFrame(data)

# --- Fetch from Supabase ---
def fetch_data():
    try:
        # Select wide columns
        response = supabase.table("sensor_data").select("*").order("timestamp", desc=False).limit(500).execute()
        if response.data:
            df = pd.DataFrame(response.data)

            # Parse ISO8601 timestamps with microseconds & timezone
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors='coerce')
            return df
        else:
            return generate_demo_data()
    except Exception as e:
        st.warning(f"⚠️ Could not fetch data from Supabase. Showing demo data. ({e})")
        return generate_demo_data()

df = fetch_data()

if not df.empty:
    # Sidebar: select vehicle
    vehicle_ids = df["vehicle_id"].unique().tolist()
    selected_vehicle = st.sidebar.selectbox("Select Vehicle", ["All"] + vehicle_ids)

    if selected_vehicle != "All":
        df = df[df["vehicle_id"] == selected_vehicle]

    st.subheader("Raw Data Table")
    st.dataframe(df.tail(20))

    # Sensor line charts
    sensors = [col for col in df.columns if col not in ["vehicle_id", "timestamp"]]
    if sensors:
        st.subheader("Sensor Data Over Time")
        sensor_type = st.sidebar.selectbox("Select Sensor", sensors)
        if sensor_type in df.columns:
            st.line_chart(df.set_index("timestamp")[sensor_type])

else:
    st.error("No data available.")
