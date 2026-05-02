"""QGIS MCP Server — Standard MCP bridge to QGIS plugin."""

# Lazy imports to avoid requiring MCP SDK at package import time
def __getattr__(name):
    if name == "mcp":
        from .server import mcp
        return mcp
    elif name == "main":
        from .server import main
        return main
    elif name == "QGISConnection":
        from .client import QGISConnection
        return QGISConnection
    elif name == "get_connection":
        from .client import get_connection
        return get_connection
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["mcp", "main", "QGISConnection", "get_connection"]
