import sys
import datetime
from surfpy.buoystation import BuoyStation
import surfpy

def get_water_temp_forecast(wave_location, hours_forecast=1):
    """
    Get water temperature data for a specific location.
    
    Args:
        wave_location: surfpy.Location object with location details
        hours_forecast: number of hours (currently only returns current temp)
    
    Returns:
        List of tuples: [(water_temp, hour), ...] - currently just one reading
    """
    try:
        print("Fetching water temperature from Torrey Pines Outer buoy (46225)...")
        
        # Use Torrey Pines Outer buoy for data
        torrey_pines_buoy = BuoyStation('46225', wave_location)
        
        # Fetch latest reading
        latest_reading = torrey_pines_buoy.fetch_latest_reading()
        
        if latest_reading and hasattr(latest_reading, 'water_temperature') and latest_reading.water_temperature is not None:
            water_temp_f = latest_reading.water_temperature
            
            # Check for valid data
            if water_temp_f == water_temp_f and water_temp_f != -999:  # Not NaN and not missing
                # Return as list of tuples with hour 0 (current reading)
                return [(water_temp_f, 0)]
        
        # Try backup stations
        backup_stations = [
            ('46232', 'Point Loma'),
            ('46086', 'San Clemente Basin'),
            ('46069', 'South Santa Rosa Island')
        ]
        
        for station_id, station_name in backup_stations:
            try:
                print(f"Trying backup station {station_id} ({station_name})...")
                buoy = BuoyStation(station_id, wave_location)
                latest_reading = buoy.fetch_latest_reading()
                
                if latest_reading and hasattr(latest_reading, 'water_temperature'):
                    water_temp_f = latest_reading.water_temperature
                    if water_temp_f == water_temp_f and water_temp_f != -999:  # Valid data
                        return [(water_temp_f, 0)]
                        
            except Exception as e:
                print(f"Error with backup station {station_id}: {e}")
                continue
                
    except Exception as e:
        print(f"Error fetching water temperature: {e}")
        
    return []

def get_water_temperature():
    """Get current water temperature from Torrey Pines Outer buoy (46225)"""
    try:
        print("Fetching water temperature from Torrey Pines Outer buoy (46225)...")
        
        # Create location for Tamarack (where we want predictions)
        tamarack_location = surfpy.Location(33.0742, -117.3095, altitude=30.0, name='Tamarack')
        tamarack_location.depth = 25.0
        tamarack_location.angle = 225.0
        tamarack_location.slope = 0.02
        
        # Use Torrey Pines Outer buoy for data
        torrey_pines_buoy = BuoyStation('46225', tamarack_location)
        
        # Fetch latest reading
        latest_reading = torrey_pines_buoy.fetch_latest_reading()
        
        if latest_reading:
            print(f"Successfully fetched buoy data from station 46225")
            
            # Check if water temperature is available and valid
            if hasattr(latest_reading, 'water_temperature') and latest_reading.water_temperature is not None:
                water_temp_f = latest_reading.water_temperature
                
                # Check for invalid data (NaN or missing data indicators)
                if water_temp_f == water_temp_f and water_temp_f != -999:  # Not NaN and not missing
                    water_temp_c = (water_temp_f - 32) * 5/9
                    
                    print(f"Water Temperature: {water_temp_f:.1f}°F ({water_temp_c:.1f}°C)")
                    print(f"Station: Torrey Pines Outer (46225)")
                    
                    # Also print other available data if present
                    if hasattr(latest_reading, 'date'):
                        print(f"Reading time: {latest_reading.date}")
                    
                    return {
                        "water_temp_f": round(water_temp_f, 1),
                        "water_temp_c": round(water_temp_c, 1),
                        "station": "Torrey Pines Outer",
                        "station_id": "46225",
                        "timestamp": latest_reading.date if hasattr(latest_reading, 'date') else None
                    }
                else:
                    print(f"Invalid water temperature data: {water_temp_f}")
            else:
                print("No water temperature data available from this buoy")
                
            # Print available attributes for debugging
            print(f"Available data attributes: {[attr for attr in dir(latest_reading) if not attr.startswith('_')]}")
            
        else:
            print("Failed to fetch data from Torrey Pines Outer buoy")
            
    except Exception as e:
        print(f"Error fetching water temperature: {e}")
        import traceback
        traceback.print_exc()
        
    return None

def get_backup_water_temperature():
    """Fallback to other nearby buoys if Torrey Pines data not available"""
    backup_stations = [
        ('46232', 'Point Loma'),
        ('46086', 'San Clemente Basin'),
        ('46069', 'South Santa Rosa Island')
    ]
    
    tamarack_location = surfpy.Location(33.0742, -117.3095, altitude=30.0, name='Tamarack')
    
    for station_id, station_name in backup_stations:
        try:
            print(f"Trying backup station {station_id} ({station_name})...")
            buoy = BuoyStation(station_id, tamarack_location)
            latest_reading = buoy.fetch_latest_reading()
            
            if latest_reading and hasattr(latest_reading, 'water_temperature'):
                water_temp_f = latest_reading.water_temperature
                if water_temp_f == water_temp_f and water_temp_f != -999:  # Valid data
                    water_temp_c = (water_temp_f - 32) * 5/9
                    
                    print(f"Backup water temperature from {station_name}: {water_temp_f:.1f}°F ({water_temp_c:.1f}°C)")
                    
                    return {
                        "water_temp_f": round(water_temp_f, 1),
                        "water_temp_c": round(water_temp_c, 1),
                        "station": station_name,
                        "station_id": station_id,
                        "timestamp": latest_reading.date if hasattr(latest_reading, 'date') else None
                    }
                    
        except Exception as e:
            print(f"Error with backup station {station_id}: {e}")
            continue
    
    return None

if __name__ == '__main__':
    print("=== Tamarack Water Temperature Report ===")
    print(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Try primary station first
    water_temp = get_water_temperature()
    
    if not water_temp:
        print("\nTrying backup stations...")
        water_temp = get_backup_water_temperature()
    
    if water_temp:
        print(f"\n=== FINAL RESULT ===")
        print(f"Water Temperature: {water_temp['water_temp_f']}°F ({water_temp['water_temp_c']}°C)")
        print(f"Source: {water_temp['station']} (Station {water_temp['station_id']})")
        if water_temp['timestamp']:
            print(f"Reading Time: {water_temp['timestamp']}")
    else:
        print("\n=== NO DATA AVAILABLE ===")
        print("Unable to retrieve water temperature from any buoy stations")