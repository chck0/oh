# sandbox/ — 작업용 임시 폴더

## 용도

데이터 확인하면서 수정·수정·수정 하는 단계의 **실험·디버깅 코드**만 여기 둠.

여기 있는 파일들은:
- ❌ 운영 파이프라인에 포함되지 않음
- ❌ `.gitignore`로 커밋되지 않음 (자유롭게 어지럽혀도 됨)
- ✅ `from config import cfg` 그대로 사용 가능 (프로젝트 루트 기준)

## 흐름

```
sandbox/foo_v1.py   ← 처음 짜봄
sandbox/foo_v2.py   ← 데이터 보고 수정
sandbox/foo_v3.py   ← 또 수정
        ↓ 검증 끝, 안정화
scripts/NN_foo.py   ← 최종 운영용으로 승격
```

## 실행

프로젝트 루트에서 실행:
```bash
cd C:\real_estate
python sandbox/foo.py
```

(config.py가 `__file__` 기준으로 .env를 찾기 때문에 어디서 실행해도 동작하긴 함)

## 정리

승격된 파일은 sandbox에서 삭제. 안 쓰는 실험 파일은 주기적으로 청소.
