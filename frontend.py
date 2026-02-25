"""
FRONTEND - Streamlit Dashboard
Displays real-time water level data with maps, charts, and alerts
"""

import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import folium
from streamlit_folium import st_folium
from config import API_URL
from datetime import datetime

st.set_page_config(page_title="A.H.H.H. Blockage Detection", page_icon="🌊", layout="wide")
st.title("A.H.H.H. Blockage Detection System")
st.subheader("Real-Time Storm Drain Monitoring with Power Analysis")

# Initialize session state for polling
if 'last_update' not in st.session_state:
    st.session_state.last_update = 0
if 'auto_refresh' not in st.session_state:
    st.session_state.auto_refresh = True

# Basin specs - 18.7 inches (47.5 cm) tall
# Multi-level classification: 25%, 50%, 75% escalation per research methodology
# Per spec: thresholds are percentage-based for scalability and interpretation
BASIN_HEIGHT_CM = 47.5
# Alert escalation levels
WARN_PCT = 0.25   # 25% capacity = 11.875 cm = 4.7" (blockage detected)
ALERT_PCT = 0.50  # 50% capacity = 23.75 cm = 9.35" (escalation level)
DANGER_PCT = 0.75 # 75% capacity = 35.625 cm = 14.025" (critical level)

WARN_THRESHOLD = BASIN_HEIGHT_CM * WARN_PCT
ALERT_THRESHOLD = BASIN_HEIGHT_CM * ALERT_PCT
DANGER_THRESHOLD = BASIN_HEIGHT_CM * DANGER_PCT

# Only show data from the active sensor
ACTIVE_SENSOR_ID = "AHHH_Arduino_01"
REFRESH_INTERVAL_SECONDS = 5  # Auto-refresh every 5 seconds

@st.cache_data(ttl=5)
def fetch_data(source='all'):
    """Pull the latest data from the Flask API with caching for smooth updates
    
    Args:
        source: 'all' (default), 'real', or 'simulated'
    """
    try:
        response = requests.get(f"{API_URL}?source={source}", timeout=5)
        all_data = response.json().get("data", []) if response.status_code == 200 else []
        
        # Filter to only active sensor to avoid old test data
        filtered_data = [d for d in all_data if d.get('sensor_id') == ACTIVE_SENSOR_ID]
        return filtered_data if filtered_data else all_data  # Fallback to all if no matches

    except requests.exceptions.RequestException:
        # If the API isn't running, let the user know
        st.error("❌ Cannot connect to backend API. Is Flask running?")
        return []

def get_status_color(capacity_pct):
    """Determine if we're normal/warning/alert/danger and pick the display emoji + color
    
    Args:
        capacity_pct: Basin capacity as a percentage (0-100)
    """
    if capacity_pct >= DANGER_PCT * 100:
        return f"🔴 DANGER ({capacity_pct:.1f}%)", "red"
    elif capacity_pct >= ALERT_PCT * 100:
        return f"🟠 ALERT ({capacity_pct:.1f}%)", "orange"
    elif capacity_pct >= WARN_PCT * 100:
        return f"🟡 WARNING ({capacity_pct:.1f}%)", "gold"
    else:
        return f"🟢 NORMAL ({capacity_pct:.1f}%)", "green"

def get_marker_color(capacity_pct):
    """Pick the color for map pins based on capacity percentage
    
    Args:
        capacity_pct: Basin capacity as a percentage (0-100)
    """
    if capacity_pct >= DANGER_PCT * 100:
        return "red"
    elif capacity_pct >= ALERT_PCT * 100:
        return "orange"
    elif capacity_pct >= WARN_PCT * 100:
        return "yellow"
    else:
        return "green"

def create_sensor_map(df):
    """Build map for active sensor with current reading"""
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
        
        folium.Circle(location=[lat, lon], radius=200, color='blue', fill=True, fillOpacity=0.1, weight=2).add_to(m)
        
        marker_color = get_marker_color(latest['capacity_pct'])
        
        folium.Marker(
            location=[lat, lon],
            popup=f"<b>{latest['sensor_id']}</b><br>Level: {latest['water_level_cm']:.1f}cm ({latest['capacity_pct']:.1f}%)",
            icon=folium.Icon(color=marker_color, icon="tint", prefix="fa")
        ).add_to(m)
        
        return m
    except Exception as e:
        print(f"Map error: {e}")
        return None

raw_data = fetch_data()

if raw_data:
    df = pd.DataFrame(raw_data)
    df['recorded_at'] = pd.to_datetime(df['recorded_at'])
    df = df.sort_values('recorded_at')
    
    # Ensure alert fields exist (for compatibility with older data)
    if 'capacity_percentage' not in df.columns:
        df['capacity_percentage'] = (df['water_level_cm'] / BASIN_HEIGHT_CM) * 100
    if 'alert_status' not in df.columns:
        df['alert_status'] = False
    if 'alert_type' not in df.columns:
        df['alert_type'] = 'normal_reading'
    
    df['capacity_pct'] = df['capacity_percentage']
    
    latest = df.iloc[-1]
    status_text, status_color = get_status_color(latest['capacity_pct'])
    
    # Metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Latest Reading", f"{latest['water_level_cm']} cm", status_text, delta_color="off")
    with col2:
        avg_level = df['water_level_cm'].mean()
        st.metric("Average", f"{avg_level:.1f} cm", f"{latest['water_level_cm'] - avg_level:.1f} cm")
    with col3:
        # Show the highest reading we've seen
        st.metric("Peak", f"{df['water_level_cm'].max():.1f} cm")
    with col4:
        # And the lowest
        st.metric("Minimum", f"{df['water_level_cm'].min():.1f} cm")
    with col5:
        # Power consumption
        latest_power = latest.get('power_consumption_watts', 0.0)
        st.metric("Power", f"{latest_power:.2f} W")
    
    st.markdown("---")
    
    # Alert section - show system status based on both capacity and alert_status 
    # Display hardware-triggered alerts vs capacity-based alerts
    col_alert1, col_alert2 = st.columns([2, 1])
    
    with col_alert1:
        if latest.get('alert_status', False):
            alert_type = latest.get('alert_type', 'unknown')
            if alert_type == 'blockage_detected':
                st.error(f"🚨 BLOCKAGE DETECTED! ({latest['capacity_pct']:.1f}% capacity) - Type: blockage_detected")
            elif alert_type == 'blockage_cleared':
                st.success(f"✅ BLOCKAGE CLEARED (Regularization Alert) - Type: blockage_cleared")
            else:
                st.info(f"📊 Normal Reading - Capacity: {latest['capacity_pct']:.1f}%")
        else:
            # Capacity-based warnings
            if latest['capacity_pct'] >= DANGER_PCT * 100:
                st.error(f"🔴 CRITICAL CAPACITY! Basin at {latest['capacity_pct']:.1f}% ({latest['water_level_cm']:.1f} cm)")
            elif latest['capacity_pct'] >= ALERT_PCT * 100:
                st.warning(f"🟠 HIGH LEVEL! Basin at {latest['capacity_pct']:.1f}% ({latest['water_level_cm']:.1f} cm)")
            elif latest['capacity_pct'] >= WARN_PCT * 100:
                st.warning(f"🟡 ELEVATED LEVEL! Basin at {latest['capacity_pct']:.1f}% ({latest['water_level_cm']:.1f} cm)")
            else:
                st.success(f"🟢 NORMAL - Basin at {latest['capacity_pct']:.1f}% capacity")
    
    with col_alert2:
        st.metric("Alert Status", "🚨 ACTIVE" if latest.get('alert_status', False) else "✓ Normal", 
                 latest.get('alert_type', 'N/A'))
    
    st.markdown("---")
    
    # Show where all the sensors are located
    st.subheader("🗺️ Sensor Location Map")
    try:
        sensor_map = create_sensor_map(df)
        if sensor_map:
            st_folium(sensor_map, width=1400, height=500)
        else:
            # Show why coordinates aren't available
            st.warning("""
            ⏳ **GPS Not Yet Locked**
            
            The hardware is searching for GPS coordinates. During this time:
            - Water level readings will show on charts
            - Map location will default to Manila, Philippines (below)
            - Once GPS locks, the map will update automatically
            
            GPS lock typically takes 30-60 seconds on first boot.
            """)
            
            # Show the default standby map
            try:
                m_fallback = folium.Map(location=[14.5994, 120.9842], zoom_start=16, tiles="OpenStreetMap")
                folium.Marker(
                    location=[14.5994, 120.9842],
                    popup="Standby Location - Awaiting GPS",
                    icon=folium.Icon(color="blue", icon="info", prefix="fa")
                ).add_to(m_fallback)
                st_folium(m_fallback, width=1400, height=500)
            except:
                st.info("📍 Default: Manila, Philippines (14.5994, 120.9842)")
    except Exception as e:
        st.error(f"Map error: {e}")
    
    st.markdown("---")
    
    # Charts section
    col1, col2 = st.columns(2)
    
    with col1:
        # Trend line showing water level over time with threshold lines
        st.subheader("📈 Water Level Over Time")
        fig_trend = go.Figure()
        fig_trend.add_trace(go.Scatter(x=df['recorded_at'], y=df['water_level_cm'], mode='lines+markers',
                                      name='Level', line=dict(color='#0066cc', width=2), fill='tozeroy'))
        # Add the threshold lines so you can see when we're approaching danger
        fig_trend.add_hline(y=WARN_THRESHOLD, line_dash="dash", line_color="yellow", annotation_text="Warning (25%)")
        fig_trend.add_hline(y=ALERT_THRESHOLD, line_dash="dash", line_color="orange", annotation_text="Alert (50%)")
        fig_trend.add_hline(y=DANGER_THRESHOLD, line_dash="dash", line_color="red", annotation_text="Danger (75%)")
        fig_trend.update_layout(height=400)
        st.plotly_chart(fig_trend, use_container_width=True)
    
    with col2:
        # Bar chart comparing average levels across sensors
        st.subheader("📊 Levels by Sensor")
        sensor_stats = df.groupby('sensor_id')['water_level_cm'].mean().reset_index()
        fig_bar = px.bar(sensor_stats, x='sensor_id', y='water_level_cm', color='water_level_cm',
                        color_continuous_scale='RdYlGn_r')
        fig_bar.update_layout(height=400)
        st.plotly_chart(fig_bar, use_container_width=True)
    
    st.markdown("---")
    
    # Quick stats
    st.subheader("📋 Stats")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Readings", len(df))
    col2.metric("Active Sensors", df['sensor_id'].nunique())
    # Calculate how long the data collection has been running
    col3.metric("Duration", f"{(df['recorded_at'].max() - df['recorded_at'].min()).total_seconds() / 3600:.1f}h")
    
    st.markdown("---")
    
    # Alert history section (alert response time tracking)
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
    
    # Data table
    st.subheader("🗂️ All Readings")
    display_df = df[['recorded_at', 'sensor_id', 'water_level_cm']].copy()
    display_df['recorded_at'] = display_df['recorded_at'].dt.strftime('%Y-%m-%d %H:%M:%S')
    # Show newest first
    st.dataframe(display_df.sort_values('recorded_at', ascending=False), use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    # Download options
    st.subheader("💾 Download/Export Data")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Export as CSV for Excel/spreadsheets
        csv = df.to_csv(index=False)
        st.download_button("� Download CSV", csv,
                          file_name=f"water_levels_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                          mime="text/csv")
    
    with col2:
        # Export as GeoJSON for QGIS/mapping
        try:
            api_base = API_URL.rsplit('/api/', 1)[0]
            response = requests.get(f"{api_base}/api/export/geojson", timeout=5)
            if response.status_code == 200:
                st.download_button("�️ Download GeoJSON", response.text,
                                  file_name=f"water_levels_{datetime.now().strftime('%Y%m%d_%H%M%S')}.geojson",
                                  mime="application/json")
        except:
            st.info("GeoJSON unavailable")
    
    with col3:
        st.info("💡 Import GeoJSON into QGIS for spatial analysis")
    
    st.markdown("---")
    
    # Auto-refresh mechanism with smooth polling
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(f"📊 Showing data from: **{ACTIVE_SENSOR_ID}** | Total readings: {len(df)} | Updated: {datetime.now().strftime('%H:%M:%S')}")
    with col2:
        if st.button("🔄 Manual Refresh"):
            st.cache_data.clear()
            st.rerun()

else:
    # Standby State (No data yet)
    st.info("📡 System Active: Listening for live hardware transmissions...")
    
    # Empty metric placeholders
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Latest Reading", "-- cm", "STANDBY", delta_color="off")
    col2.metric("Average", "-- cm")
    col3.metric("Peak", "-- cm")
    col4.metric("Minimum", "-- cm")
    col5.metric("Power", "-- W")
    
    st.markdown("---")
    
    # 1. Empty Map Layout
    st.subheader("🗺️ Sensor Location Map")
    st.caption("Awaiting live GPS. Default: Manila, Philippines")
    try:
        m_empty = folium.Map(
            location=[14.5994, 120.9842],
            zoom_start=16,
            tiles="OpenStreetMap"
        )
        
        folium.Circle(
            location=[14.5994, 120.9842],
            radius=200,
            color='blue',
            fill=True,
            fillOpacity=0.1,
            weight=2
        ).add_to(m_empty)
        
        folium.Marker(
            location=[14.5994, 120.9842],
            popup="Awaiting hardware data",
            icon=folium.Icon(color="gray", icon="question", prefix="fa")
        ).add_to(m_empty)
        
        st_folium(m_empty, width=1400, height=500)
    except Exception as e:
        st.error(f"Map display failed: {str(e)}")
    
    st.markdown("---")
    
    # 2. Empty Chart Layouts
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 Water Level Over Time")
        fig_trend_empty = go.Figure()
        # Keep the threshold lines visible to show the system's logic
        fig_trend_empty.add_hline(y=WARN_THRESHOLD, line_dash="dash", line_color="yellow", annotation_text="Warning (25%)")
        fig_trend_empty.add_hline(y=ALERT_THRESHOLD, line_dash="dash", line_color="orange", annotation_text="Alert (50%)")
        fig_trend_empty.add_hline(y=DANGER_THRESHOLD, line_dash="dash", line_color="red", annotation_text="Danger (75%)")
        # Lock the Y-axis to 50cm so it matches the physical catch basin height
        fig_trend_empty.update_layout(height=400, xaxis_title="Time", yaxis_title="Water Level (cm)", yaxis_range=[0, 50])
        st.plotly_chart(fig_trend_empty, use_container_width=True)
        
    with col2:
        st.subheader("📊 Levels by Sensor")
        fig_bar_empty = go.Figure()
        fig_bar_empty.update_layout(height=400, xaxis_title="Sensor ID", yaxis_title="Water Level (cm)", yaxis_range=[0, 50])
        st.plotly_chart(fig_bar_empty, use_container_width=True)
        
    st.markdown("---")
    st.subheader("🗂️ Logs")
    st.caption("Awaiting live sensor data logs...")
