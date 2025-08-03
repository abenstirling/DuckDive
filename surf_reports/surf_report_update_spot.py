import surfpy
import matplotlib.pyplot as plt
import csv
import datetime
import os
import json
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables from .env file
load_dotenv()
from .surf_report_wave_height import get_surf_forecast
from .surf_report_water_temperature import get_water_temp_forecast
from .surf_report_winds import get_current_wind
from .surf_report_tides import get_tide_forecast
from .surf_report_period import get_period_forecast

def get_surf_spot_data(spot_name, csv_file="surf_spots.csv"):
    """
    Get surf spot configuration data from CSV file by name.
    
    Args:
        spot_name: Name of the surf spot to look up
        csv_file: Path to the CSV file (default: surf_spots.csv)
    
    Returns:
        Dictionary with surf spot data or None if not found
    """
    try:
        with open(csv_file, 'r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                # Clean up the name field (remove quotes and spaces)
                name = row['name'].strip().strip("'\"")
                if name == spot_name:
                    return {
                        'name': name,
                        'closest_station': int(row['closest_station'].strip()),
                        'closest_tide': int(row['closest_tide'].strip()),
                        'location_n': float(row['location_n'].strip()),
                        'location_w': float(row['location_w'].strip()),
                        'altitude': float(row['altitude'].strip()),
                        'depth': float(row['depth'].strip()),
                        'angle': float(row['angle'].strip()),
                        'slope': float(row['slope'].strip()),
                        'wave_model': row['wave_model'].strip().strip("'\""),
                        'stream_link': row['stream_link'].strip() if row['stream_link'].strip().lower() != 'null' else None
                    }
        return None
    except Exception as e:
        print(f"Error reading surf spots CSV: {e}")
        return None

def get_complete_surf_report(spot_name):
    """
    Get complete surf report data for a given surf spot that can be stored in database.
    
    Args:
        spot_name: Name of the surf spot from surf_spots.csv
    
    Returns:
        Dictionary with complete surf report data for database storage
    """
    # Get surf spot configuration
    spot_data = get_surf_spot_data(spot_name)
    if not spot_data:
        print(f"Surf spot '{spot_name}' not found in CSV")
        return None
    
    print(f"Generating surf report for {spot_data['name']}")
    
    # Create wave location object
    wave_location = surfpy.Location(
        spot_data['location_n'], 
        -spot_data['location_w'],  # Convert to negative for west longitude
        altitude=spot_data['altitude'], 
        name=spot_data['name']
    )
    wave_location.depth = spot_data['depth']
    wave_location.angle = spot_data['angle']
    wave_location.slope = spot_data['slope']
    
    # Set forecast parameters
    num_hours_to_forecast = 168  # 7 day forecast
    
    # Get all forecast data
    print("Fetching wave height forecast...")
    wave_forecast = get_surf_forecast(wave_location, num_hours_to_forecast)
    
    print("Fetching wave period forecast...")
    period_forecast = get_period_forecast(wave_location, num_hours_to_forecast)
    
    print("Fetching water temperature...")
    water_temp_data = get_water_temp_forecast(wave_location, 1)
    
    print("Fetching current wind...")
    wind_data = get_current_wind(wave_location)
    
    print("Fetching tide forecast...")
    tide_forecast = get_tide_forecast(str(spot_data['closest_tide']))
    
    # Build the complete data structure for database
    report_data = {
        'timestamp': datetime.datetime.now().isoformat(),
        'spot': spot_data['name'],  # Keep original 'spot' column
        'spot_name': spot_data['name'],  # New spot_name column
        'spot_config': spot_data,
        'water_temp_f': water_temp_data[0][0] if water_temp_data else None,
        'wind_speed_mph': wind_data[0] if wind_data else None,
        'wind_direction_deg': wind_data[1] if wind_data else None,
        'wind_mph': wind_data[0] if wind_data else None,  # Keep original wind_mph column
        'stream_link': spot_data.get('stream_link'),
        'wave_forecast_168h': wave_forecast,  # [(high, low, avg, hour), ...]
        'period_forecast_168h': period_forecast,  # [(period, hour), ...]
        'tide_forecast_7d': tide_forecast,  # [(height, type, datetime), ...]
        'wave_height_forecast': wave_forecast,  # Keep original column format
        'tide_height_forecast': [(i*3, height) for i, (height, tide_type, dt) in enumerate(tide_forecast or [])]  # Convert format for original column
    }
    
    return report_data

def get_supabase_client():
    """Initialize Supabase client with environment variables"""
    try:
        url = os.environ.get('SUPABASE_URL')
        key = os.environ.get('SUPABASE_ANON_KEY')
        
        if not url or not key:
            raise Exception("SUPABASE_URL and SUPABASE_ANON_KEY environment variables are required")
        
        supabase: Client = create_client(url, key)
        return supabase
    except Exception as e:
        print(f"Error initializing Supabase client: {e}")
        return None

def update_spot_to_supabase(spot_name, table_name="surf_reports"):
    """
    Update surf spot data in Supabase database.
    
    Args:
        spot_name: Name of the surf spot to update
        table_name: Name of the Supabase table (default: surf_reports)
    
    Returns:
        Dictionary with status and details
    """
    try:
        # Get surf report data
        print(f"Generating surf report for {spot_name}...")
        report_data = get_complete_surf_report(spot_name)
        
        if not report_data:
            return {
                "status": "error",
                "message": f"Failed to generate surf report for {spot_name}",
                "spot_name": spot_name,
                "timestamp": datetime.datetime.now().isoformat()
            }
        
        # Validate data - check for null values (except stream_link which can be null)
        validation_errors = []
        required_fields = [
            'water_temp_f',
            'wind_speed_mph', 
            'wind_direction_deg',
            'wave_forecast_168h',
            'period_forecast_168h',
            'tide_forecast_7d'
        ]
        
        for field in required_fields:
            value = report_data.get(field)
            if value is None:
                validation_errors.append(f"{field} is null")
            elif isinstance(value, list) and len(value) == 0:
                validation_errors.append(f"{field} is empty")
        
        # Check if essential forecast data is present and valid
        if report_data.get('wave_forecast_168h'):
            wave_data = report_data['wave_forecast_168h']
            if not isinstance(wave_data, list) or len(wave_data) < 24:  # At least 1 day of data
                validation_errors.append("wave_forecast_168h has insufficient data (less than 24 hours)")
        
        if report_data.get('period_forecast_168h'):
            period_data = report_data['period_forecast_168h']  
            if not isinstance(period_data, list) or len(period_data) < 24:  # At least 1 day of data
                validation_errors.append("period_forecast_168h has insufficient data (less than 24 hours)")
        
        if report_data.get('tide_forecast_7d'):
            tide_data = report_data['tide_forecast_7d']
            if not isinstance(tide_data, list) or len(tide_data) < 4:  # At least 4 tide events
                validation_errors.append("tide_forecast_7d has insufficient data (less than 4 tide events)")
        
        # If validation fails, return error without updating database
        if validation_errors:
            error_message = f"Validation failed for {spot_name}: " + "; ".join(validation_errors)
            print(f"❌ {error_message}")
            return {
                "status": "error",
                "message": error_message,
                "validation_errors": validation_errors,
                "spot_name": spot_name,
                "timestamp": datetime.datetime.now().isoformat()
            }
        
        print(f"✅ Data validation passed for {spot_name}")
        
        # Initialize Supabase client
        supabase = get_supabase_client()
        if not supabase:
            return {
                "status": "error", 
                "message": "Failed to initialize Supabase client",
                "spot_name": spot_name,
                "timestamp": datetime.datetime.now().isoformat()
            }
        
        # Prepare data for Supabase (convert datetime objects to ISO strings)
        db_data = report_data.copy()
        
        # Convert tide forecast datetime objects to ISO strings
        if db_data.get('tide_forecast_7d'):
            db_data['tide_forecast_7d'] = [
                (height, tide_type, dt.isoformat() if hasattr(dt, 'isoformat') else str(dt))
                for height, tide_type, dt in db_data['tide_forecast_7d']
            ]
        
        print(f"Inserting surf report into Supabase table '{table_name}'...")
        
        # Insert or update the data
        result = supabase.table(table_name).upsert(db_data).execute()
        
        if result.data:
            print(f"✅ Successfully updated {spot_name} in Supabase!")
            return {
                "status": "success",
                "message": f"Successfully updated surf report for {spot_name}",
                "spot_name": spot_name,
                "data_points": {
                    "wave_forecast": len(report_data.get('wave_forecast_168h', [])),
                    "period_forecast": len(report_data.get('period_forecast_168h', [])),
                    "tide_forecast": len(report_data.get('tide_forecast_7d', [])),
                    "wind_data": bool(report_data.get('wind', {}).get('speed_mph')),
                    "water_temp": bool(report_data.get('water_temp_f'))
                },
                "timestamp": report_data['timestamp']
            }
        else:
            return {
                "status": "error",
                "message": "Failed to insert data into Supabase",
                "spot_name": spot_name,
                "timestamp": datetime.datetime.now().isoformat()
            }
            
    except Exception as e:
        print(f"❌ Error updating {spot_name} to Supabase: {e}")
        return {
            "status": "error",
            "message": str(e),
            "spot_name": spot_name,
            "timestamp": datetime.datetime.now().isoformat()
        }

def main():
    """
    Main function - can be used for testing or generating reports for specific spots
    """
    # Example usage - get complete surf report for Tamarack
    spot_name = 'Tamarack'
    
    print(f"=== COMPLETE SURF REPORT FOR {spot_name.upper()} ===")
    report_data = get_complete_surf_report(spot_name)
    
    if report_data:
        print(f"\n✅ Successfully generated surf report!")
        print(f"📍 Spot: {report_data['spot_name']}")
        print(f"🕐 Timestamp: {report_data['timestamp']}")
        print(f"🌊 Wave forecast: {len(report_data['wave_forecast_168h'])} hours")
        print(f"⏱️  Period forecast: {len(report_data['period_forecast_168h'])} hours") 
        print(f"🌊 Tide forecast: {len(report_data['tide_forecast_7d'])} events")
        print(f"🌡️  Water temp: {report_data['water_temp_f']}°F" if report_data['water_temp_f'] else "🌡️  Water temp: N/A")
        print(f"💨 Wind: {report_data['wind']['speed_mph']:.1f}mph @ {report_data['wind']['direction_deg']:.0f}°" if report_data['wind']['speed_mph'] else "💨 Wind: N/A")
        
        print(f"\n📊 Spot Configuration:")
        config = report_data['spot_config']
        print(f"  Location: {config['location_n']:.3f}°N, {config['location_w']:.3f}°W")
        print(f"  Depth: {config['depth']}m, Angle: {config['angle']}°, Slope: {config['slope']}")
        print(f"  Tide Station: {config['closest_tide']}")
        print(f"  Wave Model: {config['wave_model']}")
        
        # This data structure is now ready for Supabase insertion
        print(f"\n🎯 Data structure ready for database insertion!")
        return report_data
    else:
        print(f"❌ Failed to generate surf report for {spot_name}")
        return None

if __name__ == '__main__':
    main()