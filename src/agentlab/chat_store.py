"""微信 RPA 对话记录 SQLite 存储层。

wechat_rpa（写 · 单进程）与 FastAPI（读 · 多线程）共用同一份对话日志。

设计取舍：
- 双表 sessions + messages：贴合"会话列表 + 时间线气泡"的展示，且统计聚合自然。
- WAL journal_mode：允许一写多读、跨进程并发；busy_timeout 兜底锁竞争。
- 每函数新建连接、用完关闭：避免在多线程/多进程间共享连接导致的脏读。
- sessions.latest_question 冗余末条对方消息，会话列表无需 JOIN messages。
- 首次建库（messages 为空）自动写入几条专业感示例会话，供 B 端 Demo 演示。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

# data/chat_history.db（仓库根下的 data 目录；用 __file__ 定位，避免受启动 cwd 影响）
DB_PATH = Path(__file__).resolve().parents[2] / "data" / "chat_history.db"

# messages 建表语句单独抽出：新库直接用；老库在 _init_db 里热迁移到该结构
_MESSAGES_CREATE = """
CREATE TABLE IF NOT EXISTS messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role          TEXT NOT NULL CHECK (role IN ('user','assistant')),
    content       TEXT NOT NULL,
    source_chunks TEXT,
    status        TEXT NOT NULL DEFAULT 'sent' CHECK (status IN ('sent','failed','skipped','blocked')),
    qa_reason     TEXT,
    duration_ms   INTEGER,
    created_at    INTEGER NOT NULL
);
"""

_DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    contact        TEXT NOT NULL,
    avatar_color   TEXT DEFAULT '#4F46E5',
    latest_question TEXT,
    created_at     INTEGER NOT NULL,
    updated_at     INTEGER NOT NULL
);
""" + _MESSAGES_CREATE + """
CREATE INDEX IF NOT EXISTS idx_sessions_contact ON sessions(contact);
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);
"""


class ChatStore:
    """对话记录存储层（线程安全，函数级连接）。"""

    def __init__(self, db_path: str | Path = DB_PATH):
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._init_db()
        if self.count_messages() == 0:
            self.seed_demo()

    # ---------- 连接管理 ----------
    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.executescript(_DDL)
                self._migrate_messages_schema(conn)

    def _migrate_messages_schema(self, conn) -> None:
        """老库热迁移：messages 增加 qa_reason 列、status 允许 'blocked'。

        新表结构(_MESSAGES_CREATE)已含两者；老表缺任一就重建并搬数据。
        重建先 RENAME 再建新表；失败时回滚把旧表名还原，避免破坏数据。
        """
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='messages'"
        ).fetchone()
        if not row:
            return  # 首次建库，_DDL 已是新结构
        ddl = row["sql"] or ""
        if "'blocked'" in ddl and "qa_reason" in ddl:
            return  # 已是最新
        cols = [
            c["name"]
            for c in conn.execute("PRAGMA table_info(messages)").fetchall()
        ]
        has_reason = "qa_reason" in cols
        # INSERT 列清单必须与源表实际列匹配；目标表缺列时省略该列，走默认 NULL
        cols_sql = (
            "id, session_id, role, content, source_chunks, status"
            + (", qa_reason" if has_reason else "")
            + ", duration_ms, created_at"
        )
        conn.execute("ALTER TABLE messages RENAME TO messages__old")
        try:
            conn.executescript(_MESSAGES_CREATE)
            conn.execute(
                f"INSERT INTO messages ({cols_sql}) SELECT {cols_sql} FROM messages__old"
            )
            conn.execute("DROP TABLE messages__old")
            conn.execute(
                "UPDATE sqlite_sequence SET seq=(SELECT COALESCE(MAX(id),0) FROM messages) WHERE name='messages'"
            )
            conn.executescript(
                "CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at ASC);"
                "CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);"
            )
        except Exception:
            # 回滚：删掉刚建的空新表，把旧表名还原
            conn.execute("DROP TABLE IF EXISTS messages")
            conn.execute("ALTER TABLE messages__old RENAME TO messages")
            raise

    # ---------- 写 ----------
    def insert_record(
        self,
        contact: str,
        question: str,
        answer: str,
        *,
        status: str = "sent",
        duration_ms: Optional[int] = None,
        source_chunks: Optional[list[dict]] = None,
    ) -> int:
        """写入一轮问答，返回 assistant message id。contact 不存在自动建会话。"""
        now = int(time.time())
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT id FROM sessions WHERE contact=?", (contact,)
                ).fetchone()
                if row:
                    sid = row["id"]
                else:
                    cur = conn.execute(
                        "INSERT INTO sessions (contact, avatar_color, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?)",
                        (contact, "#4F46E5", now, now),
                    )
                    sid = cur.lastrowid
                chunks = json.dumps(source_chunks, ensure_ascii=False) if source_chunks else None
                cur = conn.execute(
                    "INSERT INTO messages (session_id, role, content, source_chunks, status, duration_ms, created_at) "
                    "VALUES (?, 'user', ?, NULL, 'sent', NULL, ?)",
                    (sid, question, now),
                )
                cur = conn.execute(
                    "INSERT INTO messages (session_id, role, content, source_chunks, status, duration_ms, created_at) "
                    "VALUES (?, 'assistant', ?, ?, ?, ?, ?)",
                    (sid, answer, chunks, status, duration_ms, now),
                )
                mid = cur.lastrowid
                conn.execute(
                    "UPDATE sessions SET latest_question=?, updated_at=? WHERE id=?",
                    (question, now, sid),
                )
            return mid

    def insert_qc_turn(
        self,
        contact: str,
        question: str,
        replies: list[dict],
        *,
        duration_ms: Optional[int] = None,
        source_chunks: Optional[list[dict]] = None,
    ) -> int:
        """写入一轮"带质检"的问答。

        replies 是依次产出的 AI 回复条目（同序展示），例如：
          [
            {"status": "blocked", "content": "...", "qa_reason": "涉嫌..."},
            {"status": "sent",    "content": "...", "qa_reason": None},
          ]
        每条对应一条 assistant 消息；拦截的以 blocked 记录，最终通过的以 sent 记录。
        返回最后一条 assistant 消息 id。
        """
        now = int(time.time())
        chunks = json.dumps(source_chunks, ensure_ascii=False) if source_chunks else None
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT id FROM sessions WHERE contact=?", (contact,)
                ).fetchone()
                if row:
                    sid = row["id"]
                else:
                    cur = conn.execute(
                        "INSERT INTO sessions (contact, avatar_color, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?)",
                        (contact, "#4F46E5", now, now),
                    )
                    sid = cur.lastrowid
                conn.execute(
                    "INSERT INTO messages (session_id, role, content, source_chunks, status, duration_ms, created_at) "
                    "VALUES (?, 'user', ?, NULL, 'sent', NULL, ?)",
                    (sid, question, now),
                )
                mid = None
                for i, r in enumerate(replies):
                    d = duration_ms if i == len(replies) - 1 else None
                    cur = conn.execute(
                        "INSERT INTO messages (session_id, role, content, source_chunks, status, qa_reason, duration_ms, created_at) "
                        "VALUES (?, 'assistant', ?, ?, ?, ?, ?, ?)",
                        (sid, r.get("content", ""), chunks, r.get("status", "sent"),
                         r.get("qa_reason"), d, now),
                    )
                    mid = cur.lastrowid
                    now += 1  # 同轮多条按 1s 递增，保证按序展示
                conn.execute(
                    "UPDATE sessions SET latest_question=?, updated_at=? WHERE id=?",
                    (question, now, sid),
                )
            return mid

    def record_failure(
        self,
        contact: str,
        question: str,
        duration_ms: Optional[int] = None,
    ) -> int:
        """answer/send 异常时写一条 user 消息 + 一条 failed 的 assistant 占位。"""
        now = int(time.time())
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT id FROM sessions WHERE contact=?", (contact,)
                ).fetchone()
                if row:
                    sid = row["id"]
                else:
                    cur = conn.execute(
                        "INSERT INTO sessions (contact, avatar_color, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?)",
                        (contact, "#4F46E5", now, now),
                    )
                    sid = cur.lastrowid
                conn.execute(
                    "INSERT INTO messages (session_id, role, content, source_chunks, status, duration_ms, created_at) "
                    "VALUES (?, 'user', ?, NULL, 'sent', NULL, ?)",
                    (sid, question, now),
                )
                conn.execute(
                    "INSERT INTO messages (session_id, role, content, source_chunks, status, duration_ms, created_at) "
                    "VALUES (?, 'assistant', '', NULL, 'failed', ?, ?)",
                    (sid, duration_ms, now),
                )
                conn.execute(
                    "UPDATE sessions SET latest_question=?, updated_at=? WHERE id=?",
                    (question, now, sid),
                )
            return sid

    # ---------- 读 ----------
    def list_conversations(self) -> list[dict]:
        """会话列表，附各会话消息数，按更新时间倒序。

        latest_message 取该会话最新一条消息内容（不区分发送/接收方），
        保证列表预览始终是"最后一条消息"。
        """
        sql = """
            SELECT s.contact, s.avatar_color, s.updated_at,
                   (SELECT m.content FROM messages m
                     WHERE m.session_id = s.id
                     ORDER BY m.created_at DESC, m.id DESC LIMIT 1) AS latest_message,
                   COUNT(m.id) AS message_count
            FROM sessions s
            LEFT JOIN messages m ON m.session_id = s.id
            GROUP BY s.id
            ORDER BY s.updated_at DESC
        """
        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [
            {
                "contact": r["contact"],
                "avatar_color": r["avatar_color"],
                "latest_message": r["latest_message"] or "",
                "message_count": r["message_count"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]

    def get_conversation(self, contact: str) -> list[dict]:
        """某会话的完整时间线（按时间升序）。找不到会话返回 []。"""
        sql = """
            SELECT m.id, m.role, m.content, m.source_chunks, m.status,
                   m.qa_reason, m.duration_ms, m.created_at
            FROM messages m
            JOIN sessions s ON s.id = m.session_id
            WHERE s.contact = ?
            ORDER BY m.created_at ASC, m.id ASC
        """
        with self._connect() as conn:
            rows = conn.execute(sql, (contact,)).fetchall()
        out = []
        for r in rows:
            chunks = None
            if r["source_chunks"]:
                try:
                    chunks = json.loads(r["source_chunks"])
                except json.JSONDecodeError:
                    chunks = None
            out.append(
                {
                    "id": r["id"],
                    "role": r["role"],
                    "content": r["content"],
                    "source_chunks": chunks,
                    "status": r["status"],
                    "qa_reason": r["qa_reason"],
                    "duration_ms": r["duration_ms"],
                    "created_at": r["created_at"],
                }
            )
        return out

    def stats(self) -> dict:
        """聚合统计：会话数/消息数/AI回复数/成功率/平均耗时/今日·7日（按 day0=今天 00:00 对齐）。"""
        now = int(time.time())
        day = 86400
        today = now - (now % day)  # 今日 00:00（按 UTC 对齐，够用）
        week = today - 6 * day     # 最近 7 个自然日
        with self._connect() as conn:
            total_sessions = conn.execute("SELECT COUNT(*) c FROM sessions").fetchone()["c"]
            total_messages = conn.execute("SELECT COUNT(*) c FROM messages").fetchone()["c"]
            ai_replies = conn.execute(
                "SELECT COUNT(*) c FROM messages WHERE role='assistant'"
            ).fetchone()["c"]
            sent = conn.execute(
                "SELECT COUNT(*) c FROM messages WHERE role='assistant' AND status='sent'"
            ).fetchone()["c"]
            failed = conn.execute(
                "SELECT COUNT(*) c FROM messages WHERE role='assistant' AND status='failed'"
            ).fetchone()["c"]
            avg_dur = conn.execute(
                "SELECT AVG(duration_ms) a FROM messages WHERE role='assistant' AND duration_ms IS NOT NULL"
            ).fetchone()["a"]
            today_messages = conn.execute(
                "SELECT COUNT(*) c FROM messages WHERE created_at >= ?", (today,)
            ).fetchone()["c"]
            week_messages = conn.execute(
                "SELECT COUNT(*) c FROM messages WHERE created_at >= ?", (week,)
            ).fetchone()["c"]
        denom = sent + failed
        success_rate = round(sent / denom, 4) if denom else 0.0
        return {
            "total_conversations": total_sessions,
            "total_messages": total_messages,
            "ai_replies": ai_replies,
            "success_rate": success_rate,
            "avg_duration_ms": round(avg_dur, 1) if avg_dur else 0.0,
            "today_messages": today_messages,
            "week_messages": week_messages,
        }

    def count_messages(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) c FROM messages").fetchone()["c"]

    # ---------- 示例数据 ----------
    def seed_demo(self, n: int = 3) -> None:
        """首次建库自动插入 n 条专业感示例会话（客户→AI 回复）。"""
        now = int(time.time())
        demos = [
            {
                "contact": "王总",
                "avatar_color": "#4F46E5",
                "hours_ago": 2,
                "turns": [
                    ("user", "咱们上次说的那批订单，报价方案定了吗？"),
                    ("assistant", "定了哈王总，方案我整理好了，按之前沟通的梯度给了两档，我发你确认下就行。"),
                    ("user", "行，那就按基础那档先走"),
                    ("assistant", "好勒，基础档这就给你出合同，PDF 今天下班前发你邮箱。"),
                ],
            },
            {
                "contact": "李经理",
                "avatar_color": "#0EA5E9",
                "hours_ago": 8,
                "turns": [
                    ("user", "上次你说交付周期大概多久来着？"),
                    ("assistant", "李经理，常规单子从下单到交付大概 5~7 个工作日，急单可以加急，我安排一下。"),
                    ("user", "那测试报告能随货一起给吗"),
                    ("assistant", "可以的，报告和货一起出，我们会附上项目对应的测试记录和通过结论。"),
                ],
            },
            {
                "contact": "K 姐",
                "avatar_color": "#F59E0B",
                "hours_ago": 26,
                "turns": [
                    ("user", "在吗，有个事想问问你"),
                    ("assistant", "在的在的，你说，我听着呢"),
                    ("user", "就是新品那批到货了吗？"),
                    ("assistant", "到了，刚到库，我给你先留着，你随时来提我帮你安排。"),
                ],
            },
        ]
        with self._lock:
            with self._connect() as conn:
                conn.executescript("BEGIN")
                try:
                    for d in demos[:n]:
                        created = now - int(d["hours_ago"] * 3600)
                        cur = conn.execute(
                            "INSERT INTO sessions (contact, avatar_color, created_at, updated_at) "
                            "VALUES (?, ?, ?, ?)",
                            (d["contact"], d["avatar_color"], created, created),
                        )
                        sid = cur.lastrowid
                        ts = created
                        for role, content in d["turns"]:
                            conn.execute(
                                "INSERT INTO messages (session_id, role, content, source_chunks, status, duration_ms, created_at) "
                                "VALUES (?, ?, ?, NULL, 'sent', NULL, ?)",
                                (sid, role, content, ts),
                            )
                            ts += 90  # 每条间隔 90 秒，模拟真实节奏
                        conn.execute(
                            "UPDATE sessions SET latest_question=?, updated_at=? WHERE id=?",
                            (d["turns"][-1][1], ts, sid),
                        )
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise