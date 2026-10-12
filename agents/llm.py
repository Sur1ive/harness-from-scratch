"""
llm.py - the only "infrastructure" every chapter shares.

It does three boring jobs so the chapters can stay about the harness:

  1. Talk to a model. One neutral message format, two wire formats:
       - OpenAI-compatible /chat/completions  (DeepSeek, Kimi, Qwen, GLM,
         OpenRouter, Ollama, OpenAI, ...)
       - Anthropic /v1/messages               (Claude)
  2. Fake a model. `MockLLM` replays a script, so every chapter runs
     offline with no API key - and the tests use it too.
  3. A tiny REPL + pretty printing.

Standard library only. No pip install.

The neutral message format used everywhere in this repo:

  {"role": "user",      "content": "text"}
  {"role": "assistant", "content": "text", "tool_calls": [{"id", "name", "args"}]}
  {"role": "tool",      "id": "<tool call id>", "name": "bash", "content": "output"}

Tools are described once, provider-neutral:

  {"name": "bash", "description": "...", "parameters": {<JSON schema>}}
"""

import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Provider presets. Anything OpenAI-compatible is one line here.
# ---------------------------------------------------------------------------

PRESETS = {
    #  name         wire         base url                                              key env var           default model
    "anthropic": ("anthropic", "https://api.anthropic.com", "ANTHROPIC_API_KEY", "claude-opus-5-5"),
    "deepseek": ("openai", "https://api.deepseek.com", "DEEPSEEK_API_KEY", "deepseek-chat"),
    "qwen": ("openai", "https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY", "qwen-plus"),
    "kimi": ("openai", "https://api.moonshot.cn/v1", "MOONSHOT_API_KEY", None),
    "glm": ("openai", "https://open.bigmodel.cn/api/paas/v4", "ZHIPUAI_API_KEY", None),
    "siliconflow": ("openai", "https://api.siliconflow.cn/v1", "SILICONFLOW_API_KEY", None),
    "doubao": ("openai", "https://ark.cn-beijing.volces.com/api/v3", "ARK_API_KEY", None),
    "gemini": ("openai", "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY", None),
    "openrouter": ("openai", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", None),
    "openai": ("openai", "https://api.openai.com/v1", "OPENAI_API_KEY", None),
    "ollama": ("openai", "http://localhost:11434/v1", None, None),
}


class LLMError(RuntimeError):
    pass


def _post(url, headers, body, retries=3):
    """POST JSON, retry on 429/5xx/network errors with exponential backoff."""
    data = json.dumps(body).encode()
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers={"content-type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:2000]
            if e.code in (429, 500, 502, 503, 504, 529) and attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise LLMError(f"HTTP {e.code} from {url}: {detail}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise LLMError(f"cannot reach {url}: {e}") from None


def _parse_args(raw):
    """Tool-call arguments arrive as a JSON string (OpenAI) - parse defensively."""
    if isinstance(raw, dict):
        return raw
    try:
        args = json.loads(raw or "{}")
        return args if isinstance(args, dict) else {"_invalid": raw}
    except json.JSONDecodeError:
        return {"_invalid": raw}


# ---------------------------------------------------------------------------
# OpenAI-compatible wire format
# ---------------------------------------------------------------------------

class OpenAICompatible:
    def __init__(self, model, base_url, api_key=None, max_tokens=8192):
        self.model, self.base_url, self.api_key, self.max_tokens = model, base_url.rstrip("/"), api_key, max_tokens
        self.name = f"{model} @ {self.base_url}"

    def to_wire(self, system, messages):
        out = [{"role": "system", "content": system}] if system else []
        for m in messages:
            if m["role"] == "user":
                out.append({"role": "user", "content": m["content"]})
            elif m["role"] == "assistant":
                msg = {"role": "assistant", "content": m.get("content") or (None if m.get("tool_calls") else "")}
                if m.get("tool_calls"):
                    msg["tool_calls"] = [
                        {"id": c["id"], "type": "function",
                         "function": {"name": c["name"], "arguments": json.dumps(c["args"], ensure_ascii=False)}}
                        for c in m["tool_calls"]]
                # Thinking models (DeepSeek, Kimi, ...) want their reasoning back
                # within the same tool-use turn.
                if (m.get("raw") or {}).get("reasoning_content"):
                    msg["reasoning_content"] = m["raw"]["reasoning_content"]
                out.append(msg)
            elif m["role"] == "tool":
                out.append({"role": "tool", "tool_call_id": m["id"], "content": m["content"]})
        return out

    def chat(self, system, messages, tools=()):
        body = {"model": self.model, "messages": self.to_wire(system, messages), "max_tokens": self.max_tokens}
        if tools:
            body["tools"] = [{"type": "function", "function": t} for t in tools]
        headers = {"authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        resp = _post(self.base_url + "/chat/completions", headers, body)
        choice = resp["choices"][0]
        msg = choice["message"]
        calls = [{"id": c["id"], "name": c["function"]["name"], "args": _parse_args(c["function"].get("arguments"))}
                 for c in msg.get("tool_calls") or []]
        stop = {"length": "max_tokens", "content_filter": "refusal"}.get(choice.get("finish_reason"), "end")
        return {"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls,
                "stop": "tool_use" if calls else stop, "raw": msg}


# ---------------------------------------------------------------------------
# Anthropic Messages wire format
# ---------------------------------------------------------------------------

class Anthropic:
    def __init__(self, model, base_url, api_key, max_tokens=16000):
        self.model, self.base_url, self.api_key, self.max_tokens = model, base_url.rstrip("/"), api_key, max_tokens
        self.name = f"{model} @ {self.base_url}"

    @staticmethod
    def to_wire(messages):
        out = []

        def push(role, blocks):
            # The API wants user/assistant to alternate: merge same-role neighbours.
            if out and out[-1]["role"] == role:
                out[-1]["content"].extend(blocks)
            else:
                out.append({"role": role, "content": list(blocks)})

        for m in messages:
            if m["role"] == "user":
                push("user", [{"type": "text", "text": m["content"]}])
            elif m["role"] == "assistant":
                if m.get("raw"):
                    # Send back exactly what the model produced (thinking blocks
                    # included). History is append-only; we never rewrite it.
                    push("assistant", m["raw"])
                    continue
                blocks = [{"type": "text", "text": m["content"]}] if m.get("content") else []
                blocks += [{"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["args"]}
                           for c in m.get("tool_calls") or []]
                push("assistant", blocks or [{"type": "text", "text": "(no content)"}])
            elif m["role"] == "tool":
                push("user", [{"type": "tool_result", "tool_use_id": m["id"], "content": m["content"]}])
        return out

    def chat(self, system, messages, tools=()):
        body = {"model": self.model, "max_tokens": self.max_tokens, "messages": self.to_wire(messages)}
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
                             for t in tools]
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        resp = _post(self.base_url + "/v1/messages", headers, body)
        blocks = resp.get("content") or []
        text = "".join(b.get("text", "") for b in blocks if b["type"] == "text")
        calls = [{"id": b["id"], "name": b["name"], "args": b.get("input") or {}}
                 for b in blocks if b["type"] == "tool_use"]
        stop = {"tool_use": "tool_use", "max_tokens": "max_tokens", "refusal": "refusal"}.get(resp.get("stop_reason"), "end")
        if stop == "refusal" and not text:
            text = "[the model declined this request]"
        return {"role": "assistant", "content": text, "tool_calls": calls, "stop": stop, "raw": blocks}


# ---------------------------------------------------------------------------
# MockLLM - a scripted "model" for offline demos and tests
# ---------------------------------------------------------------------------

def tool(name, /, **args):
    """A tool call inside a mock script: tool("bash", command="ls")."""
    return {"name": name, "args": args}


def turn(*items):
    """One scripted assistant turn: turn("some text", tool(...), tool(...))."""
    text = "\n".join(i for i in items if isinstance(i, str))
    calls = [i for i in items if isinstance(i, dict)]
    return {"content": text, "tool_calls": calls}


class MockLLM:
    """Replays a script of turns. A turn may also be a function(messages) -> turn,
    so the fake model can "read" real tool output and react to it."""

    name = "mock (scripted demo, no API key needed)"

    def __init__(self, script=()):
        self.script = list(script)
        self.calls = 0
        self.seen = []  # every (system, messages, tools) we were called with - handy in tests

    def load(self, script):
        self.script = list(script)

    def chat(self, system, messages, tools=()):
        self.seen.append((system, [dict(m) for m in messages], [t["name"] for t in tools]))
        step = self.script.pop(0) if self.script else turn("(demo script finished)")
        if callable(step):
            step = step(messages)
        self.calls += 1
        calls = [{"id": f"call_{self.calls}_{i}", "name": c["name"], "args": c["args"]}
                 for i, c in enumerate(step.get("tool_calls", []))]
        return {"role": "assistant", "content": step.get("content", ""), "tool_calls": calls,
                "stop": "tool_use" if calls else "end", "raw": None}


def last_tool_output(messages):
    """For mock scripts: the most recent tool result, so a scripted turn can quote it."""
    for m in reversed(messages):
        if m["role"] == "tool":
            return m["content"]
    return ""


# ---------------------------------------------------------------------------
# Pick a provider from the environment
# ---------------------------------------------------------------------------

def from_env():
    """
    HARNESS_PROVIDER  anthropic | deepseek | qwen | kimi | glm | siliconflow | doubao | gemini |
                      openrouter | openai | ollama | mock
    HARNESS_MODEL     model id (required for presets without a default)
    HARNESS_API_KEY   overrides the preset's key variable
    HARNESS_BASE_URL  any OpenAI-compatible endpoint (vLLM, LM Studio, one-api, ...)

    With nothing set we look for a known API key, and fall back to the
    offline mock so `python sXX_*.py` always does *something*.
    """
    name = os.getenv("HARNESS_PROVIDER", "").lower()
    if not name:
        if os.getenv("HARNESS_BASE_URL"):
            name = "openai"
        else:
            name = next((p for p, (_, _, key, _) in PRESETS.items() if key and os.getenv(key)), "mock")
    if name == "mock":
        return MockLLM()
    if name not in PRESETS:
        sys.exit(f"Unknown HARNESS_PROVIDER={name!r}. Choose one of: {', '.join(PRESETS)}, mock")
    wire, base_url, key_env, default_model = PRESETS[name]
    base_url = os.getenv("HARNESS_BASE_URL", base_url)
    api_key = os.getenv("HARNESS_API_KEY") or (os.getenv(key_env) if key_env else None)
    model = os.getenv("HARNESS_MODEL", default_model)
    if not model:
        sys.exit(f"Provider {name!r} needs a model: export HARNESS_MODEL=<model id>")
    if key_env and not api_key and not os.getenv("HARNESS_BASE_URL"):
        sys.exit(f"Provider {name!r} needs an API key: export {key_env}=...")
    if wire == "anthropic":
        return Anthropic(model, base_url, api_key)
    return OpenAICompatible(model, base_url, api_key)


# ---------------------------------------------------------------------------
# Terminal UI
# ---------------------------------------------------------------------------

_COLOR = sys.stdout.isatty() and os.getenv("NO_COLOR") is None


def _c(code, s):
    return f"\033[{code}m{s}\033[0m" if _COLOR else s


def dim(s): return _c("2", s)
def cyan(s): return _c("36", s)
def yellow(s): return _c("33", s)
def red(s): return _c("31", s)
def bold(s): return _c("1", s)
def magenta(s): return _c("35", s)


def show_call(name, args, indent=2):
    def brief(v):
        v = json.dumps(v, ensure_ascii=False)
        return v if len(v) <= 80 else v[:79] + "…"
    print(cyan(" " * indent + f"⏺ {name}({', '.join(f'{k}={brief(v)}' for k, v in args.items())})"))


def show_output(text, lines=6, indent=4):
    rows = str(text).splitlines() or [""]
    for row in rows[:lines]:
        print(dim(" " * indent + f"│ {row[:160]}"))
    if len(rows) > lines:
        print(dim(" " * indent + f"│ … +{len(rows) - lines} lines"))


def show_note(text, indent=2):
    """Text the model writes alongside its tool calls ("Let me check...")."""
    if text:
        print(" " * indent + text)


def show_reply(text):
    if text:
        print(f"\n{text}\n")


def repl(llm, agent, demo=(), banner="", setup=None):
    """
    agent(messages) runs one user turn to completion.
    demo is a list of (prompt, script) pairs, used when llm is MockLLM;
    setup() prepares the demo's scratch folder.
    """
    print(bold(banner) if banner else "", dim(f"[model: {llm.name}]"))
    history = []
    if isinstance(llm, MockLLM):
        workdir = tempfile.mkdtemp(prefix="harness-demo-")
        os.chdir(workdir)
        print(yellow("No API key found - running the offline demo with a scripted model."))
        print(yellow("Tools are real: they run in a scratch folder ") + dim(workdir))
        print(yellow("Set e.g. DEEPSEEK_API_KEY or ANTHROPIC_API_KEY to talk to a real model.\n"))
        if setup:
            setup()
        for prompt, script in demo:
            llm.load(script)
            print(bold(f"you › {prompt}"))
            history.append({"role": "user", "content": prompt})
            show_reply(agent(history))
        return history
    while True:
        try:
            prompt = input(bold("you › ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return history
        if prompt in ("/exit", "/quit", "q", "exit"):
            return history
        if prompt == "/clear":
            history.clear()
            print(dim("history cleared"))
            continue
        if not prompt:
            continue
        history.append({"role": "user", "content": prompt})
        try:
            show_reply(agent(history))
        except LLMError as e:
            print(red(f"model error: {e}"))
            heal(history)
        except KeyboardInterrupt:
            print(red("\ninterrupted"))
            heal(history)


def heal(history):
    """After an error or Ctrl-C mid-turn, every tool call still needs a result,
    or the next request is rejected. Answer the dangling ones."""
    answered = {m["id"] for m in history if m["role"] == "tool"}
    for m in list(history):
        for c in m.get("tool_calls") or []:
            if c["id"] not in answered:
                history.append({"role": "tool", "id": c["id"], "name": c["name"], "content": "(interrupted)"})
