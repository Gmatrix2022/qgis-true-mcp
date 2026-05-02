#!/usr/bin/env python3
"""
Run QGIS MCP Server — stdio mode (default)

Usage:
  python run_server.py                    # stdio (for Claude Desktop / Cursor)
  python run_server.py --transport sse    # SSE mode
  python run_server.py --transport http   # HTTP mode
  python run_server.py --host 192.168.0.100 --port 9876  # Custom QGIS target

Environment variables:
  QGIS_MCP_HOST   — QGIS plugin host (default: localhost)
  QGIS_MCP_PORT   — QGIS plugin port (default: 9876)
"""
import sys
import os

# Add parent dir to path so 'server' package is importable
sys.path.insert(0, os.path.dirname(__file__))

from server.server import main

if __name__ == "__main__":
    main()
