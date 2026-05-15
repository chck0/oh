"use client";

import {
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  ResponsiveContainer,
} from "recharts";

const LABELS: Record<string, string> = {
  transit:     "교통",
  convenience: "편의시설",
  education:   "교육",
  environment: "환경",
  safety:      "치안",
  infra:       "인프라",
};

export default function ScoreCard({ data }: { data: any }) {
  const radarData = Object.entries(data.categories).map(([key, value]) => ({
    subject: LABELS[key] ?? key,
    score: value,
    fullMark: 100,
  }));

  return (
    <div className="bg-white rounded-2xl shadow-md p-8 w-full max-w-md">
      <div className="text-center mb-6">
        <p className="text-gray-500 text-sm mb-1">종합 생활권 스코어</p>
        <p className="text-6xl font-bold text-blue-600">{data.total_score}</p>
        <p className="text-gray-400 text-xs mt-1">/ 100점</p>
      </div>

      <ResponsiveContainer width="100%" height={260}>
        <RadarChart data={radarData}>
          <PolarGrid />
          <PolarAngleAxis dataKey="subject" tick={{ fontSize: 12 }} />
          <Radar
            dataKey="score"
            stroke="#2563eb"
            fill="#2563eb"
            fillOpacity={0.25}
          />
        </RadarChart>
      </ResponsiveContainer>

      <div className="mt-6 space-y-2">
        {Object.entries(data.categories).map(([key, value]: any) => (
          <div key={key} className="flex items-center gap-3">
            <span className="text-sm text-gray-600 w-20">{LABELS[key]}</span>
            <div className="flex-1 bg-gray-100 rounded-full h-2">
              <div
                className="bg-blue-500 h-2 rounded-full"
                style={{ width: `${value}%` }}
              />
            </div>
            <span className="text-sm font-medium w-10 text-right">{value}점</span>
          </div>
        ))}
      </div>
    </div>
  );
}
