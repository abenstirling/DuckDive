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
    
    # Get current wave height (hour 0 from forecast)
    wave_forecast = data.get('wave_height_forecast', [])
    if wave_forecast and len(wave_forecast) > 0:
        current['wave_height'] = wave_forecast[0][1]  # [hour, height] -> height
    else:
        current['wave_height'] = 'Loading...'
    
    # Get current tide height (hour 0 from forecast)  
    tide_forecast = data.get('tide_height_forecast', [])
    if tide_forecast and len(tide_forecast) > 0:
        current['tide_height'] = tide_forecast[0][1]  # [hour, height] -> height
    else:
        current['tide_height'] = 'Loading...'
    
    current['water_temp'] = data.get('water_temp_f', 'Loading...')
    current['wind_speed'] = data.get('wind_mph', 'Loading...')
    
    return current

def get_html_template(spot: str, data: Dict[str, Any]) -> str:
    """Generate HTML page for a surf spot"""
    current = get_current_conditions(data)
    wave_height = current['wave_height']
    tide_height = current['tide_height'] 
    water_temp = current['water_temp']
    wind_speed = current['wind_speed']
    
    # Prepare forecast data for charts
    wave_forecast = data.get('wave_height_forecast', [])
    tide_forecast = data.get('tide_height_forecast', [])
    
    # Create dropdown options
    dropdown_options = ""
    for spot_name in SURF_SPOTS.keys():
        selected = "selected" if spot_name == spot else ""
        dropdown_options += f'<option value="{spot_name}" {selected}>{spot_name.title()}</option>'
    
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
<body class="bg-blue-50 min-h-screen">
    <div class="container mx-auto px-4 py-8">
        <!-- Header -->
        <div class="text-center mb-8">
            <h1 class="text-4xl font-bold text-blue-900 mb-4">🏄‍♂️ Duck Dive</h1>
            <div class="mb-4">
                <select id="spotSelector" class="px-4 py-2 border rounded-lg bg-white">
                    {dropdown_options}
                </select>
            </div>
            <h2 class="text-2xl font-semibold text-blue-700">{spot.title()}</h2>
        </div>
        
        <!-- Current Conditions Grid -->
        <div class="grid grid-cols-2 gap-4 max-w-md mx-auto mb-8">
            <div class="bg-white rounded-lg shadow-md p-6 text-center">
                <div class="text-2xl font-bold text-blue-600 mb-2">{wave_height}</div>
                <div class="text-gray-600">Wave Height (ft)</div>
            </div>
            
            <div class="bg-white rounded-lg shadow-md p-6 text-center">
                <div class="text-2xl font-bold text-green-600 mb-2">{tide_height}</div>
                <div class="text-gray-600">Tide Height (ft)</div>
            </div>
            
            <div class="bg-white rounded-lg shadow-md p-6 text-center">
                <div class="text-2xl font-bold text-purple-600 mb-2">{wind_speed}</div>
                <div class="text-gray-600">Wind Speed (mph)</div>
            </div>
            
            <div class="bg-white rounded-lg shadow-md p-6 text-center">
                <div class="text-2xl font-bold text-orange-600 mb-2">{water_temp}</div>
                <div class="text-gray-600">Water Temp (°F)</div>
            </div>
        </div>
        
        <!-- Forecast Charts -->
        <div class="max-w-4xl mx-auto mb-8">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <!-- Wave Height Forecast -->
                <div class="bg-white rounded-lg shadow-md p-6">
                    <h3 class="text-lg font-semibold text-gray-800 mb-4">Wave Height Forecast (24h)</h3>
                    <canvas id="waveChart" width="400" height="200"></canvas>
                </div>
                
                <!-- Tide Height Forecast -->
                <div class="bg-white rounded-lg shadow-md p-6">
                    <h3 class="text-lg font-semibold text-gray-800 mb-4">Tide Height Forecast (24h)</h3>
                    <canvas id="tideChart" width="400" height="200"></canvas>
                </div>
            </div>
        </div>
        
        <!-- Footer -->
        <div class="text-center mt-8 text-gray-500 text-sm">
            <p>Updates every 5 minutes</p>
            <p>Last updated: {datetime.now().strftime('%I:%M %p')}</p>
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
        
        // Forecast data
        const waveForecast = {wave_forecast};
        const tideForecast = {tide_forecast};
        
        // Wave height chart
        if (waveForecast.length > 0) {{
            const waveData = waveForecast.slice(0, 24); // First 24 hours
            const waveCtx = document.getElementById('waveChart').getContext('2d');
            new Chart(waveCtx, {{
                type: 'line',
                data: {{
                    labels: waveData.map(d => d[0] + 'h'),
                    datasets: [{{
                        label: 'Wave Height (ft)',
                        data: waveData.map(d => d[1]),
                        borderColor: 'rgb(37, 99, 235)',
                        backgroundColor: 'rgba(37, 99, 235, 0.1)',
                        tension: 0.4,
                        fill: true
                    }}]
                }},
                options: {{
                    responsive: true,
                    scales: {{
                        y: {{
                            beginAtZero: true,
                            title: {{
                                display: true,
                                text: 'Height (ft)'
                            }}
                        }},
                        x: {{
                            title: {{
                                display: true,
                                text: 'Hours from now'
                            }}
                        }}
                    }},
                    plugins: {{
                        legend: {{
                            display: false
                        }}
                    }}
                }}
            }});
        }}
        
        // Tide height chart
        if (tideForecast.length > 0) {{
            const tideData = tideForecast.slice(0, 24); // First 24 hours
            const tideCtx = document.getElementById('tideChart').getContext('2d');
            new Chart(tideCtx, {{
                type: 'line',
                data: {{
                    labels: tideData.map(d => d[0] + 'h'),
                    datasets: [{{
                        label: 'Tide Height (ft)',
                        data: tideData.map(d => d[1]),
                        borderColor: 'rgb(34, 197, 94)',
                        backgroundColor: 'rgba(34, 197, 94, 0.1)',
                        tension: 0.4,
                        fill: true
                    }}]
                }},
                options: {{
                    responsive: true,
                    scales: {{
                        y: {{
                            beginAtZero: true,
                            title: {{
                                display: true,
                                text: 'Height (ft)'  
                            }}
                        }},
                        x: {{
                            title: {{
                                display: true,
                                text: 'Hours from now'
                            }}
                        }}
                    }},
                    plugins: {{
                        legend: {{
                            display: false
                        }}
                    }}
                }}
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
    if spot not in SURF_SPOTS:
        raise HTTPException(status_code=404, detail="Surf spot not found")
    
    # Get latest data from database
    try:
        result = supabase.table('surf_reports').select('*').eq('spot', spot).order('timestamp', desc=True).limit(1).execute()
        data = result.data[0] if result.data else {}
    except Exception as e:
        logging.error(f"Database error: {e}")
        data = {}
    
    return get_html_template(spot, data)

@app.get("/api/get_report")
async def get_report(spot: str):
    """Get latest surf report for a spot"""
    try:
        # Query by spot_name (new column) or spot (old column) for compatibility
        result = supabase.table('surf_reports').select('*').or_(f'spot_name.eq.{spot},spot.eq.{spot}').order('timestamp', desc=True).limit(1).execute()
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
                'current_wave_height': data.get('wave_forecast_168h', [{}])[0][2] if data.get('wave_forecast_168h') else 'Loading...',  # avg from first entry
                'current_period': data.get('period_forecast_168h', [{}])[0][0] if data.get('period_forecast_168h') else 'Loading...',  # period from first entry
                'current_tide_height': data.get('tide_forecast_7d', [{}])[0][0] if data.get('tide_forecast_7d') else 'Loading...'  # height from first entry
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