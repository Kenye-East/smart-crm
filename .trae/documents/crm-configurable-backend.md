# 升级 /crm 为可配置后台

## Context（为什么做）

`/crm` 目前只是只读的对话记录查看页。用户希望把它升级成可配置的 B 端后台：能配置"检测的人名""读取间隔""AI 回复的 system prompt""RAG 的 system prompt"，并能上传知识库文件。让 B 端演示时既能看到对话，也能现场改参数、传文档、改 AI 口吻。

用户已确认的决策：
1. 去掉导航"仪表盘"项，但保留顶部统计卡片。
2. "设置"里可配置**两个** system prompt：微信自动回复用 + RAG 接口用。
3. 后台保存的配置**下次启动生效**：写入配置文件，微信 RPA 下次启动读取。

## 落点决策

配置放 `src/agentlab/crm_settings.py`（与 `chat_store.py` 同包的先例一致，能被 FastAPI 和 wechat_rpa 双向 import）。配置文件为 `data/crm_settings.json`。数据库/坐标/业务参数三者正交：`calibrated.json` 管屏幕坐标区域（机器相关调试产物），`crm_settings.json` 管业务参数，互不覆盖、刻意不合并。

## Schema（配置文件 `data/crm_settings.json`）

```json
{
  "target_contacts": ["李", "K"],
  "poll_interval": 15.0,
  "wechat_system_prompt": "<responder 现内嵌文案>",
  "rag_system_prompt": "<rag.py 现 RAG_SYSTEM_PROMPT 文案>"
}
```
两个 prompt 的默认文案以现状为准（responder.py `_answer_local` 的 system 文案、api/routes/rag.py 的 `RAG_SYSTEM_PROMPT`），作为单一事实来源落到 crm_settings 默认值；空串在读取端视为"未配置"回退默认。

## 改动文件清单

| 动作 | 文件 | 职责 |
|------|------|------|
| 新建 | `src/agentlab/crm_settings.py` | `get_settings()` / `update_settings(patch)`；模块锁 + 原子写（tmp + os.replace） |
| 新建 | `api/routes/crm_settings.py` | `GET ""`、`PUT ""`（SettingsPatch，model_dump exclude_none） |
| 新建 | `api/routes/knowledge.py` | `POST /upload`(multipart)、`GET /list`、`GET /status`；上传后**后台线程重建** |
| 改动 | `api/main.py` | 注册 `crm_settings`(prefix=/api/crm-settings)、`knowledge`(prefix=/api/knowledge) |
| 改动 | `api/routes/rag.py` | `query()` 改用 `get_settings()["rag_system_prompt"] or 兜底` |
| 改动 | `wechat_rpa/config.py` | dataclass 增 `wechat_system_prompt` 字段；`load()` 增读 crm_settings 覆盖 contacts/poll_interval/prompt |
| 改动 | `wechat_rpa/responder.py` | `_answer_local()` system 消息改用 `self.config.wechat_system_prompt` |
| 新建 | `web/src/app/api/crm-settings/route.ts` | GET/PUT 转发 |
| 新建 | `web/src/app/api/knowledge/route.ts` | GET(列表)/POST(上传 multipart，`req.formData()` 透传) |
| 改动 | `web/src/app/crm/page.tsx` | NAV_ITEMS 减"仪表盘"；按 activeNav 条件渲染 4 面板（对话记录/会话成员/知识库/设置） |

## 实现要点

### 1) `src/agentlab/crm_settings.py`
- `SETTINGS_PATH = Path(__file__).resolve().parents[2] / "data" / "crm_settings.json"`（与 ChatStore 同定位法）。
- 模块级 `_lock = threading.Lock()`；`update_settings(patch)`：合并→校验→`json.dump` 到 `.tmp`→`os.replace`。
- 校验：contacts 必须 `list[str]` 非空去重；poll_interval 可转 float 且 >0；prompt 允许空串。

### 2) `api/routes/knowledge.py`
- `KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge"`。
- 文件名安全化 `Path(file.filename).name`。
- **后台线程重建**（推荐，原因：embedding 首次加载/全量向量化会卡住 HTTP）：`threading.Thread(daemon=True)` 内 `RAGPipeline().index(str(KNOWLEDGE_DIR))`；`_rebuild_state` 记录 running/last_status/last_error，防重复启动。调用 `RAGPipeline()` **新实例**（不复用 rag.py 单例，避免旧 embedding/vector_store 句柄；持久化同一 Qdrant collection，新索引 query 生效）。
- `GET /list` 返回文件名+大小+更新时间。

### 3) `wechat_rpa/config.py`
- dataclass 增 `wechat_system_prompt: str`（默认= 现 responder 内嵌文案）。
- `load()` 在 calibrated.json 覆盖后，`from agentlab.crm_settings import get_settings`（**延迟导入**避免启动顺序耦合）+ try/except 兜底，覆盖 `target_contacts`/`poll_interval`/`wechat_system_prompt`。

### 4) `api/routes/rag.py`
- 保留 `RAG_SYSTEM_PROMPT` 为兜底常量；`query()` 内 `prompt = get_settings().get("rag_system_prompt") or RAG_SYSTEM_PROMPT`。

### 5) 前端 `page.tsx`
- `NAV_ITEMS = ["对话记录","会话成员","知识库","设置"]`。
- 保留现"对话记录"面板；新增三个内联子组件，统一数据流：挂载 `useEffect` fetch `GET /api/crm-settings` → 本地 state → 保存 `PUT /api/crm-settings`。
- 知识库面板：`<input type="file" multiple>` + 文件列表 + 轮询 `GET /api/knowledge/status`（~2s，running 时"索引中…"）。
- 保存成功给简单"保存成功"文案。

### 6) Next 转发
两个新 route 都 `export const dynamic = "force-dynamic"`。`/api/knowledge` 的 POST 用 `req.formData()` 后把 **FormData 原样透传**给 FastAPI（不要 parse 成 JSON，会丢 boundary/文件名）。

## 复用
- `ChatStore` 的线程安全原子写模式 → `crm_settings.py`。
- `api/main.py` 既有 `include_router` 切口。
- `scripts/index_knowledge.py` 的 `RAGPipeline().index(directory)` 流程 → knowledge `_rebuild()`。
- `page.tsx` 现有侧栏/统计卡片骨架与卡片样式。

## 风险与对策
- **Next GET 缓存**：新 GET route 一律 `force-dynamic` + `cache:"no-store"`。
- **上传 body**：route handler 用 `req.formData()`，转发透传 FormData。
- **重建期间 RPA 查询空库**：`index()` 先 clear 后 add，重建窗口内 query 可能暂空 → 仅前端提示"索引中"。文件小、窗口短，demo 可接受。
- **prompt 空串**：读取端空串回退默认文案，避免回复变空白。
- **文件名穿越**：`Path(file.filename).name` 白化。

## 验证（端到端）
1. `python -m py_compile` 所有新增/改动 Python 文件。
2. 起 FastAPI，`curl` 验证：
   - `GET /api/crm-settings` 返回 4 字段默认值；
   - `PUT /api/crm-settings`（改 target_contacts/poll_interval）后 GET 回显；
   - `POST /api/knowledge/upload` 传一个 txt，`GET /api/knowledge/list` 出现该文件，轮询 `GET /api/knowledge/status` 状态 done；
3. `wechat_rpa/config.py` 的 `Config.load()` 打印验证 contacts/poll_interval 被 crm_settings 覆盖、wechat_system_prompt 被覆盖。
4. `npx tsc --noEmit`（web）类型检查通过；浏览器 `/crm` 四个导航面板可切换，成员/设置保存后回显、知识库上传后状态流转。
5. 跑一次 RPA / RAG 接口验证新 prompt 生效（可先改成一个带明显标记的文案，看回复是否带上该标记）。