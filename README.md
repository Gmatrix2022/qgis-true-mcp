# QGIS Standard MCP

**标准 MCP 协议 QGIS 原生插件** — 让 AI 助手直接操控 QGIS 进行空间分析。

[MCP](https://modelcontextprotocol.io)
[QGIS](https://qgis.org)
[License](LICENSE)

## 这是什么？

一个遵循 [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) 官方标准的 QGIS 插件，将 QGIS 的 GIS 能力以**结构化工具**的形式暴露给 AI 助手（Hermes、Claude、ChatGPT 等）。

### 与 jjsantos01/qgis_mcp 的区别


|      | jjsantos01/qgis_mcp       | **本项目**                      |
| ---- | ------------------------- | ---------------------------- |
| 协议   | 自定义 socket JSON           | **MCP JSON-RPC 2.0**         |
| 工具调用 | LLM 生成 Python 代码 → exec() | **LLM 发结构化参数**               |
| 安全性  | 远程代码执行（无沙箱）               | **无代码执行，全部参数化**              |
| 桥接层  | 协议转换（重）                   | 传输层转换（极薄）                    |
| 工具发现 | 无                         | **tools/list + JSON Schema** |


## 工具列表


| 工具                   | 说明               |
| -------------------- | ---------------- |
| `ping`               | 连通性测试            |
| `get_qgis_info`      | QGIS 版本信息        |
| `get_project_info`   | 当前项目信息           |
| `create_project`     | 新建 QGIS 项目       |
| `load_project`       | 加载项目文件           |
| `save_project`       | 保存项目             |
| `add_vector_layer`   | 添加矢量图层           |
| `add_raster_layer`   | 添加栅格图层           |
| `get_layers`         | 列出所有图层           |
| `remove_layer`       | 删除图层             |
| `get_layer_features` | 查询图层要素（支持过滤）     |
| `set_layer_style`    | 设置图层样式           |
| `zoom_to_extent`     | 缩放到指定范围          |
| `zoom_to_layer`      | 缩放到图层范围          |
| `spatial_query`      | 空间查询（点半径/矩形）     |
| `buffer_analysis`    | 缓冲区分析            |
| `execute_processing` | 执行 Processing 算法 |
| `render_map`         | 渲染地图为图片          |


## 安装

### 1. 安装 QGIS 插件

将 `qgis_standard_mcp_plugin/` 文件夹复制到 QGIS 插件目录：

- **Windows**: `C:\Users\<用户名>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\`
- **Linux**: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
- **macOS**: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`

重启 QGIS → 插件管理器 → 勾选 "QGIS Standard MCP"

### 2. 配置 Hermes

在 `~/.hermes/config.yaml` 中添加：

```yaml
mcp_servers:
  qgis:
    command: python3
    args:
    - /path/to/qgis_mcp_stdio_bridge.py
    env:
      QGIS_MCP_HOST: host.docker.internal
      QGIS_MCP_PORT: "9876"
```

### 3. 启动

1. 打开 QGIS → Plugins → QGIS Standard MCP → Start MCP Server
2. 重启 Hermes Agent

## 架构

```
AI 助手 (Hermes/Claude/ChatGPT)
    │
    │ MCP stdio (JSON-RPC 2.0)
    ▼
qgis_mcp_stdio_bridge.py
    │
    │ TCP socket (JSON-RPC 2.0 透传)
    ▼
QGIS 插件 (MCP 原生服务端)
    │
    │ PyQGIS API
    ▼
QGIS C++ 内核
```

## 安全设计

- **无 execute_code**：移除了远程代码执行后门
- **参数化工具**：所有工具通过 JSON Schema 定义输入参数
- **无 iface 暴露**：不暴露 QGIS GUI 接口
- **端口绑定**：默认绑定 0.0.0.0:9876，生产环境建议仅本地监听

## 开发

```bash
# 克隆
git clone https://github.com/Gmatrix2022/qgis-true-mcp.git

# 插件开发
# 编辑 qgis_standard_mcp_plugin/qgis_standard_mcp_plugin.py
# 重启 QGIS 测试

# 运行测试客户端
python3 qgis_mcp_stdio_bridge.py
```

## License

MIT