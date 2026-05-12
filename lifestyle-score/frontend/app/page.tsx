"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import ScoreCard from "./components/ScoreCard";
import ComparePanel from "./components/ComparePanel";

const KakaoMap = dynamic(() => import("./components/KakaoMap"), { ssr: false });

type Tab = "search" | "map" | "compare";

export default function Home() {
  const [tab, setTab] = useState<Tab>("search");
  const [lat, setLat] = useState("");
  const [lng, setLng] = useState("");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [pickedMarker, setPickedMarker] = useState<{ lat: number; lng: number } | null>(null);

  async function handleSearch(latVal = lat, lngVal = lng) {
    if (!latVal || !lngVal) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const res = await fetch(`${base}/api/score?lat=${latVal}&lng=${lngVal}`);
      if (!res.ok) throw new Error();
      setResult(await res.json());
    } catch {
      setError("점수를 불러오지 못했습니다. 서버 상태를 확인해주세요.");
    } finally {
      setLoading(false);
    }
  }

  function handleMapPick(pickedLat: number, pickedLng: number) {
    const latStr = pickedLat.toFixed(4);
    const lngStr = pickedLng.toFixed(4);
    setLat(latStr);
    setLng(lngStr);
    setPickedMarker({ lat: pickedLat, lng: pickedLng });
    handleSearch(latStr, lngStr);
  }

  const TABS: { id: Tab; label: string }[] = [
    { id: "search", label: "좌표 검색" },
    { id: "map",    label: "지도 검색" },
    { id: "compare", label: "지역 비교" },
  ];

  return (
    <main className="min-h-screen bg-gray-50 flex flex-col items-center py-12 px-4">
      {/* 헤더 */}
      <div className="text-center mb-8">
        <h1 className="text-4xl font-bold text-gray-900 mb-2">생활권 스코어</h1>
        <p className="text-gray-500">위치를 선택하면 동네 점수를 알려드립니다</p>
      </div>

      {/* 탭 */}
      <div className="flex gap-1 bg-white border border-gray-200 rounded-xl p-1 mb-6">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-1.5 rounded-lg text-sm font-medium transition ${
              tab === t.id
                ? "bg-blue-600 text-white shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 좌표 검색 탭 */}
      {tab === "search" && (
        <>
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 w-full max-w-md mb-4">
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
              onClick={() => handleSearch()}
              disabled={loading || !lat || !lng}
            >
              {loading ? "조회 중..." : "점수 조회"}
            </button>
            {error && <p className="text-red-500 text-xs mt-2 text-center">{error}</p>}
          </div>

          <div className="flex gap-2 mb-8 flex-wrap justify-center">
            {[
              { label: "강남역", lat: "37.4979", lng: "127.0276" },
              { label: "홍대입구", lat: "37.5563", lng: "126.9228" },
              { label: "서울역", lat: "37.5547", lng: "126.9707" },
            ].map((loc) => (
              <button
                key={loc.label}
                className="text-xs bg-white border border-gray-200 rounded-full px-3 py-1.5 text-gray-600 hover:border-blue-400 hover:text-blue-600 transition"
                onClick={() => { setLat(loc.lat); setLng(loc.lng); handleSearch(loc.lat, loc.lng); }}
              >
                {loc.label}
              </button>
            ))}
          </div>

          {result && <ScoreCard data={result} />}
        </>
      )}

      {/* 지도 검색 탭 */}
      {tab === "map" && (
        <div className="w-full max-w-md space-y-4">
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
            <KakaoMap onPick={handleMapPick} marker={pickedMarker} />
          </div>
          {lat && lng && (
            <div className="bg-white rounded-2xl border border-gray-100 shadow-sm px-4 py-2 text-sm text-gray-500 text-center">
              선택 위치: {lat}, {lng}
            </div>
          )}
          {loading && <p className="text-center text-sm text-gray-400">점수 계산 중...</p>}
          {error && <p className="text-red-500 text-xs text-center">{error}</p>}
          {result && <ScoreCard data={result} />}
        </div>
      )}

      {/* 지역 비교 탭 */}
      {tab === "compare" && <ComparePanel />}
    </main>
  );
}
