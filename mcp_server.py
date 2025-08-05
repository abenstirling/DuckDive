#!/usr/bin/env python3
"""
MCP Server for DuckDive Surf Data

Provides surf forecasting data via Model Context Protocol (MCP) tools.
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool
from supabase import Client, create_client

load_dotenv()

class SurfDataMCPServer:
    def __init__(self):
        self.supabase: Optional[Client] = None
        self.surf_spots = self._load_surf_spots()
        
    def _load_surf_spots(self) -> Dict[str, Dict[str, Any]]:
        """Load surf spots from CSV file"""
        spots = {}
        try:
            import csv
            with open('surf_spots.csv', 'r') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    name = row['name'].strip().strip("'\"").lower()
                    spots[name] = {
                        "name": row['name'].strip().strip("'\""),
                        "lat": float(row['location_n'].strip()),
                        "lon": -float(row['location_w'].strip()),
                        "depth": float(row['depth'].strip()),
                        "angle": float(row['angle'].strip()),
                        "stream_link": row['stream_link'].strip() if row['stream_link'].strip().lower() != 'null' else None
                    }
        except Exception as e:
            # Fallback to hardcoded spots
            spots = {
                "tamarack": {"name": "Tamarack", "lat": 33.0742, "lon": -117.3095, "depth": 25.0, "angle": 225.0, "stream_link": None}
            }
        return spots
    
    async def initialize_supabase(self):
        """Initialize Supabase client"""
        if not self.supabase:
            self.supabase = create_client(
                os.getenv("SUPABASE_URL"),
                os.getenv("SUPABASE_ANON_KEY")
            )
    
    async def get_current_conditions(self, spot_name: str) -> Dict[str, Any]:
        """Get current surf conditions for a spot"""
        await self.initialize_supabase()
        
        try:
            # Query by spot_name first, fallback to spot column
            result = self.supabase.table('surf_reports').select('*').ilike('spot_name', spot_name).order('timestamp', desc=True).limit(1).execute()
            if not result.data:
                result = self.supabase.table('surf_reports').select('*').ilike('spot', spot_name).order('timestamp', desc=True).limit(1).execute()
            
            if result.data:
                data = result.data[0]
                
                # Extract current conditions
                current_conditions = {
                    'spot': data.get('spot_name', data.get('spot', spot_name)),
                    'timestamp': data.get('timestamp'),
                    'water_temp_f': round(data.get('water_temp_f'), 1) if data.get('water_temp_f') else None,
                    'wind_speed_mph': round(data.get('wind_speed_mph', data.get('wind_mph')), 1) if data.get('wind_speed_mph', data.get('wind_mph')) else None,
                    'wind_direction_deg': round(data.get('wind_direction_deg'), 0) if data.get('wind_direction_deg') else None,
                    'stream_link': data.get('stream_link'),
                }
                
                # Extract current wave/tide data from forecasts
                if data.get('wave_forecast_168h') and len(data.get('wave_forecast_168h')) > 0:
                    current_conditions['wave_height_ft'] = round(data.get('wave_forecast_168h')[0][2], 1)
                
                if data.get('period_forecast_168h') and len(data.get('period_forecast_168h')) > 0:
                    current_conditions['period_sec'] = round(data.get('period_forecast_168h')[0][0], 1)
                
                if data.get('tide_forecast_7d') and len(data.get('tide_forecast_7d')) > 0:
                    current_conditions['tide_height_ft'] = round(data.get('tide_forecast_7d')[0][0], 1)
                
                return current_conditions
            else:
                return {"error": "No data available", "spot": spot_name}
                
        except Exception as e:
            return {"error": f"Database error: {str(e)}", "spot": spot_name}
    
    async def get_wave_forecast(self, spot_name: str, hours: int = 168) -> Dict[str, Any]:
        """Get wave height and period forecast for a spot"""
        await self.initialize_supabase()
        
        try:
            result = self.supabase.table('surf_reports').select('*').ilike('spot_name', spot_name).order('timestamp', desc=True).limit(1).execute()
            if not result.data:
                result = self.supabase.table('surf_reports').select('*').ilike('spot', spot_name).order('timestamp', desc=True).limit(1).execute()
            
            if result.data:
                data = result.data[0]
                wave_forecast = data.get('wave_forecast_168h', [])[:hours//3]  # 3-hour intervals
                period_forecast = data.get('period_forecast_168h', [])[:hours//3]
                
                return {
                    'spot': data.get('spot_name', data.get('spot', spot_name)),
                    'timestamp': data.get('timestamp'),
                    'wave_forecast': wave_forecast,
                    'period_forecast': period_forecast,
                    'forecast_hours': len(wave_forecast) * 3
                }
            else:
                return {"error": "No forecast data available", "spot": spot_name}
                
        except Exception as e:
            return {"error": f"Database error: {str(e)}", "spot": spot_name}
    
    async def get_tide_forecast(self, spot_name: str, days: int = 7) -> Dict[str, Any]:
        """Get tide forecast for a spot"""
        await self.initialize_supabase()
        
        try:
            result = self.supabase.table('surf_reports').select('*').ilike('spot_name', spot_name).order('timestamp', desc=True).limit(1).execute()
            if not result.data:
                result = self.supabase.table('surf_reports').select('*').ilike('spot', spot_name).order('timestamp', desc=True).limit(1).execute()
            
            if result.data:
                data = result.data[0]
                tide_forecast = data.get('tide_forecast_7d', [])
                
                return {
                    'spot': data.get('spot_name', data.get('spot', spot_name)),
                    'timestamp': data.get('timestamp'),
                    'tide_forecast': tide_forecast,
                    'forecast_days': days
                }
            else:
                return {"error": "No tide data available", "spot": spot_name}
                
        except Exception as e:
            return {"error": f"Database error: {str(e)}", "spot": spot_name}

    async def list_surf_spots(self) -> Dict[str, Any]:
        """List all available surf spots"""
        return {
            'spots': [
                {
                    'name': spot_info['name'],
                    'key': spot_key,
                    'lat': spot_info['lat'],
                    'lon': spot_info['lon'],
                    'stream_link': spot_info.get('stream_link')
                }
                for spot_key, spot_info in self.surf_spots.items()
            ]
        }

server = Server("duckdive-surf")
surf_server = SurfDataMCPServer()

@server.list_tools()
async def list_tools() -> List[Tool]:
    """List available MCP tools for surf data"""
    return [
        Tool(
            name="get_current_surf_conditions",
            description="Get current surf conditions for a specific surf spot",
            inputSchema={
                "type": "object",
                "properties": {
                    "spot_name": {
                        "type": "string",
                        "description": "Name of the surf spot (e.g., 'tamarack', 'swamis', 'blacks')"
                    }
                },
                "required": ["spot_name"]
            }
        ),
        Tool(
            name="get_wave_forecast",
            description="Get wave height and period forecast for a surf spot",
            inputSchema={
                "type": "object",
                "properties": {
                    "spot_name": {
                        "type": "string",
                        "description": "Name of the surf spot"
                    },
                    "hours": {
                        "type": "integer",
                        "description": "Number of hours to forecast (default: 168, max: 168)",
                        "default": 168
                    }
                },
                "required": ["spot_name"]
            }
        ),
        Tool(
            name="get_tide_forecast",
            description="Get tide forecast for a surf spot",
            inputSchema={
                "type": "object",
                "properties": {
                    "spot_name": {
                        "type": "string",
                        "description": "Name of the surf spot"
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days to forecast (default: 7, max: 7)",
                        "default": 7
                    }
                },
                "required": ["spot_name"]
            }
        ),
        Tool(
            name="list_surf_spots",
            description="List all available surf spots with their locations",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Handle MCP tool calls"""
    
    if name == "get_current_surf_conditions":
        spot_name = arguments.get("spot_name")
        if not spot_name:
            return [{"type": "text", "text": "Error: spot_name is required"}]
        
        result = await surf_server.get_current_conditions(spot_name)
        return [{"type": "text", "text": json.dumps(result, indent=2)}]
    
    elif name == "get_wave_forecast":
        spot_name = arguments.get("spot_name")
        hours = arguments.get("hours", 168)
        if not spot_name:
            return [{"type": "text", "text": "Error: spot_name is required"}]
        
        result = await surf_server.get_wave_forecast(spot_name, hours)
        return [{"type": "text", "text": json.dumps(result, indent=2)}]
    
    elif name == "get_tide_forecast":
        spot_name = arguments.get("spot_name")
        days = arguments.get("days", 7)
        if not spot_name:
            return [{"type": "text", "text": "Error: spot_name is required"}]
        
        result = await surf_server.get_tide_forecast(spot_name, days)
        return [{"type": "text", "text": json.dumps(result, indent=2)}]
    
    elif name == "list_surf_spots":
        result = await surf_server.list_surf_spots()
        return [{"type": "text", "text": json.dumps(result, indent=2)}]
    
    else:
        return [{"type": "text", "text": f"Error: Unknown tool '{name}'"}]

async def main():
    """Run the MCP server"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="duckdive-surf",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=None,
                    experimental_capabilities=None,
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())