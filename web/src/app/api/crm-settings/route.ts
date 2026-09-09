import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.FASTAPI_URL || "http://localhost:8000";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const res = await fetch(`${API_URL}/api/crm-settings`, {
      cache: "no-store",
    });
    return NextResponse.json(await res.json(), { status: res.ok ? 200 : 500 });
  } catch (error) {
    console.error("CRM settings GET error:", error);
    return NextResponse.json(
      { error: "无法连接到后端服务" },
      { status: 500 }
    );
  }
}

export async function PUT(req: NextRequest) {
  try {
    const body = await req.json();
    const res = await fetch(`${API_URL}/api/crm-settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    return NextResponse.json(await res.json(), { status: res.ok ? 200 : 500 });
  } catch (error) {
    console.error("CRM settings PUT error:", error);
    return NextResponse.json(
      { error: "无法连接到后端服务" },
      { status: 500 }
    );
  }
}