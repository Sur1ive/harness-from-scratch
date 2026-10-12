# s05 · 子智能体：给支线任务一个全新的上下文

> 代码：[`agents/s05_subagent.py`](../../agents/s05_subagent.py) · [← s04](s04-todo.md) · 下一章：[s06 技能 →](s06-skills.md)

## 问题

"找出所有调用支付 API 的地方"可能需要 40 次 grep 和读文件，产生 200 KB 的输出。
这些全都会留在 `messages` 里直到会话结束：每次请求都要重新发送，拖慢模型，还会把真正的任务挤出视野。

## 思路

子智能体 = **同一个循环 + 一个全新的、空的 `messages`**。

```
父 agent ──task("找支付调用")──▶ 子循环（全新上下文）
         ◀──── 5 行摘要 ───────  ……40 次工具调用，用完即弃
```

```python
def run_subagent(description, prompt):
    sub_messages = [{"role": "user", "content": prompt}]   # <- 全部的诀窍就在这一行
    system = SUBAGENT_PROMPT.format(cwd=os.getcwd())
    summary = agent_loop(sub_messages, tools=SUB_TOOLS, system=system, depth=1, max_rounds=30)
    return summary
```

父 agent 只能看到 `summary`，它是 `task` 工具调用的返回结果。那 40 条中间结果随 `sub_messages` 一起被丢掉。

## 让循环可复用

为了能把循环跑两遍，`agent_loop` 现在接受参数：

```python
def agent_loop(messages, tools=None, system=None, depth=0, max_rounds=200):
```

- `tools`：子 agent 拿到的是 `SUB_TOOLS`，没有 `task`（防止无限递归），也没有 `todo_write`（不共享父 agent 的计划）。
- `system`：告诉子 agent **摘要是父 agent 唯一能看到的东西**。不加这句，子 agent 会回一句"搞定！"，父 agent 什么也没学到。
- `max_rounds`：失控的子 agent 不能把预算烧光。

## 写好任务说明

子 agent 一开始**什么都不知道**：没有对话历史，也不知道用户想要什么。`task` 工具的描述里写明了这一点，
所以父 agent 必须写出一份完整的任务说明。这和把活儿交给同事是同一种能力：找什么、去哪找、答案要什么格式。

## 什么时候用，什么时候不用

适合：大范围搜索、"调查一下 X 为什么会这样"、读一份长文档提取三条信息、互不相关的多文件修改。

不适合：小查询（跑一整个循环的开销比省下的还多），以及需要用到之前对话内容的事。

## 运行

```bash
python agents/s05_subagent.py
```

演示先搭一个小项目，再派一个子 agent 去 grep 所有 TODO。注意缩进：子 agent 的工具调用是嵌套显示的，
而 `subagent done (4 messages discarded)` 就是父 agent 不必背负的那部分上下文。

## 练习

1. 用线程并行跑多个 `task` 调用。打印部分需要做什么改动？
2. 给子 agent 区分只读工具集（`explore` 类型）和完整工具集（`general` 类型）。
3. 统计子 agent 用了多少 token，累加到总数里。
