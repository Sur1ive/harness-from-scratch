# s10 · MCP: tools from other processes

> Code: [`agents/s10_mcp.py`](../../agents/s10_mcp.py) · Server: [`examples/mcp_sqlite_server.py`](../../examples/mcp_sqlite_server.py) · [← s09](s09-memory.md)

## The problem

Every tool so far is a Python function inside the harness. Your database,
your browser, Figma, Sentry and your company's internal API are not. Writing
an adapter for each one, for each agent, doesn't scale.

## The idea

**MCP (Model Context Protocol)**: any program can offer tools, and any agent can
use them. Over stdio it is plain JSON-RPC 2.0, one JSON object per line:

```
harness ──initialize──────────────▶ server (a subprocess)
        ◀─────────── capabilities ──
        ──notifications/initialized▶
        ──tools/list──────────────▶
        ◀── [{name, description, inputSchema}, ...]
        ──tools/call {name, arguments}▶
        ◀── {content: [{type: "text", text}], isError}
```

## The client (~60 lines)

```python
class MCPServer:
    def __init__(self, name, command, args=(), env=None):
        self.proc = subprocess.Popen([command, *args], stdin=PIPE, stdout=PIPE, text=True, ...)
        self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                    "clientInfo": {"name": "harness-from-scratch", "version": "1.0"}})
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.tools = self.request("tools/list")["tools"]      # (paginated in the real code)

    def request(self, method, params=None):
        self.next_id += 1
        self.send({"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params or {}})
        while True:                                            # skip anything that isn't our answer
            msg = json.loads(self.proc.stdout.readline())
            if msg.get("id") == self.next_id and "method" not in msg:
                return msg["result"]

    def call(self, tool_name, args):
        result = self.request("tools/call", {"name": tool_name, "arguments": args})
        ...
```

Each remote tool is registered as `mcp__<server>__<tool>`, which is the same naming
Claude Code uses. Its `inputSchema` becomes our `parameters` unchanged,
because MCP and the model APIs both use JSON Schema. The handler is a
closure that forwards to `server.call`.

**Remote tools go through the same permission gate and hooks as local ones.**
An MCP server is third-party code, so this matters.

## Configuration

The same `.mcp.json` format as Claude Code and Claude Desktop:

```json
{"mcpServers": {
  "shop": {"command": "python3", "args": ["examples/mcp_sqlite_server.py"]},
  "fs":   {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]}
}}
```

## The server side

[`examples/mcp_sqlite_server.py`](../../examples/mcp_sqlite_server.py) is a
complete MCP server in about 100 lines of standard library Python. It serves a read-only
SQLite database with `list_tables`, `describe_table` and `query` tools.
Reading it is the fastest way to understand MCP, and it works with any MCP client.

## Run it

```bash
python agents/s10_mcp.py
```

The model explores a shop database through MCP and answers *"which customers
spent the most?"* with a real SQL query.

## Exercises

1. Add a read timeout: a hung server shouldn't hang the agent (hint: a reader thread + `queue.get(timeout=...)`).
2. Support MCP **resources** (`resources/list`, `resources/read`) as a `read_resource` tool.
3. Write an MCP server for something you use daily, then connect it to Claude Code too.

---

**That's the whole harness.** [`harness.py`](../../agents/harness.py) wraps s10 in a nicer
REPL (slash commands, saved sessions, a `-p` one-shot mode) for daily use.
