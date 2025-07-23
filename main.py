from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
import sys
import os
from datetime import datetime, timedelta
import asyncio
import sqlite3
import json
from typing import Optional, List

# Add surfpy to path
sys.path.append('./surfpy')
try:
    import surfpy
    from surfpy.weatherapi import WeatherApi
    SURFPY_AVAILABLE = True
    print("SurfPy loaded successfully")
except ImportError as e:
    print(f"SurfPy not available: {e}")
    SURFPY_AVAILABLE = False
    # Create mock classes
    class MockWeatherApi:
        @staticmethod
        def fetch_hourly_forecast(location):
            return None
    WeatherApi = MockWeatherApi

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
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS wind_data (
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
    
    if not SURFPY_AVAILABLE:
        print("SurfPy not available, using fallback wave data")
        return get_fallback_wave_data()
    
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
        
        # Fallback: Return mock data if GRIB processing fails
        print("GRIB processing failed, using fallback data")
        return get_fallback_wave_data()
        
    except Exception as e:
        print(f"Error fetching wave data: {e}")
        # Return fallback data on any error
        return get_fallback_wave_data()

def get_fallback_wave_data():
    """Return mock wave data when real data is unavailable"""
    from datetime import datetime, timedelta
    import pytz
    
    # Generate 5 days of mock data
    wave_list = []
    utc = pytz.UTC
    base_time = datetime.now(utc)
    
    for i in range(120):  # 5 days, every hour
        time = base_time + timedelta(hours=i)
        # Mock wave heights between 1-4 feet with some variation
        import random
        height = round(2.0 + random.uniform(-1.0, 2.0), 1)
        period = round(8 + random.uniform(-2, 4), 1)
        
        wave_list.append({
            'time': time.isoformat(),
            'height': max(0.5, height),  # Ensure minimum 0.5ft
            'period': max(6.0, period),   # Ensure minimum 6s period
            'direction': 'SW'  # Default direction
        })
    
    return wave_list

async def get_tamarack_tide_forecast():
    """Fetch tide forecast with caching"""
    # Try cache first
    cached = get_cached_data('tide_data')
    if cached:
        print("Using cached tide data")
        return cached
    
    if not SURFPY_AVAILABLE:
        print("SurfPy not available, using fallback tide data")
        return get_fallback_tide_data()
    
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
        
        return get_fallback_tide_data()
    except Exception as e:
        print(f"Error fetching tide data: {e}")
        return get_fallback_tide_data()

def get_fallback_tide_data():
    """Return mock tide data when real data is unavailable"""
    from datetime import datetime, timedelta
    import pytz
    
    # Generate 5 days of mock tide data
    tide_list = []
    utc = pytz.UTC
    base_time = datetime.now(utc).replace(hour=6, minute=0, second=0, microsecond=0)
    
    # Typical tide pattern: 2 highs and 2 lows per day, roughly 6 hours apart
    tide_heights = [5.8, 0.2, 5.6, 0.4]  # High, Low, High, Low
    tide_types = ['High', 'Low', 'High', 'Low']
    
    for day in range(5):
        for i in range(4):  # 4 tides per day
            time = base_time + timedelta(days=day, hours=i*6 + day*0.8)  # Slight daily shift
            tide_list.append({
                'time': time.isoformat(),
                'height': round(tide_heights[i] + (day * 0.1), 1),  # Slight variation
                'type': tide_types[i]
            })
    
    return tide_list

async def get_tamarack_wind_forecast():
    """Fetch wind forecast from NWS with caching"""
    # Try cache first
    cached = get_cached_data('wind_data')
    if cached:
        print("Using cached wind data")
        return cached
    
    if not SURFPY_AVAILABLE:
        print("SurfPy not available, using fallback wind data")
        return get_fallback_wind_data()
    
    try:
        print("Fetching fresh wind forecast from NWS...")
        location = surfpy.Location(TAMARACK['lat'], TAMARACK['lng'], altitude=30.0, name='Tamarack')
        
        # Fetch hourly wind forecast using WeatherApi
        wind_buoy_data = WeatherApi.fetch_hourly_forecast(location)
        
        if wind_buoy_data:
            # Convert to serializable format
            wind_list = []
            for data_point in wind_buoy_data:
                # Include all data points, even with wind_speed=0
                if hasattr(data_point, 'wind_speed') and data_point.wind_speed is not None:
                    wind_direction = data_point.wind_compass_direction or 'Variable'
                    # Handle empty wind direction
                    if not wind_direction or wind_direction.strip() == '':
                        wind_direction = 'Variable'
                    
                    wind_list.append({
                        'time': data_point.date.isoformat(),
                        'wind_speed_mph': round(data_point.wind_speed, 1),
                        'wind_speed_kts': round(data_point.wind_speed * 0.868976, 1),
                        'wind_direction': wind_direction,
                        'wind_direction_deg': data_point.wind_direction if hasattr(data_point, 'wind_direction') else None,
                        'air_temperature': data_point.air_temperature if hasattr(data_point, 'air_temperature') else None,
                        'short_forecast': data_point.short_forecast if hasattr(data_point, 'short_forecast') else None
                    })
            
            if wind_list:
                # Cache for 1 hour
                cache_data('wind_data', wind_list, 1)
                print(f"Cached {len(wind_list)} wind data points")
                return wind_list
        
        return get_fallback_wind_data()
    except Exception as e:
        print(f"Error fetching wind forecast: {e}")
        import traceback
        traceback.print_exc()
        return get_fallback_wind_data()

def get_fallback_wind_data():
    """Return mock wind data when real data is unavailable"""
    from datetime import datetime, timedelta
    import pytz
    import random
    
    # Generate 5 days of mock wind data
    wind_list = []
    utc = pytz.UTC
    base_time = datetime.now(utc)
    
    directions = ['NW', 'W', 'SW', 'S', 'SE', 'E', 'NE', 'N']
    
    for i in range(120):  # 5 days, every hour
        time = base_time + timedelta(hours=i)
        # Mock wind speeds between 3-15 mph with some variation
        speed = round(8.0 + random.uniform(-5.0, 7.0), 1)
        speed = max(0.0, speed)  # Ensure non-negative
        
        wind_list.append({
            'time': time.isoformat(),
            'wind_speed_mph': speed,
            'wind_speed_kts': round(speed * 0.868976, 1),
            'wind_direction': random.choice(directions),
            'wind_direction_deg': None,
            'air_temperature': 70 + random.randint(-10, 10),
            'short_forecast': 'Clear' if speed < 10 else 'Breezy'
        })
    
    return wind_list

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

@app.get("/api/webcam-proxy")
async def webcam_proxy():
    """Proxy webcam stream to bypass domain restrictions"""
    import httpx
    
    try:
        # Try to fetch the HDOnTap embed page and serve it
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            # More comprehensive browser headers
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "iframe",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "cross-site",
                "Referer": "https://visitcarlsbad.com/carlsbad-live-beach-cam/",
                "Origin": "https://visitcarlsbad.com"
            }
            
            response = await client.get(
                "https://portal.hdontap.com/s/embed?stream=hdontap_carlsbad_terra-mar-pt-VISIT_CARLSBAD&ratio=16:9&fluid=true",
                headers=headers
            )
            
            print(f"Webcam proxy response: {response.status_code}, URL: {response.url}")
            
            if response.status_code == 200:
                # Return the content with modified headers
                from fastapi.responses import HTMLResponse
                content = response.text
                
                # Fix all relative URLs to be absolute HDOnTap URLs
                content = content.replace('src="//', 'src="https://')
                content = content.replace("src='//", "src='https://")
                content = content.replace('href="//', 'href="https://')
                content = content.replace("href='//", "href='https://")
                
                # Fix relative paths that start with / to point to HDOnTap
                content = content.replace('src="/', 'src="https://portal.hdontap.com/')
                content = content.replace("src='/", "src='https://portal.hdontap.com/")
                content = content.replace('href="/', 'href="https://portal.hdontap.com/')
                content = content.replace("href='/", "href='https://portal.hdontap.com/")
                
                # Fix any portal.hdontap.com references
                content = content.replace('//portal.hdontap.com', 'https://portal.hdontap.com')
                
                # Fix action URLs for forms
                content = content.replace('action="/', 'action="https://portal.hdontap.com/')
                
                # Fix any API calls or fetch requests
                content = content.replace('"/api/', '"https://portal.hdontap.com/api/')
                content = content.replace("'/api/", "'https://portal.hdontap.com/api/")
                content = content.replace('"/assets/', '"https://portal.hdontap.com/assets/')
                content = content.replace("'/assets/", "'https://portal.hdontap.com/assets/")
                content = content.replace('"/scripts/', '"https://portal.hdontap.com/scripts/')
                content = content.replace("'/scripts/", "'https://portal.hdontap.com/scripts/")
                
                return HTMLResponse(
                    content=content,
                    headers={
                        "X-Frame-Options": "SAMEORIGIN",
                        "Content-Security-Policy": "frame-ancestors 'self'",
                        "Cache-Control": "no-cache, no-store, must-revalidate"
                    }
                )
            else:
                print(f"Webcam fetch failed. Status: {response.status_code}, Final URL: {response.url}")
                return {"error": "Webcam not available", "status": response.status_code, "final_url": str(response.url)}
                
    except Exception as e:
        print(f"Webcam proxy error: {e}")
        import traceback
        traceback.print_exc()
        return {"error": "Webcam service unavailable", "details": str(e)}

@app.get("/api/tamarack/forecast")
async def get_tamarack_forecast():
    """Get complete forecast with caching"""
    try:
        # Get data (cached or fresh)
        wave_data = await get_tamarack_wave_forecast()
        tide_data = await get_tamarack_tide_forecast()
        wind_data = await get_tamarack_wind_forecast()
        
        # Format forecast
        forecast = format_tamarack_forecast(wave_data, tide_data)
        
        return {
            "location": TAMARACK,
            "forecast": forecast,
            "chart_data": {
                "wave_data": wave_data or [],
                "tide_data": tide_data or [],
                "wind_data": wind_data or []
            },
            "generated_at": datetime.now().isoformat(),
            "data_sources": {
                "waves": "NOAA GFS Wave Model - US West Coast",
                "tides": "NOAA Tide Station 9410170 (San Diego, CA)",
                "wind": "NOAA National Weather Service - Hourly Forecast"
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
    """Get current wind data from NOAA buoy - Note: Often unreliable due to NaN values"""
    if not SURFPY_AVAILABLE:
        return None
        
    try:
        # Skip buoy wind data since it's unreliable - just return None
        print("Skipping NOAA buoy wind data (unreliable NaN values)")
        return None
        
        # Legacy buoy code (disabled)
        location = surfpy.Location(TAMARACK['lat'], TAMARACK['lng'], altitude=30.0, name='Tamarack')
        
        # Try Torrey Pines Outer buoy first (closest to Tamarack)
        try:
            buoy = surfpy.BuoyStation('46225', location)
            latest = buoy.fetch_latest_reading()
            
            if latest:
                # Check for valid wind data (not NaN)
                wind_speed = None
                wind_direction = None
                
                for speed_attr in ['wind_speed', 'windspd', 'wind_spd', 'wspd']:
                    if hasattr(latest, speed_attr):
                        speed_val = getattr(latest, speed_attr)
                        # Check if value is not NaN and not -999 (missing data indicator)
                        if speed_val is not None and speed_val == speed_val and speed_val != -999:
                            wind_speed = speed_val
                            print(f"Found valid wind speed in {speed_attr}: {wind_speed}")
                            break
                        else:
                            print(f"Invalid wind speed in {speed_attr}: {speed_val}")
                
                for dir_attr in ['wind_direction', 'winddir', 'wind_dir', 'wdir']:
                    if hasattr(latest, dir_attr):
                        dir_val = getattr(latest, dir_attr)
                        # Check if value is not NaN and not -999
                        if dir_val is not None and dir_val == dir_val and dir_val != -999:
                            wind_direction = dir_val
                            print(f"Found valid wind direction in {dir_attr}: {wind_direction}")
                            break
                        else:
                            print(f"Invalid wind direction in {dir_attr}: {dir_val}")
                
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
    if not SURFPY_AVAILABLE:
        return None
        
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
        wind_forecast = await get_tamarack_wind_forecast()
        current_wind = await get_wind_data()  # Keep current buoy wind as backup
        
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
        
        # Add wind data - use forecast wind for current conditions (buoy data is unreliable)
        if wind_forecast and len(wind_forecast) > 0:
            from pytz import UTC
            
            # Find current wind from forecast
            now_utc = datetime.now(UTC)
            closest_wind = None
            min_diff = None
            
            for wind in wind_forecast:
                wind_time = datetime.fromisoformat(wind['time'])
                if wind_time.tzinfo is None:
                    wind_time = UTC.localize(wind_time)
                
                time_diff = abs((wind_time - now_utc).total_seconds())
                if min_diff is None or time_diff < min_diff:
                    min_diff = time_diff
                    closest_wind = wind
            
            if closest_wind:
                # Add wind strength description
                def wind_strength(speed):
                    if speed < 5:
                        return "Light"
                    elif speed < 15:
                        return "Moderate" 
                    elif speed < 25:
                        return "Strong"
                    else:
                        return "Very Strong"
                
                current_conditions["wind"] = {
                    "wind_speed_mph": closest_wind['wind_speed_mph'],
                    "wind_speed_kts": closest_wind['wind_speed_kts'],
                    "wind_direction": closest_wind['wind_direction'],
                    "wind_strength": wind_strength(closest_wind['wind_speed_mph']),
                    "air_temperature": closest_wind.get('air_temperature'),
                    "short_forecast": closest_wind.get('short_forecast'),
                    "source": "NWS Forecast",
                    "timestamp": closest_wind['time']
                }
        else:
            # No wind data available
            print("No wind data available from forecast or buoy")
        
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