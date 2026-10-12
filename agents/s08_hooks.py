#!/usr/bin/env python3
"""
s08 - Hooks: let the user's scripts steer the agent
===================================================

Prompts are suggestions; hooks are guarantees. A hook is a shell command
the *harness* runs at fixed points - the model cannot skip it.

    .harness/hooks.json
    {
      "PreToolUse":       [{"matcher": "write_file|edit_file", "command": "python3 guard.py"}],
      "PostToolUse":      [{"matcher": "write_file|edit_file", "command": "ruff check --fix ."}],
      "UserPromptSubmit": [{"command": "git status --short"}],
      "Stop":             [{"command": "pytest -q"}]
    }

The contract (same idea as Claude Code's hooks):
  - the event is sent to the hook as JSON on stdin
  - exit 0  -> fine; anything printed on stdout is shown to the model
  - exit 2  -> BLOCK: PreToolUse skips the tool, PostToolUse/Stop send
               stderr back to the model as feedback it must address
  - other   -> hook error, shown to the user, ignored

Ten lines of glue, and "always run the linter" / "never touch .env" /
"don't stop until tests pass" stop being things you hope the model remembers.

    python agents/s08_hooks.py
"""

import json
import os
import re
import subprocess
import time
from pathlib import Path

from llm import (MockLLM, dim, from_env, magenta, red, repl, show_call, show_note, show_output, tool, turn, yellow)


def system_prompt():
    return (f"You are a coding agent working in {os.getcwd()}. "
            "Prefer read_file/edit_file/grep/glob over bash for files. Read a file before editing it. "
            "If a tool call is denied, follow the user's feedback; do not retry the same call. "
            "For any task with 3+ steps, plan it with todo_write first, keep exactly one item in_progress, "
            "and mark items completed as you go. "
            "Delegate broad searches and self-contained side tasks to a subagent with the task tool. "
            "When a task matches a skill below, load_skill it first and follow it. Be brief."
            + skills_index())


SUBAGENT_PROMPT = ("You are a subagent working in {cwd} on behalf of a parent agent. Do the task, then reply with "
                   "a short, concrete summary (file paths, line numbers, results). The summary is all the parent sees.")


# -- tools (from s02) -----------------------------------------------------------

def safe_path(p):
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

HANDLERS = {"bash": run_bash, "read_file": read_file, "write_file": write_file,
            "edit_file": edit_file, "glob": glob_files, "grep": grep}


# -- todo list (from s04) -------------------------------------------------------

class Todos:
    MARKS = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}

    def __init__(self):
        self.items = []

    def write(self, items):
        clean = []
        for item in items:
            content, status = str(item.get("content", "")).strip(), item.get("status", "pending")
            if not content:
                raise ValueError("every todo needs content")
            if status not in self.MARKS:
                raise ValueError(f"bad status {status!r}; use pending | in_progress | completed")
            clean.append({"content": content, "status": status})
        if sum(i["status"] == "in_progress" for i in clean) > 1:
            raise ValueError("only one item may be in_progress at a time")
        self.items = clean
        return self.render()

    def open_items(self):
        return [i for i in self.items if i["status"] != "completed"]

    def render(self):
        if not self.items:
            return "(no todos)"
        done = len(self.items) - len(self.open_items())
        rows = [f"{self.MARKS[i['status']]} {i['content']}" for i in self.items]
        return "\n".join(rows + [f"({done}/{len(self.items)} done)"])


TODOS = Todos()
NAG_AFTER = 3  # rounds without a todo update before we remind the model

TOOLS.append({
    "name": "todo_write",
    "description": "Replace your todo list. Use it to plan multi-step work and track progress.",
    "parameters": {"type": "object", "required": ["items"], "properties": {"items": {
        "type": "array", "items": {"type": "object", "required": ["content", "status"], "properties": {
            "content": {"type": "string"},
            "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]}}}}}},
})
HANDLERS["todo_write"] = TODOS.write


# -- subagents (from s05) ----------------------------------------------------------

TOOLS.append({
    "name": "task",
    "description": ("Run a subagent with a fresh, empty context on a self-contained task (search, investigate, "
                    "small change). It returns only its final summary, keeping your context clean."),
    "parameters": {"type": "object", "required": ["description", "prompt"], "properties": {
        "description": {"type": "string", "description": "3-5 word label"},
        "prompt": {"type": "string", "description": "Complete instructions; the subagent sees nothing else"}}},
})
SUB_TOOLS = [t for t in TOOLS if t["name"] not in ("task", "todo_write")]


def run_subagent(description, prompt):
    print(magenta(f"    ↳ subagent: {description}"))
    sub_messages = [{"role": "user", "content": prompt}]  # <- the whole trick: a fresh context
    system = SUBAGENT_PROMPT.format(cwd=os.getcwd())
    summary = agent_loop(sub_messages, tools=SUB_TOOLS, system=system, depth=1, max_rounds=30)
    print(magenta(f"    ↳ subagent done ({len(sub_messages)} messages discarded)"))
    return summary or "(the subagent returned no summary)"


HANDLERS["task"] = run_subagent


# -- skills (from s06) --------------------------------------------------------------

SKILL_DIRS = [  # first match wins, so project skills override the bundled examples
    Path(".harness/skills"), Path(".claude/skills"), Path(".agents/skills"),
    Path.home() / ".harness/skills",
    Path(__file__).resolve().parent.parent / "skills",
]


def parse_front_matter(text):
    meta = {}
    if text.startswith("---"):
        _, block, text = text.split("---", 2)
        for line in block.strip().splitlines():
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip().strip("\"'")
    return meta, text.strip()


def find_skills():
    skills = {}
    for folder in SKILL_DIRS:
        for f in sorted(folder.glob("*/SKILL.md")) if folder.is_dir() else []:
            meta, body = parse_front_matter(f.read_text())
            skills.setdefault(meta.get("name") or f.parent.name,
                              {"description": meta.get("description", ""), "body": body, "dir": f.parent})
    return skills


def skills_index():
    skills = find_skills()
    if not skills:
        return ""
    return "\n\nSkills (load with load_skill):\n" + "\n".join(
        f"- {name}: {s['description']}" for name, s in skills.items())


def load_skill(name):
    skill = find_skills().get(name)
    if not skill:
        return f"Error: no skill named {name!r}. Available: {', '.join(find_skills()) or 'none'}"
    return f"<skill name=\"{name}\" dir=\"{skill['dir']}\">\n{skill['body']}\n</skill>"


TOOLS.append({
    "name": "load_skill",
    "description": "Load the full instructions of a skill listed in the system prompt.",
    "parameters": {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}},
})
HANDLERS["load_skill"] = load_skill
SUB_TOOLS.append(TOOLS[-1])


# -- context compaction (from s07) --------------------------------------------------

COMPACT_AT = int(os.getenv("HARNESS_COMPACT_AT", "80000"))  # estimated tokens -> full summary
MICRO_AT = COMPACT_AT // 2  # estimated tokens -> clear old tool outputs
KEEP_RECENT = 3  # never clear the newest N tool results
compact_requested = False

SUMMARY_PROMPT = ("You are compressing a coding-agent session so work can continue in a fresh context. "
                  "Write a dense summary: the user's goals, decisions made, files created or changed (with paths), "
                  "commands that worked, errors hit and how they were solved, open todos, and the next step. "
                  "Keep exact names, paths and numbers. No preamble.")


def estimate_tokens(messages):
    """~4 characters per token. Crude, but the harness only needs a threshold."""
    chars = sum(len(m.get("content") or "") + len(json.dumps(m.get("tool_calls") or [])) for m in messages)
    return chars // 4


def micro_compact(messages):
    cleared = 0
    for m in [m for m in messages if m["role"] == "tool"][:-KEEP_RECENT]:
        if len(m["content"]) > 500 and not m["content"].startswith("[cleared"):
            m["content"] = f"[cleared: old {m['name']} output ({len(m['content'])} chars). Run the tool again if needed.]"
            cleared += 1
    return cleared


def full_compact(messages):
    folder = Path(".harness/transcripts")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    with path.open("w") as f:
        for m in messages:
            f.write(json.dumps({k: v for k, v in m.items() if k != "raw"}, ensure_ascii=False) + "\n")
    transcript = "\n\n".join(
        f"[{m['role']}{' ' + m['name'] if m['role'] == 'tool' else ''}] {m.get('content') or ''}"
        + "".join(f"\n  -> {c['name']}({json.dumps(c['args'], ensure_ascii=False)[:500]})" for c in m.get("tool_calls") or [])
        for m in messages)[-200_000:]
    summary = llm.chat(SUMMARY_PROMPT, [{"role": "user", "content": transcript}])["content"]
    last_request = next((m["content"] for m in reversed(messages)
                         if m["role"] == "user" and not m["content"].startswith("[compacted")), "")
    messages[:] = [{"role": "user", "content": (
        f"[compacted - full transcript saved at {path}]\n\nSummary of the session so far:\n{summary}\n\n"
        f"The user's latest request was:\n{last_request}\n\nContinue from here.")}]
    return path


def maybe_compact(messages):
    global compact_requested
    size = estimate_tokens(messages)
    if compact_requested or size > COMPACT_AT:
        compact_requested = False
        path = full_compact(messages)
        print(yellow(f"    ⟲ compacted ~{size} tokens -> ~{estimate_tokens(messages)} (transcript: {path})"))
    elif size > MICRO_AT:
        cleared = micro_compact(messages)
        if cleared:
            print(yellow(f"    ⟲ micro-compact: cleared {cleared} old tool outputs "
                         f"(~{size} -> ~{estimate_tokens(messages)} tokens)"))


def request_compact():
    global compact_requested
    compact_requested = True
    return "Compaction scheduled; the conversation will be summarized before your next step."


TOOLS.append({"name": "compact", "description": "Summarize the conversation so far to free up context.",
              "parameters": {"type": "object", "properties": {}}})
HANDLERS["compact"] = request_compact


# -- NEW in s08: hooks ---------------------------------------------------------------

HOOKS_FILE = Path(".harness/hooks.json")
MAX_STOP_BLOCKS = 3  # a Stop hook can send the model back to work, but not forever


def run_hooks(event, payload, target=""):
    """Run every hook for `event` whose matcher fits `target`.
    Returns (blocked, text): text is stdout context, or stderr feedback if blocked."""
    try:
        hooks = json.loads(HOOKS_FILE.read_text()).get(event, []) if HOOKS_FILE.exists() else []
    except (OSError, json.JSONDecodeError) as e:
        print(red(f"    hooks.json is invalid: {e}"))
        return False, ""
    notes = []
    for hook in hooks:
        matcher = hook.get("matcher", "")
        if matcher not in ("", "*") and not re.fullmatch(matcher, target):
            continue
        data = json.dumps({"event": event, "cwd": os.getcwd(), **payload}, ensure_ascii=False)
        try:
            r = subprocess.run(hook["command"], shell=True, input=data, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            print(red(f"    hook timed out: {hook['command']}"))
            continue
        print(dim(f"    ⚓ {event} hook `{hook['command']}` -> exit {r.returncode}"))
        if r.returncode == 2:
            return True, (r.stderr or r.stdout).strip() or f"blocked by {event} hook"
        if r.returncode != 0:
            print(red(f"    hook error: {r.stderr.strip()[:300]}"))
        elif r.stdout.strip():
            notes.append(r.stdout.strip())
    return False, "\n".join(notes)


# -- permission gate (from s03) -------------------------------------------------

# tools that never need approval (a subagent's own tool calls are still checked one by one)
READ_ONLY = {"read_file", "glob", "grep", "todo_write", "task", "load_skill", "compact"}
DENY_RULES = [  # checked against bash commands; a match is never allowed
    r"\bsudo\b",
    r"\brm\s+(-\w*\s+)*-\w*[rf]\w*\s+(/|~|\$HOME)(\s|/?$)",  # rm -rf / or ~
    r"\b(curl|wget)\b[^|]*\|\s*(ba|z)?sh\b",  # curl ... | sh
    r"\bmkfs\b|\bdd\s+if=|>\s*/dev/sd",
    r":\(\)\s*\{.*\};\s*:",  # fork bomb
]
MODE = os.getenv("HARNESS_PERMISSION", "ask")  # ask | auto | plan
always_allow = set()
demo_answers = []  # scripted human answers for the offline demo


def ask_human(name, args):
    if isinstance(llm, MockLLM):
        answer = demo_answers.pop(0) if demo_answers else "y"
        print(yellow(f"    allow {name}? [y/n/a/feedback] ") + answer)
        return answer
    try:
        return input(yellow(f"    allow {name}? [y]es / [n]o / [a]lways / or type feedback: ")).strip()
    except EOFError:
        return "n"


def check_permission(name, args):
    """None = go ahead. A string = the reason it was refused (sent to the model)."""
    if name == "bash":
        for rule in DENY_RULES:
            if re.search(rule, args.get("command", "")):
                return f"Denied by a safety rule ({rule}). Do not try to work around it."
    if name in READ_ONLY or MODE == "auto" or name in always_allow:
        return None
    if MODE == "plan":
        return "Denied: plan mode is read-only. Describe the change instead of making it."
    answer = ask_human(name, args)
    if answer.lower() in ("y", "yes", ""):
        return None
    if answer.lower() in ("a", "always"):
        always_allow.add(name)
        return None
    if answer.lower() in ("n", "no"):
        return "Denied by the user."
    return f"Denied by the user, who says: {answer}"


def run_tool(name, args):
    blocked, why = run_hooks("PreToolUse", {"tool": name, "args": args}, target=name)  # NEW in s08
    if blocked:
        return f"Blocked by a PreToolUse hook: {why}"
    refusal = check_permission(name, args)
    if refusal:
        return refusal
    handler = HANDLERS.get(name)
    if handler is None:
        return f"Error: unknown tool {name}"
    try:
        output = str(handler(**args))
    except Exception as e:
        output = f"Error: {type(e).__name__}: {e}"
    blocked, note = run_hooks("PostToolUse", {"tool": name, "args": args, "output": output}, target=name)
    if blocked:
        return f"{output}\n\n<hook-feedback>\n{note}\n</hook-feedback>"
    return f"{output}\n\n<hook-context>\n{note}\n</hook-context>" if note else output


def agent_loop(messages, tools=None, system=None, depth=0, max_rounds=200):
    tools = tools or TOOLS
    allowed = {t["name"] for t in tools}
    pad = 2 + 4 * depth  # indent subagent output
    rounds_since_todo = stop_blocks = 0
    if depth == 0:  # NEW in s08: UserPromptSubmit
        blocked, note = run_hooks("UserPromptSubmit", {"prompt": messages[-1]["content"]})
        if blocked:
            messages.pop()
            return f"(prompt blocked by hook: {note})"
        if note:
            messages[-1]["content"] += f"\n\n<hook-context>\n{note}\n</hook-context>"
    for _ in range(max_rounds):
        maybe_compact(messages)
        reply = llm.chat(system or system_prompt(), messages, tools)
        messages.append(reply)
        if not reply["tool_calls"]:
            if depth == 0 and stop_blocks < MAX_STOP_BLOCKS:  # NEW in s08: Stop
                blocked, why = run_hooks("Stop", {"reply": reply["content"]})
                if blocked:
                    stop_blocks += 1
                    show_note(reply["content"])
                    messages.append({"role": "user", "content": f"<hook-feedback>\nNot done yet: {why}\n</hook-feedback>"})
                    continue
            return reply["content"]
        show_note(reply["content"], indent=pad)
        for call in reply["tool_calls"]:
            show_call(call["name"], call["args"], indent=pad)
            if call["name"] in allowed:
                output = run_tool(call["name"], call["args"])
            else:
                output = f"Error: tool {call['name']} is not available here"
            show_output(output, indent=pad + 2)
            messages.append({"role": "tool", "id": call["id"], "name": call["name"], "content": output})
        used_todo = any(c["name"] == "todo_write" for c in reply["tool_calls"])
        rounds_since_todo = 0 if used_todo else rounds_since_todo + 1
        if depth == 0 and TODOS.open_items() and rounds_since_todo >= NAG_AFTER:
            reminder = "<reminder>You have open todos. Update your list with todo_write.</reminder>"
            messages[-1]["content"] += "\n\n" + reminder
            print(yellow(f"    {reminder}"))
            rounds_since_todo = 0
    return f"(stopped after {max_rounds} rounds) " + (messages[-1].get("content") or "")[:2000]


CHECK_SYNTAX = """import json, sys, py_compile
event = json.load(sys.stdin)
path = event["args"].get("path", "")
if path.endswith(".py"):
    try:
        py_compile.compile(path, doraise=True)
    except py_compile.PyCompileError as e:
        print(e.msg, file=sys.stderr)
        sys.exit(2)
"""

GUARD_ENV = """import json, sys
event = json.load(sys.stdin)
if event["args"].get("path", "").split("/")[-1].startswith(".env"):
    print("Never write .env files - secrets belong in the user's secret manager.", file=sys.stderr)
    sys.exit(2)
"""


def demo_setup():
    Path(".harness").mkdir()
    Path(".harness/check_syntax.py").write_text(CHECK_SYNTAX)
    Path(".harness/guard_env.py").write_text(GUARD_ENV)
    HOOKS_FILE.write_text(json.dumps({
        "PreToolUse": [{"matcher": "write_file|edit_file", "command": "python3 .harness/guard_env.py"}],
        "PostToolUse": [{"matcher": "write_file|edit_file", "command": "python3 .harness/check_syntax.py"}],
    }, indent=2))
    print(dim("demo hooks installed:\n" + HOOKS_FILE.read_text()) + "\n")


DEMO = [
    ("Write greet.py that greets the user by name from argv, and run it.", [
        turn(tool("write_file", path="greet.py", content="import sys\nprint(f'Hello, {sys.argv[1]}!'\n")),
        turn("The hook caught a missing parenthesis - fixing.",
             tool("edit_file", path="greet.py", old="{sys.argv[1]}!'", new="{sys.argv[1]}!')")),
        turn(tool("bash", command="python3 greet.py Ada")),
        turn("greet.py works: `python3 greet.py Ada` prints `Hello, Ada!`."),
    ]),
    ("Also save API_KEY=sk-123 into .env for me.", [
        turn(tool("write_file", path=".env", content="API_KEY=sk-123\n")),
        turn("A project hook forbids writing .env files, so I didn't. Export it in your shell instead:\n\n"
             "    export API_KEY=sk-123"),
    ]),
]

if __name__ == "__main__":
    llm = from_env()
    repl(llm, agent_loop, DEMO, banner=f"s08 · hooks (permissions: {MODE})", setup=demo_setup)
