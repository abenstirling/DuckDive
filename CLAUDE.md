# Tamarack Surf Forecast - Claude Assistant Context

## Project Overview
A real-time surf forecasting application focused specifically on Tamarack beach in San Diego County, providing accurate wave and tide predictions using NOAA data.

## Key Features
- **Real NOAA Data**: Uses GFS Wave Model (US West Coast) and San Diego Tide Station (9410170)
- **Precise Location**: Tamarack coordinates (33.146635°N, 117.345818°W)
- **Wave Heights**: Displayed to 1 decimal place (e.g., 2.1 ft)
- **5-Day Forecast**: Complete wave and tide predictions
- **Interactive Charts**: ECharts-powered visualizations
- **Clean Design**: Simplified, modern interface

## Technology Stack
- **Backend**: FastAPI (Python)
- **Frontend**: HTML/JavaScript with Tailwind CSS
- **Charts**: Apache ECharts
- **Data Source**: SurfPy library for NOAA integration

## File Structure
```
/Users/bens/Documents/git/onshoresurf/
├── main.py                 # FastAPI application
├── static/
│   └── index.html         # Frontend interface
├── surfpy/                # SurfPy library (submodule)
├── requirements.txt       # Python dependencies
└── CLAUDE.md             # This file
```

## API Endpoints
- `GET /` - Main Tamarack forecast page
- `GET /api/tamarack/forecast` - Complete forecast with chart data
- `GET /api/tamarack/current` - Current wave and tide conditions

## Development Commands
```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
python main.py

# Access application
open http://localhost:8000
```

## Data Sources
- **Waves**: NOAA GFS Wave Model - US West Coast (16km resolution)
- **Tides**: NOAA Tide Station 9410170 (San Diego, CA)
- **Processing**: SurfPy library for breaking wave height calculations

## Key Dependencies
- fastapi
- surfpy (NOAA data integration)
- uvicorn (ASGI server)
- matplotlib (for backend plotting)
- pygrib (GRIB file processing)
- pytz (timezone handling)

## Recent Updates
1. Fixed 500 Internal Server Error in current conditions API
2. Simplified design with clean, minimal UI
3. Replaced matplotlib with beautiful ECharts graphs
4. Focused application solely on Tamarack location
5. Added proper error handling and debugging

## Known Issues
- None currently identified

## Future Enhancements
- Wind data integration
- Best surf time recommendations
- Mobile app version
- Additional Southern California spots

## Data Update Frequency
- Wave forecasts: Updated every 6 hours (NOAA GFS model schedule)
- Tide predictions: Updated daily
- Frontend refresh: Every 15 minutes

## Testing
```bash
# Test current conditions
curl http://localhost:8000/api/tamarack/current

# Test forecast data
curl http://localhost:8000/api/tamarack/forecast
```

## Troubleshooting
- Ensure surfpy submodule is properly initialized
- Check NOAA data availability if forecast fails
- Verify eccodes installation for GRIB processing
- Use browser dev tools to debug frontend chart rendering