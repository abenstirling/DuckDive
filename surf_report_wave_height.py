import sys
import matplotlib.pyplot as plt
import surfpy.surfpy as surfpy

def get_surf_forecast(wave_location, num_hours_to_forecast):
    """
    Get surf forecast data for a given location and time period.
    
    Args:
        wave_location: surfpy.Location object with depth, angle, and slope set
        num_hours_to_forecast: Number of hours to forecast (e.g., 168 for 7 days)
    
    Returns:
        List of tuples: [(high, low, avg, hour_#), ...] for each hour from 0 to num_hours_to_forecast
    """
    global_wave_model = surfpy.us_west_coast_gfs_wave_model()

    print('Fetching GFS Wave Data')
    wave_grib_data = global_wave_model.fetch_grib_datas(0, num_hours_to_forecast, wave_location)
    raw_wave_data = global_wave_model.parse_grib_datas(wave_location, wave_grib_data)
    if raw_wave_data:
        data = global_wave_model.to_buoy_data(raw_wave_data)
    else:
        print('Failed to fetch wave forecast data')
        return None

    # Show breaking wave heights
    for dat in data:
        dat.solve_breaking_wave_heights(wave_location)
        dat.change_units(surfpy.units.Units.english)

    maxs = [x.maximum_breaking_height for x in data]
    mins = [x.minimum_breaking_height for x in data]
    summary = [x.wave_summary.wave_height for x in data]
    times = [x.date for x in data]

    # Plot disabled for backend use
    # plt.plot(times, maxs, c='green', label='Max')
    # plt.plot(times, mins, c='blue', label='Min')
    # plt.plot(times, summary, c='red', label='Average')
    # plt.xlabel('Hours')
    # plt.ylabel('Breaking Wave Height (ft)')
    # plt.grid(True)
    # plt.legend()
    # plt.title('GFS Wave Global: ' + global_wave_model.latest_model_time().strftime('%d/%m/%Y %Hz'))
    # plt.show()

    # Build the result list with (high, low, avg, hour_#) format
    # Model returns data every 3 hours, so multiply index by 3
    result = []
    for i, dat in enumerate(data):
        high = dat.maximum_breaking_height
        low = dat.minimum_breaking_height
        avg = dat.wave_summary.wave_height
        hour = i * 3  # Every 3 hours: 0, 3, 6, 9, 12, etc.
        result.append((high, low, avg, hour))
    
    return result

if __name__=='__main__':
    # Set wave location
    wave_location = surfpy.Location(33.0742, -117.3095, altitude=30.0, name='Tamarack')
    wave_location.depth = 25.0
    wave_location.angle = 225.0
    wave_location.slope = 0.02
    
    num_hours_to_forecast = 168  # 7 day forecast
    forecast_data = get_surf_forecast(wave_location, num_hours_to_forecast)
    
    if forecast_data:
        for high, low, avg, hour in forecast_data[:10]:  # Show first 10 hours as example
            print(f"Hour {hour}: High={high:.1f}ft, Low={low:.1f}ft, Avg={avg:.1f}ft")
    else:
        print('Failed to fetch wave forecast data')
        sys.exit(1)