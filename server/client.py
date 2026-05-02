"""
TCP Client — MCP Server ↔ QGIS Plugin

Connects to the QGIS plugin's raw TCP socket (JSON-RPC 2.0 over TCP).
The plugin listens on port 9876 and speaks MCP JSON-RPC 2.0 natively.

Protocol:
  - Raw TCP socket (no length prefix, no HTTP)
  - JSON-RPC 2.0 messages as UTF-8 bytes
  - Client accumulates data until a complete JSON object is parseable
"""

import json
import socket
import struct
import time
import logging
from typing import Any

logger = logging.getLogger("qgis-mcp")

# Default connection settings
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 9876
DEFAULT_TIMEOUT = 30
RECV_CHUNK = 65536


class QGISConnection:
    """Persistent TCP connection to QGIS MCP plugin."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self._sock: socket.socket | None = None
        self._connected = False

    def connect(self) -> bool:
        """Establish TCP connection to QGIS plugin."""
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(DEFAULT_TIMEOUT)
            self._sock.connect((self.host, self.port))
            self._connected = True
            logger.info(f"Connected to QGIS plugin at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._connected = False
            return False

    def disconnect(self):
        """Close the TCP connection."""
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Check if connection is alive."""
        if not self._connected or not self._sock:
            return False
        try:
            # Non-blocking check
            self._sock.setblocking(False)
            data = self._sock.recv(1, socket.MSG_PEEK)
            self._sock.setblocking(True)
            if not data:
                self._connected = False
                return False
        except BlockingIOError:
            # No data available yet — connection is alive
            self._sock.setblocking(True)
            return True
        except Exception:
            self._connected = False
            return False
        return True

    def send_command(self, method: str, params: dict | None = None,
                     timeout: int = DEFAULT_TIMEOUT) -> dict:
        """Send a JSON-RPC 2.0 command and return the result.

        Args:
            method: MCP method name (e.g., 'tools/call', 'tools/list')
            params: Method parameters
            timeout: Response timeout in seconds

        Returns:
            The 'result' field from the JSON-RPC response

        Raises:
            ConnectionError: If not connected
            RuntimeError: If the response contains an error
        """
        if not self._connected or not self._sock:
            raise ConnectionError("Not connected to QGIS plugin")

        # Build JSON-RPC 2.0 request
        msg_id = int(time.time() * 1000) % 1_000_000  # Simple unique ID
        request = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params

        # Send
        data = json.dumps(request, ensure_ascii=False).encode("utf-8")
        self._sock.sendall(data)

        # Receive response
        self._sock.settimeout(timeout)
        buffer = b""
        deadline = time.time() + timeout

        while time.time() < deadline:
            try:
                chunk = self._sock.recv(RECV_CHUNK)
                if not chunk:
                    raise ConnectionError("Connection closed by remote")
                buffer += chunk

                # Try to parse as complete JSON
                try:
                    response = json.loads(buffer.decode("utf-8"))
                    break
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
            except socket.timeout:
                raise TimeoutError(f"No response within {timeout}s")
        else:
            raise TimeoutError(f"Incomplete response after {timeout}s")

        # Check for JSON-RPC error
        if "error" in response:
            error = response["error"]
            raise RuntimeError(
                f"QGIS plugin error [{error.get('code')}]: {error.get('message')}"
            )

        return response.get("result", {})

    def initialize(self) -> dict:
        """Perform MCP handshake with QGIS plugin."""
        result = self.send_command("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "qgis-mcp-server", "version": "2.0.0"}
        })
        return result

    def list_tools(self) -> list[dict]:
        """Get available tools from QGIS plugin."""
        result = self.send_command("tools/list")
        return result.get("tools", [])

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        """Call a tool on the QGIS plugin."""
        return self.send_command("tools/call", {
            "name": name,
            "arguments": arguments or {}
        })


# Singleton connection
_connection: QGISConnection | None = None


def get_connection(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> QGISConnection:
    """Get or create the persistent connection to QGIS plugin."""
    global _connection
    if _connection is None or not _connection.is_connected:
        conn = QGISConnection(host, port)
        if not conn.connect():
            raise ConnectionError(f"Cannot connect to QGIS plugin at {host}:{port}")
        try:
            conn.initialize()
        except Exception:
            conn.disconnect()
            raise
        _connection = conn
    return _connection


def invalidate_connection():
    """Invalidate the current connection (for reconnection)."""
    global _connection
    if _connection:
        _connection.disconnect()
    _connection = None
