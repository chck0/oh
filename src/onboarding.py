"""온보딩 대화: 첫 부동산 구매자를 위한 3단계 프로파일링.

타깃: 부동산 지식이 없는 30대 직장인. 사용자 프로필 폼을 직접 채우기
어려운 사용자를 위해, 평이한 한국어 질문 3개로 Profile과 토픽을 생성한다.

설계 원칙:
- 순수 함수만: Streamlit 의존성 없이 테스트 가능
- 답변 → (Profile, topic) 매핑은 결정적 (deterministic)
- 답이 부분적으로 비어 있어도 합리적 기본값으로 채움
"""
from __future__ import annotations

from dataclasses import dataclass

from profiles import Profile

# 3단계 질문지: (id, 질문 텍스트, 옵션 라벨 → 내부값 매핑)
ONBOARDING_STEPS: list[dict] = [
    {
        "id": "purpose",
        "question": "이번 주택 구매의 주된 목적은 무엇인가요?",
        "options": {
            "내가 살 집 (실거주)": "residence",
            "월세 수익 (투자)": "rental",
            "시세 차익 (투자)": "capital_gain",
            "실거주 + 투자 둘 다": "mixed",
        },
    },
    {
        "id": "budget",
        "question": "구매에 동원 가능한 총 예산은 어느 정도인가요? (자기자본 + 대출 합계)",
        "options": {
            "3억 미만": 25000,
            "3~5억": 40000,
            "5~7억": 60000,
            "7~10억": 85000,
            "10억 이상": 120000,
        },
    },
    {
        "id": "loan_ratio",
        "question": "전체 예산 중 대출 비중은 어느 정도일 예정인가요?",
        "options": {
            "대출 없이 (0%)": "none",
            "30% 이하": "low",
            "30~50%": "medium",
            "50~70%": "high",
            "잘 모르겠어요": "unknown",
        },
    },
]


@dataclass
class OnboardingAnswers:
    """3단계 응답 모음. 비어 있으면 기본값으로 처리."""
    purpose: str = ""
    budget_manwon: int = 0
    loan_ratio: str = ""

    def is_complete(self) -> bool:
        return bool(self.purpose) and self.budget_manwon > 0 and bool(self.loan_ratio)


def build_profile(answers: OnboardingAnswers) -> Profile:
    """온보딩 답변을 Profile로 변환.

    매핑 규칙:
    - purpose=residence → goal=mixed (살면서 자산 가치도 봄)
    - purpose=rental → goal=rental
    - purpose=capital_gain → goal=capital_gain
    - purpose=mixed → goal=mixed
    - loan_ratio=high → risk=aggressive (레버리지 큰 만큼 공격적 평가 필요)
    - loan_ratio=none/low → risk=conservative
    - 그 외 → risk=moderate
    """
    goal_map = {
        "residence": "mixed",
        "rental": "rental",
        "capital_gain": "capital_gain",
        "mixed": "mixed",
    }
    risk_map = {
        "none": "conservative",
        "low": "conservative",
        "medium": "moderate",
        "high": "aggressive",
        "unknown": "moderate",
    }

    nickname = "첫 구매자" if answers.purpose == "residence" else "투자 입문자"

    return Profile(
        nickname=nickname,
        risk_profile=risk_map.get(answers.loan_ratio, "moderate"),
        investment_goal=goal_map.get(answers.purpose, "mixed"),
        budget_manwon=answers.budget_manwon,
        property_count=0,                    # 첫 구매 가정
        holding_years=10 if answers.purpose == "residence" else 5,
        life_stage="accumulation",           # 첫 구매자는 자산 형성기
        notes=_build_notes(answers),
    )


def _build_notes(answers: OnboardingAnswers) -> str:
    """에이전트들이 컨텍스트로 활용할 한국어 메모."""
    purpose_label = {
        "residence": "실거주 목적의 첫 주택 구매",
        "rental": "월세 수익을 위한 첫 투자",
        "capital_gain": "시세 차익을 노리는 첫 투자",
        "mixed": "실거주 + 투자 겸용 첫 구매",
    }.get(answers.purpose, "첫 부동산 구매")

    loan_label = {
        "none": "대출 없이 자기자본으로",
        "low": "대출 30% 이하 (저레버리지)",
        "medium": "대출 30~50%",
        "high": "대출 50~70% (고레버리지)",
        "unknown": "대출 비중 미정 — 상담 필요",
    }.get(answers.loan_ratio, "대출 비중 미정")

    return (
        f"{purpose_label}, {loan_label}. "
        f"부동산 경험 거의 없음. 바쁜 직장인으로 학습 시간 부족. "
        f"의사결정에 필요한 체크포인트와 공인중개사에게 물어볼 질문을 함께 제시할 것."
    )


def build_topic(answers: OnboardingAnswers) -> str:
    """기본 토픽 문장 생성. 사용자가 추가 입력하지 않아도 회의가 시작될 수 있게."""
    purpose_phrase = {
        "residence": "실거주 목적의 첫 주택",
        "rental": "월세 수익형 첫 투자",
        "capital_gain": "시세차익형 첫 투자",
        "mixed": "실거주 + 투자 겸용 첫 주택",
    }.get(answers.purpose, "첫 주택")
    budget_phrase = f"{answers.budget_manwon // 10000}억" if answers.budget_manwon >= 10000 \
        else f"{answers.budget_manwon}만원"
    return (
        f"{purpose_phrase}, 예산 {budget_phrase} 수준에서 "
        f"어떤 지역과 매물 유형을 검토해야 하는지 토론해주세요."
    )


def build_checklist(answers: OnboardingAnswers) -> list[str]:
    """첫 구매자가 매물 검토 시 챙겨야 할 체크리스트.

    공인중개사/유튜브에서는 잘 안 알려주는, 그러나 의사결정에 결정적인 항목들.
    """
    base = [
        "관리비 실제 금액 (오피스텔/아파트 모두 큰 차이 발생)",
        "전용률 (오피스텔 50~60%, 아파트 70~85%)",
        "주변 2년 내 신규 공급 물량 (입주 시점에 매매가 하락 가능)",
        "주변 재개발/재건축 진행 단계 (조합 설립? 사업시행 인가?)",
        "교통 호재의 실제 개통 시기 (계획 vs 착공 vs 개통은 다름)",
        "취득세율 (실거주 1주택 vs 투자 다주택은 4배 차이)",
        "임대 수요층 (직장인? 학생? 가족? 공실 위험과 직결)",
    ]
    if answers.loan_ratio in ("medium", "high"):
        base.append("DSR/LTV 한도 — 은행 3곳 이상 사전 상담")
    if answers.loan_ratio == "high":
        base.append("금리 1%p 상승 시 월 상환액 변화 시뮬레이션")
    if answers.purpose == "rental":
        base.append("주변 신축 임대료 변화 추이 (3년)")
    if answers.purpose == "capital_gain":
        base.append("최근 6개월 실거래가 추이 + 매물 회전율")
    return base


def build_questions_for_agent(answers: OnboardingAnswers) -> list[str]:
    """공인중개사에게 직접 물어볼 질문 (사용자가 그대로 들고 가도 됨)."""
    questions = [
        "이 단지(건물)의 현재 공실은 몇 호이고, 최근 1년 공실 추이는 어떤가요?",
        "최근 6개월 같은 평형 실거래가 범위와 거래량을 알려주실 수 있나요?",
        "주변 재개발/교통 호재로 매수 문의가 늘고 있나요? 구체적으로 어느 호재 때문인가요?",
    ]
    if answers.purpose in ("rental", "mixed"):
        questions.append("이 단지의 최근 임대 시세와 임차인 평균 거주 기간은 어떻게 되나요?")
    if answers.purpose == "residence":
        questions.append("초등학교 통학 거리, 슬리퍼 생활권 시설(편의점·마트·병원)은 어떻게 형성되어 있나요?")
    return questions
