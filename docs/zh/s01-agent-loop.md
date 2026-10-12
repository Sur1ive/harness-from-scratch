# s01 · Agent 循环

> 代码：[`agents/s01_agent_loop.py`](../../agents/s01_agent_loop.py) · 下一章：[s02 工具 →](s02-tools.md)

## 问题

语言模型本质上是一个"文本进、文本出"的函数。它跑不了 `ls`，打不开文件，
也不知道自己写的代码能不能编译。你让它"修好挂掉的测试"，得到的只是一个自信的猜测。

## 思路

让模型**提出**要做的动作，由程序**执行**，再把结果**喂回去**。如此往复，直到模型不再提要求。

```
messages = [用户请求]
循环:
    reply = 模型(messages, tools)
    追加 reply
    如果 reply 没有工具调用: 返回 reply 的文本
    对每个工具调用: 执行它，追加结果
```

跑这个循环的程序，就叫 *harness*。后面所有章节，都是往这个循环上挂东西。

## 代码

三个部分。

**1. 一份给模型看的工具说明。** 就是名字、一句描述，加上参数的 JSON Schema：

```python
TOOLS = [{
    "name": "bash",
    "description": "Run a shell command in the working directory. Returns stdout and stderr.",
    "parameters": {"type": "object",
                   "properties": {"command": {"type": "string"}},
                   "required": ["command"]},
}]
```

**2. 工具本身**，就是普通的 Python。注意超时和输出截断：harness 得扛得住 `yes` 和 `cat huge.log`。

```python
def run_bash(command):
    r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=120)
    return ((r.stdout + r.stderr).strip() or f"(no output, exit code {r.returncode})")[:50_000]
```

**3. 循环：**

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

有两个细节比看上去重要：

- **每个工具调用必须恰好有一个结果**，用调用的 `id` 对应起来。OpenAI 风格和 Anthropic 的 API
  都会拒绝"有调用没结果"的对话。这就是 `llm.heal()` 存在的原因：Ctrl-C 之后，它负责把缺失的结果补上。
- **`messages` 就是 agent 的全部记忆。** 模型是无状态的，每次调用它看到的就是这个列表。
  本教程后面的大部分内容，都在讲怎么管理这个列表里放什么。

## 关于 `llm.py`

`llm.chat(system, messages, tools)` 把线协议藏了起来。各章节统一使用一种中立的消息格式：

```python
{"role": "user",      "content": "..."}
{"role": "assistant", "content": "...", "tool_calls": [{"id", "name", "args"}]}
{"role": "tool",      "id": "...", "name": "bash", "content": "..."}
```

`llm.py` 负责把它翻译成 OpenAI 兼容的 `/chat/completions`（DeepSeek、通义千问、Kimi、智谱、Ollama……）
或 Anthropic 的 `/v1/messages`。这两个翻译函数各约 40 行，值得一读，能清楚看到两种 API 的差异。
比如 Anthropic 要求同一轮的所有工具结果放进**同一条** user 消息里。

## 运行

```bash
python agents/s01_agent_loop.py                     # 离线演示
DEEPSEEK_API_KEY=sk-... python agents/s01_agent_loop.py
```

试试："这个目录下有几个 Python 文件，最大的是哪个？"

## 真实的 harness

Claude Code、Codex 等跑的都是这个循环。它们额外加了流式输出、并行执行工具、重试，以及接下来的九章。

## 练习

1. 加一个 `max_rounds` 上限，防止糊涂的模型无限循环（s05 里有答案，先自己试试）。
2. 打印每个请求总共调用了几次模型。问个难题，看看这个数字。
3. 去掉 `[:50_000]` 截断，然后 `cat` 一个大文件。下一次请求会发生什么？
