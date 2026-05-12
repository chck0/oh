"use client";

import { useEffect, useRef } from "react";
import Script from "next/script";

declare global {
  interface Window {
    kakao: any;
  }
}

interface Props {
  onPick: (lat: number, lng: number) => void;
  marker?: { lat: number; lng: number } | null;
}

export default function KakaoMap({ onPick, marker }: Props) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<any>(null);
  const markerRef = useRef<any>(null);

  function initMap() {
    if (!mapRef.current || !window.kakao) return;
    window.kakao.maps.load(() => {
      const options = {
        center: new window.kakao.maps.LatLng(37.5326, 126.9907),
        level: 5,
      };
      const map = new window.kakao.maps.Map(mapRef.current, options);
      mapInstanceRef.current = map;

      window.kakao.maps.event.addListener(map, "click", (e: any) => {
        const lat = e.latLng.getLat();
        const lng = e.latLng.getLng();
        onPick(lat, lng);

        if (markerRef.current) markerRef.current.setMap(null);
        markerRef.current = new window.kakao.maps.Marker({
          position: e.latLng,
          map,
        });
      });
    });
  }

  useEffect(() => {
    if (marker && mapInstanceRef.current && window.kakao) {
      const pos = new window.kakao.maps.LatLng(marker.lat, marker.lng);
      if (markerRef.current) markerRef.current.setMap(null);
      markerRef.current = new window.kakao.maps.Marker({
        position: pos,
        map: mapInstanceRef.current,
      });
      mapInstanceRef.current.panTo(pos);
    }
  }, [marker]);

  return (
    <>
      <Script
        src={`//dapi.kakao.com/v2/maps/sdk.js?appkey=${process.env.NEXT_PUBLIC_KAKAO_APP_KEY}&autoload=false`}
        onLoad={initMap}
      />
      <div ref={mapRef} className="w-full h-72 rounded-2xl overflow-hidden border border-gray-200" />
      <p className="text-xs text-gray-400 mt-1 text-center">지도를 클릭하면 해당 위치의 점수를 조회합니다</p>
    </>
  );
}
