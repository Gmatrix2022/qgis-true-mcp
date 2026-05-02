"""
QGIS Standard MCP Plugin
========================
Implements the Model Context Protocol (MCP) natively in QGIS.
Exposes structured GIS tools via JSON-RPC 2.0 over TCP socket.

NO execute_code backdoor. All tools are parameterized and safe.
"""
import os
import io
import json
import socket
import traceback
import threading
import queue
import uuid
import time

from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import QObject, pyqtSignal, QThread, QSize, Qt, QTimer
from qgis.PyQt.QtWidgets import QAction, QDockWidget, QVBoxLayout, QLabel, QPushButton, QSpinBox, QWidget
from qgis.PyQt.QtGui import QColor

# ============================================================================
# MCP Protocol Constants
# ============================================================================
MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "qgis-standard-mcp"
SERVER_VERSION = "0.1.0"

# JSON-RPC 2.0 error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# ============================================================================
# MCP Tool Definitions (JSON Schema)
# ============================================================================
MCP_TOOLS = [
    {
        "name": "ping",
        "description": "Ping to check MCP server connectivity",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_qgis_info",
        "description": "Get QGIS version and installation information",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_project_info",
        "description": "Get information about the current QGIS project (layers, CRS, filename)",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "create_project",
        "description": "Create a new QGIS project and save it to disk",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Full path where the .qgz project file will be saved"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "load_project",
        "description": "Load an existing QGIS project file",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the .qgz or .qgs project file"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "save_project",
        "description": "Save the current QGIS project to disk",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to save (optional, saves to current path if omitted)"}
            }
        }
    },
    {
        "name": "add_vector_layer",
        "description": "Add a vector layer (Shapefile, GeoJSON, etc.) to the current project",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to the vector data source"},
                "name": {"type": "string", "description": "Display name for the layer (defaults to filename)"},
                "provider": {"type": "string", "default": "ogr", "description": "Data provider"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "add_raster_layer",
        "description": "Add a raster layer (GeoTIFF, etc.) to the current project",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to the raster data source"},
                "name": {"type": "string", "description": "Display name for the layer"},
                "provider": {"type": "string", "default": "gdal", "description": "Data provider"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "get_layers",
        "description": "List all layers in the current QGIS project with their properties",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "remove_layer",
        "description": "Remove a layer from the project",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layer_id": {"type": "string", "description": "ID of the layer to remove"}
            },
            "required": ["layer_id"]
        }
    },
    {
        "name": "get_layer_features",
        "description": "Get features from a vector layer with optional filter",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layer_id": {"type": "string", "description": "ID of the layer (use get_layers to find IDs)"},
                "limit": {"type": "integer", "default": 100, "description": "Maximum number of features to return"},
                "filter_expression": {"type": "string", "description": "QGIS expression to filter features"}
            },
            "required": ["layer_id"]
        }
    },
    {
        "name": "set_layer_style",
        "description": "Set the visual style of a layer (colors, symbols, opacity)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layer_id": {"type": "string", "description": "ID of the layer to style"},
                "style": {
                    "type": "object",
                    "description": "Style configuration",
                    "properties": {
                        "fill_color": {"type": "string", "description": "Fill color (e.g. '255,0,0,128')"},
                        "outline_color": {"type": "string", "description": "Outline color"},
                        "outline_width": {"type": "number", "description": "Outline width in mm"},
                        "opacity": {"type": "number", "description": "Layer opacity 0.0-1.0"},
                        "point_size": {"type": "number", "description": "Point symbol size"},
                        "point_shape": {"type": "string", "description": "circle, square, triangle, diamond, star"}
                    }
                }
            },
            "required": ["layer_id", "style"]
        }
    },
    {
        "name": "zoom_to_extent",
        "description": "Zoom the map view to a specified geographic extent",
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_lng": {"type": "number", "description": "Western boundary longitude"},
                "min_lat": {"type": "number", "description": "Southern boundary latitude"},
                "max_lng": {"type": "number", "description": "Eastern boundary longitude"},
                "max_lat": {"type": "number", "description": "Northern boundary latitude"},
                "crs": {"type": "string", "default": "EPSG:4326", "description": "Coordinate reference system"}
            },
            "required": ["min_lng", "min_lat", "max_lng", "max_lat"]
        }
    },
    {
        "name": "zoom_to_layer",
        "description": "Zoom the map view to the extent of a specific layer",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layer_id": {"type": "string", "description": "ID of the layer to zoom to"}
            },
            "required": ["layer_id"]
        }
    },
    {
        "name": "spatial_query",
        "description": "Find features within a radius of a point, or within a bounding box",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layer_id": {"type": "string", "description": "ID of the layer to query"},
                "query_type": {"type": "string", "enum": ["point_radius", "bbox"], "description": "Type of spatial query"},
                "center_lng": {"type": "number", "description": "Center longitude (for point_radius)"},
                "center_lat": {"type": "number", "description": "Center latitude (for point_radius)"},
                "radius_meters": {"type": "number", "description": "Search radius in meters (for point_radius)"},
                "min_lng": {"type": "number", "description": "Western boundary (for bbox)"},
                "min_lat": {"type": "number", "description": "Southern boundary (for bbox)"},
                "max_lng": {"type": "number", "description": "Eastern boundary (for bbox)"},
                "max_lat": {"type": "number", "description": "Northern boundary (for bbox)"},
                "limit": {"type": "integer", "default": 100, "description": "Maximum results to return"}
            },
            "required": ["layer_id", "query_type"]
        }
    },
    {
        "name": "buffer_analysis",
        "description": "Create buffer zones around features in a vector layer",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layer_id": {"type": "string", "description": "ID of the input layer"},
                "distance_meters": {"type": "number", "description": "Buffer distance in meters"},
                "output_name": {"type": "string", "description": "Name for the output buffer layer"},
                "segments": {"type": "integer", "default": 32, "description": "Number of segments for buffer approximation"}
            },
            "required": ["layer_id", "distance_meters"]
        }
    },
    {
        "name": "execute_processing",
        "description": "Execute a QGIS Processing algorithm with structured parameters",
        "inputSchema": {
            "type": "object",
            "properties": {
                "algorithm": {"type": "string", "description": "Processing algorithm ID (e.g. 'qgis:buffer')"},
                "parameters": {"type": "object", "description": "Algorithm-specific parameters"}
            },
            "required": ["algorithm", "parameters"]
        }
    },
    {
        "name": "render_map",
        "description": "Render the current map view to an image file (PNG/JPG)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Output image file path"},
                "width": {"type": "integer", "default": 1200, "description": "Image width in pixels"},
                "height": {"type": "integer", "default": 900, "description": "Image height in pixels"}
            },
            "required": ["path"]
        }
    },
]

# ============================================================================
# MCP Tool Implementations
# ============================================================================

class QGISToolExecutor:
    """Executes structured GIS tools inside the QGIS process."""

    def __init__(self, iface):
        self.iface = iface

    def ping(self, **kwargs):
        return {"pong": True, "server": SERVER_NAME, "version": SERVER_VERSION}

    def get_qgis_info(self, **kwargs):
        from qgis.utils import active_plugins
        return {
            "qgis_version": Qgis.version(),
            "profile_folder": QgsApplication.qgisSettingsDirPath(),
            "plugins_count": len(active_plugins)
        }

    def get_project_info(self, **kwargs):
        project = QgsProject.instance()
        layers = []
        for layer_id, layer in project.mapLayers().items():
            info = {
                "id": layer_id,
                "name": layer.name(),
                "visible": project.layerTreeRoot().findLayer(layer_id).isVisible()
            }
            if layer.type() == QgsMapLayer.VectorLayer:
                info["type"] = "vector"
                info["geometry_type"] = str(layer.geometryType())
                info["feature_count"] = layer.featureCount()
            elif layer.type() == QgsMapLayer.RasterLayer:
                info["type"] = "raster"
            else:
                info["type"] = str(layer.type())
            layers.append(info)
        return {
            "filename": project.fileName(),
            "title": project.title(),
            "crs": project.crs().authid(),
            "layer_count": len(project.mapLayers()),
            "layers": layers
        }

    def create_project(self, path, **kwargs):
        project = QgsProject.instance()
        if project.fileName():
            project.clear()
        project.setFileName(path)
        # Set project CRS to WGS84 by default
        project.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        self.iface.mapCanvas().refresh()
        if project.write():
            return {"created": path, "layer_count": 0}
        raise Exception(f"Failed to save project to {path}")

    def load_project(self, path, **kwargs):
        project = QgsProject.instance()
        if project.read(path):
            self.iface.mapCanvas().refresh()
            return {"loaded": path, "layer_count": len(project.mapLayers())}
        raise Exception(f"Failed to load project from {path}")

    def save_project(self, path=None, **kwargs):
        project = QgsProject.instance()
        save_path = path or project.fileName()
        if not save_path:
            raise Exception("No project path specified and no current project path")
        if project.write(save_path):
            return {"saved": save_path}
        raise Exception(f"Failed to save project to {save_path}")

    def add_vector_layer(self, path, name=None, provider="ogr", **kwargs):
        if not name:
            name = os.path.basename(path)
        layer = QgsVectorLayer(path, name, provider)
        if not layer.isValid():
            raise Exception(f"Layer is not valid: {path}")
        QgsProject.instance().addMapLayer(layer)
        # Sync project CRS with first layer added
        project = QgsProject.instance()
        if not project.crs().isValid() or project.crs().authid() == "":
            project.setCrs(layer.crs())
        # Refresh canvas and zoom to layer extent
        self.iface.mapCanvas().refresh()
        self.iface.mapCanvas().repaint()
        self.iface.setActiveLayer(layer)
        self.iface.zoomToActiveLayer()
        return {
            "id": layer.id(),
            "name": layer.name(),
            "feature_count": layer.featureCount(),
            "geometry_type": str(layer.geometryType())
        }

    def add_raster_layer(self, path, name=None, provider="gdal", **kwargs):
        if not name:
            name = os.path.basename(path)
        layer = QgsRasterLayer(path, name, provider)
        if not layer.isValid():
            raise Exception(f"Raster layer is not valid: {path}")
        QgsProject.instance().addMapLayer(layer)
        return {
            "id": layer.id(),
            "name": layer.name(),
            "width": layer.width(),
            "height": layer.height()
        }

    def get_layers(self, **kwargs):
        project = QgsProject.instance()
        layers = []
        root = project.layerTreeRoot()
        for layer_id, layer in project.mapLayers().items():
            tree_node = root.findLayer(layer_id)
            info = {
                "id": layer_id,
                "name": layer.name(),
                "visible": tree_node.isVisible() if tree_node else True
            }
            if layer.type() == QgsMapLayer.VectorLayer:
                info["type"] = "vector"
                info["geometry_type"] = str(layer.geometryType())
                info["feature_count"] = layer.featureCount()
                info["fields"] = [f.name() for f in layer.fields()]
            elif layer.type() == QgsMapLayer.RasterLayer:
                info["type"] = "raster"
            layers.append(info)
        return layers

    def remove_layer(self, layer_id, **kwargs):
        project = QgsProject.instance()
        if layer_id in project.mapLayers():
            project.removeMapLayer(layer_id)
            return {"removed": layer_id}
        raise Exception(f"Layer not found: {layer_id}")

    def get_layer_features(self, layer_id, limit=100, filter_expression=None, **kwargs):
        project = QgsProject.instance()
        if layer_id not in project.mapLayers():
            raise Exception(f"Layer not found: {layer_id}")
        layer = project.mapLayer(layer_id)
        if layer.type() != QgsMapLayer.VectorLayer:
            raise Exception(f"Layer is not a vector layer: {layer_id}")

        request = QgsFeatureRequest()
        if filter_expression:
            request.setFilterExpression(filter_expression)
        request.setLimit(limit)

        features = []
        field_names = [f.name() for f in layer.fields()]
        for feat in layer.getFeatures(request):
            raw_attrs = dict(zip(field_names, feat.attributes()))
            attrs = {k: v.toPyObj() if hasattr(v, 'toPyObj') else v for k, v in raw_attrs.items()}
            geom_wkt = feat.geometry().asWkt(precision=4) if feat.hasGeometry() else None
            features.append({
                "id": feat.id(),
                "attributes": attrs,
                "geometry_wkt": geom_wkt
            })
        return {
            "layer_id": layer_id,
            "total_features": layer.featureCount(),
            "returned": len(features),
            "fields": field_names,
            "features": features
        }

    def set_layer_style(self, layer_id, style, **kwargs):
        project = QgsProject.instance()
        if layer_id not in project.mapLayers():
            raise Exception(f"Layer not found: {layer_id}")
        layer = project.mapLayer(layer_id)

        if layer.type() == QgsMapLayer.VectorLayer:
            geom_type = layer.geometryType()
            if geom_type == QgsWkbTypes.PointGeometry:
                symbol = QgsMarkerSymbol.createSimple({})
                if "point_shape" in style:
                    symbol.symbolLayer(0).setShape(style["point_shape"])
                if "point_size" in style:
                    symbol.symbolLayer(0).setSize(style["point_size"])
                if "fill_color" in style:
                    symbol.setColor(QColor(style["fill_color"]))
                if "outline_color" in style:
                    symbol.symbolLayer(0).setStrokeColor(QColor(style["outline_color"]))
                layer.renderer().setSymbol(symbol)
            elif geom_type == QgsWkbTypes.LineGeometry:
                symbol = QgsLineSymbol.createSimple({})
                if "outline_color" in style:
                    symbol.setColor(QColor(style["outline_color"]))
                if "outline_width" in style:
                    symbol.setWidth(style["outline_width"])
                layer.renderer().setSymbol(symbol)
            else:  # PolygonGeometry
                symbol = QgsFillSymbol.createSimple({})
                if "fill_color" in style:
                    symbol.setColor(QColor(style["fill_color"]))
                if "outline_color" in style:
                    symbol.symbolLayer(0).setStrokeColor(QColor(style["outline_color"]))
                if "outline_width" in style:
                    symbol.symbolLayer(0).setStrokeWidth(style["outline_width"])
                layer.renderer().setSymbol(symbol)

        if "opacity" in style:
            layer.setOpacity(style["opacity"])

        layer.triggerRepaint()
        return {"styled": layer_id}

    def zoom_to_extent(self, min_lng, min_lat, max_lng, max_lat, crs="EPSG:4326", **kwargs):
        src_crs = QgsCoordinateReferenceSystem(crs)
        dst_crs = QgsProject.instance().crs()
        rect = QgsRectangle(min_lng, min_lat, max_lng, max_lat)
        if src_crs != dst_crs:
            transform = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance().transformContext())
            rect = transform.transformBoundingBox(rect)
        self.iface.mapCanvas().setExtent(rect)
        self.iface.mapCanvas().refresh()
        return {"zoomed_to": {"min_lng": min_lng, "min_lat": min_lat, "max_lng": max_lng, "max_lat": max_lat}}

    def zoom_to_layer(self, layer_id, **kwargs):
        project = QgsProject.instance()
        if layer_id not in project.mapLayers():
            raise Exception(f"Layer not found: {layer_id}")
        layer = project.mapLayer(layer_id)
        self.iface.setActiveLayer(layer)
        self.iface.zoomToActiveLayer()
        return {"zoomed_to": layer_id}

    def spatial_query(self, layer_id, query_type, limit=100, **kwargs):
        project = QgsProject.instance()
        if layer_id not in project.mapLayers():
            raise Exception(f"Layer not found: {layer_id}")
        layer = project.mapLayer(layer_id)
        if layer.type() != QgsMapLayer.VectorLayer:
            raise Exception(f"Layer is not a vector layer: {layer_id}")

        # Always work in layer CRS for geometry comparison
        src_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        dst_crs = layer.crs()
        to_layer = QgsCoordinateTransform(src_crs, dst_crs, project.transformContext())

        if query_type == "point_radius":
            center_lng = kwargs.get("center_lng")
            center_lat = kwargs.get("center_lat")
            radius_m = kwargs.get("radius_meters", 5000)
            if center_lng is None or center_lat is None:
                raise Exception("center_lng and center_lat required for point_radius query")

            center = QgsGeometry.fromPointXY(QgsPointXY(center_lng, center_lat))
            center.transform(to_layer)
            buffer_geom = center.buffer(radius_m, 64)

        elif query_type == "bbox":
            min_lng = kwargs.get("min_lng")
            min_lat = kwargs.get("min_lat")
            max_lng = kwargs.get("max_lng")
            max_lat = kwargs.get("max_lat")
            if None in (min_lng, min_lat, max_lng, max_lat):
                raise Exception("min_lng, min_lat, max_lng, max_lat required for bbox query")
            # Transform WGS84 bbox to layer CRS
            rect = QgsRectangle(min_lng, min_lat, max_lng, max_lat)
            if src_crs != dst_crs:
                rect = to_layer.transformBoundingBox(rect)
            buffer_geom = QgsGeometry.fromRect(rect)
        else:
            raise Exception(f"Unknown query_type: {query_type}")

        field_names = [f.name() for f in layer.fields()]
        results = []

        # Use spatial index via QgsFeatureRequest for bbox
        request = QgsFeatureRequest()
        request.setLimit(limit)
        if query_type == "bbox":
            request.setFilterRect(buffer_geom.boundingBox())
        elif query_type == "point_radius":
            request.setFilterRect(buffer_geom.boundingBox())

        for feat in layer.getFeatures(request):
            if buffer_geom.intersects(feat.geometry()):
                raw_attrs = dict(zip(field_names, feat.attributes()))
                safe_attrs = {k: v.toPyObj() if hasattr(v, 'toPyObj') else v for k, v in raw_attrs.items()}
                results.append({
                    "id": feat.id(),
                    "attributes": safe_attrs,
                    "geometry_wkt": feat.geometry().asWkt(precision=4)
                })
        return {"query_type": query_type, "count": len(results), "features": results}

    def buffer_analysis(self, layer_id, distance_meters, output_name=None, segments=32, **kwargs):
        project = QgsProject.instance()
        if layer_id not in project.mapLayers():
            raise Exception(f"Layer not found: {layer_id}")
        layer = project.mapLayer(layer_id)
        if layer.type() != QgsMapLayer.VectorLayer:
            raise Exception(f"Layer is not a vector layer: {layer_id}")

        src_crs = layer.crs()
        # Determine meters per degree for this latitude
        # If layer is geographic (degrees), we need to estimate
        if src_crs.isGeographic():
            # Average latitude for approximation
            extent = layer.extent()
            avg_lat = (extent.yMinimum() + extent.yMaximum()) / 2.0
            deg_per_meter = 1.0 / (111320.0 * max(abs(avg_lat), 0.01) / 90.0)
            buffer_dist = distance_meters * deg_per_meter
        else:
            buffer_dist = distance_meters

        # Create buffer layer
        if not output_name:
            output_name = f"{layer.name()}_buffer_{int(distance_meters)}m"

        crs_authid = src_crs.authid()
        buffer_layer = QgsVectorLayer(f"Point?crs={crs_authid}", output_name, "memory")
        provider = buffer_layer.dataProvider()

        # Add fields from original
        provider.addAttributes(layer.fields())
        buffer_layer.updateFields()

        # Create features
        out_features = []
        for feat in layer.getFeatures():
            if feat.hasGeometry():
                new_feat = QgsFeature(buffer_layer)
                new_feat.setGeometry(feat.geometry().buffer(buffer_dist, segments))
                new_feat.setAttributes(feat.attributes())
                out_features.append(new_feat)

        provider.addFeatures(out_features)
        buffer_layer.updateExtents()
        project.addMapLayer(buffer_layer)

        return {
            "output_layer_id": buffer_layer.id(),
            "output_name": output_name,
            "feature_count": len(out_features),
            "buffer_distance": f"{distance_meters}m"
        }

    def execute_processing(self, algorithm, parameters, **kwargs):
        try:
            import processing
            result = processing.run(algorithm, parameters)
            # Convert values to strings for JSON serialization
            return {
                "algorithm": algorithm,
                "result": {k: str(v) for k, v in result.items()}
            }
        except Exception as e:
            raise Exception(f"Processing error: {str(e)}")

    def render_map(self, path=None, output_path=None, width=1200, height=900, **kwargs):
        output_file = path or output_path
        if not output_file:
            raise Exception("render_map requires 'path' parameter")

        ms = QgsMapSettings()
        layers = list(QgsProject.instance().mapLayers().values())
        ms.setLayers(layers)
        # Use current canvas extent — same as nkarasiak/qgis-mcp
        rect = self.iface.mapCanvas().extent()
        ms.setExtent(rect)
        ms.setOutputSize(QSize(width, height))
        ms.setBackgroundColor(QColor(255, 255, 255))
        ms.setOutputDpi(96)

        render = QgsMapRendererParallelJob(ms)
        render.start()
        render.waitForFinished()

        img = render.renderedImage()
        if img.save(output_file):
            return {"rendered": True, "path": output_file,
                    "width": width, "height": height,
                    "layers_rendered": len(layers)}
        raise Exception(f"Failed to save rendered image to {output_file}")


# ============================================================================
# MCP JSON-RPC 2.0 Protocol Handler
# ============================================================================

class MCPProtocolHandler:
    """Handles MCP JSON-RPC 2.0 protocol messages."""

    def __init__(self, tool_executor):
        self.executor = tool_executor
        self.initialized = False

    def handle_message(self, raw_message):
        """Process a single JSON-RPC 2.0 message and return a response."""
        try:
            msg = json.loads(raw_message)
        except json.JSONDecodeError:
            return self._error_response(None, PARSE_ERROR, "Parse error")

        msg_id = msg.get("id")
        method = msg.get("method", "")
        params = msg.get("params", {})

        # Notifications (no id) - just acknowledge
        if msg_id is None:
            if method == "initialized":
                self.initialized = True
            return None  # No response for notifications

        # Handle methods
        if method == "initialize":
            return self._handle_initialize(msg_id, params)
        elif method == "ping":
            return self._handle_tool(msg_id, "ping", {})
        elif method == "tools/list":
            return self._handle_tools_list(msg_id)
        elif method == "tools/call":
            return self._handle_tools_call(msg_id, params)
        elif method == "resources/list":
            return self._response(msg_id, {"resources": []})
        else:
            return self._error_response(msg_id, METHOD_NOT_FOUND, f"Method not found: {method}")

    def _handle_initialize(self, msg_id, params):
        return self._response(msg_id, {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False}
            },
            "serverInfo": {
                "name": SERVER_NAME,
                "version": SERVER_VERSION
            }
        })

    def _handle_tools_list(self, msg_id):
        return self._response(msg_id, {"tools": MCP_TOOLS})

    def _handle_tools_call(self, msg_id, params):
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        # Find tool definition
        tool_def = next((t for t in MCP_TOOLS if t["name"] == tool_name), None)
        if not tool_def:
            return self._error_response(msg_id, METHOD_NOT_FOUND, f"Tool not found: {tool_name}")

        # Execute tool
        try:
            handler = getattr(self.executor, tool_name, None)
            if not handler:
                return self._error_response(msg_id, METHOD_NOT_FOUND, f"Tool handler not implemented: {tool_name}")

            result = handler(**arguments)
            return self._response(msg_id, {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
            })
        except Exception as e:
            return self._response(msg_id, {
                "content": [{"type": "text", "text": json.dumps({"error": str(e)}, ensure_ascii=False)}],
                "isError": True
            })

    def _response(self, msg_id, result):
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def _error_response(self, msg_id, code, message):
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


# ============================================================================
# TCP Server Thread (network I/O only — no QGIS/GUI calls)
# ============================================================================

class MCPServerThread(QThread):
    """TCP server that listens for MCP JSON-RPC connections.

    Only handles network I/O. QGIS operations are queued and executed
    on the main thread via the dock widget's QTimer.
    """

    log_message = pyqtSignal(str)

    def __init__(self, host="0.0.0.0", port=9876, parent=None):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.running = False
        self.server_socket = None
        # Thread-safe queues for producer-consumer pattern
        self.request_queue = queue.Queue()
        self.response_queue = queue.Queue()

    def run(self):
        self.running = True
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.settimeout(1.0)

        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.log_message.emit(f"MCP server listening on {self.host}:{self.port}")
        except Exception as e:
            self.log_message.emit(f"Failed to bind: {e}")
            return

        while self.running:
            try:
                client, address = self.server_socket.accept()
                self.log_message.emit(f"Client connected: {address}")
                self._handle_client(client, address)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.log_message.emit(f"Accept error: {e}")

        self.server_socket.close()
        self.log_message.emit("MCP server stopped")

    def _handle_client(self, client, address):
        """Handle a single client connection.

        Receives TCP data, queues it for main thread processing,
        waits for the response, and sends it back.
        """
        try:
            client.settimeout(30)
            buffer = b''
            while self.running:
                try:
                    chunk = client.recv(65536)
                    if not chunk:
                        break
                    buffer += chunk
                    # Try to parse as complete JSON
                    try:
                        msg_str = buffer.decode('utf-8')
                        json.loads(msg_str)  # Validate
                        buffer = b''  # Complete message received
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue  # Incomplete, keep reading

                    # Queue request for main thread processing
                    req_id = str(uuid.uuid4())
                    self.request_queue.put((msg_str, req_id))

                    # Block waiting for response from main thread
                    try:
                        response = self.response_queue.get(timeout=30)
                    except queue.Empty:
                        # Timeout — send error response
                        error_resp = {
                            "jsonrpc": "2.0",
                            "id": None,
                            "error": {
                                "code": INTERNAL_ERROR,
                                "message": "Request processing timed out"
                            }
                        }
                        resp_bytes = json.dumps(error_resp, ensure_ascii=False).encode('utf-8')
                        client.sendall(resp_bytes)
                        self.log_message.emit(f"→ {address}: [timeout error]")
                        continue

                    if response is not None:
                        resp_bytes = json.dumps(response, ensure_ascii=False).encode('utf-8')
                        client.sendall(resp_bytes)
                        self.log_message.emit(f"→ {address}: {msg_str[:100]}...")
                except socket.timeout:
                    continue
                except Exception as e:
                    self.log_message.emit(f"Client error: {e}")
                    break
        finally:
            client.close()
            self.log_message.emit(f"Client disconnected: {address}")

    def stop(self):
        self.running = False
        if self.server_socket:
            self.server_socket.close()


# ============================================================================
# QGIS Plugin UI
# ============================================================================

class QgisMCPDockWidget(QgsDockWidget):
    def __init__(self, iface):
        super().__init__("MCP Server", iface.mainWindow())
        self.iface = iface
        self.server_thread = None
        self.tool_executor = QGISToolExecutor(iface)
        self.protocol_handler = MCPProtocolHandler(self.tool_executor)

        # QTimer for main-thread processing of queued requests
        self._process_timer = QTimer(self)
        self._process_timer.timeout.connect(self._process_requests)

        # Prevent closing — only hide via toggle_dock
        self.setFeatures(
            QgsDockWidget.DockWidgetClosable
            | QgsDockWidget.DockWidgetMovable
            | QgsDockWidget.DockWidgetFloatable
        )
        self.setup_ui()

    def setup_ui(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        widget.setLayout(layout)

        port_label = QLabel("Port:")
        self.port_spin = QSpinBox()
        self.port_spin.setMinimum(1024)
        self.port_spin.setMaximum(65535)
        self.port_spin.setValue(9876)
        port_row = QVBoxLayout()
        port_row.addWidget(port_label)
        port_row.addWidget(self.port_spin)
        layout.addLayout(port_row)

        self.start_button = QPushButton("Start MCP Server")
        self.start_button.clicked.connect(self.start_server)
        layout.addWidget(self.start_button)

        self.stop_button = QPushButton("Stop Server")
        self.stop_button.clicked.connect(self.stop_server)
        self.stop_button.setEnabled(False)
        layout.addWidget(self.stop_button)

        self.status_label = QLabel("○ Stopped")
        self.status_label.setStyleSheet("font-weight: bold; color: #e74c3c;")
        layout.addWidget(self.status_label)

        log_label = QLabel("Log:")
        layout.addWidget(log_label)
        self.log_text = QLabel("")
        self.log_text.setWordWrap(True)
        self.log_text.setStyleSheet(
            "color: #666; font-size: 11px; padding: 4px; "
            "background: #f5f5f5; border: 1px solid #ddd; border-radius: 3px;"
        )
        self.log_text.setMinimumHeight(60)
        layout.addWidget(self.log_text)

        self.setWidget(widget)

    def start_server(self):
        port = self.port_spin.value()
        self.server_thread = MCPServerThread(port=port)
        self.server_thread.log_message.connect(self._on_log)
        self.server_thread.start()
        # Start the main-thread timer to drain request_queue
        self._process_timer.start(50)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.port_spin.setEnabled(False)
        self.status_label.setText(f"● Running on {port}")
        self.status_label.setStyleSheet("font-weight: bold; color: #27ae60;")

    def stop_server(self):
        # Stop the processing timer
        self._process_timer.stop()
        if self.server_thread:
            self.server_thread.stop()
            self.server_thread.wait(3000)
            self.server_thread = None
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.port_spin.setEnabled(True)
        self.status_label.setText("○ Stopped")
        self.status_label.setStyleSheet("font-weight: bold; color: #e74c3c;")
        self.log_text.setText("")

    def _process_requests(self):
        """Main-thread callback: drain the request_queue and post responses."""
        if not self.server_thread:
            return
        while not self.server_thread.request_queue.empty():
            try:
                msg_str, req_id = self.server_thread.request_queue.get_nowait()
            except queue.Empty:
                break
            try:
                response = self.protocol_handler.handle_message(msg_str)
            except Exception as e:
                # Build an error response for unexpected failures
                response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": INTERNAL_ERROR,
                        "message": f"Internal error: {str(e)}"
                    }
                }
            if response is not None:
                self.server_thread.response_queue.put(response)

    def _on_log(self, msg):
        self.log_text.setText(msg)

    def closeEvent(self, event):
        # Just hide, don't destroy — QGIS toggles show/hide
        self.stop_server()
        self.hide()
        event.ignore()


# ============================================================================
# Main Plugin Class
# ============================================================================

class QGISStandardMCPPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.dock_widget = None
        self.action = None

    def initGui(self):
        self.action = QAction("QGIS Standard MCP", self.iface.mainWindow())
        self.action.setCheckable(True)
        self.action.triggered.connect(self.toggle_dock)
        self.iface.addPluginToMenu("QGIS Standard MCP", self.action)
        self.iface.addToolBarIcon(self.action)

    def toggle_dock(self, checked):
        if checked:
            if not self.dock_widget:
                self.dock_widget = QgisMCPDockWidget(self.iface)
                self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock_widget)
            self.dock_widget.show()
            self.dock_widget.raise_()
        else:
            if self.dock_widget:
                self.dock_widget.stop_server()
                self.dock_widget.hide()

    def unload(self):
        if self.dock_widget:
            self.dock_widget.stop_server()
            self.iface.removeDockWidget(self.dock_widget)
            self.dock_widget = None
        self.iface.removePluginMenu("QGIS Standard MCP", self.action)
        self.iface.removeToolBarIcon(self.action)
