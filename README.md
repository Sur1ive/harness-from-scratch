<div align="center">

# Harness from Scratch

**Build your own Claude Code–style coding agent in 10 small steps.**<br>
Pure Python · zero dependencies · every chapter runs offline, no API key needed.

[**English**](README.md) · [**简体中文**](README.zh-CN.md)

[![test](https://github.com/Sur1ive/harness-from-scratch/actions/workflows/test.yml/badge.svg)](https://github.com/Sur1ive/harness-from-scratch/actions/workflows/test.yml)
![python](https://img.shields.io/badge/python-3.10%2B-3776ab)
![dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)
![license](https://img.shields.io/badge/license-MIT-blue)

<img src="assets/demo.svg" alt="s08: a hook catches a syntax error and the agent fixes it" width="820">

</div>

---

Claude Code, Codex, Cursor's agent, DeepSeek Harness, every "coding agent"
you have used is a **model** wrapped in a **harness**. The model writes text;
the harness is everything else: the loop, the tools, the permission prompts,
the todo list, the subagents, the context compaction, the hooks, the memory
files, the MCP servers.

The harness is also the part you can actually build, read and change.
This repo builds one from an empty file, one mechanism per chapter.
Each chapter is a **single runnable file** that adds one idea to the last one.
By s10 you have a complete harness in about 600 readable lines, and
you know why every one of them is there.

```python
def agent_loop(messages):
    while True:
        reply = llm.chat(system_prompt(), messages, TOOLS)  # 1. ask the model
        messages.append(reply)
        if not reply["tool_calls"]:                          # 2. no tools requested -> done
            return reply["content"]
        for call in reply["tool_calls"]:                     # 3. run every requested tool
            output = run_bash(call["args"]["command"])
            messages.append({"role": "tool", "id": call["id"], "name": call["name"], "content": output})
        # 4. loop: the model sees the results and decides what's next
```

That's s01. That loop **is** the agent; the other nine chapters plug into it.

<p align="center"><img src="assets/loop.svg" alt="the agent loop and where each chapter plugs in" width="820"></p>

## Quick start

```bash
git clone https://github.com/Sur1ive/harness-from-scratch
cd harness-from-scratch
python agents/s01_agent_loop.py      # no key? you get an offline demo with real tools
```

No `pip install`. Python 3.10+ is all it needs.

Without an API key every chapter plays a **scripted demo**: a fake model
"decides" what to do, but the tools, permission checks, hooks and MCP server
all run for real, in a scratch folder. To talk to a real model, export one key:

```bash
export DEEPSEEK_API_KEY=sk-...        # or ANTHROPIC_API_KEY, DASHSCOPE_API_KEY, ...
python agents/s10_mcp.py
```

## The chapters

| # | Chapter | What you add | The idea |
|---|---------|--------------|----------|
| 01 | [The agent loop](docs/en/s01-agent-loop.md) · [`code`](agents/s01_agent_loop.py) | `while` + one `bash` tool | An agent is a loop that ends when the model stops asking for tools |
| 02 | [Tools](docs/en/s02-tools.md) · [`code`](agents/s02_tools.py) | read · write · edit · glob · grep | A dispatch table; tool errors are results, not exceptions |
| 03 | [Permissions](docs/en/s03-permissions.md) · [`code`](agents/s03_permissions.py) | deny rules, ask / auto / plan modes | The harness is the last line of defence; a "no" is feedback the model can use |
| 04 | [Todos](docs/en/s04-todo.md) · [`code`](agents/s04_todo.py) | `todo_write` + a nag reminder | Models plan better when they have to write the plan down |
| 05 | [Subagents](docs/en/s05-subagent.md) · [`code`](agents/s05_subagent.py) | `task` tool | Same loop, fresh `messages`: side quests don't pollute the main context |
| 06 | [Skills](docs/en/s06-skills.md) · [`code`](agents/s06_skills.py) | `SKILL.md` + `load_skill` | Progressive disclosure: an index in the prompt, full text on demand |
| 07 | [Compaction](docs/en/s07-compact.md) · [`code`](agents/s07_compact.py) | micro-compact + summary | Forgetting on purpose, without breaking the prompt cache every turn |
| 08 | [Hooks](docs/en/s08-hooks.md) · [`code`](agents/s08_hooks.py) | Pre/PostToolUse, Stop, UserPromptSubmit | Prompts are suggestions, hooks are guarantees |
| 09 | [Memory](docs/en/s09-memory.md) · [`code`](agents/s09_memory.py) | `AGENTS.md` / `CLAUDE.md` + `remember` | Instructions and memories are just files the harness loads |
| 10 | [MCP](docs/en/s10-mcp.md) · [`code`](agents/s10_mcp.py) | a 60-line MCP client + a demo server | Tools from other processes, over JSON-RPC on stdin/stdout |
| ★ | [`harness.py`](agents/harness.py) | slash commands, sessions, `-p` mode | Everything above, packaged for daily use |

Read them in order. Every file is complete and runnable, so
`diff agents/s04_todo.py agents/s05_subagent.py` shows exactly what a chapter adds.

## Works with any model

One neutral message format, two wire protocols, every major provider. All of it is in
[`agents/llm.py`](agents/llm.py), using only the standard library's `urllib`.

| `HARNESS_PROVIDER` | API key variable | Default model |
|---|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-opus-5-5` |
| `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| `qwen` | `DASHSCOPE_API_KEY` | `qwen-plus` |
| `kimi` | `MOONSHOT_API_KEY` | set `HARNESS_MODEL` |
| `glm` | `ZHIPUAI_API_KEY` | set `HARNESS_MODEL` |
| `siliconflow` | `SILICONFLOW_API_KEY` | set `HARNESS_MODEL` |
| `doubao` (Volcengine Ark) | `ARK_API_KEY` | set `HARNESS_MODEL` |
| `gemini` | `GEMINI_API_KEY` | set `HARNESS_MODEL` |
| `openrouter` | `OPENROUTER_API_KEY` | set `HARNESS_MODEL` |
| `openai` | `OPENAI_API_KEY` | set `HARNESS_MODEL` |
| `ollama` | none (local) | set `HARNESS_MODEL` |
| any OpenAI-compatible server | `HARNESS_API_KEY` | `HARNESS_BASE_URL=http://...` + `HARNESS_MODEL` |

If you set no provider, the first key found in your environment wins. If none
is set, you get the offline demo.

## Use it for real

```bash
cd ~/your-project
python ~/harness-from-scratch/agents/harness.py            # interactive
python ~/harness-from-scratch/agents/harness.py --resume   # continue the last session
HARNESS_PERMISSION=auto python ~/harness-from-scratch/agents/harness.py -p "make the failing test pass"
```

Inside: `/tools` `/skills` `/todos` `/memory` `/mode plan` `/compact` `/clear` `/exit`.
It reads the same files other agents do: `AGENTS.md`, `CLAUDE.md`,
`.claude/skills/*/SKILL.md` and `.mcp.json`. Sessions are saved to `.harness/` after every turn.

It is small on purpose. It has no streaming, no sandbox, no IDE integration,
so for serious work keep using a production harness. Its job is to make
those tools stop being magic.

## Where you have seen these ideas

| Mechanism | Chapter | In Claude Code |
|---|---|---|
| tool loop | s01 | the core of every turn |
| dedicated file tools | s02 | `Read`, `Write`, `Edit`, `Glob`, `Grep` |
| permission modes | s03 | ask / accept edits / plan mode, `permissions.deny` |
| todo list | s04 | the todo / task list tools |
| subagents | s05 | subagents and custom agents |
| skills | s06 | `SKILL.md` skills |
| compaction | s07 | auto-compact, `/compact` |
| hooks | s08 | `PreToolUse`, `PostToolUse`, `Stop`, `UserPromptSubmit` (exit code 2 = block) |
| memory | s09 | `CLAUDE.md` files |
| MCP | s10 | `.mcp.json`, `mcp__server__tool` names |

## Design rules for this repo

- **One file per chapter, always runnable.** No framework to learn and no imports between chapters.
- **Zero dependencies.** Readers should be able to read all of it, `llm.py` included.
- **Append-only history.** We add messages and never rewrite old ones (except in s07,
  where that trade-off is explained), because that is what keeps prompt caches warm in a real harness.
- **Errors are tool results.** A failed command, a denied permission and a blocked hook
  all go back to the model as text it can react to.
- **Tests run offline.** `python tests/test_harness.py` runs every chapter's demo and checks
  both wire formats against a fake HTTP server.

## FAQ

**Why Python and not TypeScript?** It is the language most people can read without a
build step. The ideas port 1:1; s01 is a good exercise to translate.

**How is this different from other "build your own agent" tutorials?**
Three things: it runs offline out of the box (the scripted demos), it treats the
*harness* mechanisms (permissions, hooks, compaction, MCP) as the main content rather
than an afterthought, and it is provider-neutral (DeepSeek, Qwen, Kimi and GLM are first-class).

**Can the mock model do real work?** No. It replays a script so you can watch the
mechanics without a key. Set a real API key for real work.

**Windows?** The file tools work everywhere. The `bash` tool runs your
system shell, which is `cmd` on Windows, so WSL gives the best experience.

## Contributing

Translations, exercises, new chapters and bug fixes are all welcome. Good next chapters:
streaming, sandboxing, git worktrees for parallel agents, multi-agent teams, evals.
Please keep the rules above: one runnable file, no dependencies, tests offline.

If this helped you understand how coding agents work, a ⭐ helps others find it.

## License

[MIT](LICENSE)
