import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

load_dotenv()
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import random
from supabase import create_client, Client
import uvicorn
from datetime import datetime, timedelta
import pytz
import asyncio
from typing import Dict, Any
import logging
import re
from collections import defaultdict
import time

# MCP integration
from fastapi_mcp import FastApiMCP

app = FastAPI()

# ===== MCP INTEGRATION =====
# Initialize MCP with FastAPI app - exposes existing endpoints as MCP tools
mcp = FastApiMCP(app)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Rate limiting storage
request_counts = defaultdict(list)
RATE_LIMIT_REQUESTS = 5  # 5 requests
RATE_LIMIT_WINDOW = 3600  # per hour (3600 seconds)

class SpotRequest(BaseModel):
    spot_name: str
    email: str

def get_client_ip(request: Request) -> str:
    """Get client IP address from request"""
    if "x-forwarded-for" in request.headers:
        return request.headers["x-forwarded-for"].split(",")[0]
    return request.client.host

def is_rate_limited(client_ip: str) -> bool:
    """Check if client IP is rate limited"""
    now = time.time()
    # Clean old requests outside the window
    request_counts[client_ip] = [
        timestamp for timestamp in request_counts[client_ip]
        if now - timestamp < RATE_LIMIT_WINDOW
    ]
    
    # Check if over limit
    if len(request_counts[client_ip]) >= RATE_LIMIT_REQUESTS:
        return True
    
    # Add current request
    request_counts[client_ip].append(now)
    return False

def validate_spot_request(spot_name: str, email: str):
    """Validate spot request data"""
    # Validate spot name
    if not spot_name or len(spot_name.strip()) < 2:
        return False, "Spot name must be at least 2 characters"
    
    if len(spot_name.strip()) > 100:
        return False, "Spot name must be less than 100 characters"
    
    # Validate email format
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return False, "Invalid email format"
    
    # Check for suspicious patterns
    suspicious_patterns = [
        r'<script',
        r'javascript:',
        r'<iframe',
        r'onclick',
        r'onerror',
        r'eval\(',
        r'alert\(',
    ]
    
    for pattern in suspicious_patterns:
        if re.search(pattern, spot_name, re.IGNORECASE) or re.search(pattern, email, re.IGNORECASE):
            return False, "Invalid characters in request"
    
    return True, ""

# Supabase client setup
supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_ANON_KEY")
)

# Load surf spots from CSV
def get_pst_timestamp():
    """Get current timestamp in PST/PDT timezone"""
    pst = pytz.timezone('America/Los_Angeles')
    return datetime.now(pst)

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
    
    # Get current conditions from the new data structure - round to 1 decimal place
    current['wave_height'] = round(data.get('current_wave_height'), 1) if isinstance(data.get('current_wave_height'), (int, float)) else data.get('current_wave_height', 'Loading...')
    current['tide_height'] = round(data.get('current_tide_height'), 1) if isinstance(data.get('current_tide_height'), (int, float)) else data.get('current_tide_height', 'Loading...')
    current['water_temp'] = round(data.get('water_temp_f'), 1) if isinstance(data.get('water_temp_f'), (int, float)) else data.get('water_temp_f', 'Loading...')
    current['wind_speed'] = round(data.get('wind_speed_mph'), 1) if isinstance(data.get('wind_speed_mph'), (int, float)) else data.get('wind_speed_mph', 'Loading...')
    current['wind_direction'] = round(data.get('wind_direction_deg'), 0) if isinstance(data.get('wind_direction_deg'), (int, float)) else data.get('wind_direction_deg', 'Loading...')
    current['period'] = round(data.get('current_period'), 1) if isinstance(data.get('current_period'), (int, float)) else data.get('current_period', 'Loading...')
    
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
    
    # Get timestamp from database data
    db_timestamp = data.get('timestamp')
    if db_timestamp:
        try:
            # Parse ISO timestamp from database, convert to PST, and format for display
            from datetime import datetime
            timestamp_dt = datetime.fromisoformat(db_timestamp.replace('Z', '+00:00'))
            pst = pytz.timezone('America/Los_Angeles')
            pst_timestamp = timestamp_dt.astimezone(pst)
            formatted_timestamp = pst_timestamp.strftime('%I:%M %p PST on %B %d, %Y')
        except (ValueError, AttributeError):
            # Fallback to current time if parsing fails
            formatted_timestamp = get_pst_timestamp().strftime('%I:%M %p PST on %B %d, %Y')
    else:
        # Fallback to current time if no timestamp in database
        formatted_timestamp = get_pst_timestamp().strftime('%I:%M %p PST on %B %d, %Y')
    
    # Get stream link
    stream_link = data.get('stream_link')
    
    # Prepare simple chart data
    wave_forecast_168h = data.get('wave_forecast_168h', [])
    period_forecast_168h = data.get('period_forecast_168h', [])
    tide_forecast_7d = data.get('tide_forecast_7d', [])
    
    # Extract simple data arrays for charts (first 56 points = 7 days)
    wave_chart_data = []
    if wave_forecast_168h:
        for entry in wave_forecast_168h[:56]:  # 7 days of 3-hour intervals
            if len(entry) >= 3:
                wave_chart_data.append(entry[2])  # avg wave height
    
    period_chart_data = []
    if period_forecast_168h:
        for entry in period_forecast_168h[:56]:  # 7 days
            if len(entry) >= 2:
                period_chart_data.append(entry[0])  # period
    
    tide_chart_data = []
    if tide_forecast_7d:
        for entry in tide_forecast_7d:  # All tide events
            if len(entry) >= 1:
                tide_chart_data.append(entry[0])  # tide height
    
    # Create daily labels for x-axis (7 days)
    from datetime import datetime, timedelta
    daily_labels = []
    for i in range(7):
        date = get_pst_timestamp() + timedelta(days=i)
        if i == 0:
            daily_labels.append("Today")
        elif i == 1:
            daily_labels.append("Tomorrow")
        else:
            daily_labels.append(date.strftime("%m/%d"))
    
    # Create dropdown options
    dropdown_options = ""
    for spot_name, spot_info in SURF_SPOTS.items():
        selected = "selected" if spot_name == spot.lower() else ""
        display_name = spot_info.get('name', spot_name.title())
        dropdown_options += f'<option value="{spot_name}" {selected}>{display_name}</option>'
    
    # Read HTML template
    with open('static/index.html', 'r') as f:
        template = f.read()
    
    # Calculate tide direction and next tide info
    tide_direction = "→"  # Default
    tide_status = "Loading..."
    tide_time = "..."
    tide_labels = []
    
    if tide_forecast_7d and len(tide_forecast_7d) >= 2:
        try:
            # Get current and next tide heights to determine direction
            current_tide_height = tide_forecast_7d[0][0]  # height from first entry
            next_tide_height = tide_forecast_7d[1][0]     # height from second entry
            
            # Determine tide direction (↑ rising, ↓ falling)
            if next_tide_height > current_tide_height:
                tide_direction = "↑"
            else:
                tide_direction = "↓"
            
            # Get next high/low tide info
            next_tide_type = tide_forecast_7d[1][1]  # HIGH or LOW from second entry
            next_tide_datetime = tide_forecast_7d[1][2]  # datetime from second entry
            
            tide_status = next_tide_type
            if isinstance(next_tide_datetime, str):
                # Parse datetime string if needed
                from dateutil import parser
                next_tide_datetime = parser.parse(next_tide_datetime)
            tide_time = next_tide_datetime.strftime('%I:%M %p')
            
            # Create tide labels for chart hover (time labels)
            tide_labels = []
            for entry in tide_forecast_7d:
                if len(entry) >= 3:
                    tide_dt = entry[2]
                    if isinstance(tide_dt, str):
                        from dateutil import parser
                        tide_dt = parser.parse(tide_dt)
                    tide_labels.append(tide_dt.strftime('%m/%d %I:%M %p'))
                    
        except Exception as e:
            logging.error(f"Error calculating tide info: {e}")
    
    # Replace placeholders
    stream_link_html = f'<p class="text-blue-600 mt-2"><a href="{stream_link}" target="_blank" class="underline hover:text-blue-800">📹 Live Stream</a></p>' if stream_link else ''
    
    # Use string replacement instead of .format() to avoid conflicts with JavaScript
    html = template.replace('{spot_title}', spot.title())
    html = html.replace('{dropdown_options}', dropdown_options)
    html = html.replace('{stream_link_html}', stream_link_html)
    html = html.replace('{wave_height}', str(wave_height))
    html = html.replace('{period}', str(period))
    html = html.replace('{tide_height}', str(tide_height))
    html = html.replace('{tide_direction}', tide_direction)
    html = html.replace('{tide_status}', tide_status)
    html = html.replace('{tide_time}', tide_time)
    html = html.replace('{wind_speed}', str(wind_speed))
    html = html.replace('{wind_direction}', str(wind_direction))
    html = html.replace('{water_temp}', str(water_temp))
    html = html.replace('{last_updated}', formatted_timestamp)
    
    # Replace chart data placeholders with JSON data
    import json
    html = html.replace('WAVE_DATA_PLACEHOLDER', json.dumps(wave_chart_data))
    html = html.replace('PERIOD_DATA_PLACEHOLDER', json.dumps(period_chart_data))
    html = html.replace('TIDE_DATA_PLACEHOLDER', json.dumps(tide_chart_data))
    html = html.replace('TIDE_LABELS_PLACEHOLDER', json.dumps(tide_labels))
    html = html.replace('DAILY_LABELS_PLACEHOLDER', json.dumps(daily_labels))
    
    return html

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
                
                # Current conditions (extract from forecast data) - round to 1 decimal
                'current_wave_height': round(data.get('wave_forecast_168h')[0][2], 1) if data.get('wave_forecast_168h') and len(data.get('wave_forecast_168h')) > 0 else 'Loading...',  # avg from first entry
                'current_period': round(data.get('period_forecast_168h')[0][0], 1) if data.get('period_forecast_168h') and len(data.get('period_forecast_168h')) > 0 else 'Loading...',  # period from first entry
                'current_tide_height': round(data.get('tide_forecast_7d')[0][0], 1) if data.get('tide_forecast_7d') and len(data.get('tide_forecast_7d')) > 0 else 'Loading...'  # height from first entry
            }
        else:
            # Only log warning if both queries failed (no data actually found)
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
                
                # Current conditions (extract from forecast data) - round to 1 decimal
                'current_wave_height': round(data.get('wave_forecast_168h')[0][2], 1) if data.get('wave_forecast_168h') and len(data.get('wave_forecast_168h')) > 0 else 'Loading...',  # avg from first entry
                'current_period': round(data.get('period_forecast_168h')[0][0], 1) if data.get('period_forecast_168h') and len(data.get('period_forecast_168h')) > 0 else 'Loading...',  # period from first entry
                'current_tide_height': round(data.get('tide_forecast_7d')[0][0], 1) if data.get('tide_forecast_7d') and len(data.get('tide_forecast_7d')) > 0 else 'Loading...'  # height from first entry
            }
            
            return transformed_data
        else:
            return {"error": "No data available", "spot": spot}
    except Exception as e:
        logging.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Database error")

async def _update_spot_background(spot_name: str = None):
    """Background task to update surf spot data"""
    try:
        from surf_reports.surf_report_update_spot import update_spot_to_supabase
    except ImportError as e:
        logging.error(f"surf_reports module not available: {e}")
        return
    
    if not spot_name:
        # No spot specified - update all spots
        try:
            total_success = 0
            total_failed = 0
            
            for spot_key, spot_info in SURF_SPOTS.items():
                try:
                    logging.info(f"Updating spot: {spot_info['name']}")
                    result = update_spot_to_supabase(spot_info['name'])
                    
                    if result["status"] == "success":
                        total_success += 1
                        logging.info(f"Successfully updated surf spot: {spot_info['name']}")
                    else:
                        total_failed += 1
                        logging.error(f"Failed to update surf spot {spot_info['name']}: {result['message']}")
                    
                except Exception as e:
                    total_failed += 1
                    error_msg = f"Error updating spot {spot_info['name']}: {str(e)}"
                    logging.error(error_msg)
            
            logging.info(f"Background update completed: {total_success} successful, {total_failed} failed")
            
        except Exception as e:
            logging.error(f"Error updating all spots: {e}")
    
    else:
        # Single spot specified
        try:
            result = update_spot_to_supabase(spot_name)
            
            if result["status"] == "success":
                logging.info(f"Successfully updated surf spot: {spot_name}")
            else:
                logging.error(f"Failed to update surf spot {spot_name}: {result['message']}")
            
        except Exception as e:
            logging.error(f"Error updating spot {spot_name}: {e}")

@app.post("/api/update_spot")
@app.get("/api/update_spot")
async def update_spot(request: Request):
    """Kick off surf spot data update - supports ?spot=spotname query parameter or updates all spots if no spot specified"""
    import asyncio
    
    # Get spot from query parameter
    spot_name = request.query_params.get('spot')
    
    # Start the background task without awaiting it
    asyncio.create_task(_update_spot_background(spot_name))
    
    # Return immediate response
    if spot_name:
        logging.info(f"Started background update for spot: {spot_name}")
        return {"message": f"Update started for spot: {spot_name}"}
    else:
        logging.info("Started background update for all spots")
        return {"message": "Update started for all spots"}

@app.post("/api/new_spot_request")
async def new_spot_request(request: Request, spot_request: SpotRequest):
    """Submit new surf spot request with rate limiting and validation"""
    try:
        # Get client IP for rate limiting
        client_ip = get_client_ip(request)
        
        # Check rate limit
        if is_rate_limited(client_ip):
            raise HTTPException(
                status_code=429, 
                detail=f"Rate limit exceeded. Maximum {RATE_LIMIT_REQUESTS} requests per hour allowed."
            )
        
        # Validate input
        is_valid, error_message = validate_spot_request(spot_request.spot_name, str(spot_request.email))
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_message)
        
        # Check for duplicate recent requests (same email within 24 hours)
        twenty_four_hours_ago = get_pst_timestamp() - timedelta(hours=24)
        existing_requests = supabase.table('spot_requests').select("*").eq(
            'email', str(spot_request.email)
        ).gte('timestamp', twenty_four_hours_ago.isoformat()).execute()
        
        if existing_requests.data and len(existing_requests.data) > 0:
            raise HTTPException(
                status_code=400, 
                detail="You can only submit one spot request per 24 hours."
            )
        
        # Insert request into database
        result = supabase.table('spot_requests').insert({
            "email": str(spot_request.email),
            "spot_name": spot_request.spot_name.strip(),
            # Let database handle timestamp with default now()
        }).execute()
        
        if result.data:
            logging.info(f"New spot request: {spot_request.spot_name} from {spot_request.email} (IP: {client_ip})")
            return {"status": "success", "message": "Spot request submitted successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to submit request")
            
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logging.error(f"Database error in spot request: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# ===== MCP TOOL FUNCTIONS =====
# Custom MCP tools that reuse existing logic

@mcp.tool()
def list_spots() -> list:
    """Get a list of available surf spots with their names and coordinates."""
    spots_list = []
    for spot_key, spot_info in SURF_SPOTS.items():
        spots_list.append({
            "key": spot_key,
            "name": spot_info.get('name', spot_key.title()),
            "latitude": str(spot_info.get('lat', '')),
            "longitude": str(spot_info.get('lon', ''))
        })
    return spots_list

@mcp.tool()
async def get_surf_report(spot: str) -> dict:
    """Get the latest surf report for a specific spot including wave height, period, tide, wind, and water temperature.
    
    Args:
        spot: Name of the surf spot (e.g., 'tamarack', 'blacks', 'scripps')
    """
    try:
        # Query by spot_name (new column) first, fallback to spot (old column) for compatibility - case insensitive
        result = supabase.table('surf_reports').select('*').ilike('spot_name', spot).order('timestamp', desc=True).limit(1).execute()
        if not result.data:
            # Fallback to old 'spot' column if spot_name doesn't have data
            result = supabase.table('surf_reports').select('*').ilike('spot', spot).order('timestamp', desc=True).limit(1).execute()
        if result.data:
            data = result.data[0]
            
            # Transform data for compatibility (same logic as HTTP endpoint)
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
                
                # Current conditions (extract from forecast data) - round to 1 decimal
                'current_wave_height': round(data.get('wave_forecast_168h')[0][2], 1) if data.get('wave_forecast_168h') and len(data.get('wave_forecast_168h')) > 0 else 'Loading...',  # avg from first entry
                'current_period': round(data.get('period_forecast_168h')[0][0], 1) if data.get('period_forecast_168h') and len(data.get('period_forecast_168h')) > 0 else 'Loading...',  # period from first entry
                'current_tide_height': round(data.get('tide_forecast_7d')[0][0], 1) if data.get('tide_forecast_7d') and len(data.get('tide_forecast_7d')) > 0 else 'Loading...'  # height from first entry
            }
            
            return transformed_data
        else:
            return {"error": "No data available", "spot": spot}
    except Exception as e:
        logging.error(f"MCP get_report error: {e}")
        return {"error": str(e), "spot": spot}

if __name__ == "__main__":
    # Mount MCP server to the FastAPI app at /mcp endpoint
    mcp.mount()
    
    uvicorn.run(app, host="0.0.0.0", port=8000)