import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request

load_dotenv()
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import random
from supabase import create_client, Client
import uvicorn
from datetime import datetime
import asyncio
from typing import Dict, Any
import logging

app = FastAPI()

# Supabase client setup
supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_ANON_KEY")
)

# Load surf spots from CSV
def load_surf_spots():
    """Load surf spots from CSV file"""
    spots = {}
    try:
        import csv
        with open('surf_spots.csv', 'r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                name = row['name'].strip().strip("'\"").lower()
                spots[name] = {
                    "name": row['name'].strip().strip("'\""),
                    "lat": float(row['location_n'].strip()),
                    "lon": -float(row['location_w'].strip()),  # Convert to negative for west
                    "depth": float(row['depth'].strip()),
                    "angle": float(row['angle'].strip()),
                    "stream_link": row['stream_link'].strip() if row['stream_link'].strip().lower() != 'null' else None
                }
    except Exception as e:
        logging.error(f"Error loading surf spots: {e}")
        # Fallback to hardcoded spots
        spots = {
            "tamarack": {"name": "Tamarack", "lat": 33.0742, "lon": -117.3095, "depth": 25.0, "angle": 225.0, "stream_link": None}
        }
    return spots

SURF_SPOTS = load_surf_spots()

def get_current_conditions(data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract current conditions from forecast data"""
    current = {}
    
    # Get current conditions from the new data structure
    current['wave_height'] = data.get('current_wave_height', 'Loading...')
    current['tide_height'] = data.get('current_tide_height', 'Loading...')
    current['water_temp'] = data.get('water_temp_f', 'Loading...')
    current['wind_speed'] = data.get('wind_speed_mph', 'Loading...')
    current['wind_direction'] = data.get('wind_direction_deg', 'Loading...')
    current['period'] = data.get('current_period', 'Loading...')
    
    return current

def get_html_template(spot: str, data: Dict[str, Any]) -> str:
    """Generate HTML page for a surf spot"""
    current = get_current_conditions(data)
    wave_height = current['wave_height']
    tide_height = current['tide_height'] 
    water_temp = current['water_temp']
    wind_speed = current['wind_speed']
    wind_direction = current['wind_direction']
    period = current['period']
    
    # Prepare forecast data for charts - use new comprehensive data
    wave_forecast_168h = data.get('wave_forecast_168h', [])
    period_forecast_168h = data.get('period_forecast_168h', [])
    tide_forecast_7d = data.get('tide_forecast_7d', [])
    
    # Convert wave data for chart (use average wave height)
    wave_chart_data = [[entry[3], entry[2]] for entry in wave_forecast_168h] if wave_forecast_168h else []
    
    # Convert period data for chart  
    period_chart_data = [[entry[1], entry[0]] for entry in period_forecast_168h] if period_forecast_168h else []
    
    # Convert tide data for chart (extract height and create hourly approximation)
    tide_chart_data = []
    if tide_forecast_7d:
        for i, (height, tide_type, dt) in enumerate(tide_forecast_7d[:24]):  # First 24 entries
            tide_chart_data.append([i*3, height])  # Approximate hourly from tide events
    
    # Get stream link
    stream_link = data.get('stream_link')
    
    # Create dropdown options
    dropdown_options = ""
    for spot_name, spot_info in SURF_SPOTS.items():
        selected = "selected" if spot_name == spot.lower() else ""
        display_name = spot_info.get('name', spot_name.title())
        dropdown_options += f'<option value="{spot_name}" {selected}>{display_name}</option>'
    
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Duck Dive - {spot.title()}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <meta http-equiv="refresh" content="300">
</head>
<body class="bg-gradient-to-br from-blue-50 to-cyan-50 min-h-screen">
    <div class="container mx-auto px-4 py-8">
        <!-- Header -->
        <div class="text-center mb-8">
            <h1 class="text-5xl font-bold text-blue-900 mb-4">🏄‍♂️ Duck Dive</h1>
            <div class="mb-4">
                <select id="spotSelector" class="px-6 py-3 border-2 border-blue-200 rounded-xl bg-white shadow-lg text-lg font-medium">
                    {dropdown_options}
                </select>
            </div>
            <h2 class="text-3xl font-semibold text-blue-700">{spot.title()}</h2>
            {'<p class="text-blue-600 mt-2"><a href="' + stream_link + '" target="_blank" class="underline hover:text-blue-800">📹 Live Stream</a></p>' if stream_link else ''}
        </div>
        
        <!-- Current Conditions Grid -->
        <div class="grid grid-cols-2 md:grid-cols-3 gap-4 max-w-4xl mx-auto mb-8">
            <div class="bg-white rounded-xl shadow-lg p-6 text-center border-l-4 border-blue-500">
                <div class="text-3xl font-bold text-blue-600 mb-2">{wave_height}</div>
                <div class="text-gray-600 font-medium">Wave Height (ft)</div>
            </div>
            
            <div class="bg-white rounded-xl shadow-lg p-6 text-center border-l-4 border-purple-500">
                <div class="text-3xl font-bold text-purple-600 mb-2">{period}</div>
                <div class="text-gray-600 font-medium">Period (sec)</div>
            </div>
            
            <div class="bg-white rounded-xl shadow-lg p-6 text-center border-l-4 border-green-500">
                <div class="text-3xl font-bold text-green-600 mb-2">{tide_height}</div>
                <div class="text-gray-600 font-medium">Tide Height (ft)</div>
            </div>
            
            <div class="bg-white rounded-xl shadow-lg p-6 text-center border-l-4 border-cyan-500">
                <div class="text-3xl font-bold text-cyan-600 mb-2">{wind_speed}</div>
                <div class="text-gray-600 font-medium">Wind Speed (mph)</div>
                <div class="text-sm text-gray-500 mt-1">{wind_direction}°</div>
            </div>
            
            <div class="bg-white rounded-xl shadow-lg p-6 text-center border-l-4 border-orange-500">
                <div class="text-3xl font-bold text-orange-600 mb-2">{water_temp}</div>
                <div class="text-gray-600 font-medium">Water Temp (°F)</div>
            </div>
            
            <div class="bg-white rounded-xl shadow-lg p-6 text-center border-l-4 border-indigo-500">
                <div class="text-2xl font-bold text-indigo-600 mb-2">📊</div>
                <div class="text-gray-600 font-medium">7-Day Forecast</div>
                <div class="text-sm text-gray-500 mt-1">Available</div>
            </div>
        </div>
        
        <!-- Forecast Charts -->
        <div class="max-w-6xl mx-auto mb-8">
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <!-- Wave Height Forecast -->
                <div class="bg-white rounded-xl shadow-lg p-6">
                    <h3 class="text-xl font-bold text-gray-800 mb-4 text-center">Wave Height (48h)</h3>
                    <canvas id="waveChart" width="400" height="300"></canvas>
                </div>
                
                <!-- Wave Period Forecast -->
                <div class="bg-white rounded-xl shadow-lg p-6">
                    <h3 class="text-xl font-bold text-gray-800 mb-4 text-center">Wave Period (48h)</h3>
                    <canvas id="periodChart" width="400" height="300"></canvas>
                </div>
                
                <!-- Tide Height Forecast -->
                <div class="bg-white rounded-xl shadow-lg p-6">
                    <h3 class="text-xl font-bold text-gray-800 mb-4 text-center">Tide Height (24h)</h3>
                    <canvas id="tideChart" width="400" height="300"></canvas>
                </div>
            </div>
        </div>
        
        <!-- Footer -->
        <div class="text-center mt-8 text-gray-500 text-sm">
            <p class="font-medium">Updates every 5 minutes • 7-Day Comprehensive Forecast</p>
            <p>Last updated: {datetime.now().strftime('%I:%M %p on %B %d, %Y')}</p>
        </div>
    </div>
    
    <script>
        // Spot selector
        document.getElementById('spotSelector').addEventListener('change', function() {{
            const selectedSpot = this.value;
            if (selectedSpot) {{
                window.location.href = '/' + selectedSpot;
            }}
        }});
        
        // Chart configuration
        const chartConfig = {{
            responsive: true,
            maintainAspectRatio: false,
            scales: {{
                y: {{
                    beginAtZero: true,
                    grid: {{ color: 'rgba(0,0,0,0.1)' }},
                    ticks: {{ color: '#6B7280' }}
                }},
                x: {{
                    grid: {{ color: 'rgba(0,0,0,0.1)' }},
                    ticks: {{ color: '#6B7280' }}
                }}
            }},
            plugins: {{
                legend: {{ display: false }}
            }}
        }};
        
        // Wave height chart
        const waveData = {wave_chart_data};
        if (waveData.length > 0) {{
            const waveChart24h = waveData.slice(0, 16); // 48 hours (every 3 hours)
            const waveCtx = document.getElementById('waveChart').getContext('2d');
            new Chart(waveCtx, {{
                type: 'line',
                data: {{
                    labels: waveChart24h.map(d => d[0] + 'h'),
                    datasets: [{{
                        data: waveChart24h.map(d => d[1]),
                        borderColor: 'rgb(37, 99, 235)',
                        backgroundColor: 'rgba(37, 99, 235, 0.1)',
                        borderWidth: 3,
                        tension: 0.4,
                        fill: true,
                        pointBackgroundColor: 'rgb(37, 99, 235)',
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2
                    }}]
                }},
                options: chartConfig
            }});
        }}
        
        // Wave period chart
        const periodData = {period_chart_data};
        if (periodData.length > 0) {{
            const periodChart24h = periodData.slice(0, 16); // 48 hours
            const periodCtx = document.getElementById('periodChart').getContext('2d');
            new Chart(periodCtx, {{
                type: 'line',
                data: {{
                    labels: periodChart24h.map(d => d[0] + 'h'),
                    datasets: [{{
                        data: periodChart24h.map(d => d[1]),
                        borderColor: 'rgb(147, 51, 234)',
                        backgroundColor: 'rgba(147, 51, 234, 0.1)',
                        borderWidth: 3,
                        tension: 0.4,
                        fill: true,
                        pointBackgroundColor: 'rgb(147, 51, 234)',
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2
                    }}]
                }},
                options: chartConfig
            }});
        }}
        
        // Tide height chart
        const tideData = {tide_chart_data};
        if (tideData.length > 0) {{
            const tideChart24h = tideData.slice(0, 8); // 24 hours worth
            const tideCtx = document.getElementById('tideChart').getContext('2d');
            new Chart(tideCtx, {{
                type: 'line',
                data: {{
                    labels: tideChart24h.map(d => d[0] + 'h'),
                    datasets: [{{
                        data: tideChart24h.map(d => d[1]),
                        borderColor: 'rgb(34, 197, 94)',
                        backgroundColor: 'rgba(34, 197, 94, 0.1)',
                        borderWidth: 3,
                        tension: 0.4,
                        fill: true,
                        pointBackgroundColor: 'rgb(34, 197, 94)',
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2
                    }}]
                }},
                options: chartConfig
            }});
        }}
    </script>
</body>
</html>
"""

@app.get("/")
async def root():
    """Redirect to random surf spot"""
    random_spot = random.choice(list(SURF_SPOTS.keys()))
    return RedirectResponse(url=f"/{random_spot}")

@app.get("/{spot}", response_class=HTMLResponse)
async def get_spot_page(spot: str):
    """Get surf spot page"""
    if spot.lower() not in SURF_SPOTS:
        raise HTTPException(status_code=404, detail="Surf spot not found")
    
    # Get latest data using the updated get_report logic
    try:
        logging.info(f"Querying Supabase for spot: {spot}")
        result = supabase.table('surf_reports').select('*').ilike('spot_name', spot).order('timestamp', desc=True).limit(1).execute()
        logging.info(f"Query result for spot_name ilike {spot}: {len(result.data) if result.data else 0} records")
        
        if not result.data:
            # Fallback to old 'spot' column if spot_name doesn't have data
            logging.info(f"Trying fallback query with spot ilike {spot}")
            result = supabase.table('surf_reports').select('*').ilike('spot', spot).order('timestamp', desc=True).limit(1).execute()
            logging.info(f"Fallback query result for spot ilike {spot}: {len(result.data) if result.data else 0} records")
            
        if result.data:
            data = result.data[0]
            logging.info(f"Found data for {spot}: keys={list(data.keys())}")
            logging.info(f"Sample data: wave_forecast_168h length={len(data.get('wave_forecast_168h', []))}")
            logging.info(f"Sample data: water_temp_f={data.get('water_temp_f')}")
            logging.info(f"Sample data: wind_speed_mph={data.get('wind_speed_mph')}")
            
            # Transform data for frontend compatibility (same as get_report)
            transformed_data = {
                'spot': data.get('spot_name', data.get('spot', spot)),
                'timestamp': data.get('timestamp'),
                'water_temp_f': data.get('water_temp_f'),
                'wind_speed_mph': data.get('wind_speed_mph', data.get('wind_mph')),
                'wind_direction_deg': data.get('wind_direction_deg'),
                'stream_link': data.get('stream_link'),
                'spot_config': data.get('spot_config', {}),
                
                # Wave data
                'wave_forecast_168h': data.get('wave_forecast_168h', []),
                'wave_height_forecast': data.get('wave_height_forecast', []),
                
                # Period data  
                'period_forecast_168h': data.get('period_forecast_168h', []),
                
                # Tide data
                'tide_forecast_7d': data.get('tide_forecast_7d', []),
                'tide_height_forecast': data.get('tide_height_forecast', []),
                
                # Current conditions (extract from forecast data)
                'current_wave_height': data.get('wave_forecast_168h')[0][2] if data.get('wave_forecast_168h') and len(data.get('wave_forecast_168h')) > 0 else 'Loading...',  # avg from first entry
                'current_period': data.get('period_forecast_168h')[0][0] if data.get('period_forecast_168h') and len(data.get('period_forecast_168h')) > 0 else 'Loading...',  # period from first entry
                'current_tide_height': data.get('tide_forecast_7d')[0][0] if data.get('tide_forecast_7d') and len(data.get('tide_forecast_7d')) > 0 else 'Loading...'  # height from first entry
            }
        else:
            logging.warning(f"No data found for spot: {spot}")
            transformed_data = {}
    except Exception as e:
        logging.error(f"Database error: {e}")
        transformed_data = {}
    
    return get_html_template(spot, transformed_data)

@app.get("/api/get_report")
async def get_report(spot: str):
    """Get latest surf report for a spot"""
    try:
        # Query by spot_name (new column) first, fallback to spot (old column) for compatibility - case insensitive
        result = supabase.table('surf_reports').select('*').ilike('spot_name', spot).order('timestamp', desc=True).limit(1).execute()
        if not result.data:
            # Fallback to old 'spot' column if spot_name doesn't have data
            result = supabase.table('surf_reports').select('*').ilike('spot', spot).order('timestamp', desc=True).limit(1).execute()
        if result.data:
            data = result.data[0]
            
            # Transform data for frontend compatibility
            transformed_data = {
                'spot': data.get('spot_name', data.get('spot', spot)),
                'timestamp': data.get('timestamp'),
                'water_temp_f': data.get('water_temp_f'),
                'wind_speed_mph': data.get('wind_speed_mph', data.get('wind_mph')),
                'wind_direction_deg': data.get('wind_direction_deg'),
                'stream_link': data.get('stream_link'),
                'spot_config': data.get('spot_config', {}),
                
                # Wave data
                'wave_forecast_168h': data.get('wave_forecast_168h', []),
                'wave_height_forecast': data.get('wave_height_forecast', []),
                
                # Period data  
                'period_forecast_168h': data.get('period_forecast_168h', []),
                
                # Tide data
                'tide_forecast_7d': data.get('tide_forecast_7d', []),
                'tide_height_forecast': data.get('tide_height_forecast', []),
                
                # Current conditions (extract from forecast data)
                'current_wave_height': data.get('wave_forecast_168h')[0][2] if data.get('wave_forecast_168h') and len(data.get('wave_forecast_168h')) > 0 else 'Loading...',  # avg from first entry
                'current_period': data.get('period_forecast_168h')[0][0] if data.get('period_forecast_168h') and len(data.get('period_forecast_168h')) > 0 else 'Loading...',  # period from first entry
                'current_tide_height': data.get('tide_forecast_7d')[0][0] if data.get('tide_forecast_7d') and len(data.get('tide_forecast_7d')) > 0 else 'Loading...'  # height from first entry
            }
            
            return transformed_data
        else:
            return {"error": "No data available", "spot": spot}
    except Exception as e:
        logging.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Database error")

@app.post("/api/update_spot")
@app.get("/api/update_spot")
async def update_spot(request: Request):
    """Update surf spot data - supports ?spot=spotname query parameter"""
    from surf_report_update_spot import update_spot_to_supabase
    
    # Get spot from query parameter
    spot_name = request.query_params.get('spot')
    
    if not spot_name:
        return {
            "status": "error",
            "message": "Missing 'spot' query parameter. Use ?spot=spotname",
            "example": "/api/update_spot?spot=Tamarack",
            "timestamp": datetime.now().isoformat()
        }
    
    try:
        # Call the surf report update function
        result = update_spot_to_supabase(spot_name)
        
        if result["status"] == "success":
            logging.info(f"Successfully updated surf spot: {spot_name}")
        else:
            logging.error(f"Failed to update surf spot {spot_name}: {result['message']}")
        
        return result
        
    except Exception as e:
        logging.error(f"Error updating spot {spot_name}: {e}")
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}",
            "spot_name": spot_name,
            "timestamp": datetime.now().isoformat()
        }

@app.post("/api/new_spot_request")
async def new_spot_request(email: str, spot_name: str):
    """Submit new surf spot request"""
    try:
        result = supabase.table('spot_requests').insert({
            "email": email,
            "spot_name": spot_name,
            "timestamp": datetime.now().isoformat(),
            "implemented": False
        }).execute()
        return {"status": "success", "message": "Spot request submitted"}
    except Exception as e:
        logging.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Database error")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)