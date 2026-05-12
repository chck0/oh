"use client";

import { useState } from "react";
import ScoreCard from "./components/ScoreCard";

export default function Home() {
  const [lat, setLat] = useState("");
  const [lng, setLng] = useState("");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSearch() {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const res = await fetch(`http://localhost:8000/api/score?lat=${lat}&lng=${lng}`);
      if (!res.ok) throw new Error("API 오류");
      setResult(await res.json());
    } catch {
      setError("점수를 불러오지 못했습니다. 서버 상태를 확인해주세요.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-gray-50 flex flex-col items-center py-16 px-4">
      {/* 헤더 */}
      <div className="text-center mb-10">
        <h1 className="text-4xl font-bold text-gray-900 mb-2">생활권 스코어</h1>
        <p className="text-gray-500">위경도를 입력하면 동네 점수를 알려드립니다</p>
      </div>

      {/* 입력 폼 */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 w-full max-w-md mb-6">
        <div className="flex gap-3 mb-1">
          <div className="flex-1">
            <label className="block text-xs text-gray-500 mb-1">위도 (lat)</label>
            <input
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="37.4979"
              value={lat}
              onChange={(e) => setLat(e.target.value)}
            />
          </div>
          <div className="flex-1">
            <label className="block text-xs text-gray-500 mb-1">경도 (lng)</label>
            <input
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="127.0276"
              value={lng}
              onChange={(e) => setLng(e.target.value)}
            />
          </div>
        </div>
        <button
          className="mt-3 w-full bg-blue-600 text-white py-2.5 rounded-lg text-sm font-semibold hover:bg-blue-700 transition disabled:opacity-40"
          onClick={handleSearch}
          disabled={loading || !lat || !lng}
        >
          {loading ? "조회 중..." : "점수 조회"}
        </button>
        {error && <p className="text-red-500 text-xs mt-2 text-center">{error}</p>}
      </div>

      {/* 예시 좌표 */}
      <div className="flex gap-2 mb-8 flex-wrap justify-center">
        {[
          { label: "강남역", lat: "37.4979", lng: "127.0276" },
          { label: "홍대입구", lat: "37.5563", lng: "126.9228" },
          { label: "서울역", lat: "37.5547", lng: "126.9707" },
        ].map((loc) => (
          <button
            key={loc.label}
            className="text-xs bg-white border border-gray-200 rounded-full px-3 py-1.5 text-gray-600 hover:border-blue-400 hover:text-blue-600 transition"
            onClick={() => { setLat(loc.lat); setLng(loc.lng); }}
          >
            {loc.label}
          </button>
        ))}
      </div>

      {result && <ScoreCard data={result} />}
    </main>
  );
}
