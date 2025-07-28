import sys
import matplotlib.pyplot as plt

import surfpy.surfpy as surfpy

if __name__=='__main__':
    # Set wave location
    wave_location = surfpy.Location(33.0742, -117.3095, altitude=30.0, name='Tamarack')
    wave_location.depth = 25.0
    wave_location.angle = 225.0
    wave_location.slope = 0.02
    global_wave_model = surfpy.us_west_coast_gfs_wave_model()

    print('Fetching GFS Wave Data')
    num_hours_to_forecast = 192 # 6 hour forecast. Change to 384 to get a 16 day forecast
    wave_grib_data = global_wave_model.fetch_grib_datas(0, num_hours_to_forecast, wave_location)
    raw_wave_data = global_wave_model.parse_grib_datas(wave_location, wave_grib_data)
    if raw_wave_data:
        data = global_wave_model.to_buoy_data(raw_wave_data)
    else:
        print('Failed to fetch wave forecast data')
        sys.exit(1)


    # Show breaking wave heights
    for dat in data:
        dat.solve_breaking_wave_heights(wave_location)
        dat.change_units(surfpy.units.Units.english)

    maxs =[x.maximum_breaking_height for x in data]
    mins = [x.minimum_breaking_height for x in data]
    summary = [x.wave_summary.wave_height for x in data]
    times = [x.date for x in data]

    plt.plot(times, maxs, c='green')
    plt.plot(times, mins, c='blue')
    plt.plot(times, summary, c='red')
    plt.xlabel('Hours')
    plt.ylabel('Breaking Wave Height (ft)')
    plt.grid(True)
    plt.title('GFS Wave Global: ' + global_wave_model.latest_model_time().strftime('%d/%m/%Y %Hz'))
    plt.show()