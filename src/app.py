"""Streamlit 채팅 UI — 부동산 투자 자문 시스템 웹 프론트엔드.

Usage:
    streamlit run src/app.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

from meeting import Meeting
from personas import AGENT_CONFIG
from archive import list_meetings
from profiles import (
    INVESTMENT_GOALS,
    LIFE_STAGES,
    RISK_PROFILES,
    Profile,
    list_profiles,
    load_profile,
    save_profile,
)
from real_estate import REGION_CODES, REGION_GROUPS, PROPERTY_TYPES
from file_parser import parse_file, SUPPORTED_EXTENSIONS
from file_parser import format_for_agents as format_files_for_agents
from yield_analyzer import InvestmentParams
from scenario import rate_sensitivity, vacancy_sensitivity, price_sensitivity, stress_test
from cashflow import CashFlowParams, build_multi_cashflow
from monte_carlo import run_multi_monte_carlo
from tax import TaxParams
from pipeline import PipelineResult, run_pipeline
from briefing import generate_ceo_briefing
from manual import MANUAL_TEXT, FILE_SAMPLE_TEXT
from charts import (
    sensitivity_line_chart, stress_bar_chart, region_radar,
    cashflow_chart, monte_carlo_histogram,
    tax_comparison_chart, scorecard_chart, portfolio_scatter,
)
from demo_mock import MOCK_TURNS, MOCK_MINUTES, DEMO_TOPIC, DEMO_REGIONS


st.set_page_config(
    page_title="부동산 투자 자문 시스템",
    page_icon="🏢",
    layout="wide",
)

AGENT_COLORS = {
    "practitioner": "#1565C0",
    "redteam": "#C62828",
    "mentor": "#2E7D32",
    "clerk": "#E65100",
}


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ------------------------------------------------------------------
# Sidebar: 회의 설정
# ------------------------------------------------------------------

with st.sidebar:
    st.markdown("## 🏢 회의 설정")

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        api_key = st.text_input(
            "Anthropic API Key",
            type="password",
            help="ANTHROPIC_API_KEY 환경변수 또는 .env 파일로도 설정 가능",
        )
        if api_key:
            os.environ["ANTHROPIC_API_KEY"] = api_key

    st.divider()

    selected_profile: Profile | None = None
    with st.expander("👤 사용자 프로필", expanded=False):
        available_profiles = list_profiles()
        sel_options = ["(사용 안 함)"] + available_profiles
        sel_pick = st.selectbox(
            "저장된 프로필",
            options=sel_options,
            help="회의 시작 시 투자컨설턴트에게 컨텍스트로 주입됩니다.",
        )
        if sel_pick != "(사용 안 함)":
            selected_profile = load_profile(sel_pick)
            if selected_profile:
                st.markdown(
                    f"**{selected_profile.nickname}** · "
                    f"{selected_profile.risk_label} · "
                    f"{selected_profile.goal_label}"
                )
                st.caption(
                    f"예산 {selected_profile.budget_manwon:,}만원 · "
                    f"{selected_profile.holding_years}년 보유 · "
                    f"{selected_profile.life_stage_label}"
                )
                if selected_profile.notes:
                    st.caption(f"📝 {selected_profile.notes}")

        with st.expander("➕ 새로 만들기 / ✏️ 편집", expanded=False):
            with st.form("profile_form", clear_on_submit=False):
                base = selected_profile or Profile()
                edit_name = st.text_input(
                    "프로필 이름 (영문/숫자/언더스코어)",
                    value=sel_pick if sel_pick != "(사용 안 함)" else "default",
                )
                form_nickname = st.text_input("닉네임", value=base.nickname)
                risk_keys = list(RISK_PROFILES.keys())
                form_risk = st.selectbox(
                    "리스크 프로파일",
                    options=risk_keys,
                    index=risk_keys.index(base.risk_profile)
                    if base.risk_profile in risk_keys else 1,
                    format_func=lambda k: RISK_PROFILES[k],
                )
                goal_keys = list(INVESTMENT_GOALS.keys())
                form_goal = st.selectbox(
                    "투자 목적",
                    options=goal_keys,
                    index=goal_keys.index(base.investment_goal)
                    if base.investment_goal in goal_keys else 0,
                    format_func=lambda k: INVESTMENT_GOALS[k],
                )
                form_budget = st.number_input(
                    "가용 예산 (만원, 0=미입력)",
                    min_value=0, max_value=10_000_000,
                    value=int(base.budget_manwon), step=1000,
                )
                form_count = st.number_input(
                    "보유 주택 수 (0=무주택)",
                    min_value=0, max_value=20,
                    value=int(base.property_count), step=1,
                )
                form_holding = st.number_input(
                    "투자 시계 (년)",
                    min_value=1, max_value=30,
                    value=int(base.holding_years), step=1,
                )
                life_keys = list(LIFE_STAGES.keys())
                form_life = st.selectbox(
                    "생애주기",
                    options=life_keys,
                    index=life_keys.index(base.life_stage)
                    if base.life_stage in life_keys else 1,
                    format_func=lambda k: LIFE_STAGES[k],
                )
                form_notes = st.text_area("메모 (선택)", value=base.notes, height=80)

                if st.form_submit_button("💾 프로필 저장"):
                    new_profile = Profile(
                        nickname=form_nickname,
                        risk_profile=form_risk,
                        investment_goal=form_goal,
                        budget_manwon=int(form_budget),
                        property_count=int(form_count),
                        holding_years=int(form_holding),
                        life_stage=form_life,
                        notes=form_notes,
                    )
                    path = save_profile(new_profile, edit_name)
                    st.success(f"✅ 저장됨: `{path.name}`")
                    st.rerun()

    topic = st.text_input(
        "📌 회의 안건",
        placeholder="예: 강남 오피스텔 투자 검토",
    )

    property_type = st.radio(
        "🏠 매물 유형",
        options=["officetel", "apartment"],
        format_func=lambda x: "오피스텔" if x == "officetel" else "아파트",
        horizontal=True,
    )

    region_area = st.selectbox(
        "🗺 지역 권역",
        options=list(REGION_GROUPS.keys()),
        index=0,
    )
    selected_regions = st.multiselect(
        "📈 실거래 데이터 지역",
        options=REGION_GROUPS[region_area],
        default=[REGION_GROUPS[region_area][0]] if REGION_GROUPS[region_area] else [],
        help=f"{region_area} 권역 {len(REGION_GROUPS[region_area])}개 지역 | 전체 {len(REGION_CODES)}개 지역 지원",
    )

    uploaded_files = st.file_uploader(
        "📎 파일 업로드",
        type=["xlsx", "xls", "pdf"],
        accept_multiple_files=True,
        help="매물 리스트(Excel), 계약서(PDF) 등",
    )

    with st.expander("🗣 토론 설정", expanded=False):
        debate_mode = st.checkbox("에이전트 간 토론 모드", value=False,
                                  help="에이전트가 서로의 의견에 반론·보충합니다")
        debate_rounds = st.slider("토론 라운드", 1, 3, 2,
                                  disabled=not debate_mode)
        auto_challenge = st.checkbox("자동 반론 주입", value=True,
                                     help="전원 합의 시 확증편향 방지 프롬프트")

    with st.expander("⚙️ 투자 분석 조건", expanded=False):
        ltv_pct = st.slider("LTV (대출비율 %)", 0, 80, 60, 5,
                             help="매매가 대비 대출 비율 (시장 평균 약 60%)")
        ltv = ltv_pct / 100.0
        loan_rate = st.slider("대출금리 (연 %)", 2.0, 7.0, 4.0, 0.5,
                               help="주담대 변동금리 기준 (2025 시장 평균 약 4%)")
        vacancy = st.slider("연간 공실 (개월)", 0.0, 3.0, 1.0, 0.5,
                             help="보수적 추정 1개월, 비역세권 1.5~2개월")
        mgmt_fee = st.number_input("월 관리비 (만원)", 0, 100, 15, 1,
                                    help="오피스텔 평균 10~20��원, 아파트 평균 20~30만원")

    invest_params = InvestmentParams(
        ltv=ltv,
        loan_rate=loan_rate,
        vacancy_months=vacancy,
        mgmt_fee=mgmt_fee,
    )

    st.divider()

    col1, col2 = st.columns(2)
    start_btn = col1.button("🚀 회의 시작", type="primary", use_container_width=True)
    end_btn = col2.button("📝 회의 종료", use_container_width=True)

    if st.button("🗑 새 회의", use_container_width=True):
        for key in ["meeting", "messages", "finalized", "minutes", "mock_mode"]:
            st.session_state.pop(key, None)
        st.rerun()

    mock_btn = st.button("🎭 Mock 데모", use_container_width=True,
                         help="API 키 없이 Gold Standard 기반 데모를 실행합니다")

    st.divider()
    st.caption("참석자")
    for key in ["practitioner", "redteam", "mentor"]:
        cfg = AGENT_CONFIG[key]
        st.markdown(f"{cfg['emoji']} **{cfg['name']}** ({cfg['label']})")

    st.divider()
    help_col1, help_col2 = st.columns(2)
    manual_btn = help_col1.button("📖 사용 매뉴얼", use_container_width=True)
    sample_btn = help_col2.button("📎 파일 양식", use_container_width=True)

    past_meetings = list_meetings(include_mock=True)
    if past_meetings:
        with st.expander(f"📚 과거 회의록 ({len(past_meetings)}건)", expanded=False):
            for m in past_meetings[:10]:
                date_str = f"{m.date} {m.time}".strip()
                st.markdown(f"**{m.topic}**  \n{date_str}")
                if m.summary:
                    st.caption(m.summary[:100] + ("..." if len(m.summary) > 100 else ""))
                st.divider()


# ------------------------------------------------------------------
# 회의 시작
# ------------------------------------------------------------------

if start_btn:
    if not os.getenv("ANTHROPIC_API_KEY"):
        st.error("❌ Anthropic API Key를 먼저 설정해 주세요.")
        st.stop()
    if not topic:
        st.error("❌ 회의 안건을 입력해 주세요.")
        st.stop()

    p = PipelineResult()
    if selected_regions:
        try:
            with st.status("데이터 분석 중...", expanded=True) as status:
                status.update(label="📈 실거래 데이터 로딩 중...")
                p = run_pipeline(
                    selected_regions,
                    invest_params=invest_params,
                    property_type=property_type,
                )
                status.update(label="✅ 분석 완료", state="complete", expanded=False)
        except Exception as e:
            st.warning(f"⚠️ 데이터 분석 중 오류가 발생했습니다: {e}\n샘플 데이터로 계속합니다.")
    market_data = p.market_text
    yield_data = p.yield_text
    scenario_data = p.scenario_text
    cashflow_data = p.cashflow_text
    mc_data = p.mc_text
    tax_data = p.tax_text
    score_data = p.score_text
    port_data = p.port_text

    file_data = ""
    if uploaded_files:
        file_texts: list[tuple[str, str]] = []
        for uf in uploaded_files:
            suffix = Path(uf.name).suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(uf.getvalue())
                tmp_path = tmp.name
            try:
                text = parse_file(tmp_path)
                file_texts.append((uf.name, text))
            except Exception as e:
                st.warning(f"⚠️ {uf.name} 파싱 실패: {e}")
            finally:
                os.unlink(tmp_path)
        if file_texts:
            file_data = format_files_for_agents(file_texts)

    all_data = "\n".join(filter(None, [
        market_data, yield_data, scenario_data, cashflow_data, mc_data,
        tax_data, score_data, port_data,
    ]))
    meeting = Meeting(
        topic,
        profile=selected_profile,
        market_data=market_data,
        yield_data=yield_data,
        scenario_data=all_data,
        file_data=file_data,
    )
    meeting.auto_challenge = auto_challenge
    st.session_state["meeting"] = meeting
    st.session_state["messages"] = []
    st.session_state["finalized"] = False
    st.session_state["debate_mode"] = debate_mode
    st.session_state["debate_rounds"] = debate_rounds
    st.session_state["analyses"] = p.analyses
    st.session_state["summaries"] = p.summaries
    st.session_state["cf_tables"] = p.cf_tables
    st.session_state["mc_results"] = p.mc_results
    st.session_state["tax_summaries"] = p.tax_summaries
    st.session_state["scorecards"] = p.scorecards
    st.session_state["portfolios"] = p.portfolios

    briefing_text = generate_ceo_briefing(p, topic)
    st.session_state["briefing"] = briefing_text

    init_msgs: list[dict] = []
    if briefing_text:
        init_msgs.append({"role": "system", "content": briefing_text, "type": "briefing"})
    if market_data:
        init_msgs.append({"role": "system", "content": market_data, "type": "market"})
    if yield_data:
        init_msgs.append({"role": "system", "content": yield_data, "type": "yield"})
    if scenario_data:
        init_msgs.append({"role": "system", "content": scenario_data, "type": "scenario"})
    if cashflow_data:
        init_msgs.append({"role": "system", "content": cashflow_data, "type": "cashflow"})
    if mc_data:
        init_msgs.append({"role": "system", "content": mc_data, "type": "montecarlo"})
    if tax_data:
        init_msgs.append({"role": "system", "content": tax_data, "type": "tax"})
    if score_data:
        init_msgs.append({"role": "system", "content": score_data, "type": "scorecard"})
    if port_data:
        init_msgs.append({"role": "system", "content": port_data, "type": "portfolio"})
    if file_data:
        init_msgs.append({"role": "system", "content": file_data, "type": "file"})
    st.session_state["messages"] = init_msgs
    st.rerun()


# ------------------------------------------------------------------
# Mock 데모 모드
# ------------------------------------------------------------------

if mock_btn:
    from datetime import datetime

    mp = run_pipeline(DEMO_REGIONS)

    meeting = Meeting(DEMO_TOPIC, market_data=mp.market_text,
                      yield_data=mp.yield_text, scenario_data=mp.scenario_text)
    st.session_state["meeting"] = meeting
    st.session_state["mock_mode"] = True
    st.session_state["finalized"] = False
    st.session_state["analyses"] = mp.analyses
    st.session_state["summaries"] = mp.summaries
    st.session_state["cf_tables"] = mp.cf_tables
    st.session_state["mc_results"] = mp.mc_results
    st.session_state["tax_summaries"] = mp.tax_summaries
    st.session_state["scorecards"] = mp.scorecards
    st.session_state["portfolios"] = mp.portfolios

    mock_briefing = generate_ceo_briefing(mp, DEMO_TOPIC)
    st.session_state["briefing"] = mock_briefing

    msgs: list[dict] = []
    if mock_briefing:
        msgs.append({"role": "system", "content": mock_briefing, "type": "briefing"})
    if mp.market_text:
        msgs.append({"role": "system", "content": mp.market_text, "type": "market"})
    if mp.yield_text:
        msgs.append({"role": "system", "content": mp.yield_text, "type": "yield"})
    if mp.scenario_text:
        msgs.append({"role": "system", "content": mp.scenario_text, "type": "scenario"})

    for turn in MOCK_TURNS:
        msgs.append({"role": "user", "content": turn["user"]})
        for key in ("practitioner", "redteam", "mentor"):
            msgs.append({"role": "agent", "agent_key": key, "content": turn[key]})

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    minutes_text = MOCK_MINUTES.format(timestamp=timestamp)
    msgs.append({"role": "minutes", "content": minutes_text})

    st.session_state["messages"] = msgs
    st.session_state["finalized"] = True
    st.rerun()


# ------------------------------------------------------------------
# 메인 채팅 영역
# ------------------------------------------------------------------

st.markdown("## 🏢 Data 기반 Multi-Agent 부동산 투자 자문 시스템")

# ------------------------------------------------------------------
# 매뉴얼 / 파일 양식 표시
# ------------------------------------------------------------------

if manual_btn:
    st.session_state["show_manual"] = not st.session_state.get("show_manual", False)
    st.session_state["show_sample"] = False
if sample_btn:
    st.session_state["show_sample"] = not st.session_state.get("show_sample", False)
    st.session_state["show_manual"] = False

if st.session_state.get("show_manual"):
    st.markdown(MANUAL_TEXT)
    st.divider()

if st.session_state.get("show_sample"):
    st.markdown(FILE_SAMPLE_TEXT)
    st.divider()

meeting: Meeting | None = st.session_state.get("meeting")

if meeting is None:
    st.markdown(
        "3명의 AI C-suite(CFO · CSO · 투자컨설턴트)가 **실거래 데이터 기반**으로 "
        "부동산 투자를 토론하며 의사결정을 돕습니다."
    )
    hero_cols = st.columns([1, 1, 1])
    hero_cols[0].metric("분석 권역", f"{len(REGION_CODES)}개 전국")
    hero_cols[1].metric("분석 모듈", "8종 (수익률·세금·MC 등)")
    hero_cols[2].metric("AI 에이전트", "3명 + 비서실장")
    st.divider()
    st.markdown("#### 시작하기")
    start_cols = st.columns(2)
    start_cols[0].markdown(
        "**API 모드** — 사이드바에서 안건 입력 후 `회의 시작`"
    )
    start_cols[1].markdown(
        "**데모 모드** — API 키 없이 즉시 체험 → 사이드바 `Mock 데모`"
    )
    st.stop()

mock_label = "  |  🎭 Mock 데모" if st.session_state.get("mock_mode") else ""
st.caption(f"📌 안건: {meeting.topic}  |  🗂 세션: {meeting.session_id}{mock_label}")

messages = st.session_state.get("messages", [])

for msg in messages:
    if msg["role"] == "system":
        msg_type = msg.get("type", "")
        if msg_type == "briefing":
            with st.expander("📋 CEO 사전 브리핑 보고서", expanded=True):
                st.markdown(msg["content"])
            continue
        type_labels = {
            "market": "📈 실거래 데이터",
            "yield": "📊 수익률 분석",
            "scenario": "🔮 시나리오 시뮬레이션",
            "cashflow": "💰 10년 현금흐름",
            "montecarlo": "🎲 Monte Carlo",
            "tax": "🏛 세금 시뮬레이션",
            "scorecard": "📋 투자 스코어카드",
            "portfolio": "📦 포트폴리오 분석",
            "file": "📎 업로드 파일",
        }
        label = type_labels.get(msg_type, "📋 데이터")
        with st.expander(label, expanded=False):
            st.text(msg["content"])
    elif msg["role"] == "user":
        with st.chat_message("user", avatar="🧑"):
            st.markdown(msg["content"])
    elif msg["role"] == "agent":
        key = msg.get("agent_key", "")
        cfg = AGENT_CONFIG.get(key, {})
        avatar = cfg.get("emoji", "🤖")
        name = cfg.get("name", "Agent")
        label = cfg.get("label", "")
        color = AGENT_COLORS.get(key, "#666")
        with st.chat_message("assistant", avatar=avatar):
            st.markdown(
                f"<span style='color:{color};font-weight:bold;'>"
                f"{name}({label})</span>",
                unsafe_allow_html=True,
            )
            st.markdown(msg["content"])
    elif msg["role"] == "minutes":
        st.divider()
        st.markdown("### 📝 회의록")
        st.markdown(msg["content"])

# ------------------------------------------------------------------
# 차트 시각화
# ------------------------------------------------------------------

analyses_data = st.session_state.get("analyses", [])
summaries_data = st.session_state.get("summaries", [])

if analyses_data:
    with st.expander("📊 시각화 차트", expanded=True):
        chart_tabs = st.tabs([
            "권역 비교", "민감도", "스트레스", "현금흐름",
            "Monte Carlo", "세금", "스코어카드", "포트폴리오",
        ])
        with chart_tabs[0]:
            st.plotly_chart(region_radar(analyses_data), use_container_width=True)
        with chart_tabs[1]:
            for s in summaries_data[:2]:
                rt = rate_sensitivity(s, invest_params)
                if rt:
                    st.plotly_chart(sensitivity_line_chart(rt), use_container_width=True)
        with chart_tabs[2]:
            tests = [stress_test(s, invest_params) for s in summaries_data]
            tests = [t for t in tests if t]
            if tests:
                st.plotly_chart(stress_bar_chart(tests), use_container_width=True)
        with chart_tabs[3]:
            cf_tables_data = st.session_state.get("cf_tables", [])
            if not cf_tables_data:
                cf_tables_data = build_multi_cashflow(analyses_data)
            for t in cf_tables_data[:2]:
                st.plotly_chart(cashflow_chart(t), use_container_width=True)
        with chart_tabs[4]:
            mc_data_cached = st.session_state.get("mc_results", [])
            if not mc_data_cached:
                mc_data_cached = run_multi_monte_carlo(analyses_data)
            for r in mc_data_cached:
                if r.n_simulations > 0:
                    st.plotly_chart(monte_carlo_histogram(r), use_container_width=True)
        with chart_tabs[5]:
            tax_data_cached = st.session_state.get("tax_summaries", [])
            if tax_data_cached:
                st.plotly_chart(tax_comparison_chart(tax_data_cached), use_container_width=True)
                for s in tax_data_cached:
                    with st.container():
                        st.markdown(f"**{s.region}** — 총 세금 {s.total_tax:,.0f}만원 (실효세율 {s.effective_tax_rate_pct}%)")
                        cols = st.columns(3)
                        cols[0].metric("취득세", f"{s.acquisition.amount:,.0f}만원", f"{s.acquisition.rate_pct}%")
                        cols[1].metric("보유세(연)", f"{s.holding.total_annual:,.0f}만원")
                        cols[2].metric("세후 순이익", f"{s.net_gain_after_tax:,.0f}만원")
            else:
                st.info("세금 분석 데이터가 없습니다. 회의 시작 시 자동으로 계산됩니다.")
        with chart_tabs[6]:
            score_data_cached = st.session_state.get("scorecards", [])
            if score_data_cached:
                st.plotly_chart(scorecard_chart(score_data_cached), use_container_width=True)
                for card in score_data_cached:
                    verdict_colors = {"투자 추천": "green", "조건부 추천": "orange", "대기": "gray", "패스": "red"}
                    color = verdict_colors.get(card.verdict, "gray")
                    st.markdown(
                        f"**{card.region}** — "
                        f"<span style='color:{color};font-weight:bold;'>{card.verdict}</span> "
                        f"({card.total_score}/{card.max_possible}점)",
                        unsafe_allow_html=True,
                    )
                    if card.key_strengths:
                        st.markdown(f"  - 강점: {'; '.join(card.key_strengths)}")
                    if card.key_risks:
                        st.markdown(f"  - 리스크: {'; '.join(card.key_risks)}")
            else:
                st.info("스코어카드 데이터가 없습니다. 회의 시작 시 자동으로 계산됩니다.")
        with chart_tabs[7]:
            port_data_cached = st.session_state.get("portfolios", [])
            if port_data_cached:
                st.plotly_chart(portfolio_scatter(port_data_cached), use_container_width=True)
                best = max(port_data_cached, key=lambda c: c.result.portfolio_irr)
                safest = min(port_data_cached, key=lambda c: c.result.portfolio_std)
                st.markdown(f"**수익 최적**: {best.combo_label} (IRR {best.result.portfolio_irr:.1f}%)")
                st.markdown(f"**안정 최적**: {safest.combo_label} (변동성 {safest.result.portfolio_std:.1f}%)")
            else:
                st.info("포트폴리오 비교를 위해 2개 이상 지역을 선택해 주세요.")

# ------------------------------------------------------------------
# 회의 종료 → 회의록 생성
# ------------------------------------------------------------------

if end_btn and meeting and not st.session_state.get("finalized"):
    user_turns = [m for m in messages if m["role"] == "user"]
    if not user_turns:
        st.warning("⚠️ 아직 대화가 없습니다. 먼저 발언해 주세요.")
    else:
        with st.spinner("📝 비서실장이 회의록을 정리하는 중..."):
            try:
                minutes_text, path = _run_async(meeting.finalize())
                st.session_state["finalized"] = True
                st.session_state["minutes"] = minutes_text
                messages.append({"role": "minutes", "content": minutes_text})
                st.session_state["messages"] = messages
                st.success(f"✅ 회의록 저장: {path}")
                st.rerun()
            except Exception as e:
                st.error(f"❌ 회의록 생성 실패: {e}")

# ------------------------------------------------------------------
# 채팅 입력
# ------------------------------------------------------------------

if not st.session_state.get("finalized"):
    if user_input := st.chat_input("대표님, 말씀하세요..."):
        messages.append({"role": "user", "content": user_input})

        with st.chat_message("user", avatar="🧑"):
            st.markdown(user_input)

        use_debate = st.session_state.get("debate_mode", False)
        n_rounds = st.session_state.get("debate_rounds", 2)

        try:
            if use_debate and n_rounds > 1:
                with st.spinner(f"에이전트 토론 중 ({n_rounds} 라운드)..."):
                    all_rounds = _run_async(
                        meeting.user_says_with_debate(user_input, rounds=n_rounds)
                    )
                turns = [t for rnd in all_rounds for t in rnd]
            else:
                with st.spinner("에이전트 응답 생성 중..."):
                    turns = _run_async(meeting.user_says(user_input))
        except Exception as e:
            st.error(f"❌ 에이전트 응답 생성 실패: {e}")
            st.info("API 키를 확인하거나, 네트워크 연결 상태를 점검해 주세요.")
            turns = []

        for turn in turns:
            key = turn["agent_key"]
            cfg = AGENT_CONFIG[key]
            color = AGENT_COLORS.get(key, "#666")
            msg_data = {
                "role": "agent",
                "agent_key": key,
                "content": turn["text"],
            }
            messages.append(msg_data)

            with st.chat_message("assistant", avatar=cfg["emoji"]):
                st.markdown(
                    f"<span style='color:{color};font-weight:bold;'>"
                    f"{cfg['name']}({cfg['label']})</span>",
                    unsafe_allow_html=True,
                )
                st.markdown(turn["text"])

        st.session_state["messages"] = messages
