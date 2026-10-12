# s01 · The agent loop

> Code: [`agents/s01_agent_loop.py`](../../agents/s01_agent_loop.py) · Next: [s02 Tools →](s02-tools.md)

## The problem

A language model is a function from text to text. It cannot run `ls`, open a
file, or check whether its code compiles. Ask it to "fix the failing test"
and you get a confident guess.

## The idea

Let the model **ask** for actions, have the program **perform** them, and
**feed the results back**. Repeat until the model stops asking.

```
messages = [user request]
loop:
    reply = model(messages, tools)
    append reply
    if reply has no tool calls: return reply text
    for each tool call: run it, append the result
```

The program running this loop is the *harness*. Everything in later
chapters is something attached to this loop.

## The code

Three pieces.

**1. A tool description** the model can read. It's just a name, a sentence
and a JSON schema for the arguments:

```python
TOOLS = [{
    "name": "bash",
    "description": "Run a shell command in the working directory. Returns stdout and stderr.",
    "parameters": {"type": "object",
                   "properties": {"command": {"type": "string"}},
                   "required": ["command"]},
}]
```

**2. The tool itself**, which is plain Python. Note the timeout and the output cap.
A harness has to survive `yes` and `cat huge.log`.

```python
def run_bash(command):
    r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=120)
    return ((r.stdout + r.stderr).strip() or f"(no output, exit code {r.returncode})")[:50_000]
```

**3. The loop:**

```python
def agent_loop(messages):
    while True:
        reply = llm.chat(system_prompt(), messages, TOOLS)
        messages.append(reply)
        if not reply["tool_calls"]:
            return reply["content"]
        for call in reply["tool_calls"]:
            output = run_bash(call["args"].get("command", ""))
            messages.append({"role": "tool", "id": call["id"], "name": call["name"], "content": output})
```

Two details matter more than they look:

- **Every tool call gets exactly one result**, tagged with the call's `id`.
  Both OpenAI-style and Anthropic APIs reject a conversation where a call
  has no answer. This is why `llm.heal()` exists: after a Ctrl-C it fills
  in the missing results.
- **`messages` is the agent's entire memory.** The model is stateless and
  sees exactly that list on every call. Most of what follows in this tutorial
  is about managing what goes into it.

## About `llm.py`

`llm.chat(system, messages, tools)` hides the wire format. The chapters use
one neutral message shape:

```python
{"role": "user",      "content": "..."}
{"role": "assistant", "content": "...", "tool_calls": [{"id", "name", "args"}]}
{"role": "tool",      "id": "...", "name": "bash", "content": "..."}
```

`llm.py` translates that into OpenAI-compatible `/chat/completions` (DeepSeek,
Qwen, Kimi, GLM, Ollama, ...) or Anthropic `/v1/messages`. The two
translators are worth a read: they are ~40 lines each and show exactly how
the two APIs differ. For example, Anthropic wants all tool results of one
turn inside a **single** user message.

## Run it

```bash
python agents/s01_agent_loop.py                     # offline demo
DEEPSEEK_API_KEY=sk-... python agents/s01_agent_loop.py
```

Try: *"how many Python files are in this folder, and which is the largest?"*

## In real harnesses

Claude Code, Codex and the rest run this same loop. What they add is
streaming, parallel tool execution, retries, and the nine chapters that follow.

## Exercises

1. Add a `max_rounds` limit so a confused model can't loop forever. (s05 does this; try it yourself first.)
2. Print how many model calls a request took. Ask for something hard and watch the number.
3. Remove the `[:50_000]` cap and `cat` a big file. What happens to the next request?
