import sys
import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

import surfpy.surfpy as surfpy

def fetch_tide_data():
    """Fetch tide data for Tamarack area using La Jolla station"""
    try:
        print("Fetching tide stations...")
        stations = surfpy.TideStations()
        stations.fetch_stations()
        
        # Use La Jolla station (closest to Tamarack)
        la_jolla_station_id = '9410230'
        
        # Find the station in the list
        station = None
        for s in stations.stations:
            if getattr(s, 'station_id', '') == la_jolla_station_id:
                station = s
                break
        
        if not station:
            print(f"Station {la_jolla_station_id} not found")
            return None, None
        
        print(f"Using station: {station.name} ({la_jolla_station_id})")
        
        # Set date range - 1 week from today
        today = datetime.datetime.today()
        end_date = today + datetime.timedelta(days=7)
        
        print(f"Fetching tide data from {today.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        
        # Fetch both tidal events (high/low) and continuous water level data
        print("Fetching tidal events (high/low tides)...")
        tidal_events, _ = station.fetch_tide_data(
            today, 
            end_date, 
            interval=surfpy.TideStation.DataInterval.high_low,
            unit=surfpy.units.Units.english
        )
        
        print("Fetching continuous water level data...")
        _, tidal_data = station.fetch_tide_data(
            today, 
            end_date, 
            interval=surfpy.TideStation.DataInterval.default,
            unit=surfpy.units.Units.english
        )
        
        if tidal_events:
            print(f"Retrieved {len(tidal_events)} tidal events")
        if tidal_data:
            print(f"Retrieved {len(tidal_data)} continuous data points")
            
        return tidal_events, tidal_data
        
    except Exception as e:
        print(f"Error fetching tide data: {e}")
        import traceback
        traceback.print_exc()
        return None, None

def plot_tide_chart(tidal_events, tidal_data):
    """Create comprehensive tide chart"""
    if not tidal_events and not tidal_data:
        print("No tide data to plot")
        return
    
    fig, ax = plt.subplots(figsize=(15, 8))
    
    # Plot continuous water level if available
    if tidal_data:
        dates = [x.date for x in tidal_data]
        levels = [x.water_level for x in tidal_data]
        ax.plot(dates, levels, 'b-', linewidth=2, label='Water Level', alpha=0.7)
    
    # Plot tidal events (high/low points)
    if tidal_events:
        high_dates = [x.date for x in tidal_events if x.tidal_event == surfpy.TideEvent.TidalEventType.high_tide]
        high_levels = [x.water_level for x in tidal_events if x.tidal_event == surfpy.TideEvent.TidalEventType.high_tide]
        low_dates = [x.date for x in tidal_events if x.tidal_event == surfpy.TideEvent.TidalEventType.low_tide]
        low_levels = [x.water_level for x in tidal_events if x.tidal_event == surfpy.TideEvent.TidalEventType.low_tide]
        
        ax.scatter(high_dates, high_levels, c='green', s=100, marker='^', label='High Tide', zorder=5)
        ax.scatter(low_dates, low_levels, c='red', s=100, marker='v', label='Low Tide', zorder=5)
        
        # Add text labels for high/low times and heights
        for date, level in zip(high_dates, high_levels):
            ax.annotate(f'{level:.1f}ft\n{date.strftime("%I:%M%p")}', 
                       xy=(date, level), xytext=(5, 10), 
                       textcoords='offset points', fontsize=8, 
                       ha='left', va='bottom', color='green')
        
        for date, level in zip(low_dates, low_levels):
            ax.annotate(f'{level:.1f}ft\n{date.strftime("%I:%M%p")}', 
                       xy=(date, level), xytext=(5, -20), 
                       textcoords='offset points', fontsize=8, 
                       ha='left', va='top', color='red')
    
    # Format the chart
    ax.set_xlabel('Date and Time')
    ax.set_ylabel('Water Level (feet)')
    ax.set_title('Tamarack Beach - 7 Day Tide Forecast\n(La Jolla Station 9410230)')
    ax.grid(True, alpha=0.3)
    ax.legend()
    
    # Format x-axis to show dates nicely
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d\n%I%p'))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=12))
    ax.xaxis.set_minor_locator(mdates.HourLocator(interval=6))
    
    # Rotate x-axis labels for better readability
    plt.xticks(rotation=45)
    
    # Add zero line for reference
    ax.axhline(y=0, color='black', linestyle='--', alpha=0.5, linewidth=1)
    
    plt.tight_layout()
    plt.show()

def print_tide_summary(tidal_events):
    """Print a text summary of upcoming tides"""
    if not tidal_events:
        print("No tidal events data available")
        return
    
    print("\n" + "="*60)
    print("TAMARACK BEACH - 7 DAY TIDE SUMMARY")
    print("="*60)
    
    current_date = None
    for event in tidal_events:
        event_date = event.date.date()
        
        # Print date header for new days
        if current_date != event_date:
            current_date = event_date
            print(f"\n{event_date.strftime('%A, %B %d, %Y')}")
            print("-" * 40)
        
        # Format tide event
        tide_type = "HIGH" if event.tidal_event == surfpy.TideEvent.TidalEventType.high_tide else "LOW"
        time_str = event.date.strftime('%I:%M %p')
        height = event.water_level
        
        # Add quality indicators
        if tide_type == "HIGH":
            if height > 6.0:
                quality = "Excellent"
            elif height > 5.0:
                quality = "Good"
            elif height > 4.0:
                quality = "Fair"
            else:
                quality = "Poor"
        else:  # LOW tide
            if height < 0.5:
                quality = "Excellent"
            elif height < 1.0:
                quality = "Good"
            elif height < 1.5:
                quality = "Fair"
            else:
                quality = "Poor"
        
        print(f"  {time_str:>8} - {tide_type:>4} {height:>4.1f}ft ({quality})")

def analyze_surf_windows(tidal_events):
    """Analyze best surf windows based on tide patterns"""
    if not tidal_events:
        return
    
    print("\n" + "="*60)
    print("SURF WINDOW ANALYSIS")
    print("="*60)
    print("Best surf times are typically 1-2 hours before/after mid-tide")
    print("(when tide is moving but not too high or too low)")
    
    # Group events by day
    daily_events = {}
    for event in tidal_events:
        date = event.date.date()
        if date not in daily_events:
            daily_events[date] = []
        daily_events[date].append(event)
    
    for date, events in daily_events.items():
        if len(events) >= 2:
            print(f"\n{date.strftime('%A, %B %d')}:")
            
            # Find mid-tide times (between high and low)
            for i in range(len(events) - 1):
                current = events[i]
                next_event = events[i + 1]
                
                # Calculate mid-tide time and height
                mid_time = current.date + (next_event.date - current.date) / 2
                mid_height = (current.water_level + next_event.water_level) / 2
                
                # Determine if this is a good surf window
                if 1.5 <= mid_height <= 4.5:  # Good surf height range
                    window_start = mid_time - datetime.timedelta(hours=1.5)
                    window_end = mid_time + datetime.timedelta(hours=1.5)
                    
                    print(f"  Good surf window: {window_start.strftime('%I:%M %p')} - {window_end.strftime('%I:%M %p')}")
                    print(f"    Mid-tide: {mid_time.strftime('%I:%M %p')} at {mid_height:.1f}ft")

if __name__ == '__main__':
    print("=== TAMARACK BEACH - 7 DAY TIDE REPORT ===")
    print(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Using La Jolla tide station (9410230) - closest to Tamarack Beach")
    print()
    
    # Fetch tide data
    tidal_events, tidal_data = fetch_tide_data()
    
    if tidal_events or tidal_data:
        # Create visual chart
        plot_tide_chart(tidal_events, tidal_data)
        
        # Print text summary
        print_tide_summary(tidal_events)
        
        # Analyze surf windows
        analyze_surf_windows(tidal_events)
        
    else:
        print("Failed to retrieve tide data. Please check your internet connection and try again.")
        
    print(f"\n=== Report completed at {datetime.datetime.now().strftime('%H:%M:%S')} ===")