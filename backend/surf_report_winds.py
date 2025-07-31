import sys
import surfpy as surfpy

def get_current_wind(location):
    """
    Get current wind conditions for a given location.
    
    Args:
        location: surfpy.Location object
    
    Returns:
        Tuple: (wind_speed_mph, wind_direction_degrees) or None if failed
    """
    try:
        print("Fetching current wind data...")
        
        # Use the global weather model to get current wind data
        global_weather_model = surfpy.weathermodel.global_gfs_weather_model()
        num_hours_to_forecast = 6  # Just get current and next few hours
        weather_grib_data = global_weather_model.fetch_grib_datas(0, num_hours_to_forecast, location)
        
        if weather_grib_data:
            raw_weather_data = global_weather_model.parse_grib_datas(location, weather_grib_data)
            if raw_weather_data:
                weather_data = global_weather_model.to_buoy_data(raw_weather_data)
                if weather_data and len(weather_data) > 0:
                    current = weather_data[0]  # First data point (most recent)
                    wind_speed_mph = current.wind_speed
                    wind_direction = current.wind_direction
                    
                    print(f"Current wind: {wind_speed_mph:.1f} mph at {wind_direction:.0f}°")
                    return (wind_speed_mph, wind_direction)
        
        print("No valid wind data from weather model")
        return None
        
    except Exception as e:
        print(f"Error fetching wind data: {e}")
        return None

if __name__ == '__main__':
    # Test the function with Tamarack location
    wave_location = surfpy.Location(33.0742, -117.3095, altitude=30.0, name='Tamarack')
    
    wind_data = get_current_wind(wave_location)
    
    if wind_data:
        wind_speed, wind_direction = wind_data
        print(f"Current wind conditions at {wave_location.name}:")
        print(f"Speed: {wind_speed:.1f} mph")
        print(f"Direction: {wind_direction:.0f}°")
    else:
        print("Failed to retrieve current wind data")