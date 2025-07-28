import sys
import datetime
import matplotlib.pyplot as plt

import surfpy.surfpy as surfpy

def fetch_wind_forecast():
    """Fetch wind forecast data from weather model"""
    try:
        # Tamarack location
        tamarack_location = surfpy.Location(33.0742, -117.3095, altitude=30.0, name='Tamarack')
        
        print("Fetching wind forecast from weather model...")
        
        # Use the global weather model to get wind forecast
        global_weather_model = surfpy.weathermodel.global_gfs_weather_model()
        num_hours_to_forecast = 120  # 5 days
        weather_grib_data = global_weather_model.fetch_grib_datas(0, num_hours_to_forecast, tamarack_location)
        
        if weather_grib_data:
            raw_weather_data = global_weather_model.parse_grib_datas(tamarack_location, weather_grib_data)
            if raw_weather_data:
                weather_data = global_weather_model.to_buoy_data(raw_weather_data)
                if weather_data and len(weather_data) > 0:
                    print(f"Retrieved {len(weather_data)} hours of wind forecast data")
                    return weather_data
        
        print("No valid wind data from weather model")
        return None
        
    except Exception as e:
        print(f"Error fetching wind data: {e}")
        import traceback
        traceback.print_exc()
        return None

def degrees_to_compass(degrees):
    """Convert wind direction in degrees to compass direction"""
    if degrees is None:
        return "Variable"
    
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                 "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return directions[round(degrees / 22.5) % 16]

def wind_strength_description(speed):
    """Convert wind speed to descriptive text"""
    if speed < 5:
        return "Light"
    elif speed < 15:
        return "Moderate"
    elif speed < 25:
        return "Strong"
    else:
        return "Very Strong"

def plot_wind_forecast(weather_data):
    """Plot wind speed and direction over time"""
    if not weather_data:
        print("No wind data to plot")
        return
    
    # Extract wind data
    times = [x.date for x in weather_data]
    wind_speeds = [x.wind_speed for x in weather_data]
    wind_directions = [x.wind_direction for x in weather_data]
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10))
    
    # Plot 1: Wind Speed
    ax1.plot(times, wind_speeds, 'b-', linewidth=2, label="Wind Speed (mph)")
    ax1.fill_between(times, wind_speeds, alpha=0.3, color='blue')
    ax1.set_ylabel('Wind Speed (mph)', color='blue')
    ax1.set_title('Tamarack Beach - 5 Day Wind Forecast')
    ax1.grid(True, alpha=0.3)
    ax1.tick_params(axis='y', labelcolor='blue')
    
    # Plot 2: Wind Direction
    ax2.plot(times, wind_directions, 'r-', linewidth=2, label="Wind Direction (°)")
    ax2.set_xlabel('Time')
    ax2.set_ylabel('Wind Direction (°)', color='red')
    ax2.grid(True, alpha=0.3)
    ax2.tick_params(axis='y', labelcolor='red')
    
    # Add compass direction labels
    ax2.set_yticks([0, 45, 90, 135, 180, 225, 270, 315, 360])
    ax2.set_yticklabels(['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW', 'N'])
    
    plt.tight_layout()
    plt.show()

def print_current_conditions(weather_data):
    """Print current wind conditions"""
    if not weather_data:
        return
    
    current = weather_data[0]  # First data point (most recent)
    
    print("\n" + "="*50)
    print("CURRENT WIND CONDITIONS")
    print("="*50)
    
    compass_dir = getattr(current, 'wind_compass_direction', None)
    if not compass_dir:
        compass_dir = degrees_to_compass(current.wind_direction)
    
    strength = wind_strength_description(current.wind_speed)
    
    print(f"Wind Speed: {current.wind_speed:.1f} mph")
    print(f"Wind Direction: {compass_dir}")
    if current.wind_direction:
        print(f"Wind Direction (degrees): {current.wind_direction:.0f}°")
    print(f"Wind Strength: {strength}")
    print(f"Forecast Time: {current.date.strftime('%Y-%m-%d %I:%M %p')}")
    
    # Convert to knots
    speed_knots = current.wind_speed * 0.868976
    print(f"Wind Speed (knots): {speed_knots:.1f} kts")

def print_wind_summary(weather_data):
    """Print wind forecast summary"""
    if not weather_data:
        return
    
    print("\n" + "="*60)
    print("5-DAY WIND FORECAST SUMMARY")
    print("="*60)
    
    # Group by day
    daily_data = {}
    for data_point in weather_data:
        date = data_point.date.date()
        if date not in daily_data:
            daily_data[date] = []
        daily_data[date].append(data_point)
    
    for date, day_data in sorted(daily_data.items())[:5]:  # 5 days
        print(f"\n{date.strftime('%A, %B %d, %Y')}")
        print("-" * 30)
        
        # Calculate daily stats
        speeds = [d.wind_speed for d in day_data]
        directions = [d.wind_direction for d in day_data if d.wind_direction is not None]
        
        avg_speed = sum(speeds) / len(speeds)
        max_speed = max(speeds)
        min_speed = min(speeds)
        
        if directions:
            avg_direction = sum(directions) / len(directions)
            most_common_compass = degrees_to_compass(avg_direction)
        else:
            most_common_compass = 'Variable'
        
        print(f"  Average: {avg_speed:.1f} mph {most_common_compass}")
        print(f"  Range: {min_speed:.1f} - {max_speed:.1f} mph")
        
        # Show key times (morning, afternoon, evening)
        key_times = []
        for d in day_data:
            hour = d.date.hour
            if hour in [6, 12, 18]:  # 6am, 12pm, 6pm
                compass_dir = getattr(d, 'wind_compass_direction', None)
                if not compass_dir:
                    compass_dir = degrees_to_compass(d.wind_direction)
                time_str = d.date.strftime('%I%p').lower()
                key_times.append(f"{time_str}: {d.wind_speed:.1f}mph {compass_dir}")
        
        if key_times:
            print(f"  Key Times: {' | '.join(key_times)}")

if __name__ == '__main__':
    print("=== TAMARACK BEACH - WIND FORECAST ===")
    print(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Using NOAA Global Forecast System (GFS) Weather Model")
    print()
    
    # Fetch wind forecast data
    weather_data = fetch_wind_forecast()
    
    if weather_data:
        # Show current conditions
        print_current_conditions(weather_data)
        
        # Create wind forecast plot
        plot_wind_forecast(weather_data)
        
        # Print forecast summary
        print_wind_summary(weather_data)
        
    else:
        print("Failed to retrieve wind forecast data from weather model.")
        
    print(f"\n=== Report completed at {datetime.datetime.now().strftime('%H:%M:%S')} ===")