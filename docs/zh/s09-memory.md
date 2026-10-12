# s09 · 记忆：AGENTS.md 和跨会话的笔记

> 代码：[`agents/s09_memory.py`](../../agents/s09_memory.py) · [← s08](s08-hooks.md) · 下一章：[s10 MCP →](s10-mcp.md)

## 问题

每个会话都从零开始。你又一次解释测试要用 `make test` 跑、staging 数据库在 5433 端口、你喜欢简单的 assert。
这些模型昨天都学会了，进程一退出，全忘了。

## 两剂便宜的药

**1. 项目指令就是文件。** 第一次请求之前，harness 读取：

```python
INSTRUCTION_FILES = [Path.home() / ".harness/AGENTS.md", Path("AGENTS.md"), Path("CLAUDE.md")]
```

并把它们放进系统提示词。`AGENTS.md` 是跨 agent 的通用约定，`CLAUDE.md` 是 Claude Code 读的文件。
两者都支持，一个文件就能配置你团队用的所有 agent。

**2. 一个记忆工具。** 由模型判断什么值得记住：

```python
def remember(note):
    with MEMORY_FILE.open("a") as f:      # .harness/memory.md
        f.write(f"- {note}\n")
```

这个文件会被加载进之后每一次的系统提示词。在这个规模下，"长期记忆"就只需要这么多：
没有向量数据库，没有 embedding，就是一个你能读、能改、能提交的 Markdown 文件。

```
<instructions file="AGENTS.md">
# Project notes
- Python 3.10+, standard library only.
- Run tests with: python3 -m unittest
</instructions>

<memory file=".harness/memory.md">
- User prefers pytest-style plain asserts in tests.
- Staging DB: localhost:5433.
</memory>
```

## 设计要点

- **模型决定记什么，harness 决定记在哪、何时加载。** 系统提示词让模型保存持久的事实：
  约定、偏好、坑。当前任务的内容不应该存进去。
- **设上限。** 指令最多 20 KB，记忆只加载最后 10 KB。无限增长的记忆文件，会变成下一个上下文问题。
- **优先级。** 先用户级（`~/.harness/AGENTS.md`），再项目级。真实的 harness 还会在 agent 进入子目录时，
  加载那里的 `AGENTS.md`。
- **放进 git。** 提交 `AGENTS.md`，整个团队得到一样的 agent 行为。

## 运行

```bash
python agents/s09_memory.py
```

## 练习

1. 加一个 `forget(pattern)` 工具，并想一想：它需要权限确认吗？
2. 从当前目录一路往上到 git 根目录，加载每一层的 `AGENTS.md`。
3. 当 `memory.md` 超过 50 行时，让模型整理它（合并重复、删掉过时的事实）。
