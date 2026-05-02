#!/usr/bin/env python3
"""
QGIS Standard MCP - stdio-to-TCP bridge

This is a THIN bridge that converts MCP stdio transport (JSON-RPC over stdin/stdout)
to TCP socket communication with the QGIS plugin.

It does NOT parse or transform the MCP protocol — it passes raw JSON-RPC messages
through unchanged. All protocol logic lives in the QGIS plugin.

Usage (for Hermes config.yaml):
  mcp_servers:
    qgis:
      command: python
      args: ["/path/to/qgis_mcp_stdio_bridge.py"]
      env:
        QGIS_MCP_HOST: host.docker.internal
        QGIS_MCP_PORT: "9876"
"""
import socket
import json
import sys
import os
import threading
import logging

logging.basicConfig(level=logging.INFO, format='[bridge] %(levelname)s: %(message)s')
logger = logging.getLogger("qgis-mcp-bridge")

QGIS_HOST = os.environ.get("QGIS_MCP_HOST", "host.docker.internal")
QGIS_PORT = int(os.environ.get("QGIS_MCP_PORT", "9876"))


def connect_to_qgis(host, port, retries=5, delay=2):
    """Connect to the QGIS MCP plugin with retry logic."""
    for attempt in range(retries):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(30)
            sock.connect((host, port))
            logger.info(f"Connected to QGIS MCP plugin at {host}:{port}")
            return sock
        except (ConnectionRefusedError, OSError) as e:
            logger.warning(f"Connection attempt {attempt+1}/{retries} failed: {e}")
            if attempt < retries - 1:
                import time
                time.sleep(delay)
    logger.error(f"Failed to connect after {retries} attempts")
    return None


def read_jsonrpc_message(stream):
    """Read a single JSON-RPC message from a stream (stdin)."""
    line = stream.readline()
    if not line:
        return None
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON: {line[:100]}")
        return None


def forward_to_qgis(sock, message):
    """Send a JSON-RPC message to QGIS and receive the response."""
    raw = json.dumps(message, ensure_ascii=False)
    sock.sendall(raw.encode('utf-8'))

    # Read response
    buffer = b''
    sock.settimeout(30)
    while True:
        try:
            chunk = sock.recv(65536)
            if not chunk:
                return None
            buffer += chunk
            # Validate JSON
            try:
                resp = json.loads(buffer.decode('utf-8'))
                return resp
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
        except socket.timeout:
            return None


def main():
    logger.info(f"Connecting to QGIS at {QGIS_HOST}:{QGIS_PORT}")
    sock = connect_to_qgis(QGIS_HOST, QGIS_PORT)
    if not sock:
        # Write error to stderr and exit
        sys.stderr.write("Failed to connect to QGIS MCP plugin\n")
        sys.exit(1)

    try:
        while True:
            # Read MCP message from stdin (Hermes sends JSON-RPC)
            message = read_jsonrpc_message(sys.stdin)
            if message is None:
                break  # EOF or invalid

            logger.debug(f"← {json.dumps(message, ensure_ascii=False)[:120]}...")

            # Forward raw to QGIS plugin, get raw response
            response = forward_to_qgis(sock, message)

            if response is not None:
                logger.debug(f"→ {json.dumps(response, ensure_ascii=False)[:120]}...")
                # Write raw JSON-RPC response to stdout (Hermes reads this)
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()
            else:
                logger.error("No response from QGIS plugin")
                # Try to reconnect
                sock.close()
                sock = connect_to_qgis(QGIS_HOST, QGIS_PORT)
                if not sock:
                    break

    except KeyboardInterrupt:
        pass
    finally:
        if sock:
            sock.close()
        logger.info("Bridge shut down")


if __name__ == "__main__":
    main()
