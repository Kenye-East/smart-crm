"use client";

import { useState } from "react";

type Mode = "agent" | "rag";

interface ExecutionStep {
  step: number;
  type: string;
  content?: string;
  tool_name?: string;
  arguments?: Record<string, unknown>;
  result?: string;
  sources?: RagSource[];
  timestamp: string;
}

interface RagSource {
  source: string;
  content: string;
  score: number;
}

interface ConversationEntry {
  id: string;
  mode: Mode;
  userMessage: string;
  steps: ExecutionStep[];
  finalResponse: string;
  sources?: RagSource[];
  rawResponse: unknown;
}

export default function Home() {
  const [mode, setMode] = useState<Mode>("rag");
  const [message, setMessage] = useState("");
  const [conversations, setConversations] = useState<ConversationEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!message.trim() || loading) return;

    const userMessage = message.trim();
    setMessage("");
    setLoading(true);

    try {
      const url =
        mode === "rag"
          ? "http://localhost:8000/api/rag/query"
          : "http://localhost:8000/api/chat";
      const body =
        mode === "rag"
          ? JSON.stringify({ question: userMessage })
          : JSON.stringify({ message: userMessage });

      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
      });
      const data = await res.json();

      const entry: ConversationEntry = {
        id: Date.now().toString(),
        mode,
        userMessage,
        steps: data.steps,
        finalResponse: mode === "rag" ? data.answer : data.response,
        sources: data.sources,
        rawResponse: data,
      };
      setConversations((prev) => [...prev, entry]);
    } catch (err) {
      console.error("请求失败:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async () => {
    if (mode === "agent") {
      try {
        await fetch("http://localhost:8000/api/reset", { method: "POST" });
      } catch (err) {
        console.error("重置失败:", err);
      }
    }
    setConversations([]);
    setMessage("");
  };

  const getTypeLabel = (type: string) => {
    switch (type) {
      case "reasoning":
        return "推理";
      case "thinking":
        return "思考";
      case "tool_call":
        return "工具调用";
      case "retrieval":
        return "检索";
      case "response":
        return "回复";
      default:
        return "未知";
    }
  };

  return (
    <div className="min-h-screen bg-white">
      {/* 顶部输入区 */}
      <div className="sticky top-0 z-10 bg-white/80 backdrop-blur-xl border-b border-gray-200">
        <div className="max-w-3xl mx-auto px-6 py-4">
          {/* 模式切换 */}
          <div className="flex gap-2 mb-3">
            <button
              onClick={() => setMode("rag")}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                mode === "rag"
                  ? "bg-gray-900 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              RAG 问答
            </button>
            <button
              onClick={() => setMode("agent")}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                mode === "agent"
                  ? "bg-gray-900 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              Agent 对话
            </button>
          </div>

          <form onSubmit={handleSubmit} className="flex gap-3">
            <input
              type="text"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder={
                mode === "rag" ? "基于知识库提问..." : "输入消息..."
              }
              className="flex-1 px-4 py-2.5 bg-gray-100 rounded-xl text-gray-900 placeholder-gray-400 text-base focus:outline-none focus:ring-2 focus:ring-gray-300 transition-all"
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || !message.trim()}
              className="px-5 py-2.5 bg-gray-900 text-white rounded-xl text-base font-medium hover:bg-gray-800 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? "..." : "发送"}
            </button>
            <button
              type="button"
              onClick={handleReset}
              className="px-4 py-2.5 text-gray-500 rounded-xl text-base hover:bg-gray-100 transition-colors"
            >
              重置
            </button>
          </form>
        </div>
      </div>

      {/* 对话列表 */}
      <div className="max-w-3xl mx-auto px-6 py-8 space-y-10">
        {conversations.length === 0 && (
          <div className="text-center py-20">
            <p className="text-gray-400 text-base">
              {mode === "rag"
                ? "基于知识库提问，回答会附带来源引用"
                : "输入消息开始对话"}
            </p>
          </div>
        )}

        {conversations.map((entry) => (
          <div key={entry.id} className="space-y-4">
            {/* 用户消息 */}
            <div className="flex justify-end">
              <div className="bg-gray-900 text-white px-4 py-2.5 rounded-2xl rounded-br-md max-w-[80%] text-base">
                {entry.userMessage}
              </div>
            </div>

            {/* 执行步骤 */}
            <div className="space-y-3">
              {entry.steps.map((step) => (
                <div key={step.step} className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-gray-400 uppercase tracking-wider">
                      {getTypeLabel(step.type)}
                    </span>
                    <div className="flex-1 h-px bg-gray-100" />
                  </div>

                  {step.type === "reasoning" && (
                    <div className="bg-gray-50 rounded-xl px-4 py-3">
                      <p className="text-gray-400 text-sm leading-relaxed italic">
                        {step.content}
                      </p>
                    </div>
                  )}

                  {step.type === "thinking" && (
                    <div className="bg-gray-50 rounded-xl px-4 py-3">
                      <p className="text-gray-600 text-base leading-relaxed">
                        {step.content}
                      </p>
                    </div>
                  )}

                  {step.type === "tool_call" && (
                    <div className="bg-gray-50 rounded-xl px-4 py-3 space-y-2">
                      <div className="flex items-center gap-2">
                        <code className="text-sm font-mono text-gray-900 font-medium">
                          {step.tool_name}
                        </code>
                        <code className="text-sm font-mono text-gray-400">
                          ({JSON.stringify(step.arguments)})
                        </code>
                      </div>
                      <div className="h-px bg-gray-200" />
                      <p className="text-gray-600 text-base">{step.result}</p>
                    </div>
                  )}

                  {step.type === "retrieval" && (
                    <div className="bg-gray-50 rounded-xl px-4 py-3 space-y-2">
                      <p className="text-gray-500 text-sm">
                        {step.content}
                      </p>
                      {step.sources && (
                        <div className="space-y-1.5">
                          {step.sources.map((src, i) => (
                            <div
                              key={i}
                              className="flex items-start gap-2 text-xs"
                            >
                              <span className="text-gray-400 font-mono shrink-0">
                                {src.score.toFixed(4)}
                              </span>
                              <span className="text-gray-500 truncate">
                                {src.source}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {step.type === "response" && (
                    <div className="bg-gray-50 rounded-xl px-4 py-3">
                      <p className="text-gray-900 text-base leading-relaxed">
                        {step.content}
                      </p>
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* RAG 来源引用 */}
            {entry.mode === "rag" && entry.sources && entry.sources.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-gray-400 uppercase tracking-wider">
                    来源引用
                  </span>
                  <div className="flex-1 h-px bg-gray-100" />
                </div>
                {entry.sources.map((src, i) => (
                  <div
                    key={i}
                    className="bg-blue-50/50 border border-blue-100 rounded-xl px-4 py-3"
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-xs font-medium text-blue-700">
                        {src.source}
                      </span>
                      <span className="text-xs text-blue-400 font-mono">
                        相关度 {src.score.toFixed(4)}
                      </span>
                    </div>
                    <p className="text-gray-600 text-sm leading-relaxed line-clamp-3">
                      {src.content}
                    </p>
                  </div>
                ))}
              </div>
            )}

            {/* 展开原始数据 */}
            <div>
              <button
                onClick={() =>
                  setExpandedId(expandedId === entry.id ? null : entry.id)
                }
                className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
              >
                {expandedId === entry.id
                  ? "收起原始数据"
                  : "查看原始数据"}
              </button>

              {expandedId === entry.id && (
                <div className="mt-2 bg-gray-50 rounded-xl p-4">
                  <pre className="text-xs font-mono text-gray-500 whitespace-pre-wrap break-all">
                    {JSON.stringify(entry.rawResponse, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
