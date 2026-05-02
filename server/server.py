"""
QGIS MCP Server — Standard MCP Server using FastMCP Framework

This server bridges standard MCP clients (Claude Desktop, Cursor, Hermes, etc.)
to the QGIS plugin via TCP.

Architecture:
  MCP Client → [stdio/SSE/HTTP] → FastMCP Server → [TCP] → QGIS Plugin → PyQGIS

The FastMCP framework handles:
  - MCP protocol (JSON-RPC 2.0)
  - Tool registration with JSON Schema
  - Transport (stdio, SSE, HTTP)
  - Client session management

The TCP client handles:
  - Connection to QGIS plugin
  - Command forwarding
  - Response parsing
"""

import asyncio
import json
import logging
import os
import sys
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import TextContent

from .client import get_connection, invalidate_connection, QGISConnection

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger("qgis-mcp")
_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logger.addHandler(_handler)
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# FastMCP initialization
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="QGIS MCP Server",
    instructions=(
        "Use this server to interact with QGIS desktop GIS software. "
        "You can add/remove layers, query features, set styles, render maps, "
        "and perform spatial analysis. All operations require the QGIS plugin "
        "to be running (Plugins > QGIS Standard MCP > Start MCP Server)."
    ),
)

# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

QGIS_HOST = os.environ.get("QGIS_MCP_HOST", "localhost")
QGIS_PORT = int(os.environ.get("QGIS_MCP_PORT", "9876"))


def _get_conn() -> QGISConnection:
    """Get QGIS connection with auto-reconnect."""
    try:
        return get_connection(QGIS_HOST, QGIS_PORT)
    except Exception:
        invalidate_connection()
        return get_connection(QGIS_HOST, QGIS_PORT)


def _send(method: str, params: dict | None = None) -> dict:
    """Forward a command to QGIS plugin and return result.

    Retries once on connection error.
    """
    try:
        conn = _get_conn()
        return conn.send_command(method, params)
    except (ConnectionError, RuntimeError):
        invalidate_connection()
        conn = _get_conn()
        return conn.send_command(method, params)


def _call_tool(tool_name: str, arguments: dict) -> Any:
    """Call a QGIS tool and return the result.

    The QGIS plugin returns MCP-format content:
    {"content": [{"type": "text", "text": "..."}]}
    """
    result = _send("tools/call", {"name": tool_name, "arguments": arguments})
    # Parse the content
    content = result.get("content", [])
    if content and isinstance(content, list):
        text = content[0].get("text", "{}")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return result


def _call_tool_raw(tool_name: str, arguments: dict) -> dict:
    """Call a QGIS tool and return the raw MCP response (for text rendering)."""
    result = _send("tools/call", {"name": tool_name, "arguments": arguments})
    content = result.get("content", [])
    if content and isinstance(content, list):
        return content[0].get("text", "{}")
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Error hints
# ---------------------------------------------------------------------------

def _error_hint(message: str) -> str | None:
    """Return a helpful hint based on common error messages."""
    msg = message.lower()
    if "not found" in msg and "layer" in msg:
        return "Try calling 'get_layers' to see all valid layer IDs."
    if "connection" in msg or "refused" in msg:
        return "Ensure the QGIS MCP plugin is started (Plugins > QGIS Standard MCP > Start MCP Server)."
    if "timeout" in msg:
        return "The operation took too long. For large renders, this is expected."
    if "not connected" in msg:
        return "QGIS plugin is not running. Start QGIS and enable the MCP plugin."
    return None


# ============================================================================
# MCP Tools
# ============================================================================

@mcp.tool(
    title="Ping QGIS",
    description="Check connectivity to QGIS and the MCP plugin."
)
async def ping(ctx: Context) -> list[TextContent]:
    try:
        result = _call_tool("ping", {})
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as exc:
        hint = _error_hint(str(exc))
        msg = f"{exc}\n\nHINT: {hint}" if hint else str(exc)
        return [TextContent(type="text", text=json.dumps({"error": msg}))]


@mcp.tool(
    title="Get QGIS Info",
    description="Get QGIS version and installation information."
)
async def get_qgis_info(ctx: Context) -> list[TextContent]:
    try:
        result = _call_tool("get_qgis_info", {})
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as exc:
        hint = _error_hint(str(exc))
        msg = f"{exc}\n\nHINT: {hint}" if hint else str(exc)
        return [TextContent(type="text", text=json.dumps({"error": msg}))]


@mcp.tool(
    title="Get Project Info",
    description="Get information about the current QGIS project (layers, CRS, filename)."
)
async def get_project_info(ctx: Context) -> list[TextContent]:
    try:
        result = _call_tool("get_project_info", {})
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as exc:
        hint = _error_hint(str(exc))
        msg = f"{exc}\n\nHINT: {hint}" if hint else str(exc)
        return [TextContent(type="text", text=json.dumps({"error": msg}))]


@mcp.tool(
    title="Create Project",
    description="Create a new QGIS project and save it to disk."
)
async def create_project(ctx: Context, path: str) -> list[TextContent]:
    try:
        result = _call_tool("create_project", {"path": path})
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as exc:
        hint = _error_hint(str(exc))
        msg = f"{exc}\n\nHINT: {hint}" if hint else str(exc)
        return [TextContent(type="text", text=json.dumps({"error": msg}))]


@mcp.tool(
    title="Load Project",
    description="Load an existing QGIS project file (.qgz or .qgs)."
)
async def load_project(ctx: Context, path: str) -> list[TextContent]:
    try:
        result = _call_tool("load_project", {"path": path})
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as exc:
        hint = _error_hint(str(exc))
        msg = f"{exc}\n\nHINT: {hint}" if hint else str(exc)
        return [TextContent(type="text", text=json.dumps({"error": msg}))]


@mcp.tool(
    title="Save Project",
    description="Save the current QGIS project to disk."
)
async def save_project(ctx: Context, path: str | None = None) -> list[TextContent]:
    try:
        args = {}
        if path:
            args["path"] = path
        result = _call_tool("save_project", args)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as exc:
        hint = _error_hint(str(exc))
        msg = f"{exc}\n\nHINT: {hint}" if hint else str(exc)
        return [TextContent(type="text", text=json.dumps({"error": msg}))]


@mcp.tool(
    title="Add Vector Layer",
    description="Add a vector layer (Shapefile, GeoJSON, GeoPackage, etc.) to the project."
)
async def add_vector_layer(
    ctx: Context, path: str, name: str | None = None, provider: str = "ogr"
) -> list[TextContent]:
    try:
        args = {"path": path, "provider": provider}
        if name:
            args["name"] = name
        result = _call_tool("add_vector_layer", args)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as exc:
        hint = _error_hint(str(exc))
        msg = f"{exc}\n\nHINT: {hint}" if hint else str(exc)
        return [TextContent(type="text", text=json.dumps({"error": msg}))]


@mcp.tool(
    title="Add Raster Layer",
    description="Add a raster layer (GeoTIFF, etc.) to the project."
)
async def add_raster_layer(
    ctx: Context, path: str, name: str | None = None, provider: str = "gdal"
) -> list[TextContent]:
    try:
        args = {"path": path, "provider": provider}
        if name:
            args["name"] = name
        result = _call_tool("add_raster_layer", args)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as exc:
        hint = _error_hint(str(exc))
        msg = f"{exc}\n\nHINT: {hint}" if hint else str(exc)
        return [TextContent(type="text", text=json.dumps({"error": msg}))]


@mcp.tool(
    title="Get Layers",
    description="List all layers in the current QGIS project with their properties."
)
async def get_layers(ctx: Context) -> list[TextContent]:
    try:
        result = _call_tool("get_layers", {})
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as exc:
        hint = _error_hint(str(exc))
        msg = f"{exc}\n\nHINT: {hint}" if hint else str(exc)
        return [TextContent(type="text", text=json.dumps({"error": msg}))]


@mcp.tool(
    title="Remove Layer",
    description="Remove a layer from the project."
)
async def remove_layer(ctx: Context, layer_id: str) -> list[TextContent]:
    try:
        result = _call_tool("remove_layer", {"layer_id": layer_id})
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as exc:
        hint = _error_hint(str(exc))
        msg = f"{exc}\n\nHINT: {hint}" if hint else str(exc)
        return [TextContent(type="text", text=json.dumps({"error": msg}))]


@mcp.tool(
    title="Get Layer Features",
    description="Get features from a vector layer with optional filter expression."
)
async def get_layer_features(
    ctx: Context, layer_id: str, limit: int = 100, filter_expression: str | None = None
) -> list[TextContent]:
    try:
        args = {"layer_id": layer_id, "limit": limit}
        if filter_expression:
            args["filter_expression"] = filter_expression
        result = _call_tool("get_layer_features", args)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as exc:
        hint = _error_hint(str(exc))
        msg = f"{exc}\n\nHINT: {hint}" if hint else str(exc)
        return [TextContent(type="text", text=json.dumps({"error": msg}))]


@mcp.tool(
    title="Set Layer Style",
    description="Set the visual style of a layer (colors, symbols, opacity)."
)
async def set_layer_style(
    ctx: Context, layer_id: str, style: dict
) -> list[TextContent]:
    try:
        result = _call_tool("set_layer_style", {"layer_id": layer_id, "style": style})
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as exc:
        hint = _error_hint(str(exc))
        msg = f"{exc}\n\nHINT: {hint}" if hint else str(exc)
        return [TextContent(type="text", text=json.dumps({"error": msg}))]


@mcp.tool(
    title="Zoom to Extent",
    description="Zoom the map view to a specified geographic extent."
)
async def zoom_to_extent(
    ctx: Context,
    min_lng: float, min_lat: float,
    max_lng: float, max_lat: float,
    crs: str = "EPSG:4326"
) -> list[TextContent]:
    try:
        result = _call_tool("zoom_to_extent", {
            "min_lng": min_lng, "min_lat": min_lat,
            "max_lng": max_lng, "max_lat": max_lat,
            "crs": crs
        })
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as exc:
        hint = _error_hint(str(exc))
        msg = f"{exc}\n\nHINT: {hint}" if hint else str(exc)
        return [TextContent(type="text", text=json.dumps({"error": msg}))]


@mcp.tool(
    title="Zoom to Layer",
    description="Zoom the map view to the extent of a specific layer."
)
async def zoom_to_layer(ctx: Context, layer_id: str) -> list[TextContent]:
    try:
        result = _call_tool("zoom_to_layer", {"layer_id": layer_id})
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as exc:
        hint = _error_hint(str(exc))
        msg = f"{exc}\n\nHINT: {hint}" if hint else str(exc)
        return [TextContent(type="text", text=json.dumps({"error": msg}))]


@mcp.tool(
    title="Spatial Query",
    description="Find features within a radius of a point, or within a bounding box."
)
async def spatial_query(
    ctx: Context,
    layer_id: str,
    query_type: str,
    center_lng: float | None = None,
    center_lat: float | None = None,
    radius_meters: float | None = None,
    min_lng: float | None = None,
    min_lat: float | None = None,
    max_lng: float | None = None,
    max_lat: float | None = None,
    limit: int = 100
) -> list[TextContent]:
    try:
        args = {"layer_id": layer_id, "query_type": query_type, "limit": limit}
        if center_lng is not None:
            args["center_lng"] = center_lng
        if center_lat is not None:
            args["center_lat"] = center_lat
        if radius_meters is not None:
            args["radius_meters"] = radius_meters
        if min_lng is not None:
            args["min_lng"] = min_lng
        if min_lat is not None:
            args["min_lat"] = min_lat
        if max_lng is not None:
            args["max_lng"] = max_lng
        if max_lat is not None:
            args["max_lat"] = max_lat
        result = _call_tool("spatial_query", args)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as exc:
        hint = _error_hint(str(exc))
        msg = f"{exc}\n\nHINT: {hint}" if hint else str(exc)
        return [TextContent(type="text", text=json.dumps({"error": msg}))]


@mcp.tool(
    title="Buffer Analysis",
    description="Create buffer polygons around features."
)
async def buffer_analysis(
    ctx: Context,
    layer_id: str,
    distance: float,
    output_path: str | None = None
) -> list[TextContent]:
    try:
        args = {"layer_id": layer_id, "distance": distance}
        if output_path:
            args["output_path"] = output_path
        result = _call_tool("buffer_analysis", args)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as exc:
        hint = _error_hint(str(exc))
        msg = f"{exc}\n\nHINT: {hint}" if hint else str(exc)
        return [TextContent(type="text", text=json.dumps({"error": msg}))]


@mcp.tool(
    title="Execute Processing Algorithm",
    description="Execute a QGIS processing algorithm (e.g., clip, intersect, dissolve)."
)
async def execute_processing(
    ctx: Context,
    algorithm: str,
    parameters: dict
) -> list[TextContent]:
    try:
        result = _call_tool("execute_processing", {
            "algorithm": algorithm,
            "parameters": parameters
        })
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as exc:
        hint = _error_hint(str(exc))
        msg = f"{exc}\n\nHINT: {hint}" if hint else str(exc)
        return [TextContent(type="text", text=json.dumps({"error": msg}))]


@mcp.tool(
    title="Render Map",
    description="Render the current map view to an image file (PNG/JPG)."
)
async def render_map(
    ctx: Context,
    output_path: str,
    width: int = 1200,
    height: int = 900
) -> list[TextContent]:
    try:
        result = _call_tool("render_map", {
            "output_path": output_path,
            "width": width,
            "height": height
        })
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as exc:
        hint = _error_hint(str(exc))
        msg = f"{exc}\n\nHINT: {hint}" if hint else str(exc)
        return [TextContent(type="text", text=json.dumps({"error": msg}))]


# ============================================================================
# Entry point
# ============================================================================

def main():
    """Run the MCP server."""
    global QGIS_HOST, QGIS_PORT
    import argparse

    parser = argparse.ArgumentParser(description="QGIS MCP Server")
    parser.add_argument("--host", default=QGIS_HOST, help="QGIS plugin host")
    parser.add_argument("--port", type=int, default=QGIS_PORT, help="QGIS plugin port")
    parser.add_argument("--transport", choices=["stdio", "sse", "http"],
                       default="stdio", help="MCP transport (default: stdio)")
    parser.add_argument("--sse-port", type=int, default=8080, help="SSE/HTTP port")
    args = parser.parse_args()

    QGIS_HOST = args.host
    QGIS_PORT = args.port

    logger.info(f"QGIS MCP Server starting (transport={args.transport})")
    logger.info(f"QGIS plugin target: {args.host}:{args.port}")

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    elif args.transport == "sse":
        mcp.run(transport="sse", sse_port=args.sse_port)
    elif args.transport == "http":
        mcp.run(transport="http", port=args.sse_port)


if __name__ == "__main__":
    main()
