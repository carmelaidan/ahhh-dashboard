"""
FRONTEND - Streamlit Dashboard
Displays real-time water level data with maps, charts, alerts, and system health
"""

import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import folium
from streamlit_folium import st_folium
from config import API_URL
from datetime import datetime, timedelta, timezone

st.set_page_config(page_title="A.H.H.H. Blockage Detection", page_icon="🌊", layout="wide")
st.title("A.H.H.H. Blockage Detection System")
st.subheader("Real-Time Storm Drain Monitoring with Power Analysis")

# Initialize session state for polling
if 'last_update' not in st.session_state:
    st.session_state.last_update = 0
if 'auto_refresh' not in st.session_state:
    st.session_state.auto_refresh = True

BASIN_HEIGHT_CM = 47.5
WARN_PCT = 0.25   
ALERT_PCT = 0.50  
DANGER_PCT = 0.75 

WARN_THRESHOLD = BASIN_HEIGHT_CM * WARN_PCT
ALERT_THRESHOLD = BASIN_HEIGHT_CM * ALERT_PCT
DANGER_THRESHOLD = BASIN_HEIGHT_CM * DANGER_PCT

ACTIVE_SENSOR_ID = "AHHH_Arduino_01"
REFRESH_INTERVAL_SECONDS = 5  

@st.cache_data(ttl=5)
def fetch_data(source='all'):
    try:
        response = requests.get(f"{API_URL}?source={source}", timeout=5)
        all_data = response.json().get("data", []) if response.status_code == 200 else []
        return all_data 
    except requests.exceptions.RequestException:
        st.error("❌ Cannot connect to backend API. Is Flask running?")
        return []

def get_status_color(capacity_pct):
    if capacity_pct >= DANGER_PCT * 100:
        return f"🔴 DANGER ({capacity_pct:.1f}%)", "red"
    elif capacity_pct >= ALERT_PCT * 100:
        return f"🟠 ALERT ({capacity_pct:.1f}%)", "orange"
    elif capacity_pct >= WARN_PCT * 100:
        return f"🟡 WARNING ({capacity_pct:.1f}%)", "gold"
    else:
        return f"🟢 NORMAL ({capacity_pct:.1f}%)", "green"

def get_marker_color(capacity_pct):
    if capacity_pct >= DANGER_PCT * 100:
        return "red"
    elif capacity_pct >= ALERT_PCT * 100:
        return "orange"
    elif capacity_pct >= WARN_PCT * 100:
        return "yellow"
    else:
        return "green"

def create_sensor_map(df, is_active):
    try:
        if df.empty or 'latitude' not in df.columns:
            return None
        
        df_map = df[df['sensor_id'] == ACTIVE_SENSOR_ID].copy()
        df_map = df_map.dropna(subset=['latitude', 'longitude'])
        if df_map.empty:
            return None
        
        latest = df_map.iloc[-1]
        lat = float(latest['latitude'])
        lon = float(latest['longitude'])
        
        m = folium.Map(location=[lat, lon], zoom_start=16, tiles="OpenStreetMap")
        
        circle_color = 'blue' if is_active else 'gray'
        marker_color = get_marker_color(latest['capacity_pct']) if is_active else 'lightgray'
        status_text = f"Level: {latest['water_level_cm']:.1f}cm" if is_active else "Status: OFFLINE"
        
        folium.Circle(location=[lat, lon], radius=200, color=circle_color, fill=True, fillOpacity=0.1, weight=2).add_to(m)
        
        folium.Marker(
            location=[lat, lon],
            popup=f"<b>{latest['sensor_id']}</b><br>{status_text}",
            icon=folium.Icon(color=marker_color, icon="tint" if is_active else "ban", prefix="fa")
        ).add_to(m)
        
        return m
    except Exception as e:
        print(f"Map error: {e}")
        return None

raw_data = fetch_data()

# Current PST Time
current_pst = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=8)

if raw_data:
    df_all = pd.DataFrame(raw_data)
    df_all['recorded_at'] = pd.to_datetime(df_all['recorded_at'], errors='coerce')
    df_all = df_all.sort_values('recorded_at')
    
    df = df_all[df_all['sensor_id']
