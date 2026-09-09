# 微信 RPA 对话记录 SQLite + /crm 专业后台

## Context（为什么做）

微信 RPA（`wechat_rpa/`）目前自动回复后**不留任何记录**，无法回答"AI 回了哪些客户、回得怎么样"，也不能作为 B 端产品 Demo 展示。本次给它加一个 SQLite 对话日志存储层，并新增 `/crm` 专业后台页面，供 B 端展示"通过 AI 自动回复的全部对话记录"。

用户已确认的决策：
1. 数据链路：`wechat_rpa` 写入 SQLite → **FastAPI 新增读接口** → Next.js api route 转发 → `/crm` 页。
2. demo 首次建库时**内置几条专业感示例会话**。
3. `/crm` 做成**完整后台外壳**（左侧导航 + 统计卡片 + 左会话列表 + 右对话时间线）。
4. 纯 Tailwind，不引入新 UI/图表库。

## 落点决策（关键）

存储层放 **`src/agentlab/chat_store.py`**，不放 `wechat_rpa/` 内。原因：`agentlab` 是唯一能被 RPA 与 FastAPI 双向稳定 `import` 的包（RPA 代码已依赖 `agentlab.rag`/`agentlab.llm`），而 `wechat_rpa` 是独立目录、FastAPI 不保证能 import。DB 文件放 `data/chat_history.db`（`data/` 已存在且不被 cwd 影响：`Path(__file__).resolve().parents[2] / "data"`）。

## Schema（`data/chat_history.db`，双表）

```sql
PRAGMA journal_mode = WAL;  -- 跨进程一写多读
CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  contact TEXT NOT NULL,
  avatar_color TEXT DEFAULT '#4F46E5',   -- B端头像底色（seed 预置）
  latest_question TEXT,                   -- 末条对方消息预览，列表免 JOIN
  created_at INTEGER NOT NULL,           -- unix 秒
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK(role IN ('user','assistant')),
  content TEXT NOT NULL,
  source_chunks TEXT,                     -- JSON 数组，可选
  status TEXT NOT NULL DEFAULT 'sent' CHECK(status IN ('sent','failed','skipped')),
  duration_ms INTEGER,
  created_at INTEGER NOT NULL
);
-- 索引：idx_sessions_updated(updated_at DESC)、idx_messages_session(session_id, created_at ASC)
```

## 改动文件清单

| 动作 | 文件 | 职责 |
|------|------|------|
| 新建 | `src/agentlab/chat_store.py` | 存储层：建库+seed、insert、查询、聚合 |
| 新建 | `api/routes/chat_history.py` | FastAPI 读库接口 |
| 改动 | `api/main.py` | 注册 `include_router(chat_history.router, prefix="/api/chat-history")` |
| 改动 | `wechat_rpa/main.py` | `_handle_contact` 发送后调 `ChatStore.insert_record` |
| 新建 | `web/src/app/api/chat-history/route.ts` | Next 转发：会话列表 |
| 新建 | `web/src/app/api/chat-history/[contact]/route.ts` | Next 转发：单会话时间线 |
| 新建 | `web/src/app/crm/page.tsx` | `/crm` 后台页面（"use client"，纯 Tailwind） |

## 实现要点

### 1) `src/agentlab/chat_store.py`
- 模块级 `threading.Lock()` + 每函数新建连接用完关闭（`sqlite3` 标准库，`row_factory=Row`，`busy_timeout=5000`），避免多线程/多进程共享连接脏读；WAL 兜底跨进程。
- 方法：
  - `insert_record(contact, question, answer, *, status, duration_ms, source_chunks=None) -> int`：同事务内「按 contact 找/建 session + 插 message」，更新 `latest_question/updated_at`。
  - `record_failure(contact, question, duration_ms)`：异常时插一条 `status='failed'`。
  - `list_conversations() -> list[dict]`：contact/avatar_color/latest_question/updated_at + LEFT JOIN 消息数。
  - `get_conversation(contact) -> list[dict]`：按 `created_at ASC` 返回时间线。
  - `stats() -> dict`：会话数/消息数/AI回复数/发送成功率/平均耗时/今日·7日计数。
  - `seed_demo()`：首次建库（`count_messages()==0`）自动插入 3 条专业感示例会话，时间用 `time.time()` 回退数小时/数天。

### 2) `api/routes/chat_history.py`（对齐 rag.py style）
pydantic 响应模型 + 模块级 `_store = ChatStore()` 单例：
- `GET /conversations` → 会话列表
- `GET /conversations/{contact}` → 时间线（空则 404）
- `GET /stats` → 聚合统计
- 在 `api/main.py` 注册 `prefix="/api/chat-history"`。

### 3) `wechat_rpa/main.py` 写入接入
- `main()` 里 `store = ChatStore()`（实例化即建库+seed），传入 `_handle_contact`。
- `_handle_contact` 末尾、`send` 之后调用：
  `store.insert_record(contact=row["name"], question=question, answer=answer, status="sent"/"failed", duration_ms=...)`，`t0` 从 `answer` 前计到发送完成。不动 RAG/发送逻辑，风险最小。`source_chunks` 本期留空（本地 RAG 内部不可见，属有意范围控制）。

### 4) Next.js 转发（复现现有 `chat.py route.ts` 模式）
两个 route.ts：`export const dynamic = 'force-dynamic'`（**重要**，否则 GET 被缓存，/crm 只见 seed），`FASTAPI_URL || localhost:8000`。`[contact]/route.ts` 需 `await params`（Next 15+/16）。

### 5) `web/src/app/crm/page.tsx`
`"use client"`。布局：
```
侧栏 240px（深色 bg-slate-900）
  ├ 仪表盘 / 对话记录 / 会话成员 / 设置（占位高亮）
主内容区：
  ├ 顶部统计卡片 4 张（会话数/消息数/成功率/平均耗时）
  └ 左会话列表 + 右对话时间线（气泡：assistant 左·AI / user 右·对方）
```
- 挂载并行 `fetch('/api/chat-history')` 与 `/api/chat-history/stats`；选中会话后 `fetch('/api/chat-history/{contact}')`。
- 可选轮询：`useEffect` + `setInterval` 刷新统计与列表（清理定时器）。
- 时间线复用现有气泡样式（`rounded-2xl rounded-br-md/bl-md`）；assistant 气泡可展开 `source_chunks` 蓝色引用卡。
- 配色：卡片 `bg-white border-slate-200 shadow-sm`、AI 气泡 `bg-indigo-600 text-white`、对方 `bg-slate-100 text-slate-900`。

## 复用的现有内容
- FastAPI 路由风格：`api/routes/rag.py`、`chat.py`（APIRouter + pydantic + 延迟单例）。
- Next 转发模式：`web/src/app/api/chat/route.ts`、`reset/route.ts`（`FASTAPI_URL` + fetch）。
- 气泡样式：`web/src/app/page.tsx`（`rounded-2xl rounded-br-md` 等）。
- Tailwind 已接入：`src/app/globals.css` 含 `@tailwind` 指令、`tailwind.config.js` 存在。

## 实施顺序
1. `src/agentlab/chat_store.py`（建库+seed+读写+stats）→ 用 `python -c` 验证建库。
2. `api/routes/chat_history.py` + `api/main.py` 注册 → `curl /api/chat-history/conversations` 验证。
3. Next 两个 route.ts + `/crm/page.tsx` → 浏览器验证展示。
4. `wechat_rpa/main.py` 接入 insert（依赖步骤 1，可与 2/3 并行）。

## 验证（端到端）
1. `python -m py_compile` 所有改动/新增的 Python 文件。
2. 运行 FastAPI `python -m uvicorn api.main:app --port 8000`，`curl http://localhost:8000/api/chat-history/conversations`、`/stats`、`/conversations/王总` 均返回 seed 数据。
3. `cd web && npm run dev`，浏览器打开 `/crm`：看到侧栏、统计卡片、左侧示例会话列表；点选会话右侧出现时间线气泡。
4. （可选）跑一次 RPA 回复后回 `/crm`，确认新记录出现（验证写入链路）。