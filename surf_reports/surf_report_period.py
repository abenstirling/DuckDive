import sys
import matplotlib.pyplot as plt
import surfpy

def get_period_forecast(wave_location, num_hours_to_forecast):
    """
    Get wave period forecast data for a given location and time period.
    
    Args:
        wave_location: surfpy.Location object with depth, angle, and slope set
        num_hours_to_forecast: Number of hours to forecast (e.g., 168 for 7 days)
    
    Returns:
        List of tuples: [(period_seconds, hour_#), ...] for each hour from 0 to num_hours_to_forecast
    """
    global_wave_model = surfpy.us_west_coast_gfs_wave_model()

    print('Fetching GFS Wave Data for period forecast')
    wave_grib_data = global_wave_model.fetch_grib_datas(0, num_hours_to_forecast, wave_location)
    raw_wave_data = global_wave_model.parse_grib_datas(wave_location, wave_grib_data)
    if raw_wave_data:
        data = global_wave_model.to_buoy_data(raw_wave_data)
    else:
        print('Failed to fetch wave forecast data')
        return None

    # Process the wave data
    for dat in data:
        dat.solve_breaking_wave_heights(wave_location)
        dat.change_units(surfpy.units.Units.english)

    # Extract period data
    periods = [x.wave_summary.period for x in data]
    times = [x.date for x in data]

    # Plot disabled for backend use
    # plt.plot(times, periods, c='purple', label='Wave Period', linewidth=2)
    # plt.xlabel('Hours')
    # plt.ylabel('Wave Period (seconds)')
    # plt.grid(True)
    # plt.legend()
    # plt.title('GFS Wave Period: ' + global_wave_model.latest_model_time().strftime('%d/%m/%Y %Hz'))
    # plt.show()

    # Build the result list with (period, hour_#) format
    # Model returns data every 3 hours, so multiply index by 3
    result = []
    for i, dat in enumerate(data):
        period = dat.wave_summary.period
        hour = i * 3  # Every 3 hours: 0, 3, 6, 9, 12, etc.
        result.append((period, hour))
    
    return result

if __name__=='__main__':
    # Set wave location
    wave_location = surfpy.Location(33.0742, -117.3095, altitude=30.0, name='Tamarack')
    wave_location.depth = 25.0
    wave_location.angle = 225.0
    wave_location.slope = 0.02
    
    num_hours_to_forecast = 168  # 7 day forecast
    forecast_data = get_period_forecast(wave_location, num_hours_to_forecast)
    
    # Show all forecast data
    if forecast_data:
        for period, hour in forecast_data:
            print(f"Hour {hour}: Period={period:.1f}s")
    else:
        print('Failed to fetch wave forecast data')
        sys.exit(1)
