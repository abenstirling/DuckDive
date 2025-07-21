from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
import sys
import os
from datetime import datetime, timedelta
import asyncio
import sqlite3
import json
from typing import Optional

# Add surfpy to path
sys.path.append('./surfpy')
import surfpy

app = FastAPI(title="Tamarack Surf Forecast")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Database setup
DB_PATH = "tamarack_cache.db"

def init_db():
    """Initialize SQLite database for caching"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS wave_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            data TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tide_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            data TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    ''')
    
    conn.commit()
    conn.close()

def get_cached_data(table_name: str) -> Optional[dict]:
    """Get cached data if still valid"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    now = datetime.now().isoformat()
    cursor.execute(f'''
        SELECT data FROM {table_name} 
        WHERE expires_at > ? 
        ORDER BY timestamp DESC 
        LIMIT 1
    ''', (now,))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return json.loads(result[0])
    return None

def cache_data(table_name: str, data: dict, hours_valid: int = 1):
    """Cache data with expiration"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    now = datetime.now()
    expires = now + timedelta(hours=hours_valid)
    
    # Clear old data
    cursor.execute(f'DELETE FROM {table_name} WHERE expires_at <= ?', (now.isoformat(),))
    
    # Insert new data
    cursor.execute(f'''
        INSERT INTO {table_name} (timestamp, data, expires_at)
        VALUES (?, ?, ?)
    ''', (now.isoformat(), json.dumps(data), expires.isoformat()))
    
    conn.commit()
    conn.close()

# Tamarack location
TAMARACK = {
    "name": "Tamarack",
    "lat": 33.146635,
    "lng": -117.345818,
    "county": "San Diego"
}

async def get_tamarack_wave_forecast():
    """Fetch wave forecast with caching"""
    # Try cache first
    cached = get_cached_data('wave_data')
    if cached:
        print("Using cached wave data")
        return cached
    
    try:
        print(f"Fetching fresh Tamarack wave data...")
        location = surfpy.Location(TAMARACK['lat'], TAMARACK['lng'], altitude=30.0, name='Tamarack')
        location.depth = 30.0
        location.angle = 225.0
        location.slope = 0.02
        
        wave_model = surfpy.wavemodel.us_west_coast_gfs_wave_model()
        wave_grib_data = wave_model.fetch_grib_datas(0, 120)  # 5 days
        
        if wave_grib_data:
            raw_wave_data = wave_model.parse_grib_datas(location, wave_grib_data)
            if raw_wave_data:
                data = wave_model.to_buoy_data(raw_wave_data)
                if data:
                    for dat in data:
                        dat.solve_breaking_wave_heights(location)
                        dat.change_units(surfpy.units.Units.english)
                    
                    # Convert to serializable format
                    wave_list = []
                    for d in data:
                        wave_list.append({
                            'time': d.date.isoformat(),
                            'height': round(d.wave_summary.wave_height, 1),
                            'period': round(d.wave_summary.period, 1),
                            'direction': d.wave_summary.compass_direction
                        })
                    
                    # Cache for 1 hour
                    cache_data('wave_data', wave_list, 1)
                    print(f"Cached {len(wave_list)} wave data points")
                    return wave_list
        
        return None
    except Exception as e:
        print(f"Error fetching wave data: {e}")
        return None

async def get_tamarack_tide_forecast():
    """Fetch tide forecast with caching"""
    # Try cache first
    cached = get_cached_data('tide_data')
    if cached:
        print("Using cached tide data")
        return cached
    
    try:
        print("Fetching fresh Tamarack tide data...")
        stations = surfpy.TideStations()
        stations.fetch_stations()
        
        san_diego_station = None
        for station in stations.stations:
            if hasattr(station, 'station_id') and station.station_id == '9410170':
                san_diego_station = station
                break
        
        if san_diego_station:
            start_date = datetime.now()
            end_date = start_date + timedelta(days=5)
            
            tidal_events, tidal_data = san_diego_station.fetch_tide_data(
                start_date, 
                end_date, 
                interval=surfpy.TideStation.DataInterval.high_low,
                unit=surfpy.units.Units.english
            )
            
            if tidal_events:
                # Convert to serializable format
                tide_list = []
                for event in tidal_events:
                    tide_list.append({
                        'time': event.date.isoformat(),
                        'height': round(event.water_level, 1),
                        'type': 'High' if event.tidal_event == surfpy.TideEvent.TidalEventType.high_tide else 'Low'
                    })
                
                # Cache for 6 hours
                cache_data('tide_data', tide_list, 6)
                print(f"Cached {len(tide_list)} tide data points")
                return tide_list
        
        return None
    except Exception as e:
        print(f"Error fetching tide data: {e}")
        return None

def format_tamarack_forecast(wave_data, tide_data=None):
    """Format forecast data for display"""
    if not wave_data:
        return []
    
    # Organize tide data by date
    daily_tides = {}
    if tide_data:
        import pytz
        local_tz = pytz.timezone('America/Los_Angeles')
        
        for event in tide_data:
            event_time = datetime.fromisoformat(event['time'])
            # Convert to local timezone for grouping by local date
            if event_time.tzinfo is not None:
                local_time = event_time.astimezone(local_tz)
            else:
                local_time = event_time
            
            event_date = local_time.date()
            if event_date not in daily_tides:
                daily_tides[event_date] = []
            daily_tides[event_date].append({
                "time": local_time.strftime("%I:%M %p"),
                "height": event['height'],
                "type": event['type']
            })
    
    # Group wave data by day
    daily_forecasts = []
    current_date = None
    daily_data = []
    
    import pytz
    local_tz = pytz.timezone('America/Los_Angeles')
    
    for wave_point in wave_data:
        wave_time = datetime.fromisoformat(wave_point['time'])
        # Convert to local timezone for grouping by local date
        if wave_time.tzinfo is not None:
            local_wave_time = wave_time.astimezone(local_tz)
        else:
            local_wave_time = wave_time
        wave_date = local_wave_time.date()
        
        if current_date != wave_date:
            if daily_data:
                # Process previous day
                heights = [d['height'] for d in daily_data]
                periods = [d['period'] for d in daily_data]
                
                avg_height = sum(heights) / len(heights)
                avg_period = sum(periods) / len(periods)
                direction = daily_data[0]['direction']
                
                # Quality rating
                if avg_height >= 4.0 and avg_period >= 12:
                    quality, quality_color = "Good", "green"
                elif avg_height >= 2.5 and avg_period >= 10:
                    quality, quality_color = "Fair", "yellow"
                elif avg_height >= 1.5:
                    quality, quality_color = "Poor-Fair", "orange"
                else:
                    quality, quality_color = "Poor", "red"
                
                forecast_day = {
                    "date": current_date.strftime("%Y-%m-%d"),
                    "day_name": current_date.strftime("%A"),
                    "wave_height_avg": round(avg_height, 1),
                    "wave_period": round(avg_period, 0),
                    "wave_direction": direction,
                    "quality": quality,
                    "quality_color": quality_color,
                    "tides": daily_tides.get(current_date, [])
                }
                
                daily_forecasts.append(forecast_day)
            
            current_date = wave_date
            daily_data = [wave_point]
        else:
            daily_data.append(wave_point)
    
    return daily_forecasts[:5]

@app.get("/")
async def read_root():
    """Serve the main page"""
    return FileResponse('static/index.html')

@app.get("/api/tamarack/forecast")
async def get_tamarack_forecast():
    """Get complete forecast with caching"""
    try:
        # Get data (cached or fresh)
        wave_data = await get_tamarack_wave_forecast()
        tide_data = await get_tamarack_tide_forecast()
        
        # Format forecast
        forecast = format_tamarack_forecast(wave_data, tide_data)
        
        return {
            "location": TAMARACK,
            "forecast": forecast,
            "chart_data": {
                "wave_data": wave_data or [],
                "tide_data": tide_data or []
            },
            "generated_at": datetime.now().isoformat(),
            "data_sources": {
                "waves": "NOAA GFS Wave Model - US West Coast",
                "tides": "NOAA Tide Station 9410170 (San Diego, CA)"
            }
        }
        
    except Exception as e:
        print(f"Error generating forecast: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500, 
            content={"error": "Failed to generate forecast", "details": str(e)}
        )

async def get_wind_data():
    """Get current wind data from NOAA buoy"""
    try:
        print("Fetching wind data from NOAA buoy...")
        location = surfpy.Location(TAMARACK['lat'], TAMARACK['lng'], altitude=30.0, name='Tamarack')
        
        # Try Torrey Pines Outer buoy first (closest to Tamarack)
        try:
            buoy = surfpy.BuoyStation('46225', location)
            latest = buoy.fetch_latest_reading()
            print(f"Buoy 46225 latest reading attributes: {dir(latest) if latest else 'None'}")
            
            if latest:
                # Check all available attributes for debugging
                for attr in dir(latest):
                    if not attr.startswith('_'):
                        try:
                            value = getattr(latest, attr)
                            if 'wind' in attr.lower():
                                print(f"Wind-related attribute {attr}: {value}")
                        except:
                            pass
                
                # Try different possible wind attribute names
                wind_speed = None
                wind_direction = None
                
                for speed_attr in ['wind_speed', 'windspd', 'wind_spd', 'wspd']:
                    if hasattr(latest, speed_attr):
                        speed_val = getattr(latest, speed_attr)
                        if speed_val and speed_val != -999 and not (speed_val != speed_val):
                            wind_speed = speed_val
                            print(f"Found wind speed in {speed_attr}: {wind_speed}")
                            break
                
                for dir_attr in ['wind_direction', 'winddir', 'wind_dir', 'wdir']:
                    if hasattr(latest, dir_attr):
                        dir_val = getattr(latest, dir_attr)
                        if dir_val and dir_val != -999 and not (dir_val != dir_val):
                            wind_direction = dir_val
                            print(f"Found wind direction in {dir_attr}: {wind_direction}")
                            break
                
                if wind_speed:
                    # Convert wind direction to compass direction
                    def degrees_to_compass(degrees):
                        if degrees is None:
                            return "Variable"
                        directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                                    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
                        return directions[round(degrees / 22.5) % 16]
                    
                    # Wind strength description
                    def wind_strength(speed):
                        if speed < 5:
                            return "Light"
                        elif speed < 15:
                            return "Moderate"
                        elif speed < 25:
                            return "Strong"
                        else:
                            return "Very Strong"
                    
                    wind_dir = degrees_to_compass(wind_direction) if wind_direction else "Variable"
                    
                    return {
                        "wind_speed_mph": round(wind_speed, 1),
                        "wind_speed_kts": round(wind_speed * 0.868976, 1),
                        "wind_direction": wind_dir,
                        "wind_strength": wind_strength(wind_speed),
                        "station": "Torrey Pines Outer",
                        "station_id": "46225"
                    }
        except Exception as e:
            print(f"Error with buoy 46225 wind: {e}")
        
        # Fallback to Point Loma buoy
        try:
            buoy = surfpy.BuoyStation('46232', location)
            latest = buoy.fetch_latest_reading()
            print(f"Buoy 46232 latest reading attributes: {dir(latest) if latest else 'None'}")
            
            if latest:
                # Try different possible wind attribute names
                wind_speed = None
                wind_direction = None
                
                for speed_attr in ['wind_speed', 'windspd', 'wind_spd', 'wspd']:
                    if hasattr(latest, speed_attr):
                        speed_val = getattr(latest, speed_attr)
                        if speed_val and speed_val != -999 and not (speed_val != speed_val):
                            wind_speed = speed_val
                            print(f"Found wind speed in {speed_attr}: {wind_speed}")
                            break
                
                for dir_attr in ['wind_direction', 'winddir', 'wind_dir', 'wdir']:
                    if hasattr(latest, dir_attr):
                        dir_val = getattr(latest, dir_attr)
                        if dir_val and dir_val != -999 and not (dir_val != dir_val):
                            wind_direction = dir_val
                            print(f"Found wind direction in {dir_attr}: {wind_direction}")
                            break
                
                if wind_speed:
                    # Convert wind direction to compass direction
                    def degrees_to_compass(degrees):
                        if degrees is None:
                            return "Variable"
                        directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                                    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
                        return directions[round(degrees / 22.5) % 16]
                    
                    # Wind strength description
                    def wind_strength(speed):
                        if speed < 5:
                            return "Light"
                        elif speed < 15:
                            return "Moderate"
                        elif speed < 25:
                            return "Strong"
                        else:
                            return "Very Strong"
                    
                    wind_dir = degrees_to_compass(wind_direction) if wind_direction else "Variable"
                    
                    return {
                        "wind_speed_mph": round(wind_speed, 1),
                        "wind_speed_kts": round(wind_speed * 0.868976, 1),
                        "wind_direction": wind_dir,
                        "wind_strength": wind_strength(wind_speed),
                        "station": "Point Loma",
                        "station_id": "46232"
                    }
        except Exception as e:
            print(f"Error with buoy 46232 wind: {e}")
        
        return None
        
    except Exception as e:
        print(f"Error fetching wind data: {e}")
        return None

async def get_water_temperature():
    """Get current water temperature from NOAA buoy"""
    try:
        print("Fetching water temperature from NOAA buoy...")
        location = surfpy.Location(TAMARACK['lat'], TAMARACK['lng'], altitude=30.0, name='Tamarack')
        
        # Try Torrey Pines Outer buoy first (closest to Tamarack)
        try:
            buoy = surfpy.BuoyStation('46225', location)
            latest = buoy.fetch_latest_reading()
            if latest and not (hasattr(latest, 'water_temperature') and 
                             (latest.water_temperature != latest.water_temperature or latest.water_temperature == -999)):
                return {
                    "water_temp_f": round(latest.water_temperature, 1),
                    "water_temp_c": round((latest.water_temperature - 32) * 5/9, 1),
                    "station": "Torrey Pines Outer",
                    "station_id": "46225"
                }
        except Exception as e:
            print(f"Error with buoy 46225: {e}")
        
        # Fallback to Point Loma buoy
        try:
            buoy = surfpy.BuoyStation('46232', location)
            latest = buoy.fetch_latest_reading()
            if latest and not (hasattr(latest, 'water_temperature') and 
                             (latest.water_temperature != latest.water_temperature or latest.water_temperature == -999)):
                return {
                    "water_temp_f": round(latest.water_temperature, 1),
                    "water_temp_c": round((latest.water_temperature - 32) * 5/9, 1),
                    "station": "Point Loma",
                    "station_id": "46232"
                }
        except Exception as e:
            print(f"Error with buoy 46232: {e}")
        
        return None
        
    except Exception as e:
        print(f"Error fetching water temperature: {e}")
        return None

@app.get("/api/tamarack/current")
async def get_tamarack_current():
    """Get current conditions"""
    try:
        # Use cached data for speed
        wave_data = await get_tamarack_wave_forecast()
        tide_data = await get_tamarack_tide_forecast()
        water_temp = await get_water_temperature()
        wind_data = await get_wind_data()
        
        current_conditions = {}
        
        # Current wave conditions (find closest to current time)
        if wave_data and len(wave_data) > 0:
            from pytz import UTC
            import pytz
            
            # Use UTC for all comparisons
            now_utc = datetime.now(UTC)
            closest_wave = None
            min_diff = None
            
            for wave in wave_data:
                wave_time = datetime.fromisoformat(wave['time'])
                # Ensure wave_time is timezone-aware
                if wave_time.tzinfo is None:
                    wave_time = UTC.localize(wave_time)
                
                time_diff = abs((wave_time - now_utc).total_seconds())
                if min_diff is None or time_diff < min_diff:
                    min_diff = time_diff
                    closest_wave = wave
            
            if closest_wave:
                current_conditions["waves"] = {
                    "height": closest_wave['height'],
                    "period": round(closest_wave['period'], 0),
                    "direction": closest_wave['direction'],
                    "timestamp": closest_wave['time']
                }
        
        # Current tide (determine if rising or falling)
        if tide_data and len(tide_data) > 0:
            from pytz import UTC
            
            # Use UTC for all comparisons
            now_utc = datetime.now(UTC)
            previous_tide = None
            next_tide = None
            
            # Find the tides around current time
            for i, tide in enumerate(tide_data):
                try:
                    tide_time = datetime.fromisoformat(tide['time'])
                    # Ensure tide_time is timezone-aware
                    if tide_time.tzinfo is None:
                        tide_time = UTC.localize(tide_time)
                    
                    if tide_time <= now_utc:
                        previous_tide = tide
                    elif tide_time > now_utc and next_tide is None:
                        next_tide = tide
                        break
                        
                except Exception as e:
                    print(f"Error parsing tide time {tide['time']}: {e}")
                    continue
            
            # We need both previous and next tide to determine direction properly
            if previous_tide and next_tide:
                try:
                    # Determine direction based on tide types
                    is_rising = previous_tide['type'] == 'Low' and next_tide['type'] == 'High'
                    direction = "Rising" if is_rising else "Falling"
                    
                    # Calculate current tide height by interpolating between previous and next
                    prev_time = datetime.fromisoformat(previous_tide['time'])
                    next_time = datetime.fromisoformat(next_tide['time'])
                    if prev_time.tzinfo is None:
                        prev_time = UTC.localize(prev_time)
                    if next_time.tzinfo is None:
                        next_time = UTC.localize(next_time)
                    
                    # Linear interpolation
                    total_duration = (next_time - prev_time).total_seconds()
                    elapsed_duration = (now_utc - prev_time).total_seconds()
                    progress = elapsed_duration / total_duration if total_duration > 0 else 0
                    
                    # Interpolate height
                    height_diff = next_tide['height'] - previous_tide['height']
                    current_height = previous_tide['height'] + (height_diff * progress)
                    
                    # Format next tide time for display
                    local_tz = pytz.timezone('America/Los_Angeles')
                    local_time = next_time.astimezone(local_tz)
                    
                    current_conditions["current_tide"] = {
                        "current_height": round(current_height, 1),
                        "next_time": local_time.strftime("%I:%M %p"),
                        "next_height": next_tide['height'],
                        "next_type": next_tide['type'],
                        "direction": direction,
                        "timestamp": next_tide['time']
                    }
                except Exception as e:
                    print(f"Error formatting current tide time: {e}")
                    raise e
        
        # Add water temperature if available
        if water_temp:
            current_conditions["water_temp"] = water_temp
        
        # Add wind data if available
        if wind_data:
            current_conditions["wind"] = wind_data
        
        return current_conditions
        
    except Exception as e:
        print(f"Error getting current conditions: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to get current conditions", "details": str(e)}
        )

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    init_db()
    print("Database initialized")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)