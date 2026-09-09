"use client";

import { useEffect, useRef, useState } from "react";

/* ---------- 类型 ---------- */
interface Conversation {
  contact: string;
  avatar_color: string;
  latest_message: string;
  message_count: number;
  updated_at: number;
}

interface MessageItem {
  id: number;
  role: "user" | "assistant";
  content: string;
  source_chunks: {
    source: string;
    score?: number;
    content?: string;
  }[] | null;
  status: string;
  qa_reason: string | null;
  duration_ms: number | null;
  created_at: number;
}

interface Stats {
  total_conversations: number;
  total_messages: number;
  ai_replies: number;
  success_rate: number;
  avg_duration_ms: number;
  today_messages: number;
  week_messages: number;
}

interface Settings {
  target_contacts: string[];
  poll_interval: number;
  quality_enabled: boolean;
  wechat_system_prompt: string;
  rag_system_prompt: string;
  quality_system_prompt: string;
}

interface KnowledgeFile {
  name: string;
  size: number;
  mtime: number;
}

interface RebuildStatus {
  running: boolean;
  last_status?: { documents: number; chunks: number; status: string } | null;
  last_error?: string | null;
  last_at?: number | null;
}

const NAV_ITEMS = ["对话记录", "会话成员", "知识库", "设置"];

const EMPTY_STATS: Stats = {
  total_conversations: 0,
  total_messages: 0,
  ai_replies: 0,
  success_rate: 0,
  avg_duration_ms: 0,
  today_messages: 0,
  week_messages: 0,
};

function formatTime(sec: number): string {
  const d = new Date(sec * 1000);
  const now = new Date();
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
    });
  }
  return (
    d.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" }) +
    " " +
    d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/* ---------- 对话记录面板（原功能） ---------- */
function ConversationsPanel(props: {
  stats: Stats;
  conversations: Conversation[];
  loadingList: boolean;
  selected: string | null;
  onSelect: (contact: string) => void;
  timeline: MessageItem[];
  loadingTimeline: boolean;
  openRef: React.MutableRefObject<Record<number, boolean>>;
}) {
  const {
    stats,
    conversations,
    loadingList,
    selected,
    onSelect,
    timeline,
    loadingTimeline,
    openRef,
  } = props;

  return (
    <div className="grid grid-cols-[340px_1fr] gap-6 min-h-[60vh]">
      {/* 会话列表 */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden flex flex-col">
        <div className="px-4 py-3 border-b border-slate-100 text-sm font-medium text-slate-600">
          会话列表
        </div>
        <div className="flex-1 overflow-y-auto">
          {loadingList ? (
            <div className="p-6 text-center text-sm text-slate-400">加载中…</div>
          ) : conversations.length === 0 ? (
            <div className="p-6 text-center text-sm text-slate-400">
              暂无会话记录
            </div>
          ) : (
            conversations.map((conv) => (
              <button
                key={conv.contact}
                onClick={() => onSelect(conv.contact)}
                className={`w-full text-left px-4 py-3 border-b border-slate-50 transition-colors hover:bg-slate-50 ${
                  selected === conv.contact ? "bg-indigo-50" : ""
                }`}
              >
                <div className="flex items-center gap-3">
                  <div
                    className="w-9 h-9 rounded-full flex items-center justify-center text-white text-sm font-medium shrink-0"
                    style={{ backgroundColor: conv.avatar_color }}
                  >
                    {conv.contact.slice(0, 1)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-slate-800 truncate">
                        {conv.contact}
                      </span>
                      <span className="text-xs text-slate-400 shrink-0">
                        {formatTime(conv.updated_at)}
                      </span>
                    </div>
                    <div className="text-xs text-slate-500 truncate mt-0.5">
                      {conv.latest_message || "—"}
                    </div>
                  </div>
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* 对话时间线 */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm flex flex-col overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
          <div className="text-sm font-medium text-slate-600">
            {selected ? (
              <>
                <span className="text-slate-800">{selected}</span>
                <span className="text-slate-400 ml-2">
                  {timeline.length} 条消息
                </span>
              </>
            ) : (
              "选择左侧会话查看对话详情"
            )}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-slate-50/50">
          {loadingTimeline ? (
            <div className="text-center text-sm text-slate-400 py-10">加载中…</div>
          ) : selected && timeline.length === 0 ? (
            <div className="text-center text-sm text-slate-400 py-10">
              暂无消息
            </div>
          ) : selected === null ? (
            <div className="text-center text-sm text-slate-400 py-16">
              ← 从左侧选择一个会话，查看 AI 自动回复的完整过程
            </div>
          ) : (
            timeline.map((msg) => {
              const isAI = msg.role === "assistant";
              const showRefs = openRef.current[msg.id];
              return (
                <div
                  key={msg.id}
                  className={`flex ${isAI ? "justify-start" : "justify-end"}`}
                >
                  <div
                    className={`max-w-[75%] ${
                      isAI
                        ? "bg-white border border-slate-200 rounded-2xl rounded-bl-md px-4 py-2.5"
                        : "bg-indigo-600 text-white rounded-2xl rounded-br-md px-4 py-2.5"
                    }`}
                  >
                    <div className="text-xs flex items-center gap-2 mb-1">
                      <span
                        className={
                          isAI ? "text-indigo-600 font-medium" : "text-indigo-200"
                        }
                      >
                        {isAI ? "AI 回复" : selected}
                      </span>
                      <span
                        className={
                          isAI ? "text-slate-400" : "text-indigo-200/80"
                        }
                      >
                        {formatTime(msg.created_at)}
                      </span>
                      {isAI && (
                        <span
                          className={`text-[10px] px-1.5 py-0.5 rounded ${
                            msg.status === "sent"
                              ? "bg-emerald-50 text-emerald-600"
                              : msg.status === "failed"
                              ? "bg-red-50 text-red-600"
                              : msg.status === "blocked"
                              ? "bg-amber-50 text-amber-600"
                              : "bg-slate-100 text-slate-500"
                          }`}
                        >
                          {msg.status === "sent"
                            ? "已发送"
                            : msg.status === "failed"
                            ? "失败"
                            : msg.status === "blocked"
                            ? "已拦截"
                            : "跳过"}
                        </span>
                      )}
                    </div>
                    <p
                      className={`text-sm leading-relaxed break-words ${
                        isAI ? "text-slate-800" : "text-white"
                      }`}
                    >
                      {msg.content || (
                        <span
                          className={
                            isAI ? "text-slate-400" : "text-indigo-200/80"
                          }
                        >
                          （发送失败，无内容）
                        </span>
                      )}
                    </p>
                    {isAI &&
                      msg.status === "blocked" &&
                      msg.qa_reason && (
                        <div className="mt-1.5 flex gap-1.5">
                          <span className="text-[10px] px-1.5 py-0.5 bg-amber-500/10 text-amber-600 rounded">
                            质检拦截
                          </span>
                          <span className="text-xs text-amber-600/90">
                            {msg.qa_reason}
                          </span>
                        </div>
                      )}
                    {isAI &&
                      msg.source_chunks &&
                      msg.source_chunks.length > 0 && (
                        <div className="mt-2">
                          <button
                            onClick={() =>
                              (openRef.current[msg.id] = !showRefs)
                            }
                            className="text-xs text-blue-500 hover:text-blue-700"
                          >
                            {showRefs ? "收起引用来源" : "查看引用来源"}
                          </button>
                          {showRefs && (
                            <div className="mt-2 space-y-1.5">
                              {msg.source_chunks.map((src, i) => (
                                <div
                                  key={i}
                                  className="bg-blue-50 border border-blue-100 rounded-lg px-3 py-2"
                                >
                                  <div className="flex items-center justify-between">
                                    <span className="text-xs font-medium text-blue-700">
                                      {src.source}
                                    </span>
                                    {typeof src.score === "number" && (
                                      <span className="text-xs text-blue-400 font-mono">
                                        {src.score.toFixed(4)}
                                      </span>
                                    )}
                                  </div>
                                  {src.content && (
                                    <p className="text-xs text-slate-600 mt-1 leading-relaxed line-clamp-2">
                                      {src.content}
                                    </p>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}

/* ---------- 会话成员面板 ---------- */
function MembersPanel(props: {
  settings: Settings | null;
  onSave: (patch: Partial<Settings>) => Promise<boolean>;
}) {
  const { settings, onSave } = props;
  const [input, setInput] = useState("");
  const [names, setNames] = useState<string[]>([]);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (settings) setNames(settings.target_contacts || []);
  }, [settings]);

  const addName = () => {
    const v = input.trim();
    if (v && !names.includes(v)) setNames([...names, v]);
    setInput("");
  };

  const save = async () => {
    if (names.length === 0) {
      setMsg("至少保留一个检测人名");
      return;
    }
    const ok = await onSave({ target_contacts: names });
    setMsg(ok ? "保存成功，下次启动 RPA 生效" : "保存失败");
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm px-6 py-5 max-w-2xl">
      <div className="text-sm font-medium text-slate-800 mb-1">检测人名</div>
      <p className="text-sm text-slate-500 mb-4">
        自动回复这些联系人的消息（会话名包含任意关键词即命中）。
      </p>
      <div className="flex flex-wrap gap-2 mb-4">
        {names.map((n) => (
          <span
            key={n}
            className="inline-flex items-center gap-1.5 bg-indigo-50 text-indigo-700 text-sm rounded-lg pl-3 pr-1.5 py-1"
          >
            {n}
            <button
              onClick={() => setNames(names.filter((x) => x !== n))}
              className="text-indigo-400 hover:text-indigo-700"
            >
              ×
            </button>
          </span>
        ))}
        {(names.length === 0 || true) && (
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addName();
              }
            }}
            placeholder="输入人名后回车添加"
            className="px-3 py-1 text-sm bg-slate-100 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300 placeholder-slate-400"
          />
        )}
      </div>
      <div className="flex items-center gap-3">
        <button
          onClick={save}
          className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-500 transition-colors"
        >
          保存
        </button>
        {msg && <span className="text-sm text-slate-500">{msg}</span>}
      </div>
    </div>
  );
}

/* ---------- 知识库面板 ---------- */
function KnowledgePanel() {
  const [files, setFiles] = useState<KnowledgeFile[]>([]);
  const [status, setStatus] = useState<RebuildStatus>({ running: false });
  const [msg, setMsg] = useState("");

  const loadList = async () => {
    try {
      const res = await fetch("/api/knowledge");
      if (res.ok) setFiles(await res.json());
    } catch {
      /* ignore */
    }
  };
  const loadStatus = async () => {
    try {
      const res = await fetch("/api/knowledge/status");
      if (res.ok) setStatus(await res.json());
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    loadList();
    loadStatus();
  }, []);

  // 索引中轮询状态
  useEffect(() => {
    if (!status.running) return;
    const timer = setInterval(loadStatus, 2000);
    return () => clearInterval(timer);
  }, [status.running]);

  const upload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const filesSel = Array.from(e.target.files || []);
    if (filesSel.length === 0) return;
    setMsg("");
    const fd = new FormData();
    for (const f of filesSel) fd.append("file", f);
    try {
      const res = await fetch("/api/knowledge", {
        method: "POST",
        body: fd,
      });
      const data = await res.json();
      if (res.ok) {
        setMsg(`已上传 ${data.filename}，正在后台索引…`);
        loadStatus();
      } else {
        setMsg("上传失败");
      }
    } catch {
      setMsg("上传失败：后端未连接");
    }
    e.target.value = "";
    setTimeout(loadList, 1500);
  };

  return (
    <div className="max-w-2xl space-y-6">
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm px-6 py-5">
        <div className="text-sm font-medium text-slate-800 mb-1">上传文档</div>
        <p className="text-sm text-slate-500 mb-4">
          支持 PDF / TXT / Markdown 等，上传后自动重建向量索引，AI 即可引用新内容。
        </p>
        <label className="inline-flex items-center gap-2 px-4 py-2 cursor-pointer bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-500 transition-colors">
          选择文件上传
          <input
            type="file"
            multiple
            onChange={upload}
            className="hidden"
          />
        </label>
        {msg && <div className="text-sm text-slate-500 mt-3">{msg}</div>}
        {status.running && (
          <div className="mt-3 flex items-center gap-2 text-sm text-indigo-600">
            <span className="inline-block w-3 h-3 border-2 border-indigo-300 border-t-indigo-600 rounded-full animate-spin" />
            向量库索引中…
          </div>
        )}
        {status.last_error && (
          <div className="mt-3 text-sm text-red-600">索引失败：{status.last_error}</div>
        )}
      </div>

      <div className="bg-white border border-slate-200 rounded-xl shadow-sm px-6 py-5">
        <div className="text-sm font-medium text-slate-800 mb-3">知识库文件</div>
        {files.length === 0 ? (
          <div className="text-sm text-slate-400">暂无文件</div>
        ) : (
          <ul className="divide-y divide-slate-100">
            {files.map((f) => (
              <li key={f.name} className="flex items-center justify-between py-2">
                <span className="text-sm text-slate-700">{f.name}</span>
                <span className="text-xs text-slate-400">
                  {formatSize(f.size)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/* ---------- 设置面板 ---------- */
function SettingsPanel(props: {
  settings: Settings | null;
  onSave: (patch: Partial<Settings>) => Promise<boolean>;
}) {
  const { settings, onSave } = props;
  const [interval, setInterval] = useState(15);
  const [qualityEnabled, setQualityEnabled] = useState(true);
  const [wechatPrompt, setWechatPrompt] = useState("");
  const [ragPrompt, setRagPrompt] = useState("");
  const [qualityPrompt, setQualityPrompt] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (settings) {
      setInterval(settings.poll_interval);
      setQualityEnabled(settings.quality_enabled);
      setWechatPrompt(settings.wechat_system_prompt || "");
      setRagPrompt(settings.rag_system_prompt || "");
      setQualityPrompt(settings.quality_system_prompt || "");
    }
  }, [settings]);

  const save = async () => {
    const val = Number(interval);
    if (!val || val <= 0) {
      setMsg("读取间隔须大于 0");
      return;
    }
    const ok = await onSave({
      poll_interval: val,
      quality_enabled: qualityEnabled,
      wechat_system_prompt: wechatPrompt,
      rag_system_prompt: ragPrompt,
      quality_system_prompt: qualityPrompt,
    });
    setMsg(ok ? "保存成功，下次启动 RPA 生效" : "保存失败");
  };

  return (
    <div className="max-w-2xl space-y-6">
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm px-6 py-5">
        <label className="block text-sm font-medium text-slate-800 mb-2">
          检测间隔（秒）
        </label>
        <p className="text-sm text-slate-500 mb-3">
          自动回复扫描会话列表的频率。
        </p>
        <input
          type="number"
          min={1}
          value={interval}
          onChange={(e) => setInterval(e.target.value as unknown as number)}
          className="px-3 py-2 bg-slate-100 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 w-40"
        />
      </div>

      <div className="bg-white border border-slate-200 rounded-xl shadow-sm px-6 py-5">
        <label className="block text-sm font-medium text-slate-800 mb-2">
          发送前质检
        </label>
        <p className="text-sm text-slate-500 mb-3">
          发送前用质检 Agent 审查回复，命中高危（黄赌毒、诈骗、泄密、辱骂威胁等）即拦截并重新生成。
        </p>
        <label className="inline-flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={qualityEnabled}
            onChange={(e) => setQualityEnabled(e.target.checked)}
            className="w-4 h-4 text-indigo-600"
          />
          <span className="text-sm text-slate-700">启用发送前质检</span>
        </label>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl shadow-sm px-6 py-5">
        <label className="block text-sm font-medium text-slate-800 mb-2">
          对话自动回复提示词（system prompt）
        </label>
        <p className="text-sm text-slate-500 mb-3">
          控制替你在聊天中回复的口吻。留空则用默认人设。
        </p>
        <textarea
          value={wechatPrompt}
          onChange={(e) => setWechatPrompt(e.target.value)}
          rows={6}
          className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-800 font-mono focus:outline-none focus:ring-2 focus:ring-indigo-300"
        />
      </div>

      <div className="bg-white border border-slate-200 rounded-xl shadow-sm px-6 py-5">
        <label className="block text-sm font-medium text-slate-800 mb-2">
          质检 Agent 提示词（system prompt）
        </label>
        <p className="text-sm text-slate-500 mb-3">
          控制质检 Agent 的审查标准。留空则用默认拦截规则。
        </p>
        <textarea
          value={qualityPrompt}
          onChange={(e) => setQualityPrompt(e.target.value)}
          rows={6}
          className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-800 font-mono focus:outline-none focus:ring-2 focus:ring-indigo-300"
        />
      </div>

      <div className="bg-white border border-slate-200 rounded-xl shadow-sm px-6 py-5">
        <label className="block text-sm font-medium text-slate-800 mb-2">
          RAG 问答提示词（system prompt）
        </label>
        <p className="text-sm text-slate-500 mb-3">
          控制基于知识库回答的风格。留空则用默认。
        </p>
        <textarea
          value={ragPrompt}
          onChange={(e) => setRagPrompt(e.target.value)}
          rows={6}
          className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-800 font-mono focus:outline-none focus:ring-2 focus:ring-indigo-300"
        />
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={save}
          className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-500 transition-colors"
        >
          保存
        </button>
        {msg && <span className="text-sm text-slate-500">{msg}</span>}
      </div>
    </div>
  );
}

/* ---------- 主页面 ---------- */
export default function CrmPage() {
  const [activeNav, setActiveNav] = useState("对话记录");
  const [stats, setStats] = useState<Stats>(EMPTY_STATS);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<MessageItem[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingTimeline, setLoadingTimeline] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const openRef = useRef<Record<number, boolean>>({});

  const [settings, setSettings] = useState<Settings | null>(null);

  const loadOverview = async () => {
    try {
      const [convRes, statsRes] = await Promise.all([
        fetch("/api/chat-history"),
        fetch("/api/chat-history/stats"),
      ]);
      if (!convRes.ok || !statsRes.ok) throw new Error();
      setConversations(await convRes.json());
      setStats(await statsRes.json());
      setError(null);
    } catch {
      setError("无法连接后端服务，请确认 FastAPI 已启动");
    } finally {
      setLoadingList(false);
    }
  };

  const loadSettings = async () => {
    try {
      const res = await fetch("/api/crm-settings");
      if (res.ok) setSettings(await res.json());
    } catch {
      /* 忽略，面板内显示默认 */
    }
  };

  useEffect(() => {
    loadOverview();
    loadSettings();
    const timer = setInterval(loadOverview, 30000);
    return () => clearInterval(timer);
  }, []);

  const openConversation = async (contact: string) => {
    setSelected(contact);
    setTimeline([]);
    setLoadingTimeline(true);
    openRef.current = {};
    try {
      const res = await fetch(`/api/chat-history/${encodeURIComponent(contact)}`);
      if (!res.ok) throw new Error();
      setTimeline(await res.json());
      setError(null);
    } catch {
      setError("加载会话详情失败");
    } finally {
      setLoadingTimeline(false);
    }
  };

  const saveSettings = async (patch: Partial<Settings>): Promise<boolean> => {
    try {
      const res = await fetch("/api/crm-settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      if (!res.ok) return false;
      setSettings({ ...(settings ?? {} as Settings), ...patch });
      return true;
    } catch {
      return false;
    }
  };

  const statsCards = [
    { label: "会话数", value: String(stats.total_conversations), accent: "text-indigo-600" },
    { label: "消息数", value: String(stats.total_messages), accent: "text-sky-600" },
    { label: "发送成功率", value: `${(stats.success_rate * 100).toFixed(0)}%`, accent: "text-emerald-600" },
    { label: "平均响应", value: stats.avg_duration_ms ? `${(stats.avg_duration_ms / 1000).toFixed(1)}s` : "—", accent: "text-amber-600" },
  ];

  const navTitle: Record<string, string> = {
    对话记录: "所有经由 AI 自动回复的对话",
    会话成员: "配置需要自动回复的检测人名",
    知识库: "上传文档并重建向量索引",
    设置: "运行参数与 AI 提示词配置",
  };

  return (
    <div className="flex h-screen bg-slate-50 text-slate-900 overflow-hidden">
      {/* 左侧导航外壳 */}
      <aside className="w-56 shrink-0 bg-slate-900 text-slate-300 flex flex-col">
        <div className="px-5 py-5 border-b border-slate-800">
          <div className="text-white text-lg font-semibold tracking-tight">
            Smart CRM
          </div>
          <div className="text-xs text-slate-500 mt-1">对话智能后台</div>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1">
          {NAV_ITEMS.map((item) => (
            <button
              key={item}
              onClick={() => setActiveNav(item)}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                activeNav === item
                  ? "bg-indigo-600 text-white"
                  : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
              }`}
            >
              {item}
            </button>
          ))}
        </nav>
        <div className="px-5 py-4 border-t border-slate-800 text-xs text-slate-500">
          当前页面：{activeNav}
        </div>
      </aside>

      {/* 主内容区 */}
      <main className="flex-1 flex flex-col min-w-0">
        <header className="px-6 py-4 bg-white border-b border-slate-200 flex items-center justify-between shrink-0">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">{activeNav}</h1>
            <p className="text-sm text-slate-500 mt-0.5">{navTitle[activeNav]}</p>
          </div>
          <div className="text-sm text-slate-500">
            今日{" "}
            <span className="font-medium text-slate-700">
              {stats.today_messages}
            </span>{" "}
            条 · 近7日{" "}
            <span className="font-medium text-slate-700">
              {stats.week_messages}
            </span>{" "}
            条
          </div>
        </header>

        <div className="p-6 space-y-6 overflow-auto">
          {/* 顶部统计卡片（全局保留） */}
          <div className="grid grid-cols-4 gap-4 shrink-0">
            {statsCards.map((c) => (
              <div
                key={c.label}
                className="bg-white border border-slate-200 rounded-xl px-5 py-4 shadow-sm"
              >
                <div className="text-sm text-slate-500">{c.label}</div>
                <div className={`mt-1 text-2xl font-semibold ${c.accent}`}>
                  {c.value}
                </div>
              </div>
            ))}
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3">
              {error}
            </div>
          )}

          {activeNav === "对话记录" && (
            <ConversationsPanel
              stats={stats}
              conversations={conversations}
              loadingList={loadingList}
              selected={selected}
              onSelect={openConversation}
              timeline={timeline}
              loadingTimeline={loadingTimeline}
              openRef={openRef}
            />
          )}

          {activeNav === "会话成员" && (
            <MembersPanel settings={settings} onSave={saveSettings} />
          )}

          {activeNav === "知识库" && <KnowledgePanel />}

          {activeNav === "设置" && (
            <SettingsPanel settings={settings} onSave={saveSettings} />
          )}
        </div>
      </main>
    </div>
  );
}