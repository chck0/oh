# Spec 27: 친구 채팅 파일·이미지 첨부

> **상태**: Implemented ✅ (Word/PPT 제외 — Vercel lxml 제약)
> **작성일**: 2026-05-31
> **구현 브랜치**: hjkang83

---

## 1. Why

텍스트 대화만으로는 사용자가 갖고 있는 자료(가격 캡처, 계약서, 분양 자료 등)를 분석받을 수 없어
다른 채널(카카오톡 등)로 우회하거나 직접 타이핑해야 하는 불편이 있음.

---

## 2. Scope

### In-scope
- **이미지** (.jpg .jpeg .png .webp .gif) → Claude Vision으로 직접 분석
- **Word** (.docx) → python-docx로 텍스트 추출 → 컨텍스트 추가
- **PPT** (.pptx) → python-pptx로 텍스트 추출
- **PDF** (.pdf) → pypdf로 텍스트 추출 (최대 10페이지)
- **텍스트** (.txt) → 직접 읽기
- 파일 크기 제한: 3MB (Vercel 4.5MB 제약 고려)
- 메시지당 최대 1개 첨부

### Out-of-scope
- Excel (.xlsx) — 부동산 채팅에서 활용도 낮음
- 서버 영구 저장 (세션 내 처리만)
- 스트리밍 응답

---

## 3. Functional Requirements

### F1. 프론트엔드

- 📎 버튼 클릭 → 파일 피커 오픈
- 선택 시 미리보기 표시 (이미지: 썸네일, 문서: 파일명)
- 전송 후 첨부 자동 초기화
- 3MB 초과 시 경고 후 취소

### F2. 백엔드

`AptChatRequest`에 `attachments: list[dict] | None` 추가:
```json
{"type": "image", "media_type": "image/jpeg", "data": "<base64>", "filename": "photo.jpg"}
```

처리 로직:
- 이미지 → Claude Messages API vision content block으로 직접 전달
- 문서 → 서버에서 텍스트 추출 → system prompt 하단에 `== 첨부 파일 ==` 섹션 추가
- 첨부 있을 때는 캐시 비활성화

---

## 4. 구현 파일

| 파일 | 변경 |
|------|------|
| `requirements.txt` | python-docx, python-pptx, pypdf 추가 |
| `app/search.py` | `_extract_doc_text()`, `AptChatRequest.attachments`, `apt_chat` 비전/문서 처리 |
| `web/result.html` | 📎 버튼, 파일 인풋, 첨부 미리보기 CSS/HTML/JS |

---

## 5. Acceptance Criteria

- [x] AC1: 이미지 첨부 후 전송 → Claude Vision으로 이미지 내용 분석
- [x] AC2: PDF 첨부 → pypdf 텍스트 추출 → Claude 분석
- [x] AC2b: Word/PPT 첨부 → "PDF로 변환 후 첨부" 안내 (lxml 의존으로 Vercel 미지원)
- [x] AC3: 3MB 초과 파일 → 경고 메시지, 전송 차단
- [x] AC4: 전송 후 미리보기 초기화
- [x] AC5: pytest 387+ passed 유지

## 구현 제약 (Vercel)
- `python-docx` / `python-pptx` → `lxml` C 확장 의존 → Vercel 빌드 실패
- `pypdf` (순수 Python) 만 사용, Word/PPT는 PDF 변환 후 첨부 안내
