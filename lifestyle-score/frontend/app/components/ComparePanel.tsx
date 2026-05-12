"use client";

import { useState } from "react";
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer, Legend } from "recharts";

const LABELS: Record<string, string> = {
  transit: "교통", convenience: "편의시설", education: "교육",
  environment: "환경", safety: "치안", infra: "인프라",
};

const COLORS = ["#2563eb", "#10b981", "#f59e0b", "#ef4444"];

const PRESETS = [
  { label: "강남역", lat: "37.4979", lng: "127.0276" },
  { label: "홍대입구", lat: "37.5563", lng: "126.9228" },
  { label: "서울역", lat: "37.5547", lng: "126.9707" },
  { label: "판교역", lat: "37.3940", lng: "127.1112" },
];

interface ScoreData {
  label: string;
  total_score: number;
  categories: Record<string, number>;
}

export default function ComparePanel() {
  const [slots, setSlots] = useState<(ScoreData | null)[]>([null, null]);
  const [loading, setLoading] = useState<boolean[]>([false, false]);

  async function fetchScore(idx: number, label: string, lat: string, lng: string) {
    setLoading((prev) => { const n = [...prev]; n[idx] = true; return n; });
    try {
      const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const res = await fetch(`${base}/api/score?lat=${lat}&lng=${lng}`);
      if (!res.ok) throw new Error();
      const data = await res.json();
      setSlots((prev) => {
        const n = [...prev];
        n[idx] = { ...data, label };
        return n;
      });
    } finally {
      setLoading((prev) => { const n = [...prev]; n[idx] = false; return n; });
    }
  }

  const radarData = Object.keys(LABELS).map((key) => {
    const row: any = { subject: LABELS[key] };
    slots.forEach((s, i) => { if (s) row[`score${i}`] = s.categories[key] ?? 0; });
    return row;
  });

  const filled = slots.filter(Boolean) as ScoreData[];

  return (
    <div className="w-full max-w-2xl space-y-4">
      {/* 지역 선택 */}
      <div className="grid grid-cols-2 gap-3">
        {slots.map((slot, idx) => (
          <div key={idx} className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4">
            <p className="text-xs text-gray-400 mb-2">지역 {idx + 1}</p>
            <div className="flex flex-wrap gap-1.5 mb-3">
              {PRESETS.map((p) => (
                <button
                  key={p.label}
                  className="text-xs border border-gray-200 rounded-full px-2.5 py-1 hover:border-blue-400 hover:text-blue-600 transition"
                  onClick={() => fetchScore(idx, p.label, p.lat, p.lng)}
                >
                  {p.label}
                </button>
              ))}
            </div>
            {loading[idx] && <p className="text-xs text-gray-400">조회 중...</p>}
            {slot && (
              <div className="text-center">
                <p className="text-4xl font-bold text-blue-600">{slot.total_score}</p>
                <p className="text-sm text-gray-500">{slot.label}</p>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* 레이더 비교 */}
      {filled.length >= 2 && (
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4">
          <p className="text-sm font-semibold text-gray-700 mb-3">카테고리 비교</p>
          <ResponsiveContainer width="100%" height={260}>
            <RadarChart data={radarData}>
              <PolarGrid stroke="#e5e7eb" />
              <PolarAngleAxis dataKey="subject" tick={{ fontSize: 11, fill: "#6b7280" }} />
              {filled.map((s, i) => (
                <Radar
                  key={i}
                  name={s.label}
                  dataKey={`score${i}`}
                  stroke={COLORS[i]}
                  fill={COLORS[i]}
                  fillOpacity={0.15}
                  strokeWidth={2}
                />
              ))}
              <Legend />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* 바 비교 */}
      {filled.length >= 2 && (
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5 space-y-3">
          {Object.keys(LABELS).map((key) => (
            <div key={key}>
              <p className="text-xs text-gray-500 mb-1">{LABELS[key]}</p>
              {filled.map((s, i) => (
                <div key={i} className="flex items-center gap-2 mb-0.5">
                  <span className="text-xs w-14 shrink-0 text-right" style={{ color: COLORS[i] }}>{s.label}</span>
                  <div className="flex-1 bg-gray-100 rounded-full h-1.5">
                    <div
                      className="h-1.5 rounded-full transition-all"
                      style={{ width: `${s.categories[key] ?? 0}%`, backgroundColor: COLORS[i] }}
                    />
                  </div>
                  <span className="text-xs w-8 text-right text-gray-600">{s.categories[key] ?? 0}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
