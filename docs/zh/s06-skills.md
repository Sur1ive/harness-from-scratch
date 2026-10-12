# s06 · 技能：按需加载的知识

> 代码：[`agents/s06_skills.py`](../../agents/s06_skills.py) · [← s05](s05-subagent.md) · 下一章：[s07 上下文压缩 →](s07-compact.md)

## 问题

你的团队有提交信息规范、代码评审清单、写测试指南、发布手册。全塞进系统提示词，
每次请求都要为 20 KB 的说明买单，而它们可能只有 5% 的时候用得上。更糟的是，模型还得自己判断现在哪些适用。

## 思路：渐进式披露

```
系统提示词    每个技能一行：名字 + "什么时候用"        约 100 token
load_skill()  完整的 SKILL.md，只在相关时加载           按需
```

模型先看到目录，需要时才翻到那一章。

## 技能是什么

一个文件夹，里面一个 `SKILL.md`：YAML 头信息 + Markdown 正文。

```markdown
---
name: commit-message
description: Write a clear git commit message (Conventional Commits). Use when the user asks to commit, or to write/fix a commit message.
---

# Writing commit messages

1. Look at what actually changed first: `git status` and `git diff --staged` ...
```

`description` 负责"路由"，所以要写清**什么时候用**，而不只是"它是什么"。
本仓库在 [`skills/`](../../skills) 里自带了三个示例。

这和 Claude Code 等 agent 读取的格式相同，同一个技能写一次，换个 harness 也能用。
s06 会按顺序查找这些目录，先找到的优先：

```python
SKILL_DIRS = [
    Path(".harness/skills"), Path(".claude/skills"), Path(".agents/skills"),
    Path.home() / ".harness/skills",
    Path(__file__).resolve().parent.parent / "skills",   # 自带的示例
]
```

## 代码

三个小函数：

```python
def skills_index():          # 放进系统提示词
    return "\n\nSkills (load with load_skill):\n" + "\n".join(
        f"- {name}: {s['description']}" for name, s in find_skills().items())

def load_skill(name):        # 模型调用的工具
    skill = find_skills().get(name)
    return f"<skill name=\"{name}\" dir=\"{skill['dir']}\">\n{skill['body']}\n</skill>"
```

`load_skill` 以**工具结果**的形式返回技能内容，所以它会出现在上下文末尾，紧挨着它要服务的那个任务。

## 技能 vs. 其他方案

| | 一直在上下文里？ | 谁决定用？ |
|---|---|---|
| 系统提示词 / `AGENTS.md`（s09） | 是 | 永远生效 |
| 技能 | 只有一行描述 | 模型 |
| 子智能体（s05） | 否，独立上下文 | 模型 |
| 钩子（s08） | 否 | harness，确定性执行 |

经验法则：每个任务都适用的东西放 `AGENTS.md`，特定类型任务的操作流程做成技能。

## 运行

```bash
python agents/s06_skills.py
```

## 练习

1. 让技能可以附带脚本：如果 `SKILL.md` 提到了 `scripts/lint.sh`，模型应该能执行它。
2. 加一个 `/skill <name>` 命令强制加载某个技能（`harness.py` 里已经有列出技能的 `/skills`）。
3. 为你自己团队的规范写一个技能，并用真实模型测一测。
