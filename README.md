# QGIS MCP Server

**标准 MCP 协议 QGIS 集成方案** — 让 AI 助手直接操控 QGIS 进行空间分析。

[MCP](https://modelcontextprotocol.io) · [QGIS](https://qgis.org) · [License](LICENSE)

## 这是什么？

一个遵循 [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) 标准的 QGIS 集成方案，将 QGIS 的 GIS 能力以**结构化工具**的形式暴露给 AI 助手（Claude、Cursor、Hermes 等）。

## 架构

```
MCP 客户端 (Claude / Cursor / Hermes)
    │
    │ stdio / SSE / HTTP（MCP 标准传输层）
    │ JSON-RPC 2.0（MCP 标准协议）
    ▼
MCP Server (FastMCP 框架)
    │
    │ raw TCP socket（内部通信）
    │ JSON-RPC 2.0（QGIS 插件原生协议）
    ▼
QGIS 插件
    │
    │ PyQGIS API
    ▼
QGIS 内核
```

## 工具列表（18个）

| 工具 | 说明 |
|------|------|
| `ping` | 连通性测试 |
| `get_qgis_info` | QGIS 版本信息 |
| `get_project_info` | 当前项目信息 |
| `create_project` | 新建 QGIS 项目 |
| `load_project` | 加载项目文件 |
| `save_project` | 保存项目 |
| `add_vector_layer` | 添加矢量图层 |
| `add_raster_layer` | 添加栅格图层 |
| `get_layers` | 列出所有图层 |
| `remove_layer` | 删除图层 |
| `get_layer_features` | 查询图层要素 |
| `set_layer_style` | 设置图层样式 |
| `zoom_to_extent` | 缩放到指定范围 |
| `zoom_to_layer` | 缩放到图层范围 |
| `spatial_query` | 空间查询（点半径/矩形） |
| `buffer_analysis` | 缓冲区分析 |
| `execute_processing` | 执行 Processing 算法 |
| `render_map` | 渲染地图为图片 |

## 快速开始

### 1. 安装 QGIS 插件

将 `qgis_standard_mcp_plugin/` 复制到 QGIS 插件目录：

- **Windows**: `C:\Users\<用户名>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\`
- **Linux**: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
- **macOS**: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`

重启 QGIS → 插件管理器 → 勾选 "QGIS Standard MCP"

### 2. 安装 MCP Server

```bash
pip install mcp
```

### 3. 配置 MCP 客户端

**Claude Desktop**:
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

**Hermes**:
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

### 4. 启动

1. 打开 QGIS → Plugins → QGIS Standard MCP → Start MCP Server
2. 启动 MCP Server：`python run_server.py`

## 安全设计

- **无 execute_code**：移除了远程代码执行后门
- **参数化工具**：所有工具通过 JSON Schema 定义输入参数
- **无 iface 暴露**：不暴露 QGIS GUI 接口
- **端口绑定**：默认绑定 0.0.0.0:9876，生产环境建议仅本地监听

## 文件结构

```
qgis-standard-mcp/
├── server/                     # MCP Server（FastMCP 框架）
│   ├── __init__.py
│   ├── __main__.py
│   ├── server.py               # 工具注册、参数校验
│   └── client.py               # TCP 客户端连接 QGIS 插件
├── qgis_standard_mcp_plugin/   # QGIS 插件
│   ├── __init__.py
│   ├── metadata.txt
│   └── qgis_standard_mcp_plugin.py
├── run_server.py               # 启动脚本
├── pyproject.toml              # Python 包配置
├── qgis-mcp-v2-tutorial.md     # 开发教程（Markdown）
├── qgis-mcp-v2-tutorial.html   # 开发教程（HTML）
└── qgis-mcp-v2-comparison.html # V1→V2 架构对比
```

## 开发

```bash
# 克隆
git clone https://github.com/Gmatrix2022/qgis-true-mcp.git

# 安装依赖
pip install mcp

# 运行测试
python -c "from server.client import QGISConnection; conn = QGISConnection('localhost', 9876); conn.connect(); print(conn.call_tool('ping'))"

# 启动 MCP Server
python run_server.py
```

## License

MIT
