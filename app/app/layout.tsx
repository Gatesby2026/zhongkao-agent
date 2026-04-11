import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "中考数学学习规划 - 智能 Agent",
  description: "基于AI的中考数学个性化学习规划系统",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="bg-gray-50 min-h-screen">{children}</body>
    </html>
  );
}
