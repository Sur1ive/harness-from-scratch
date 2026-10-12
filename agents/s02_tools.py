#!/usr/bin/env python3
"""
s02 - Tools
===========

The loop from s01 does not change. What changes: instead of one hard-wired
shell, we keep a table   tool name -> (schema the model sees, Python handler).

Adding a tool is now two lines, and the loop just looks up the handler.

Why not do everything through bash? You *can*, but dedicated tools are:
  - safer      (paths are checked to stay inside the workspace)
  - cheaper    (read_file returns line numbers + a slice, not a 5 MB cat)
  - reliable   (edit_file replaces one exact snippet - no sed escaping hell)

    python agents/s02_tools.py
"""

import os
import re
import subprocess
from pathlib import Path

from llm import from_env, last_tool_output, repl, show_call, show_note, show_output, tool, turn


def system_prompt():
    return (f"You are a coding agent working in {os.getcwd()}. "
            "Prefer read_file/edit_file/grep/glob over bash for files. Read a file before editing it. Be brief.")


# -- tool handlers -----------------------------------------------------------

def safe_path(p):
    """Resolve p inside the working directory; refuse to escape it."""
    root = Path.cwd().resolve()
    path = (root / p).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"path escapes the workspace: {p}")
    return path


def run_bash(command):
    try:
        r = subprocess.run(command, shell=True, cwd=os.getcwd(), capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return "Error: command timed out after 120s"
    return ((r.stdout + r.stderr).strip() or f"(no output, exit code {r.returncode})")[:50_000]


def read_file(path, offset=1, limit=400):
    lines = safe_path(path).read_text(errors="replace").splitlines()
    start = max(int(offset), 1)
    chunk = lines[start - 1:start - 1 + int(limit)]
    body = "\n".join(f"{i:>5}  {line}" for i, line in enumerate(chunk, start))
    rest = len(lines) - (start - 1 + len(chunk))
    return body + (f"\n... ({rest} more lines, use offset={start + len(chunk)})" if rest > 0 else "") or "(empty file)"


def write_file(path, content):
    p = safe_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"wrote {len(content)} chars to {path}"


def edit_file(path, old, new):
    p = safe_path(path)
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        return f"Error: `old` must appear exactly once in {path}, found {count} times. Add more context."
    p.write_text(text.replace(old, new, 1))
    return f"edited {path}"


def glob_files(pattern):
    root = Path.cwd()
    hits = sorted(str(p.relative_to(root)) for p in root.glob(pattern) if ".git" not in p.parts)
    return "\n".join(hits[:200]) or "(no matches)"


def grep(pattern, path=".", glob="**/*"):
    rx = re.compile(pattern)
    base = safe_path(path)
    files = [base] if base.is_file() else (p for p in base.glob(glob) if p.is_file() and ".git" not in p.parts)
    hits = []
    for f in files:
        try:
            for n, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{f.relative_to(Path.cwd())}:{n}: {line.strip()[:200]}")
        except OSError:
            continue
        if len(hits) >= 100:
            break
    return "\n".join(hits) or "(no matches)"


# -- the tool table: what the model sees + what we run ------------------------

def schema(name, description, required=(), **props):
    return {"name": name, "description": description,
            "parameters": {"type": "object", "required": list(required),
                           "properties": {k: {"type": t, "description": d} for k, (t, d) in props.items()}}}


TOOLS = [
    schema("bash", "Run a shell command in the working directory.", ["command"],
           command=("string", "The command to run")),
    schema("read_file", "Read a text file with line numbers.", ["path"],
           path=("string", "Relative path"), offset=("integer", "First line (1-based)"),
           limit=("integer", "Max lines to return")),
    schema("write_file", "Create or overwrite a file.", ["path", "content"],
           path=("string", "Relative path"), content=("string", "Full file content")),
    schema("edit_file", "Replace one exact, unique snippet in a file.", ["path", "old", "new"],
           path=("string", "Relative path"), old=("string", "Exact text to find"),
           new=("string", "Replacement text")),
    schema("glob", "List files matching a glob pattern, e.g. **/*.py", ["pattern"],
           pattern=("string", "Glob pattern")),
    schema("grep", "Search file contents with a regex.", ["pattern"],
           pattern=("string", "Python regex"), path=("string", "File or folder (default .)"),
           glob=("string", "File filter inside the folder (default **/*)")),
]

HANDLERS = {
    "bash": run_bash,
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "glob": glob_files,
    "grep": grep,
}


def run_tool(name, args):
    handler = HANDLERS.get(name)
    if handler is None:
        return f"Error: unknown tool {name}"
    try:
        return str(handler(**args))
    except Exception as e:  # tool errors go back to the model, not up the stack
        return f"Error: {type(e).__name__}: {e}"


# -- the loop: identical to s01, except it dispatches through the table -------

def agent_loop(messages):
    while True:
        reply = llm.chat(system_prompt(), messages, TOOLS)
        messages.append(reply)
        if not reply["tool_calls"]:
            return reply["content"]
        show_note(reply["content"])
        for call in reply["tool_calls"]:
            show_call(call["name"], call["args"])
            output = run_tool(call["name"], call["args"])
            show_output(output)
            messages.append({"role": "tool", "id": call["id"], "name": call["name"], "content": output})


DEMO = [
    ("Write fizzbuzz.py for 1..15, run it, then make it print 'Fizz Buzz' with a space.", [
        turn(tool("write_file", path="fizzbuzz.py", content=(
            "for i in range(1, 16):\n"
            "    print('FizzBuzz' if i % 15 == 0 else 'Fizz' if i % 3 == 0 else 'Buzz' if i % 5 == 0 else i)\n"))),
        turn(tool("bash", command="python3 fizzbuzz.py | tail -3")),
        turn(tool("edit_file", path="fizzbuzz.py", old="'FizzBuzz'", new="'Fizz Buzz'")),
        turn(tool("grep", pattern="Fizz Buzz", path="fizzbuzz.py"), tool("bash", command="python3 fizzbuzz.py | tail -1")),
        lambda msgs: turn(f"Done. The last line now prints: `{last_tool_output(msgs)}`"),
    ]),
]

if __name__ == "__main__":
    llm = from_env()
    repl(llm, agent_loop, DEMO, banner="s02 · tools")
