import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Smart CRM",
  description: "对话智能后台",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
