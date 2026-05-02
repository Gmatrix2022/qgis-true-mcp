# QGIS MCP Server V2 开发教程

> 标准 MCP 协议 + FastMCP 框架，让 AI 助手操控 QGIS
>
> 2026-05-02 | V2.0.0

---

## 一、项目概述

**QGIS MCP Server** 是一个遵循 [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) 标准的 QGIS 集成方案，将 QGIS 的 GIS 能力以结构化工具的形式暴露给 AI 助手。

### 核心特性

- ✅ **标准 MCP 协议**：JSON-RPC 2.0 over stdio/SSE/HTTP
- ✅ **FastMCP 框架**：`@mcp.tool()` 自动注册工具、生成 JSON Schema
- ✅ **18 个结构化工具**：覆盖图层管理、空间查询、样式渲染等核心操作
- ✅ **无代码执行**：全部参数化，安全可控
- ✅ **多传输层**：stdio（本地）、SSE（远程）、HTTP（Streamable）

### V1 → V2 升级

| 维度 | V1（旧） | V2（新） |
|------|---------|---------|
| 协议 | 自定义 TCP socket | **标准 MCP（JSON-RPC 2.0）** |
| 传输层 | raw TCP | **stdio / SSE / HTTP** |
| 框架 | 手写协议处理 | **FastMCP（官方框架）** |
| 工具注册 | 手动定义 schema | **@mcp.tool() 自动注册** |
| 客户端兼容 | 仅自定义客户端 | **任何 MCP 客户端** |

---

## 二、架构设计

### 2.1 三层架构

```
┌─────────────────────────────────────────────────────────────┐
│                MCP 客户端 (Claude / Cursor / Hermes)          │
│              stdio / SSE / StreamableHTTP                    │
└──────────────────────────┬──────────────────────────────────┘
                           │ JSON-RPC 2.0 (MCP 标准协议)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                MCP Server (FastMCP 框架)                      │
│          server/server.py — 工具注册、参数校验、响应封装         │
│          server/client.py — TCP 客户端连接 QGIS 插件          │
└──────────────────────────┬──────────────────────────────────┘
                           │ raw TCP socket (内部通信)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                QGIS 插件 (plugin.py)                          │
│          QTimer 主线程安全执行 PyQGIS API                      │
│          TCP Server 监听 :9876                                │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 协议分层

| 层级 | 协议 | 说明 |
|------|------|------|
| **MCP 客户端 ↔ MCP Server** | JSON-RPC 2.0 over stdio/SSE/HTTP | 标准 MCP 协议 |
| **MCP Server ↔ QGIS 插件** | raw TCP + JSON-RPC 2.0 | 内部通信，不对外暴露 |

### 2.3 文件结构

```
qgis-standard-mcp/
├── server/                     # MCP Server（V2 新增）
│   ├── __init__.py
│   ├── __main__.py
│   ├── server.py               # FastMCP 服务器，注册 18 个工具
│   └── client.py               # TCP 客户端，连接 QGIS 插件
├── qgis_standard_mcp_plugin/   # QGIS 插件
│   ├── __init__.py
│   ├── metadata.txt
│   └── qgis_standard_mcp_plugin.py
├── run_server.py               # 启动脚本
├── pyproject.toml              # Python 包配置
├── README.md
└── LICENSE
```

---

## 三、安装部署

### 3.1 安装 QGIS 插件

将 `qgis_standard_mcp_plugin/` 文件夹复制到 QGIS 插件目录：

**Windows**：
```
C:\Users\<用户名>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\
```

**Linux**：
```
~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/
```

**macOS**：
```
~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/
```

重启 QGIS → 插件管理器 → 勾选 "QGIS Standard MCP"

### 3.2 安装 MCP Server 依赖

```bash
pip install mcp
# 或使用 uv
uv pip install mcp
```

### 3.3 配置 MCP 客户端

**Claude Desktop** (`claude_desktop_config.json`)：
```json
{
  "mcpServers": {
    "qgis": {
      "command": "python",
      "args": ["/path/to/run_server.py"],
      "env": {
        "QGIS_MCP_HOST": "localhost",
        "QGIS_MCP_PORT": "9876"
      }
    }
  }
}
```

**Hermes** (`~/.hermes/config.yaml`)：
```yaml
mcp_servers:
  qgis:
    command: python3
    args:
    - /path/to/run_server.py
    env:
      QGIS_MCP_HOST: host.docker.internal
      QGIS_MCP_PORT: "9876"
```

**Cursor** (`.cursor/mcp.json`)：
```json
{
  "mcpServers": {
    "qgis": {
      "command": "python",
      "args": ["/path/to/run_server.py"]
    }
  }
}
```

### 3.4 启动

1. 打开 QGIS → Plugins → QGIS Standard MCP → Start MCP Server
2. 启动 MCP Server：
   ```bash
   python run_server.py
   # 或
   python -m server
   ```

---

## 四、工具 API 参考

### 4.1 基础连接

#### `ping`
检查 MCP 服务器连通性。

**参数**：无

**返回**：
```json
{
  "pong": true,
  "server": "qgis-standard-mcp",
  "version": "0.1.0"
}
```

#### `get_qgis_info`
获取 QGIS 版本和安装信息。

**参数**：无

**返回**：
```json
{
  "qgis_version": "3.44.9-Solothurn",
  "profile_folder": "C:/Users/.../QGIS3/profiles/default/",
  "plugins_count": 9
}
```

### 4.2 项目管理

#### `get_project_info`
获取当前项目信息。

**参数**：无

**返回**：
```json
{
  "filename": "D:/GISDATA/test.qgz",
  "title": "测试项目",
  "crs": "EPSG:4326",
  "layer_count": 2,
  "layers": [...]
}
```

#### `create_project`
创建新项目。

**参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `path` | string | ✅ | 项目保存路径 |

#### `load_project`
加载已有项目。

**参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `path` | string | ✅ | 项目文件路径 |

#### `save_project`
保存当前项目。

**参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `path` | string | ❌ | 保存路径（可选） |

### 4.3 图层管理

#### `get_layers`
列出所有图层。

**参数**：无

**返回**：
```json
[
  {
    "id": "layer_id_abc123",
    "name": "云南省界",
    "type": "vector",
    "geometry_type": "Polygon",
    "feature_count": 1,
    "fields": ["name", "code"]
  }
]
```

#### `add_vector_layer`
添加矢量图层。

**参数**：
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `path` | string | ✅ | - | 数据源路径 |
| `name` | string | ❌ | 文件名 | 图层显示名称 |
| `provider` | string | ❌ | "ogr" | 数据提供者 |

**示例**：
```json
{
  "path": "D:/GISDATA/YUNNAN-WGS84/yn_LL_wgs84/yn_boud.shp",
  "name": "云南省界",
  "provider": "ogr"
}
```

#### `add_raster_layer`
添加栅格图层。

**参数**：
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `path` | string | ✅ | - | 数据源路径 |
| `name` | string | ❌ | 文件名 | 图层显示名称 |
| `provider` | string | ❌ | "gdal" | 数据提供者 |

#### `remove_layer`
删除图层。

**参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `layer_id` | string | ✅ | 图层 ID |

### 4.4 要素查询

#### `get_layer_features`
获取图层要素。

**参数**：
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `layer_id` | string | ✅ | - | 图层 ID |
| `limit` | integer | ❌ | 100 | 最大返回数 |
| `filter_expression` | string | ❌ | - | QGIS 表达式过滤 |

**示例**：
```json
{
  "layer_id": "layer_id_abc123",
  "limit": 50,
  "filter_expression": "\"name\" LIKE '%昆明%'"
}
```

#### `spatial_query`
空间查询。

**参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `layer_id` | string | ✅ | 图层 ID |
| `query_type` | string | ✅ | "point_radius" 或 "bbox" |
| `center_lng` | number | 条件 | 中心经度（point_radius） |
| `center_lat` | number | 条件 | 中心纬度（point_radius） |
| `radius_meters` | number | 条件 | 搜索半径（米） |
| `min_lng` | number | 条件 | 西边界（bbox） |
| `min_lat` | number | 条件 | 南边界（bbox） |
| `max_lng` | number | 条件 | 东边界（bbox） |
| `max_lat` | number | 条件 | 北边界（bbox） |
| `limit` | integer | ❌ | 最大返回数（默认 100） |

### 4.5 样式渲染

#### `set_layer_style`
设置图层样式。

**参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `layer_id` | string | ✅ | 图层 ID |
| `style` | object | ✅ | 样式配置 |

**style 对象属性**：
| 属性 | 类型 | 说明 |
|------|------|------|
| `fill_color` | string | 填充颜色（如 "#e74c3c"） |
| `outline_color` | string | 轮廓颜色 |
| `outline_width` | number | 轮廓宽度（mm） |
| `opacity` | number | 透明度（0.0-1.0） |
| `point_size` | number | 点符号大小 |
| `point_shape` | string | 点形状（circle/square/triangle/diamond/star） |

#### `render_map`
渲染地图为图片。

**参数**：
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `output_path` | string | ✅ | - | 输出文件路径 |
| `width` | integer | ❌ | 1200 | 图片宽度 |
| `height` | integer | ❌ | 900 | 图片高度 |

### 4.6 视图控制

#### `zoom_to_extent`
缩放到指定范围。

**参数**：
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `min_lng` | number | ✅ | - | 西边界 |
| `min_lat` | number | ✅ | - | 南边界 |
| `max_lng` | number | ✅ | - | 东边界 |
| `max_lat` | number | ✅ | - | 北边界 |
| `crs` | string | ❌ | "EPSG:4326" | 坐标系 |

#### `zoom_to_layer`
缩放到图层范围。

**参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `layer_id` | string | ✅ | 图层 ID |

### 4.7 空间分析

#### `buffer_analysis`
缓冲区分析。

**参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `layer_id` | string | ✅ | 图层 ID |
| `distance` | number | ✅ | 缓冲距离（米） |
| `output_path` | string | ❌ | 输出路径 |

#### `execute_processing`
执行 QGIS Processing 算法。

**参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `algorithm` | string | ✅ | 算法名称 |
| `parameters` | object | ✅ | 算法参数 |

**示例**：
```json
{
  "algorithm": "native:buffer",
  "parameters": {
    "INPUT": "layer_id_abc123",
    "DISTANCE": 1000,
    "OUTPUT": "D:/GISDATA/buffer_output.shp"
  }
}
```

---

## 五、开发手记

### 5.1 线程安全模型

QGIS 的所有 GUI API 必须在主线程执行。插件采用生产者-消费者模式：

```
TCP Server 线程 (socket.recv)          QTimer 主线程回调
        │                                    │
        │  recv 数据 → 解析 JSON-RPC          │
        │  放入 request_queue                 │
        │                                    │
        │  ──────────────────────────────►    │
        │                                    │  从队列取出请求
        │                                    │  执行 PyQGIS API
        │                                    │  放入 response_queue
        │                                    │
        │  ◄──────────────────────────────    │
        │  从 response_queue 取响应           │
        │  sendall 回客户端                    │
```

### 5.2 已知陷阱

#### CRS 不匹配
bbox 坐标输入是 WGS84 (EPSG:4326)，但图层可能是投影坐标系。必须做坐标转换：
```python
src_crs = QgsCoordinateReferenceSystem("EPSG:4326")
dst_crs = layer.crs()
transform = QgsCoordinateTransform(src_crs, dst_crs, project.transformContext())
rect = transform.transformBoundingBox(QgsRectangle(min_lng, min_lat, max_lng, max_lat))
```

#### 画布白屏
三个条件必须同时满足：
1. `create_project` 必须设 CRS
2. `add_vector_layer` 必须 `refresh()` + `zoomToActiveLayer()`
3. `render_map` 必须用图层联合范围

#### QVariant 序列化
QGIS 属性值是 QVariant，JSON 不认识。必须：
```python
attrs = {k: v.toPyObj() if hasattr(v, 'toPyObj') else v for k, v in raw_attrs.items()}
```

#### QgsDockWidget vs QDockWidget
插件面板必须用 `QgsDockWidget`（QGIS 专用），不是 Qt 的 `QDockWidget`。

---

## 六、测试验证

### 6.1 原始 TCP 测试

```python
import socket, json

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(('localhost', 9876))

# 握手
request = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
           "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                      "clientInfo": {"name": "test", "version": "1.0"}}}
sock.sendall(json.dumps(request).encode())
response = json.loads(sock.recv(65536))
print(response)

# 调用工具
request = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
           "params": {"name": "get_layers", "arguments": {}}}
sock.sendall(json.dumps(request).encode())
response = json.loads(sock.recv(65536))
print(response)
```

### 6.2 MCP Server 测试

```python
from server.client import QGISConnection

conn = QGISConnection('localhost', 9876)
conn.connect()
conn.initialize()

# 列出工具
tools = conn.list_tools()
print(f"{len(tools)} 个工具")

# 调用工具
result = conn.call_tool('ping')
print(result)
```

---

## 七、License

MIT

---

*Generated 2026-05-02 | QGIS MCP Server V2.0.0*
