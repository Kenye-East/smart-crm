import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.FASTAPI_URL || "http://localhost:8000";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const res = await fetch(`${API_URL}/api/chat-history/conversations`, {
      cache: "no-store",
    });
    return NextResponse.json(await res.json(), { status: res.ok ? 200 : 500 });
  } catch (error) {
    console.error("Chat history API error:", error);
    return NextResponse.json(
      { error: "无法连接到后端服务" },
      { status: 500 }
    );
  }
}