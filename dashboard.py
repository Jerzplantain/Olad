import streamlit as st
import pandas as pd
import requests
import time

# FastAPI server URL
SERVER_URL = "https://olad.onrender.com/"

st.set_page_config(page_title="Vehicle Data Dashboard", layout="wide")
st.title("📊 Vehicle Sensor Data Dashboard")

# Sidebar options
st.sidebar.header("Options")
REFRESH_RATE = 5  # auto-refresh every 5 seconds

# Predefined sensors in order
SENSOR_LIST = [
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

while True:
    # Fetch data from FastAPI
    try:
        response = requests.get(f"{SERVER_URL}/data")
        if response.status_code == 200:
            data = response.json()["data"]
            df = pd.DataFrame(data)

            if not df.empty:
                if "timestamp" in df.columns:
                    df["timestamp"] = pd.to_datetime(df["timestamp"])

                # Vehicle selection
                vehicle_ids = df["vehicle_id"].unique().tolist()
                selected_vehicle = st.sidebar.selectbox("Select Vehicle", ["All"] + vehicle_ids)

                if selected_vehicle != "All":
                    df = df[df["vehicle_id"] == selected_vehicle]

                st.subheader("Raw Data Table")
                st.dataframe(df.tail(20))

                # Sensor selection from predefined list
                st.subheader("Sensor Data Over Time")
                sensor_type = st.sidebar.selectbox("Select Sensor", SENSOR_LIST)
                df_sensor = df[df["sensor"] == sensor_type]

                if not df_sensor.empty:
                    st.line_chart(df_sensor.set_index("timestamp")["value"])

                # Anomaly scores
                if "anomaly_score" in df.columns:
                    st.subheader("Anomaly Scores Over Time")
                    df_anomaly = df[df["sensor"] == sensor_type]
                    if not df_anomaly.empty:
                        st.line_chart(df_anomaly.set_index("timestamp")["anomaly_score"])

            else:
                st.warning("No data found in the database.")
        else:
            st.error(f"Error fetching data: {response.status_code}")
    except Exception as e:
        st.error(f"Could not connect to API server: {e}")

    # Wait and refresh
    time.sleep(REFRESH_RATE)


