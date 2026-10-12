#!/usr/bin/env python3
"""
A complete MCP server in ~100 lines of standard-library Python.

MCP (Model Context Protocol) over stdio is just JSON-RPC 2.0, one JSON
object per line: the client writes requests to our stdin, we answer on
stdout. Three methods matter:

    initialize   -> who we are and what we support
    tools/list   -> the tools we offer (name, description, JSON schema)
    tools/call   -> run one, return content blocks

This server exposes a read-only SQLite database. With no argument it
serves a small demo shop; pass a path to serve your own .db file:

    python3 examples/mcp_sqlite_server.py [path/to/db.sqlite]

It works with any MCP client (Claude Code, Claude Desktop, Cursor, ...)
- and with the client we build in agents/s10_mcp.py.
"""

import json
import sqlite3
import sys


def demo_db():
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, city TEXT);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, total_cents INTEGER, placed_at TEXT);
        INSERT INTO customers VALUES (1, 'Ada', 'London'), (2, 'Linus', 'Helsinki'), (3, 'Grace', 'New York'),
                                     (4, 'Wang', 'Shanghai');
        INSERT INTO orders VALUES (1, 1, 4200, '2026-09-01'), (2, 2, 1999, '2026-09-03'), (3, 1, 15000, '2026-09-10'),
                                  (4, 3, 8800, '2026-09-12'), (5, 4, 23000, '2026-09-20'), (6, 2, 500, '2026-09-21');
    """)
    return db


DB = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True) if len(sys.argv) > 1 else demo_db()
DB.execute("PRAGMA query_only = ON")  # belt and braces: no writes, ever

TOOLS = [
    {"name": "list_tables", "description": "List all tables in the database.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "describe_table", "description": "Show the columns of a table.",
     "inputSchema": {"type": "object", "required": ["table"], "properties": {"table": {"type": "string"}}}},
    {"name": "query", "description": "Run a read-only SQL query (SELECT / WITH). Returns up to 100 rows.",
     "inputSchema": {"type": "object", "required": ["sql"], "properties": {"sql": {"type": "string"}}}},
]


def call_tool(name, args):
    if name == "list_tables":
        rows = DB.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").fetchall()
        return "\n".join(r[0] for r in rows)
    if name == "describe_table":
        rows = DB.execute("SELECT name, type FROM pragma_table_info(?)", (args["table"],)).fetchall()
        if not rows:
            raise ValueError(f"no such table: {args['table']}")
        return "\n".join(f"{n} {t}" for n, t in rows)
    if name == "query":
        cur = DB.execute(args["sql"])
        cols = [d[0] for d in cur.description or []]
        rows = cur.fetchmany(100)
        return "\n".join([" | ".join(cols)] + [" | ".join(map(str, r)) for r in rows])
    raise ValueError(f"unknown tool: {name}")


def handle(msg):
    method, params = msg.get("method"), msg.get("params") or {}
    if method == "initialize":
        return {"protocolVersion": params.get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "sqlite-demo", "version": "1.0.0"}}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        try:
            text, is_error = call_tool(params["name"], params.get("arguments") or {}), False
        except Exception as e:  # errors are results the model can read, not protocol failures
            text, is_error = f"{type(e).__name__}: {e}", True
        return {"content": [{"type": "text", "text": text}], "isError": is_error}
    raise LookupError(method)


for line in sys.stdin:
    if not line.strip():
        continue
    msg = json.loads(line)
    if "id" not in msg:  # a notification (e.g. notifications/initialized): no reply
        continue
    try:
        reply = {"jsonrpc": "2.0", "id": msg["id"], "result": handle(msg)}
    except LookupError:
        reply = {"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": f"unknown method {msg.get('method')}"}}
    print(json.dumps(reply), flush=True)
