# DuckDive MCP Server Setup

This MCP server provides surf data access for Claude through the Model Context Protocol.

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables in `.env`:
```
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_supabase_anon_key
```

3. Update the path in `mcp_config.json` to match your local installation.

## Claude Configuration

Add this to your Claude Desktop configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "duckdive-surf": {
      "command": "python",
      "args": ["/path/to/your/DuckDive/mcp_server.py"],
      "env": {
        "SUPABASE_URL": "your_supabase_url_here",
        "SUPABASE_ANON_KEY": "your_supabase_anon_key_here"
      }
    }
  }
}
```

## Available Tools

- `get_current_surf_conditions`: Get current surf conditions for a spot
- `get_wave_forecast`: Get wave height and period forecast (up to 168 hours)
- `get_tide_forecast`: Get tide forecast (up to 7 days) 
- `list_surf_spots`: List all available surf spots

## Usage Example

After setup, you can ask Claude:
- "What are the current surf conditions at Tamarack?"
- "Show me the wave forecast for Swamis"
- "What surf spots are available?"
- "When is the next high tide at Blacks?"