# On-Go

 유적지 가이드

## 기능
- 유적지 사진 업로드 → GPS 자동 인식 → 장소 매칭
- 페르소나별 맞춤 설명 (어린이 / 일반 / 역사 마니아)
- AI 음성 해설 (TTS)
- 방문 기록 자동 저장 + 지도 앨범

## 실행
```bash
pip install -r requirements.txt
streamlit run app.py
```

## 환경 변수
`.env` 파일에 Gemini API 키를 설정하세요:
```
GEMINI_API_KEY=your_key_here
```

## 배포
Streamlit Community Cloud에서 GitHub 저장소를 연결하고, Secrets에 `GEMINI_API_KEY`를 설정하세요.
