#!/usr/bin/env python3
"""
harness.py - the finished harness, for daily use
================================================

s10 already contains every mechanism: loop, tools, permissions, todos,
subagents, skills, compaction, hooks, memory, MCP. This file only wraps it
in a friendlier front end:

    python agents/harness.py                 interactive session
    python agents/harness.py --resume        continue the last session in this folder
    python agents/harness.py -p "fix the failing test"   one-shot, prints the answer

Slash commands: /help /tools /skills /todos /memory /mode /compact /clear /exit

Sessions are saved after every turn to .harness/sessions/, so a crash or a
closed terminal never loses work.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import s10_mcp as core
from llm import LLMError, MockLLM, bold, dim, from_env, heal, red, repl, show_reply, yellow

SESSIONS = Path(".harness/sessions")

HELP = """\
  /tools            list the tools the model can use
  /skills           list available skills
  /todos            show the model's todo list
  /memory           show what is loaded from AGENTS.md / CLAUDE.md / memory
  /mode [ask|auto|plan]   show or change the permission mode
  /compact          summarize the conversation now
  /clear            start a fresh conversation
  /exit             quit (the session stays saved)"""


def save(history, path):
    if not history:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, ensure_ascii=False, indent=1, default=str))


def load_latest():
    files = sorted(SESSIONS.glob("*.json"))
    if not files:
        return [], None
    return json.loads(files[-1].read_text()), files[-1]


def slash(cmd, history):
    """Handle a /command. Returns False to quit."""
    name, _, arg = cmd.partition(" ")
    if name in ("/exit", "/quit"):
        return False
    if name == "/help":
        print(HELP)
    elif name == "/tools":
        core.connect_mcp()
        for t in core.TOOLS:
            print(f"  {bold(t['name'])}  {dim(t['description'][:90])}")
    elif name == "/skills":
        for n, s in core.find_skills().items():
            print(f"  {bold(n)}  {dim(s['description'][:90])}")
    elif name == "/todos":
        print(core.TODOS.render())
    elif name == "/memory":
        print(core.project_memory().strip() or "(no AGENTS.md, CLAUDE.md or .harness/memory.md here)")
    elif name == "/mode":
        if arg.strip() in ("ask", "auto", "plan"):
            core.MODE = arg.strip()
        print(f"permission mode: {core.MODE}")
    elif name == "/compact":
        if history:
            path = core.full_compact(history)
            print(dim(f"compacted; transcript saved to {path}"))
    elif name == "/clear":
        history.clear()
        core.TODOS.items = []
        print(dim("fresh conversation"))
    else:
        print(red(f"unknown command {name} - try /help"))
    return True


def main():
    ap = argparse.ArgumentParser(description="A small, complete coding-agent harness.")
    ap.add_argument("-p", "--prompt", help="run one prompt non-interactively and print the answer")
    ap.add_argument("--resume", action="store_true", help="continue the most recent session in this folder")
    opts = ap.parse_args()

    core.llm = from_env()
    if isinstance(core.llm, MockLLM):  # no API key: show the s10 demo instead
        repl(core.llm, core.agent_loop, core.DEMO, banner="harness (offline demo)", setup=core.demo_setup)
        return

    history, path = load_latest() if opts.resume else ([], None)
    path = path or SESSIONS / f"{time.strftime('%Y%m%d-%H%M%S')}.json"

    if opts.prompt:
        history.append({"role": "user", "content": opts.prompt})
        try:
            print(core.agent_loop(history))
        finally:
            save(history, path)
        return

    print(bold("harness") + dim(f"  [model: {core.llm.name}]  [permissions: {core.MODE}]  /help for commands"))
    if history:
        print(dim(f"resumed {path} ({len(history)} messages)"))
    while True:
        try:
            prompt = input(bold("you › ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not prompt:
            continue
        if prompt.startswith("/"):
            if not slash(prompt, history):
                break
            save(history, path)
            continue
        history.append({"role": "user", "content": prompt})
        try:
            show_reply(core.agent_loop(history))
        except LLMError as e:
            print(red(f"model error: {e}"))
            heal(history)
        except KeyboardInterrupt:
            print(yellow("\ninterrupted"))
            heal(history)
        save(history, path)
    print(dim(f"session saved: {path}  (resume with --resume)"))


if __name__ == "__main__":
    sys.exit(main())
