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
    
    df = df_all[df_all['sensor_id'] == ACTIVE_SENSOR_ID].copy()
    
    if 'capacity_percentage' not in df.columns:
        df['capacity_percentage'] = (df['water_level_cm'] / BASIN_HEIGHT_CM) * 100
    if 'alert_status' not in df.columns:
        df['alert_status'] = False
    if 'alert_type' not in df.columns:
        df['alert_type'] = 'normal_reading'
    
    df['capacity_pct'] = df['capacity_percentage']
    
    if not df.empty:
        latest = df.iloc[-1]
        
        latest_time = latest['recorded_at']
        time_since_ping = None
        is_system_active = False

        if pd.notna(latest_time):
            time_since_ping = (current_pst - latest_time).total_seconds()
            is_system_active = time_since_ping <= 120
            
        status_text, status_color = get_status_color(latest['capacity_pct'])
        
        # Metrics
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            if is_system_active:
                st.metric("Latest Reading", f"{latest['water_level_cm']} cm", status_text, delta_color="off")
            else:
                st.metric("Latest Reading", "-- cm", "🔴 OFFLINE", delta_color="off")
        with col2:
            avg_level = df['water_level_cm'].mean()
            st.metric("Average", f"{avg_level:.1f} cm")
        with col3:
            st.metric("Peak", f"{df['water_level_cm'].max():.1f} cm")
        with col4:
            st.metric("Minimum", f"{df['water_level_cm'].min():.1f} cm")
        with col5:
            if is_system_active:
                st.metric("Power", f"{latest.get('power_consumption_watts', 0.0):.2f} W")
            else:
                st.metric("Power", "-- W")
            
        st.markdown("---")
        
        # System Health Display 
        st.subheader("🖥️ System & Device Health")
        
        active_sensors = []
        inactive_sensors = []
        
        last_pings = df_all.groupby('sensor_id')['recorded_at'].max()
        for s_id, last_time in last_pings.items():
            if pd.isna(last_time):
                inactive_sensors.append((s_id, "Unknown"))
            else:
                delta_seconds = (current_pst - last_time).total_seconds()
                if delta_seconds <= 120:  
                    active_sensors.append((s_id, int(delta_seconds)))
                else:
                    inactive_sensors.append((s_id, int(delta_seconds/60)))
        
        col_sys1, col_sys2, col_sys3 = st.columns(3)
        
        has_gps = pd.notna(latest.get('latitude')) and pd.notna(latest.get('longitude'))
        has_power = latest.get('power_consumption_watts', 0.0) > 0
        
        with col_sys1:
            st.markdown("**📡 Network Status**")
            if pd.isna(latest_time) or time_since_ping is None:
                st.error("🔴 Offline (Last ping: Unknown)")
            elif is_system_active:
                st.success(f"🟢 Active (Last ping: {int(time_since_ping)}s ago)")
            else:
                st.error(f"🔴 Offline (Last ping: {int(time_since_ping/60)}m ago)")
                
        with col_sys2:
            st.markdown("**🛰️ GPS Status**")
            if not is_system_active:
                st.error("🔴 Offline")
            elif has_gps:
                st.success(f"🟢 Locked ({latest['latitude']}, {latest['longitude']})")
            else:
                st.warning("🟡 Searching (No line of sight)")
                
        with col_sys3:
            st.markdown("**🔋 Power Sensor**")
            if not is_system_active:
                st.error("🔴 Offline")
            elif has_power:
                st.success(f"🟢 Active ({latest['power_consumption_watts']:.3f} W)")
            else:
                st.error("🔴 Inactive / 0.0 W")

        col_list1, col_list2 = st.columns(2)
        with col_list1:
            st.markdown("##### 🟢 Active Sensors")
            if active_sensors:
                for s in active_sensors:
                    st.write(f"- {s[0]} *(Pinged {s[1]}s ago)*")
            else:
                st.write("*None*")
                
        with col_list2:
            st.markdown("##### 🔴 Inactive Sensors")
            if inactive_sensors:
                for s in inactive_sensors:
                    if s[1] == "Unknown":
                        st.write(f"- {s[0]} *(Offline: Unknown)*")
                    else:
                        st.write(f"- {s[0]} *(Offline for {s[1]} mins)*")
            else:
                st.write("*None*")

        st.markdown("---")
        
        # Alert Section Display
        col_alert1, col_alert2 = st.columns([2, 1])
        with col_alert1:
            if not is_system_active:
                st.error("🔴 SYSTEM OFFLINE - Sensor disconnected. Cannot verify current water level.")
            elif latest.get('alert_status', False):
                alert_type = latest.get('alert_type', 'unknown')
                if alert_type == 'blockage_detected':
                    st.error(f"🚨 BLOCKAGE DETECTED! ({latest['capacity_pct']:.1f}% capacity) - Type: blockage_detected")
                elif alert_type == 'blockage_cleared':
                    st.success(f"✅ BLOCKAGE CLEARED (Regularization Alert) - Type: blockage_cleared")
                else:
                    st.info(f"📊 Normal Reading - Capacity: {latest['capacity_pct']:.1f}%")
            else:
                if latest['capacity_pct'] >= DANGER_PCT * 100:
                    st.error(f"🔴 CRITICAL CAPACITY! Basin at {latest['capacity_pct']:.1f}% ({latest['water_level_cm']:.1f} cm)")
                elif latest['capacity_pct'] >= ALERT_PCT * 100:
                    st.warning(f"🟠 HIGH LEVEL! Basin at {latest['capacity_pct']:.1f}% ({latest['water_level_cm']:.1f} cm)")
                elif latest['capacity_pct'] >= WARN_PCT * 100:
                    st.warning(f"🟡 ELEVATED LEVEL! Basin at {latest['capacity_pct']:.1f}% ({latest['water_level_cm']:.1f} cm)")
                else:
                    st.success(f"🟢 NORMAL - Basin at {latest['capacity_pct']:.1f}% capacity")
        
        with col_alert2:
            if not is_system_active:
                st.metric("Alert Status", "🔴 UNKNOWN")
            else:
                st.metric("Alert Status", "🚨 ACTIVE" if latest.get('alert_status', False) else "✓ Normal", 
                         latest.get('alert_type', 'N/A'))
        
        st.markdown("---")
        
        st.subheader("🗺️ Sensor Location Map")
        try:
            sensor_map = create_sensor_map(df, is_system_active)
            if sensor_map:
                st_folium(sensor_map, width=1400, height=500)
            else:
                st.warning("⏳ **GPS Not Yet Locked** - Awaiting live coordinates.")
                try:
                    m_fallback = folium.Map(location=[14.5994, 120.9842], zoom_start=16, tiles="OpenStreetMap")
                    folium.Marker(location=[14.5994, 120.9842], popup="Standby Location", icon=folium.Icon(color="gray", icon="info", prefix="fa")).add_to(m_fallback)
                    st_folium(m_fallback, width=1400, height=500)
                except:
                    st.info("📍 Default: Manila, Philippines")
        except Exception as e:
            st.error(f"Map error: {e}")
        
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📈 Water Level Over Time")
            fig_trend = go.Figure()
            valid_dates_df = df.dropna(subset=['recorded_at'])
            fig_trend.add_trace(go.Scatter(x=valid_dates_df['recorded_at'], y=valid_dates_df['water_level_cm'], mode='lines+markers',
                                          name='Level', line=dict(color='#0066cc', width=2), fill='tozeroy'))
            fig_trend.add_hline(y=WARN_THRESHOLD, line_dash="dash", line_color="yellow", annotation_text="Warning (25%)")
            fig_trend.add_hline(y=ALERT_THRESHOLD, line_dash="dash", line_color="orange", annotation_text="Alert (50%)")
            fig_trend.add_hline(y=DANGER_THRESHOLD, line_dash="dash", line_color="red", annotation_text="Danger (75%)")
            fig_trend.update_layout(height=400)
            st.plotly_chart(fig_trend, use_container_width=True)
        
        with col2:
            st.subheader("📊 Levels by Sensor")
            sensor_stats = df_all.groupby('sensor_id')['water_level_cm'].mean().reset_index()
            fig_bar = px.bar(sensor_stats, x='sensor_id', y='water_level_cm', color='water_level_cm',
                            color_continuous_scale='RdYlGn_r')
            fig_bar.update_layout(height=400)
            st.plotly_chart(fig_bar, use_container_width=True)
        
        st.markdown("---")
        
        st.subheader("🚨 Alert History")
        alerts_df = df[df['alert_status'] == True].copy() if 'alert_status' in df.columns else pd.DataFrame()
        
        if not alerts_df.empty:
            alerts_display = alerts_df[['recorded_at', 'sensor_id', 'water_level_cm', 'alert_type', 'capacity_percentage']].copy()
            alerts_display['recorded_at'] = alerts_display['recorded_at'].dt.strftime('%Y-%m-%d %H:%M:%S')
            alerts_display = alerts_display.sort_values('recorded_at', ascending=False)
            st.dataframe(alerts_display, use_container_width=True, hide_index=True)
            st.metric("Total Alerts", len(alerts_df))
        else:
            st.info("✓ No alerts recorded during this period")
        
        st.markdown("---")
        
        st.subheader("🗂️ All Readings")
        display_df = df[['recorded_at', 'sensor_id', 'water_level_cm']].copy()
        display_df['recorded_at'] = display_df['recorded_at'].dt.strftime('%Y-%m-%d %H:%M:%S')
        st.dataframe(display_df.sort_values('recorded_at', ascending=False), use_container_width=True, hide_index=True)
        
        st.markdown("---")
        
        st.subheader("💾 Download/Export Data")
        col1, col2, col3 = st.columns(3)
        with col1:
            csv = df.to_csv(index=False)
            st.download_button(" Download CSV", csv, file_name=f"water_levels_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", mime="text/csv")
        with col2:
            try:
                api_base = API_URL.rsplit('/api/', 1)[0]
                response = requests.get(f"{api_base}/api/export/geojson", timeout=5)
                if response.status_code == 200:
                    st.download_button("️ Download GeoJSON", response.text, file_name=f"water_levels_{datetime.now().strftime('%Y%m%d_%H%M%S')}.geojson", mime="application/json")
            except:
                st.info("GeoJSON unavailable")
        with col3:
            st.info("💡 Import GeoJSON into QGIS for spatial analysis")

# ==========================================
# EMPTY STATE (When Database is Cleared)
# ==========================================
else:
    st.info("📡 System Active: Listening for live hardware transmissions...")
    
    # Empty Metrics Placeholder
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Latest Reading", "-- cm", "STANDBY", delta_color="off")
    col2.metric("Average", "-- cm")
    col3.metric("Peak", "-- cm")
    col4.metric("Minimum", "-- cm")
    col5.metric("Power", "-- W")
    
    st.markdown("---")
    
    # Empty System Health Placeholder
    st.subheader("🖥️ System & Device Health")
    col_sys1, col_sys2, col_sys3 = st.columns(3)
    
    with col_sys1:
        st.markdown("**📡 Network Status**")
        st.warning("🟡 Waiting for data...")
            
    with col_sys2:
        st.markdown("**🛰️ GPS Status**")
        st.warning("🟡 Waiting for data...")
            
    with col_sys3:
        st.markdown("**🔋 Power Sensor**")
        st.warning("🟡 Waiting for data...")

    col_list1, col_list2 = st.columns(2)
    with col_list1:
        st.markdown("##### 🟢 Active Sensors")
        st.write("*None*")
            
    with col_list2:
        st.markdown("##### 🔴 Inactive Sensors")
        st.write(f"- {ACTIVE_SENSOR_ID} *(Awaiting first connection...)*")

    st.markdown("---")
    
    # Empty Map Placeholder
    st.subheader("🗺️ Sensor Location Map")
    st.caption("Awaiting live GPS. Default: Manila, Philippines")
    try:
        m_empty = folium.Map(location=[14.5994, 120.9842], zoom_start=16, tiles="OpenStreetMap")
        folium.Marker(
            location=[14.5994, 120.9842],
            popup="Standby Location - Awaiting Data",
            icon=folium.Icon(color="gray", icon="question", prefix="fa")
        ).add_to(m_empty)
        st_folium(m_empty, width=1400, height=500)
    except:
        st.info("📍 Default: Manila, Philippines")
        
    st.markdown("---")
    
    # Empty Charts Placeholder
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📈 Water Level Over Time")
        fig_trend_empty = go.Figure()
        fig_trend_empty.add_hline(y=WARN_THRESHOLD, line_dash="dash", line_color="yellow", annotation_text="Warning (25%)")
        fig_trend_empty.add_hline(y=ALERT_THRESHOLD, line_dash="dash", line_color="orange", annotation_text="Alert (50%)")
        fig_trend_empty.add_hline(y=DANGER_THRESHOLD, line_dash="dash", line_color="red", annotation_text="Danger (75%)")
        fig_trend_empty.update_layout(height=400, yaxis_range=[0, 50])
        st.plotly_chart(fig_trend_empty, use_container_width=True)
    
    with col2:
        st.subheader("📊 Levels by Sensor")
        fig_bar_empty = go.Figure()
        fig_bar_empty.update_layout(height=400, xaxis_title="Sensor ID", yaxis_title="Water Level (cm)", yaxis_range=[0, 50])
        st.plotly_chart(fig_bar_empty, use_container_width=True)
        
    st.markdown("---")
    
    st.subheader("🚨 Alert History")
    st.info("✓ No alerts recorded")
    
    st.markdown("---")
    
    st.subheader("🗂️ All Readings")
    st.caption("Awaiting live sensor data logs...")

# --- SYSTEM MANAGEMENT MODULE ---
st.markdown("---")
st.subheader("⚙️ System Management")

col_m1, col_m2 = st.columns([1, 4])
with col_m1:
    if st.button("🔄 Manual Refresh"):
        st.cache_data.clear()
        st.rerun()

with col_m2:
    if st.button("🗑️ Clear All Logs (Reset Database)", type="primary"):
        try:
            api_base = API_URL.rsplit('/api/', 1)[0]
            res = requests.post(f"{api_base}/api/clear-logs", timeout=5)
            if res.status_code == 200:
                st.cache_data.clear()
                st.success("Database wiped successfully! Waiting for fresh data...")
                st.rerun()
            else:
                st.error("Failed to clear logs.")
        except Exception as e:
            st.error(f"Error connecting to server: {e}")

if raw_data:
    st.caption(f"📊 Total readings: {len(df_all)} | Updated: {current_pst.strftime('%H:%M:%S PST')}")
