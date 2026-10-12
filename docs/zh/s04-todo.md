# s04 · 待办清单：让模型自己做计划

> 代码：[`agents/s04_todo.py`](../../agents/s04_todo.py) · [← s03](s03-permissions.md) · 下一章：[s05 子智能体 →](s05-subagent.md)

## 问题

给模型一个十步的任务。到第六步左右，它一头扎进一个挂掉的测试，修好了，然后宣布"完成"。
第七到第十步被忘得一干二净。计划只存在于模型"脑子里"，而现在它被埋在了 30 条工具结果上面。

## 思路

一个几乎什么都不干的工具：存一份清单，再显示回来。

```python
todo_write(items=[
    {"content": "Write calc.py with add() and sub()", "status": "in_progress"},
    {"content": "Write test_calc.py",                 "status": "pending"},
    {"content": "Run the tests",                      "status": "pending"},
])
```
```
[>] Write calc.py with add() and sub()
[ ] Write test_calc.py
[ ] Run the tests
(0/3 done)
```

把计划写下来，模型就会按计划走；而每次更新都会把剩下的步骤重新放到上下文的**最末尾**，
也就是模型注意力最集中的地方。

## 两条 harness 规则

**同一时间只能有一项"进行中"。**

```python
if sum(i["status"] == "in_progress" for i in clean) > 1:
    raise ValueError("only one item may be in_progress at a time")
```

这迫使模型一件一件做。这个错误和其他工具错误一样，会被送回给模型。

**计划过期时催一下。** 如果清单里还有未完成项，而模型连续三轮都没更新它，
harness 就在最新的工具结果后面附一条提醒：

```python
if TODOS.open_items() and rounds_since_todo >= NAG_AFTER:
    messages[-1]["content"] += "\n\n<reminder>You have open todos. Update your list with todo_write.</reminder>"
```

## 为什么是"追加"，而不是"插入"？

我们完全可以插一条新的 system 消息，或者改写系统提示词。但我们没有，因为**历史只追加**。
服务商会缓存提示词的前缀：第一个变化字节之前的内容都能便宜地复用。改了系统提示词或旧消息，
从那个位置往后的缓存就全部失效。而追加到最新一条（还没发出去的）消息上，不花任何代价。

这个思路会贯穿整个 harness：想在任务中途对模型说点什么，就把它附在你本来就要发的内容上。

## 运行

```bash
python agents/s04_todo.py
```

看演示里的模型连续三轮没更新清单、被提醒，然后把清单全部勾完。

## 练习

1. 每次更新后，在终端用一行进度条显示待办清单。
2. 如果某项被标为 completed 却从没进入过 in_progress，就拒绝这份清单。这样会不会太严格？
3. 把清单持久化到 `.harness/todos.json`，重启后还能接着用。
