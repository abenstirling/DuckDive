import sys
import datetime
import surfpy.surfpy as surfpy

def get_tide_forecast(station_id):
    """
    Get 7-day tide forecast for a given station.
    
    Args:
        station_id: NOAA tide station ID (e.g., '9410230' for La Jolla)
    
    Returns:
        List of tuples: [(tide_height_ft, tide_type, datetime), ...] for the week
        tide_type will be 'HIGH' or 'LOW'
    """
    try:
        print(f"Fetching tide data for station {station_id}...")
        stations = surfpy.TideStations()
        stations.fetch_stations()
        
        # Find the station in the list
        station = None
        for s in stations.stations:
            if getattr(s, 'station_id', '') == station_id:
                station = s
                break
        
        if not station:
            print(f"Station {station_id} not found")
            return None
        
        print(f"Using station: {station.name}")
        
        # Set date range - 1 week from today
        today = datetime.datetime.today()
        end_date = today + datetime.timedelta(days=7)
        
        # Fetch tidal events (high/low tides)
        tidal_events, _ = station.fetch_tide_data(
            today, 
            end_date, 
            interval=surfpy.TideStation.DataInterval.high_low,
            unit=surfpy.units.Units.english
        )
        
        if not tidal_events:
            print("No tidal events retrieved")
            return None
        
        print(f"Retrieved {len(tidal_events)} tidal events")
        
        # Build the result list with (height, type, datetime) format
        result = []
        for event in tidal_events:
            height = event.water_level
            tide_type = "HIGH" if event.tidal_event == surfpy.TideEvent.TidalEventType.high_tide else "LOW"
            datetime_obj = event.date
            result.append((height, tide_type, datetime_obj))
        
        return result
        
    except Exception as e:
        print(f"Error fetching tide data: {e}")
        return None

if __name__ == '__main__':
    # Test the function with La Jolla station (closest to Tamarack)
    la_jolla_station_id = '9410230'
    
    tide_data = get_tide_forecast(la_jolla_station_id)
    
    if tide_data:
        print(f"\n7-day tide forecast:")
        for height, tide_type, dt in tide_data:
            print(f"{dt.strftime('%m/%d %I:%M %p')}: {tide_type} tide at {height:.1f}ft")
    else:
        print("Failed to retrieve tide data")