import surfpy.surfpy as surfpy
import matplotlib.pyplot as plt
from surf_report_wave_height import get_surf_forecast
from surf_report_water_temperature import get_water_temp_forecast

def main():
    # Set up wave location for Tamarack
    wave_location = surfpy.Location(33.0742, -117.3095, altitude=30.0, name='Tamarack')
    wave_location.depth = 25.0
    wave_location.angle = 225.0
    wave_location.slope = 0.02
    
    # Set up wave model
    wave_model = surfpy.us_west_coast_gfs_wave_model()
    
    # Get one week forecast (168 hours)  
    num_hours_to_forecast = 168
    
    # Get global surf forecast
    forecast_data = get_surf_forecast(wave_location, num_hours_to_forecast)
    
    # Get water temperature
    water_temp_data = get_water_temp_forecast(wave_location, 1)
    
    if forecast_data:
        print("All surf forecast data fetched successfully")
        print(f"Forecasting for {num_hours_to_forecast} hours starting now...")
        print(f"Location: {wave_location.name} ({wave_location.latitude}, {wave_location.longitude})")
        print(f"Depth: {wave_location.depth}m, Angle: {wave_location.angle}°, Slope: {wave_location.slope}")
        print(f"Total forecast hours: {len(forecast_data)}")
        print("Forecast data for each hour:")
        print(f"Total forecast hours: {len(forecast_data)}")
        print("Forecast data for each hour:")
        for high, low, avg, hour in forecast_data:
            print(f"Hour {hour}: High={high:.1f}ft, Low={low:.1f}ft, Avg={avg:.1f}ft")

        # Extract data for plotting
        hours = [hour for high, low, avg, hour in forecast_data]
        highs = [high for high, low, avg, hour in forecast_data]
        lows = [low for high, low, avg, hour in forecast_data]
        avgs = [avg for high, low, avg, hour in forecast_data]
        
        # Calculate wave statistics
        max_height = max(highs)
        min_height = min(lows)
        overall_avg = sum(avgs) / len(avgs)
        
        print(f"Max: {max_height:.2f} ft")
        print(f"Min: {min_height:.2f} ft") 
        print(f"Average: {overall_avg:.2f} ft")
        
        # Plot the data
        plt.figure(figsize=(12, 6))
        plt.plot(hours, highs, c='green', label='High', linewidth=2)
        plt.plot(hours, lows, c='blue', label='Low', linewidth=2)
        plt.plot(hours, avgs, c='red', label='Average', linewidth=2)
        
        # Add day markers
        day_hours = [0, 24, 48, 72, 96, 120, 144, 168]
        day_labels = ['Day 1', 'Day 2', 'Day 3', 'Day 4', 'Day 5', 'Day 6', 'Day 7', 'Day 8']
        
        # Only show day markers that exist in our data
        valid_day_hours = [h for h in day_hours if h <= max(hours)]
        valid_day_labels = day_labels[:len(valid_day_hours)]
        
        plt.xticks(valid_day_hours, valid_day_labels, rotation=45)
        plt.xlabel('Days')
        plt.ylabel('Breaking Wave Height (ft)')
        plt.title('Surf Forecast - Tamarack')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
    else:
        print("No wave forecast data available")
    
    if water_temp_data:
        print(f"\nWater Temperature: {water_temp_data[0][0]:.1f}°F")
    else:
        print("\nNo water temperature data available")

if __name__ == '__main__':
    main()