# dashboard.py (wide-format Supabase with alert summary)
import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client

# --- Supabase config ---
SUPABASE_URL = "https://zhrlppnknfjxhwhfsdxd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpocmxwcG5rbmZqeGh3aGZzZHhkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTY1NjY3NjIsImV4cCI6MjA3MjE0Mjc2Mn0.EVrzx09YwDglwFUCjS3hKbrg2Wdy1hjSPV1gWxnN_yU"  # ⚠️ Use service_role key for updates
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="Vehicle Data Dashboard", layout="wide")
st.title("📊 Vehicle Sensor Data Dashboard (Wide Format)")

# --- Sensor columns ---
SENSOR_COLUMNS = [
    "battery_voltage", "fuel_trim", "alternator_output", "misfire_count",
    "engine_rpms", "engine_run_time", "coolant_temperature",
    "engine_oil_temperature", "transmission_oil_temperature"
]

ALERT_COLUMNS = [f"{s}_alert" for s in SENSOR_COLUMNS]
ANOMALY_COLUMNS = [f"{s}_anomaly" for s in SENSOR_COLUMNS]

# --- Fetch data from Supabase ---
def fetch_data():
    try:
        response = (
            supabase.table("sensor_data")
            .select("*")
            .order("timestamp", desc=False)
            .limit(500)
            .execute()
        )
        if response.data:
            df = pd.DataFrame(response.data)
            # Convert timestamp to datetime
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
            return df
        else:
            return pd.DataFrame()
    except Exception as e:
        st.warning(f"⚠️ Could not fetch data from Supabase. ({e})")
        return pd.DataFrame()

df = fetch_data()

if not df.empty:
    # Sidebar: select vehicle
    vehicle_ids = df["vehicle_id"].unique().tolist()
    selected_vehicle = st.sidebar.selectbox("Select Vehicle", ["All"] + vehicle_ids)
    if selected_vehicle != "All":
        df = df[df["vehicle_id"] == selected_vehicle]

    # --- Alert summary ---
    st.subheader("⚠️ Sensor Alert Summary")
    if ALERT_COLUMNS:
        alert_counts = df[ALERT_COLUMNS].sum().sort_values(ascending=False)
        st.bar_chart(alert_counts)

    # --- Raw data table ---
    st.subheader("Raw Data Table")
    st.dataframe(df.tail(20))

    # --- Sensor plotting ---
    st.subheader("Sensor Data Over Time")
    sensor_to_plot = st.sidebar.selectbox("Select Sensor", SENSOR_COLUMNS)
    if sensor_to_plot in df.columns:
        st.line_chart(df.set_index("timestamp")[sensor_to_plot])

    # --- Alerts / anomaly table ---
    st.subheader("Sensor Alerts & Anomaly Scores (Last 20 entries)")
    st.dataframe(df[["vehicle_id", "timestamp"] + ALERT_COLUMNS + ANOMALY_COLUMNS].tail(20))

else:
    st.error("No data available from Supabase.")

