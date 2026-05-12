import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "생활권 스코어",
  description: "내 기준으로 동네를 점수화합니다",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="bg-gray-50 text-gray-900">{children}</body>
    </html>
  );
}
