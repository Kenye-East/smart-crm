import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.FASTAPI_URL || "http://localhost:8000";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const res = await fetch(`${API_URL}/api/knowledge/list`, {
      cache: "no-store",
    });
    return NextResponse.json(await res.json(), { status: res.ok ? 200 : 500 });
  } catch (error) {
    console.error("Knowledge list error:", error);
    return NextResponse.json(
      { error: "无法连接到后端服务" },
      { status: 500 }
    );
  }
}

export async function POST(req: NextRequest) {
  try {
    const fd = await req.formData(); // multipart 解析，整体转发给 FastAPI
    const res = await fetch(`${API_URL}/api/knowledge/upload`, {
      method: "POST",
      body: fd,
      cache: "no-store",
    });
    return NextResponse.json(await res.json(), { status: res.ok ? 200 : 500 });
  } catch (error) {
    console.error("Knowledge upload error:", error);
    return NextResponse.json(
      { error: "无法连接到后端服务" },
      { status: 500 }
    );
  }
}