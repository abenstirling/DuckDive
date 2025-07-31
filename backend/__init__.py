"""
DuckDive Backend Package

This package contains all the surf report data fetching and processing modules.
Each module handles a specific type of oceanographic data from NOAA sources.
"""

# Import main functions for easy access
from .surf_report_update_spot import update_spot_to_supabase
from .surf_report_wave_height import get_surf_forecast
from .surf_report_tides import get_tide_forecast
from .surf_report_winds import get_current_wind
from .surf_report_water_temperature import get_water_temp_forecast
from .surf_report_period import get_period_forecast

__all__ = [
    'update_spot_to_supabase',
    'get_surf_forecast',
    'get_tide_forecast', 
    'get_current_wind',
    'get_water_temp_forecast',
    'get_period_forecast'
]