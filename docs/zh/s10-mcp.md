# s10 · MCP：来自其他进程的工具

> 代码：[`agents/s10_mcp.py`](../../agents/s10_mcp.py) · 服务器：[`examples/mcp_sqlite_server.py`](../../examples/mcp_sqlite_server.py) · [← s09](s09-memory.md)

## 问题

到目前为止，所有工具都是 harness 内部的 Python 函数。但你的数据库、浏览器、Figma、Sentry、公司内部 API 不是。
为每一个服务、每一个 agent 都写一遍适配器，根本做不完。

## 思路

**MCP（Model Context Protocol，模型上下文协议）**：任何程序都可以提供工具，任何 agent 都能使用。
走 stdio 时，它就是普通的 JSON-RPC 2.0，一行一个 JSON 对象：

```
harness ──initialize──────────────▶ server（一个子进程）
        ◀─────────── capabilities ──
        ──notifications/initialized▶
        ──tools/list──────────────▶
        ◀── [{name, description, inputSchema}, ...]
        ──tools/call {name, arguments}▶
        ◀── {content: [{type: "text", text}], isError}
```

## 客户端（约 60 行）

```python
class MCPServer:
    def __init__(self, name, command, args=(), env=None):
        self.proc = subprocess.Popen([command, *args], stdin=PIPE, stdout=PIPE, text=True, ...)
        self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                    "clientInfo": {"name": "harness-from-scratch", "version": "1.0"}})
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.tools = self.request("tools/list")["tools"]      # （实际代码里处理了分页）

    def request(self, method, params=None):
        self.next_id += 1
        self.send({"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params or {}})
        while True:                                            # 跳过不是给我们的回复
            msg = json.loads(self.proc.stdout.readline())
            if msg.get("id") == self.next_id and "method" not in msg:
                return msg["result"]

    def call(self, tool_name, args):
        result = self.request("tools/call", {"name": tool_name, "arguments": args})
        ...
```

每个远程工具都注册为 `mcp__<server>__<tool>`，和 Claude Code 的命名方式一致。它的 `inputSchema`
原样变成我们的 `parameters`，因为 MCP 和模型 API 用的都是 JSON Schema。处理函数是一个闭包，把调用转发给 `server.call`。

**远程工具和本地工具一样，要经过同一道权限关卡和同一组钩子。** MCP 服务器是第三方代码，这一点很重要。

## 配置

与 Claude Code、Claude Desktop 相同的 `.mcp.json` 格式：

```json
{"mcpServers": {
  "shop": {"command": "python3", "args": ["examples/mcp_sqlite_server.py"]},
  "fs":   {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]}
}}
```

## 服务端

[`examples/mcp_sqlite_server.py`](../../examples/mcp_sqlite_server.py) 是一个完整的 MCP 服务器，
大约 100 行，只用标准库。它提供一个只读的 SQLite 数据库，带 `list_tables`、`describe_table`、`query` 三个工具。
读它是理解 MCP 最快的方式，而且它能接入任何 MCP 客户端。

## 运行

```bash
python agents/s10_mcp.py
```

模型通过 MCP 探索一个商店数据库，用一条真实的 SQL 回答"哪些顾客花钱最多？"。

## 练习

1. 加读超时：卡住的服务器不应该把 agent 也卡住（提示：读线程 + `queue.get(timeout=...)`）。
2. 支持 MCP 的 **resources**（`resources/list`、`resources/read`），包装成一个 `read_resource` 工具。
3. 为你每天都用的某个东西写一个 MCP 服务器，然后把它也接进 Claude Code。

---

**整个 harness 到此完成。** [`harness.py`](../../agents/harness.py) 把 s10 包装成更好用的命令行
（斜杠命令、会话保存、`-p` 单次模式），可以日常使用。
