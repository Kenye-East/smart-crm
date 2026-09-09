import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.FASTAPI_URL || "http://localhost:8000";

export const dynamic = "force-dynamic";

export async function GET(
  req: NextRequest,
  context: { params: Promise<{ contact: string }> }
) {
  try {
    const { contact } = await context.params;
    const decoded = decodeURIComponent(contact);
    // /api/chat-history/stats  命中 FastAPI 的 stats 聚合接口，而非当作 contact
    const target =
      decoded === "stats"
        ? `${API_URL}/api/chat-history/stats`
        : `${API_URL}/api/chat-history/conversations/${encodeURIComponent(
            decoded
          )}`;
    const res = await fetch(target, { cache: "no-store" });
    return NextResponse.json(await res.json(), { status: res.ok ? 200 : 500 });
  } catch (error) {
    console.error("Chat history detail API error:", error);
    return NextResponse.json(
      { error: "无法连接到后端服务" },
      { status: 500 }
    );
  }
}