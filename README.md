# 小航：从零实现的最小 CLI Agent

使用 Python 和真实 DeepSeek API 实现的命令行 Agent。

项目未使用 LangGraph、OpenHands、OpenClaw 等 Agent 框架。
Agent Loop、工具注册、请求与响应转换、会话管理和基础上下文处理由项目自行实现。
使用 OpenAI Python SDK 作为兼容 DeepSeek API 的网络客户端。

## 功能

- 由 LLM 根据工具描述和参数 Schema 选择工具。
- 支持直接回答、工具调用和连续多步工具调用。
- 提供 calculator、离线 mock search、todo 三个工具。
- 使用 `(user_id, session_id)` 隔离会话。
- 支持同一进程内切换会话并恢复原会话状态。
- 支持连续对话、纯对话追问和工具调用追问。
- 对旧历史生成有长度限制的摘录，并保留近期完整对话轮次。
- 支持基础参数校验、工具异常处理和工具执行日志。
- 每次用户输入默认最多调用模型 8 次。
- 使用 FakeLLM 和 unittest 进行离线自动测试。

## 环境与安装

建议使用 Python 3.11 或以上版本。
开发过程中实际使用 Python 3.14.3、OpenAI Python SDK 3.19.2。

在项目根目录执行以下命令。下面以 Windows PowerShell 为例：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

直接使用虚拟环境中的解释器即可，不要求先激活虚拟环境。

## 配置与启动

支持以下进程环境变量：

| 变量 | 用途 | 默认值 |
|---|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek API key | 无 |
| `DEEPSEEK_BASE_URL` | API 地址 | `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | 模型名 | `deepseek-chat` |

`.env.example` 仅提供配置参考。当前程序不会自动加载 `.env` 文件。

启动：

```powershell
.\.venv\Scripts\python.exe -m agent_cli --user-id alice --session-id window-1
```

如果没有设置 `DEEPSEEK_API_KEY`，程序会提示输入。
输入时不显示字符，按 Enter 提交。
通过提示输入的 key 仅保存在本次进程中，不写入项目文件。

出现下面的提示后，即可输入聊天内容：

```text
[alice/window-1] 你：
```

示例：

```text
请调用 calculator 计算 (10 + 2) * 3。
把刚才的结果除以 5。
请创建一条待办：完成 README。
请调用 todo 工具列出当前会话的待办。
```

CLI 命令：

```text
/session window-2
/session window-1
/exit
```

`/session` 切换当前用户的会话，不调用模型。
`/exit` 退出程序。

真实模型请求会产生 API 用量。API key 不应写入源码、文档、测试或 Git 提交。

## 项目结构

```text
agent_cli.py               CLI 入口、配置和会话切换
agent_runtime/
    models.py              Message、ToolCall、ToolSpec、Session 等数据模型
    llm.py                 LLMClient、FakeLLM、DeepSeek 客户端和格式转换
    tools.py               工具注册、参数校验及三个工具
    session.py             进程内 SessionStore
    context.py             上下文构造、旧历史摘录和近期消息保留
    runtime.py             Agent Loop、工具执行与错误处理
tests/
    test_runtime.py        Loop、工具结果回传、异常和追问测试
    test_session.py        会话隔离与状态保留测试
    test_context.py        历史缩短、todo 保留和工具交互完整性测试
    test_llm.py            响应解析测试
docs/
    superpowers/           早期设计和实施计划
```

早期设计文档记录了方案演进；当前行为以源码和本 README 为准。
例如，当前测试使用标准库 unittest，而不是早期计划中的 pytest。

## Agent Loop

每次收到一条普通用户输入，runtime 执行：

1. 为当前会话建立工具注册表，todo handler 绑定当前 Session。
2. 将用户输入追加到会话历史。
3. 构造上下文，并将消息和工具 Schema 发送给模型。
4. 解析模型响应，保存 assistant 消息。
5. 如果没有工具调用，返回回答。
6. 如果存在工具调用，按名称查找工具、校验参数并执行 handler。
7. 将执行结果保存为 tool 消息，使用调用 ID 关联原请求。
8. 再次请求模型，直到返回回答或达到循环上限。

典型消息顺序：

```text
user → assistant(tool_calls) → tool → assistant
```

默认的 `max_steps=8` 限制本轮模型调用次数。
一次模型响应可能包含多个工具调用，因此它不是工具执行总数的上限。

运行时依赖 `LLMClient.complete()` 接口。
真实运行使用 DeepSeekLLMClient；离线测试使用 FakeLLM。

## 工具设计

每个 ToolSpec 包含：

- name：工具名称。
- description：工具用途。
- parameters：JSON Schema。
- handler：本地 Python 函数。

发送给模型的工具定义不包含 handler。
模型返回工具名和参数，runtime 在本地查找并调用 handler。

| 工具 | 实现方式 |
|---|---|
| calculator | 使用 AST 白名单计算算术表达式，支持指定运算符、数学函数和常量 |
| search | 在固定的内置文档中进行关键词包含查询，不访问互联网 |
| todo | 在当前 Session 中创建、列出或标记待办完成 |

todo 的 `complete` 只更新状态，不执行待办描述中的实际工作。
系统提示要求在用户确认完成，或任务执行并验证成功后才标记完成；
当前代码没有实现通用的任务完成证据校验。

本地参数校验覆盖当前工具使用的必填字段、额外字段、字符串类型和枚举。
它不是完整的 JSON Schema 验证器。

## Session 与 memory

SessionStore 使用以下键保存会话：

```python
(user_id, session_id)
```

不同用户或不同会话编号对应不同 Session。
同一个 store 中再次请求相同键，会返回原对象。

会话包含两类数据：

- `messages`：用户消息、assistant 消息及工具结果。
- `todos`：待办的当前结构化状态。

每次模型调用前，ContextManager 根据当前 Session 构造请求消息。
这是本项目的 memory 召回时机。

未达到压缩阈值时：

```text
系统提示 + 完整历史
```

超过历史文本字符阈值时：

```text
系统提示 + 旧历史摘录 + 未完成 todo 提示 + 近期完整对话轮次
```

旧历史摘录最多选取旧历史末尾 6 条消息；
每条保留最多 120 个字符并按需加省略号；
整段摘录最多 600 个字符。

近期消息的切分位置会向前移动到 user 消息，
避免截断同一轮中的工具请求和结果。

当前摘录和 todo 提示以额外 system 消息放在近期对话之前。
它们是历史数据，不应被视为用户无法覆盖的新指令；
将不可信历史放入 system 角色仍是当前版本需要改进的设计点。

原始 Session 历史不被压缩过程修改。
摘要每次按需构造，不单独持久化。

工具日志不作为对话消息发送给模型。
可选的 `reasoning_content` 会被客户端解析，
但当前 runtime 不将它保存到会话或执行日志。
主流程不依赖该字段。

本项目没有向量检索、RAG 或跨进程长期记忆。

## 异常与日志

工具名称错误、参数校验失败、工具执行异常及结果序列化失败，
会转换成包含错误类型和简短说明的 tool 消息。
模型可据此继续处理或解释失败。

日志记录工具开始、成功、失败、工具名、调用 ID 和异常类型。
日志默认输出到终端，不写入独立日志文件。

API 请求和响应解析异常目前由 CLI 捕获，
显示错误类型并结束本轮处理。
SDK 请求超时设置为 30 秒，关闭自动重试。

## 测试

在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

默认测试完全离线，不需要 API key。

当前 12 个测试方法覆盖：

- 正常工具结果回传给下一次模型请求。
- 非法参数在 handler 执行前被拒绝。
- 未知工具错误及循环继续。
- 工具执行异常回传和失败日志。
- 最大模型调用次数限制。
- 纯对话追问的历史传递。
- 用户及 session 隔离、消息和 todo 状态保留。
- 长历史缩短、未完成 todo 保留和原历史不变。
- 压缩时保留完整工具交互。
- 正常响应解析、非法参数 JSON、空 choices。

已通过手动真实 DeepSeek 请求验证：

- 普通文本回答。
- calculator 工具调用和完整 Agent Loop。
- 根据上一轮计算结果继续调用工具。
- CLI 中 todo 会话切换、隔离与恢复的交互表现。
- 纯对话追问。

真实 API 验证目前通过手动运行 CLI 或实验命令完成，
尚未提供独立的自动化 live 测试套件。

## 已知限制

- 会话仅保存在当前进程内；退出后丢失，不同进程不共享 store。
- 基础摘录是有损截取，可能丢失早期重要信息。
- `max_chars` 是历史正文长度的触发阈值，不是严格请求 token 上限；
  当前未完整统计工具 Schema 和工具调用参数。
- 保留完整近期轮次和未完成 todo 后，请求仍可能超过目标预算。
- 原始消息历史持续保存在内存中，没有限制会话内存总量。
- 响应参数 JSON 解析失败时结束本轮，未实现自动修复重试。
- API 失败后不自动回滚已经保存的消息或执行成功的工具操作。
- calculator 使用语法白名单，但未设置完整的计算资源限制。
- 未实现通用任务执行器、数据库持久化或并发服务端。

## AI 辅助开发

开发过程中使用 AI 辅助方案设计、接口讲解、代码示例和错误诊断，
开发者逐文件输入代码并运行验证。

代表性任务 Prompt、实现决策与验证过程见
[AI 辅助开发与问题解决记录](docs/superpowers/ai-development-log.md)。
