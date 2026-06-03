# Level 1 — Schedule + Secure 제출물

> 과제: 실제 텀 프로젝트에서 자율/스케줄 루프 1개 이상 실행, 보안 위협 1개 제약

---

## a) What did the agent actually do?

### 루프 1: ODsay API 키 상태 자동 감시

**스크립트**: `scripts/monitor_odsay.py`
**실행 방식**: 자율 루프 (종료 조건: 전체 키 체크 완료 시 자동 exit)

**실제 실행 로그** (2026-06-03 02:09 UTC):
```
[ODsay Monitor] 7개 키 점검 시작
  키 #1 테스트... OK
  키 #2 테스트... OK
  키 #3 테스트... FAIL  ← ApiKeyAuthFailed
  키 #4 테스트... OK
  키 #5 테스트... OK
  키 #6 테스트... OK
  키 #7 테스트... FAIL  ← ApiKeyAuthFailed
[ODsay Monitor] 완료 - 정상 5개 / 이상 2개
Exit code: 2 (이상 키 존재)
```

**생성된 리포트**: `wiki/odsay_report.md`

에이전트가 한 일:
- 7개 ODsay API 키 각각 실제 HTTP 호출 테스트
- 키 #3, #7 이 `ApiKeyAuthFailed` 임을 자동 감지 (기존에 몰랐던 문제)
- 이상 키 조치 권고 리포트 자동 생성
- 모든 키 체크 완료 후 스스로 종료 (closed loop)

---

### 루프 2: Claude API 비용 일일 모니터링

**스크립트**: `scripts/monitor_costs.py`
**실행 방식**: 자율 루프 (종료 조건: 집계 + 리포트 생성 완료 시 자동 exit)

**실제 실행 로그** (2026-06-03 02:10 UTC):
```
[Cost Monitor] 비용 집계 시작 (2026-06-03 02:10 UTC)
[Cost Monitor] 리포트 저장: wiki/cost_report.md
[Cost Monitor] 당일 예상 비용: $0.0000  OK
[Cost Monitor] 완료
Exit code: 0
```

**생성된 리포트**: `wiki/cost_report.md`

에이전트가 한 일:
- Supabase DB의 `apt_pt_friend_comment` 테이블 SELECT (읽기 전용)
- 최근 30일: Haiku 3,528회 호출 → **예상 비용 $1.69** 자동 산출
- 모델별 단가 × 평균 토큰 추정으로 비용 계산
- 임계값($10/일) 미초과 확인 후 스스로 종료 (closed loop)

---

### 스케줄 설정 (스텝 3)

**루틴 ID**: `trig_01Je8ZoiRWaFkjijxXSkpcWf`
**스케줄**: 매일 00:00 UTC = **09:00 KST**
**첫 실행 예정**: 2026-06-04 09:01 KST
**링크**: https://claude.ai/code/routines/trig_01Je8ZoiRWaFkjijxXSkpcWf

루틴이 매일 자동으로:
1. `python scripts/monitor_odsay.py` 실행
2. `python scripts/monitor_costs.py` 실행
3. 결과를 `wiki/loop_report.md` 에 저장 + git commit

---

## b) Name one threat you constrained

**위협**: 에이전트가 이상 키 발견 시 자동으로 환경변수 수정·키 삭제·외부 알림 발송

**제약 방법**: Allowlist + Human Gate (`.claude/settings.json`)

```json
{
  "permissions": {
    "allow": [
      "Bash(python scripts/monitor_odsay.py)",
      "Bash(python scripts/monitor_costs.py)",
      "Bash(python -m pytest*)",
      "Bash(git status)", "Bash(git log*)", "Bash(git diff*)",
      "Read(**)"
    ],
    "deny": [
      "Bash(git push*)",
      "Bash(rm *)",
      "Bash(pip install*)",
      "Bash(DROP*)",
      "Bash(DELETE FROM*)"
    ]
  }
}
```

구체적으로 막은 것:
- `git push` 차단 → 에이전트가 코드 수정 후 자동 배포 불가
- `rm` 차단 → 이상 키 발견 시 자동 파일 삭제 불가
- `DELETE FROM` 차단 → DB 데이터 자동 삭제 불가
- 임계값 초과 시 **경고 출력만** → 실제 차단 조치는 사람이 직접 결정 (Human Gate)

→ 에이전트는 감지·보고만 하고, 실제 조치는 항상 인간이 승인 후 진행합니다.

---

## 루프가 "Closed"된 근거

두 루프 모두 **자체 종료 조건**을 충족해 자동 exit:
- `monitor_odsay.py`: 전체 키 체크 완료 → `sys.exit(0 or 2)`
- `monitor_costs.py`: 집계 + 리포트 저장 완료 → `sys.exit(0)`

에러 발생 시에도 `sys.exit(1)`로 명확히 종료 (무한 루프 없음).
