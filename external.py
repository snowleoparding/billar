import requests
from dataclasses import dataclass
from datetime import date
import pandas as pd
import streamlit as st
import altair as alt

BASELINE_YEAR = 2024
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# ----------------------------
# Style Tweaks & Cat Silhouette
# ----------------------------
st.set_page_config(page_title="Daylight & Energy", layout="wide")

# Grey headings + slightly smaller margins
st.markdown("""
    <style>
    h2, h3, .stSubheader, .stMarkdown {
        color: #555 !important;
        font-weight: 600 !important;
        margin-top: 0.3rem;
        margin-bottom: 0.3rem;
    }
    </style>
""", unsafe_allow_html=True)

# Title with cat silhouette
st.markdown("""
    <div style="display:flex; justify-content:space-between; align-items:center;">
        <h1 style="margin: 0;">🌤️ External Lighting Energy Calculator</h1>
        <img src="https://www.svgrepo.com/show/527635/cat.svg" 
             alt="cat" width="45" style="opacity:0.4; margin-left:10px;">
    </div>
""", unsafe_allow_html=True)

st.caption("Compare two cities | Night-only vs Hourly GHI-based lighting control")

# ----------------------------
# City List (UK Expanded)
# ----------------------------
@dataclass(frozen=True)
class City:
    name: str
    country: str
    lat: float
    lon: float
    tz: str

ALL_CITIES = [
    # UK
    City("London", "UK", 51.5074, -0.1278, "Europe/London"),
    City("Edinburgh", "UK", 55.9533, -3.1883, "Europe/London"),
    City("Glasgow", "UK", 55.8642, -4.2518, "Europe/London"),
    City("Aberdeen", "UK", 57.1497, -2.0943, "Europe/London"),
    City("Inverness", "UK", 57.4778, -4.2247, "Europe/London"),
    City("Dundee", "UK", 56.4620, -2.9707, "Europe/London"),
    City("Belfast", "UK", 54.5973, -5.9301, "Europe/London"),
    City("Derry", "UK", 55.0068, -7.3183, "Europe/London"),
    City("Cardiff", "UK", 51.4816, -3.1791, "Europe/London"),
    City("Manchester", "UK", 53.4808, -2.2426, "Europe/London"),
    City("Birmingham", "UK", 52.4862, -1.8904, "Europe/London"),
    City("Newcastle upon Tyne", "UK", 54.9783, -1.6178, "Europe/London"),
    City("Plymouth", "UK", 50.3755, -4.1427, "Europe/London"),

    # Europe
    City("Madrid", "Spain", 40.4168, -3.7038, "Europe/Madrid"),
    City("Oslo", "Norway", 59.9139, 10.7522, "Europe/Oslo"),

    # India
    City("Delhi", "India", 28.6139, 77.2090, "Asia/Kolkata"),
    City("Kochi", "India", 9.9312, 76.2673, "Asia/Kolkata"),
]

CITY_NAMES = [f"{c.name}, {c.country}" for c in ALL_CITIES]

# ----------------------------
# Sidebar
# ----------------------------
with st.sidebar:
    st.header("📍 Select Cities")
    city_choice_1 = st.selectbox("City 1", CITY_NAMES, index=0)
    city_choice_2 = st.selectbox("City 2 (optional)", ["None"] + CITY_NAMES, index=0)

    st.markdown("---")
    st.header("💡 Lighting Inputs")
    facade_area = st.number_input("Façade area (m²)", min_value=0.0, value=1000.0, step=10.0)
    lpd_w_per_m2 = st.number_input("Lighting Power Density (W/m²)", min_value=0.0, value=1.6, step=0.1)
    control_factor = st.slider("Control factor (0–1)", 0.0, 1.0, 0.8, 0.05)

    st.markdown("---")
    st.header("🌞 Hourly GHI Control Thresholds")
    ghi_on_threshold = st.number_input("Lights ON below (W/m²)", min_value=0.0, value=10.0, step=1.0)
    ghi_off_threshold = st.number_input("Lights OFF above (W/m²)", min_value=0.0, value=50.0, step=5.0)

st.markdown(
    f"> ℹ️ **Night-only:** Lights ON during dark hours only.  \n"
    f"**Hourly GHI:** Lights turn ON when GHI < **{ghi_on_threshold:.0f} W/m²** "
    f"and stay ON until GHI > **{ghi_off_threshold:.0f} W/m²**.  \n"
    f"Data source: [Open-Meteo Weather API](https://open-meteo.com/en/docs)",
    unsafe_allow_html=True,
)

# ----------------------------
# Weather & Data Functions
# ----------------------------
def fetch_current_weather(city):
    params = {"latitude": city.lat, "longitude": city.lon, "current_weather": True, "timezone": city.tz}
    r = requests.get(OPEN_METEO_FORECAST_URL, params=params, timeout=30)
    r.raise_for_status()
    return r.json()["current_weather"]

def weather_icon(code):
    if code in [0]: return "☀️ Clear"
    if code in [1, 2]: return "🌤️ Partly Cloudy"
    if code in [3]: return "☁️ Overcast"
    if code in [45, 48]: return "🌫️ Fog"
    if code in [51, 53, 55, 61, 63, 65]: return "🌧️ Rain"
    if code in [71, 73, 75, 77]: return "❄️ Snow"
    return "🌙"

@st.cache_data(ttl=7*24*3600)
def fetch_city_daily(lat, lon, tz, year):
    params = {"latitude": lat, "longitude": lon, "start_date": f"{year}-01-01", "end_date": f"{year}-12-31",
              "daily": "daylight_duration", "timezone": tz}
    r = requests.get(OPEN_METEO_ARCHIVE_URL, params=params, timeout=30)
    r.raise_for_status()
    daily = r.json()["daily"]
    df = pd.DataFrame({"date": pd.to_datetime(daily["time"]),
                       "daylight_h": [x / 3600 for x in daily["daylight_duration"]]})
    df["night_h"] = 24 - df["daylight_h"]
    return df

@st.cache_data(ttl=7*24*3600)
def fetch_city_hourly(lat, lon, tz, year):
    params = {"latitude": lat, "longitude": lon, "start_date": f"{year}-01-01", "end_date": f"{year}-12-31",
              "hourly": "shortwave_radiation", "timezone": tz}
    r = requests.get(OPEN_METEO_ARCHIVE_URL, params=params, timeout=60)
    r.raise_for_status()
    hourly = r.json()["hourly"]
    return pd.DataFrame({"datetime": pd.to_datetime(hourly["time"]), "GHI_Wm2": hourly["shortwave_radiation"]})

def monthly_totals_daily(df):
    df["month"] = df["date"].dt.month
    agg = df.groupby("month").sum(numeric_only=True).reset_index()
    agg["Month"] = pd.Categorical(agg["month"].apply(lambda m: date(2000, m, 1).strftime("%B")),
        categories=["January","February","March","April","May","June","July",
                    "August","September","October","November","December"], ordered=True)
    return agg.sort_values("month")

def monthly_lights_on_from_hourly(df, on_thr, off_thr):
    lights_on = False
    states = []
    for ghi in df["GHI_Wm2"]:
        if not lights_on and ghi < on_thr:
            lights_on = True
        elif lights_on and ghi > off_thr:
            lights_on = False
        states.append(lights_on)
    df["lights_on_flag"] = states
    df["lights_on_h"] = df["lights_on_flag"].astype(int)
    df["month"] = df["datetime"].dt.month
    agg = df.groupby("month")["lights_on_h"].sum().reset_index()
    agg["Month"] = pd.Categorical(agg["month"].apply(lambda m: date(2000, m, 1).strftime("%B")),
        categories=["January","February","March","April","May","June","July",
                    "August","September","October","November","December"], ordered=True)
    return agg.sort_values("month")

def process_city(city, on_thr, off_thr):
    daily = fetch_city_daily(city.lat, city.lon, city.tz, BASELINE_YEAR)
    hourly = fetch_city_hourly(city.lat, city.lon, city.tz, BASELINE_YEAR)
    agg = monthly_totals_daily(daily)
    agg["lights_on_h"] = agg["night_h"]
    monthly_ghi = monthly_lights_on_from_hourly(hourly.copy(), on_thr, off_thr)
    agg = agg.merge(monthly_ghi, on=["month", "Month"], suffixes=("", "_ghi"))
    agg["Energy Night (kWh)"] = (lpd_w_per_m2 * facade_area * agg["lights_on_h"] * control_factor) / 1000
    agg["Energy GHI (kWh)"] = (lpd_w_per_m2 * facade_area * agg["lights_on_h_ghi"] * control_factor) / 1000
    return agg

# ----------------------------
# Run Calculations
# ----------------------------
city_obj_1 = ALL_CITIES[CITY_NAMES.index(city_choice_1)]
agg1 = process_city(city_obj_1, ghi_on_threshold, ghi_off_threshold)
weather1 = fetch_current_weather(city_obj_1)

agg2, weather2 = None, None
if city_choice_2 != "None":
    city_obj_2 = ALL_CITIES[CITY_NAMES.index(city_choice_2)]
    agg2 = process_city(city_obj_2, ghi_on_threshold, ghi_off_threshold)
    weather2 = fetch_current_weather(city_obj_2)

# ----------------------------
# Weather Cards
# ----------------------------
st.subheader("🌍 Current Weather")
col1, col2 = st.columns(2)
with col1:
    st.markdown(f"### {city_choice_1}")
    st.markdown(f"{weather_icon(weather1['weathercode'])}  **{weather1['temperature']}°C**, {weather1['windspeed']} km/h wind")
if agg2 is not None and not agg2.empty:
    with col2:
        st.markdown(f"### {city_choice_2}")
        st.markdown(f"{weather_icon(weather2['weathercode'])}  **{weather2['temperature']}°C**, {weather2['windspeed']} km/h wind")

# ----------------------------
# Metric Cards
# ----------------------------
st.subheader("📊 Annual Metrics")
def show_metrics(city_name, agg):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"☀️ {city_name} Daylight", f"{agg['daylight_h'].sum():,.0f} h")
    c2.metric(f"🌌 {city_name} Night", f"{agg['night_h'].sum():,.0f} h")
    c3.metric(f"⚡ Night-only", f"{agg['Energy Night (kWh)'].sum():,.0f} kWh")
    c4.metric(f"⚡ Hourly GHI", f"{agg['Energy GHI (kWh)'].sum():,.0f} kWh")

show_metrics(city_choice_1, agg1)
if agg2 is not None and not agg2.empty:
    show_metrics(city_choice_2, agg2)

st.caption(f"🔧 Calculated with ON < **{ghi_on_threshold:.0f} W/m²**, OFF > **{ghi_off_threshold:.0f} W/m²** (hysteresis enabled).")

# ----------------------------
# Line Chart (Fixed Y-axis)
# ----------------------------
st.markdown("### 🌗 Daylight vs Dark Hours")
line_data = agg1[["Month","daylight_h","lights_on_h"]].melt("Month", var_name="Type", value_name="Hours")
line_data["City"] = city_choice_1
if agg2 is not None and not agg2.empty:
    line2 = agg2[["Month","daylight_h","lights_on_h"]].melt("Month", var_name="Type", value_name="Hours")
    line2["City"] = city_choice_2
    line_data = pd.concat([line_data, line2])

line_chart = (
    alt.Chart(line_data)
    .mark_line(point=True, interpolate="monotone")
    .encode(
        x=alt.X("Month", axis=alt.Axis(labelAngle=0)),
        y=alt.Y("Hours", scale=alt.Scale(domain=[100, 600])),  # Fixed range
        color="City",
        strokeDash="Type",
        tooltip=["City","Month","Type","Hours"]
    )
    .properties(height=450)
)
st.altair_chart(line_chart, use_container_width=True)

# ----------------------------
# Monthly Table
# ----------------------------
st.markdown("### 📑 Monthly Data Table")
if agg2 is not None and not agg2.empty:
    merged = agg1[["Month","lights_on_h","lights_on_h_ghi","Energy Night (kWh)","Energy GHI (kWh)"]].merge(
        agg2[["Month","lights_on_h","lights_on_h_ghi","Energy Night (kWh)","Energy GHI (kWh)"]],
        on="Month", suffixes=(f" ({city_choice_1})", f" ({city_choice_2})"))
    st.dataframe(merged.round(1), use_container_width=True)
else:
    st.dataframe(agg1[["Month","lights_on_h","lights_on_h_ghi","Energy Night (kWh)","Energy GHI (kWh)"]].round(1),
                 use_container_width=True)

