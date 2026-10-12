#!/usr/bin/env python3
"""
s01 - The Agent Loop
====================

The whole secret of every coding agent, in one sentence:

    call the model -> if it asked for tools, run them, append the results,
    and call the model again -> stop when it answers without asking for tools.

That `while` loop is the harness. Everything in s02-s10 is something we
bolt onto it. Here we give the model exactly one tool: a shell.

    python agents/s01_agent_loop.py
"""

import os
import subprocess

from llm import from_env, last_tool_output, repl, show_call, show_note, show_output, tool, turn


def system_prompt():
    return f"You are a coding agent. Your working directory is {os.getcwd()}. Use bash to inspect and change things. Be brief."


TOOLS = [{
    "name": "bash",
    "description": "Run a shell command in the working directory. Returns stdout and stderr.",
    "parameters": {
        "type": "object",
        "properties": {"command": {"type": "string", "description": "The command to run"}},
        "required": ["command"],
    },
}]


def run_bash(command):
    try:
        r = subprocess.run(command, shell=True, cwd=os.getcwd(), capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return "Error: command timed out after 120s"
    out = (r.stdout + r.stderr).strip() or f"(no output, exit code {r.returncode})"
    return out[:50_000]


def agent_loop(messages):
    while True:
        reply = llm.chat(system_prompt(), messages, TOOLS)  # 1. ask the model
        messages.append(reply)
        if not reply["tool_calls"]:  # 2. no tools requested -> done
            return reply["content"]
        show_note(reply["content"])
        for call in reply["tool_calls"]:  # 3. run every requested tool
            show_call(call["name"], call["args"])
            output = run_bash(call["args"].get("command", ""))
            show_output(output)
            messages.append({"role": "tool", "id": call["id"], "name": call["name"], "content": output})
        # 4. loop: the model now sees the results and decides what's next


# Offline demo: a scripted "model" that drives real tools.
DEMO = [
    ("Which Python version is installed here? Then create notes.txt containing 'hello harness'.", [
        turn("Let me check.", tool("bash", command="python3 --version || python --version")),
        lambda msgs: turn(f"It's {last_tool_output(msgs)}. Now the file:",
                          tool("bash", command="echo 'hello harness' > notes.txt && cat notes.txt")),
        turn("Done - notes.txt now contains `hello harness`."),
    ]),
]

if __name__ == "__main__":
    llm = from_env()
    repl(llm, agent_loop, DEMO, banner="s01 · the agent loop")
