import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.FASTAPI_URL || "http://localhost:8000";

export async function POST() {
  try {
    const res = await fetch(`${API_URL}/api/reset`, {
      method: "POST",
    });

    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Reset API error:", error);
    return NextResponse.json(
      { error: "无法连接到后端服务" },
      { status: 500 }
    );
  }
}
