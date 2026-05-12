"use client";

import { RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer } from "recharts";

const LABELS: Record<string, string> = {
  transit:     "교통",
  convenience: "편의시설",
  education:   "교육",
  environment: "환경",
  safety:      "치안",
  infra:       "인프라",
};

const COLOR_MAP: Record<string, string> = {
  transit:     "bg-blue-500",
  convenience: "bg-emerald-500",
  education:   "bg-violet-500",
  environment: "bg-green-500",
  safety:      "bg-orange-400",
  infra:       "bg-gray-400",
};

function gradeLabel(score: number) {
  if (score >= 90) return { text: "최상", color: "text-blue-600 bg-blue-50" };
  if (score >= 75) return { text: "상",   color: "text-emerald-600 bg-emerald-50" };
  if (score >= 60) return { text: "중",   color: "text-yellow-600 bg-yellow-50" };
  return              { text: "하",   color: "text-red-500 bg-red-50" };
}

export default function ScoreCard({ data }: { data: any }) {
  const radarData = Object.entries(data.categories).map(([key, value]) => ({
    subject: LABELS[key] ?? key,
    score: value,
    fullMark: 100,
  }));

  const grade = gradeLabel(data.total_score);

  return (
    <div className="w-full max-w-md space-y-4">
      {/* 종합 점수 */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 text-center">
        <p className="text-sm text-gray-500 mb-1">종합 생활권 스코어</p>
        <div className="flex items-end justify-center gap-2">
          <span className="text-7xl font-bold text-blue-600">{data.total_score}</span>
          <span className="text-gray-400 text-lg mb-2">/ 100</span>
        </div>
        <span className={`inline-block mt-2 text-sm font-semibold px-3 py-1 rounded-full ${grade.color}`}>
          {grade.text}
        </span>
      </div>

      {/* 레이더 차트 */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
        <ResponsiveContainer width="100%" height={240}>
          <RadarChart data={radarData}>
            <PolarGrid stroke="#e5e7eb" />
            <PolarAngleAxis dataKey="subject" tick={{ fontSize: 12, fill: "#6b7280" }} />
            <Radar dataKey="score" stroke="#2563eb" fill="#2563eb" fillOpacity={0.2} strokeWidth={2} />
          </RadarChart>
        </ResponsiveContainer>
      </div>

      {/* 카테고리 바 */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 space-y-3">
        {Object.entries(data.categories).map(([key, value]: any) => (
          <div key={key} className="flex items-center gap-3">
            <span className="text-sm text-gray-600 w-16 shrink-0">{LABELS[key]}</span>
            <div className="flex-1 bg-gray-100 rounded-full h-2">
              <div
                className={`${COLOR_MAP[key] ?? "bg-blue-500"} h-2 rounded-full transition-all`}
                style={{ width: `${value}%` }}
              />
            </div>
            <span className="text-sm font-semibold text-gray-700 w-10 text-right">{value}점</span>
          </div>
        ))}
      </div>
    </div>
  );
}
