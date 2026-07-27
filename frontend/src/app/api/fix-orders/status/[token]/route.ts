import { NextRequest, NextResponse } from "next/server";

const API_BASE = "https://sublime-illumination-production-5373.up.railway.app";

export async function GET(request: NextRequest, { params }: { params: Promise<{ token: string }> }) {
  try {
    const { token } = await params;
    const res = await fetch(`${API_BASE}/api/fix-orders/status/${token}`);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    console.error("Fix orders status proxy error:", error);
    return NextResponse.json({ detail: "Service unavailable" }, { status: 502 });
  }
}