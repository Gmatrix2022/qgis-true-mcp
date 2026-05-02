#!/usr/bin/env python3
"""Test the QGIS Standard MCP plugin directly via TCP socket."""
import socket
import json
import sys

def test_mcp(host="host.docker.internal", port=9876):
    print(f"Connecting to {host}:{port}...")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)
    
    try:
        s.connect((host, port))
    except Exception as e:
        print(f"Connection failed: {e}")
        print("Make sure QGIS is running and QGIS Standard MCP plugin is started.")
        sys.exit(1)
    
    print("Connected!\n")
    
    # Test 1: initialize
    print("=== Test 1: initialize ===")
    resp = send_recv(s, {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "0.1.0"}
        }
    })
    print_result(resp)
    
    # Send initialized notification
    send_only(s, {
        "jsonrpc": "2.0",
        "method": "initialized",
        "params": {}
    })
    print("(sent initialized notification)\n")
    
    # Test 2: tools/list
    print("=== Test 2: tools/list ===")
    resp = send_recv(s, {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    })
    if resp and "result" in resp:
        tools = resp["result"].get("tools", [])
        print(f"Found {len(tools)} tools:")
        for t in tools:
            print(f"  - {t['name']}: {t['description'][:60]}...")
    else:
        print_result(resp)
    print()
    
    # Test 3: ping
    print("=== Test 3: ping ===")
    resp = call_tool(s, 3, "ping", {})
    print_result(resp)
    print()
    
    # Test 4: get_qgis_info
    print("=== Test 4: get_qgis_info ===")
    resp = call_tool(s, 4, "get_qgis_info", {})
    print_result(resp)
    print()
    
    # Test 5: get_project_info
    print("=== Test 5: get_project_info ===")
    resp = call_tool(s, 5, "get_project_info", {})
    print_result(resp)
    print()
    
    # Test 6: get_layers
    print("=== Test 6: get_layers ===")
    resp = call_tool(s, 6, "get_layers", {})
    print_result(resp)
    print()
    
    # Test 7: zoom_to_extent (Yunnan)
    print("=== Test 7: zoom_to_extent (Yunnan) ===")
    resp = call_tool(s, 7, "zoom_to_extent", {
        "min_lng": 97.5, "min_lat": 21.0,
        "max_lng": 106.5, "max_lat": 29.5
    })
    print_result(resp)
    print()
    
    # Test 8: render_map
    print("=== Test 8: render_map ===")
    resp = call_tool(s, 8, "render_map", {
        "path": "D:/GISDATA/mcp_test_render.png",
        "width": 1200,
        "height": 900
    })
    print_result(resp)
    
    s.close()
    print("\n=== All tests complete ===")

def send_recv(s, msg):
    raw = json.dumps(msg, ensure_ascii=False)
    s.sendall(raw.encode('utf-8'))
    data = b''
    while True:
        chunk = s.recv(65536)
        if not chunk:
            return None
        data += chunk
        try:
            return json.loads(data.decode('utf-8'))
        except:
            continue

def send_only(s, msg):
    raw = json.dumps(msg, ensure_ascii=False)
    s.sendall(raw.encode('utf-8'))

def call_tool(s, req_id, tool_name, arguments):
    return send_recv(s, {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments}
    })

def print_result(resp):
    if resp is None:
        print("  No response (timeout)")
        return
    text = json.dumps(resp, indent=2, ensure_ascii=False)
    for line in text.split('\n'):
        print(f"  {line}")

if __name__ == "__main__":
    test_mcp()
