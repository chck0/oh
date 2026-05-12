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
      const res = await fetch(
        `http://localhost:8000/api/score?lat=${lat}&lng=${lng}`
      );
      if (!res.ok) throw new Error("API 오류");
      const data = await res.json();
      setResult(data);
    } catch (e) {
      setError("점수를 불러오지 못했습니다. 서버 상태를 확인해주세요.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex flex-col items-center py-16 px-4">
      <h1 className="text-3xl font-bold mb-2">생활권 스코어</h1>
      <p className="text-gray-500 mb-10">위경도를 입력하면 동네 점수를 알려드립니다</p>

      <div className="flex gap-3 mb-6">
        <input
          className="border rounded-lg px-4 py-2 w-40 text-sm"
          placeholder="위도 (37.4979)"
          value={lat}
          onChange={(e) => setLat(e.target.value)}
        />
        <input
          className="border rounded-lg px-4 py-2 w-40 text-sm"
          placeholder="경도 (127.0276)"
          value={lng}
          onChange={(e) => setLng(e.target.value)}
        />
        <button
          className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
          onClick={handleSearch}
          disabled={loading || !lat || !lng}
        >
          {loading ? "조회 중..." : "점수 조회"}
        </button>
      </div>

      {error && <p className="text-red-500 text-sm mb-4">{error}</p>}
      {result && <ScoreCard data={result} />}
    </main>
  );
}
