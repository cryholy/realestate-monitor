"""텔레그램 알림 + 메시지 포맷."""
import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def format_won(만원: int) -> str:
    """198000 만원 → '19억 8,000'."""
    if 만원 == 0:
        return "0"
    억 = 만원 // 10000
    rest = 만원 % 10000
    if 억 == 0:
        return f"{rest:,}"
    if rest == 0:
        return f"{억}억"
    return f"{억}억 {rest:,}"


def format_price_message(
    rule: dict,
    record: dict,
    *,
    median_sale: int,
    median_jeonse: int | None,
    sample_count_jeonse: int,
) -> str:
    """가격 임계값 도달 알림 메시지."""
    head = (
        f"🏠 매매가 임계값 도달 ({rule['display_name']} {rule['size_label']}㎡)\n\n"
        f"💰 매매가  {format_won(record['price_만원'])} "
        f"({record.get('floor')}층, {record['deal_date']} 신고)"
    )
    if record.get("dealing_type"):
        head += f" · {record['dealing_type']}"

    if median_jeonse is None:
        body = f"\n📊 전세 데이터 부족 (최근 90일 {sample_count_jeonse}건)"
        body += "\n🔻 갭 계산 불가"
    else:
        gap = record["price_만원"] - median_jeonse
        ratio = median_jeonse / record["price_만원"]
        body = (
            f"\n📊 직전 90일 전세 시세 ({rule['size_label']}㎡, {sample_count_jeonse}건)\n"
            f"   • 중위값  {format_won(median_jeonse)}\n"
            f"🔻 갭 (매매 − 전세 중위값)  약 {format_won(gap)}\n"
            f"📈 전세가율  {ratio*100:.1f}%"
        )
    return head + body


def format_jeonse_message(
    rule: dict,
    *,
    ratio: float,
    median_sale: int,
    median_jeonse: int,
    sample_count_sale: int,
    sample_count_jeonse: int,
    month_key: str,
) -> str:
    """전세가율 임계값 도달 알림 메시지."""
    threshold_pct = rule['min_jeonse_ratio'] * 100
    gap = median_sale - median_jeonse
    return (
        f"📈 전세가율 임계값 도달 ({rule['display_name']} {rule['size_label']}㎡, "
        f"{threshold_pct:.0f}% ↑)\n\n"
        f"📊 직전 90일 중위값\n"
        f"   • 매매  {format_won(median_sale)}\n"
        f"   • 전세  {format_won(median_jeonse)}\n"
        f"🔻 갭  약 {format_won(gap)}\n"
        f"📈 전세가율  {ratio*100:.1f}%  (임계값 {threshold_pct:.1f}%)\n\n"
        f"표본: 매매 {sample_count_sale}건 / 전세 {sample_count_jeonse}건\n"
        f"{month_key} 신호 — 이 달은 추가 알림 없음"
    )


def format_summary_message(
    *,
    run_started_at: str,
    months: int,
    districts: int,
    sales_total: int,
    sales_new: int,
    rents_total: int,
    rents_new: int,
    rules_active: int,
    price_alerts_sent: int,
    jeonse_alerts_sent: int,
) -> str:
    """배치 실행 결과 요약 메시지.

    매 cron 실행 후 1회 발송 — 알림이 0건이어도 발송돼서
    "배치 자체가 살아 있다"는 신호 역할을 한다.

    Args:
        run_started_at: 실행 시작 시각 (사람 친화적 KST 표기 권장, 예: "2026-05-14 14:30 KST")
        months: backfill 대상 개월 수
        districts: 수집 대상 구 개수
        sales_total: 이번 실행 매매 API 응답 총건수
        sales_new: 이번 실행 매매 신규 (DB에 처음 들어온 것)
        rents_total: 이번 실행 전월세 API 응답 총건수
        rents_new: 이번 실행 전월세 신규
        rules_active: 활성 알림 룰 수
        price_alerts_sent: 매매가 임계값 알림 발송 건수
        jeonse_alerts_sent: 전세가율 알림 발송 건수

    Returns:
        텔레그램에 그대로 보낼 수 있는 단일 문자열.
    """
    total_alerts = price_alerts_sent + jeonse_alerts_sent
    lines = [
        "📋 일일 모니터링 보고",
        f"실행 {run_started_at}",
        "",
        f"🗺  대상  {districts}개 구 × {months}개월",
        "",
        f"🏠 매매  {sales_total:,}건 (신규 {sales_new:,}건)",
        f"🏡 전월세  {rents_total:,}건 (신규 {rents_new:,}건)",
        "",
        f"🔔 알림 룰 {rules_active}개 활성",
        f"   • 매매가 임계값  {price_alerts_sent}건 발송",
        f"   • 전세가율 임계값  {jeonse_alerts_sent}건 발송",
    ]
    if total_alerts == 0:
        lines.append("")
        lines.append("✅ 특이사항 없음")
    return "\n".join(lines)


def send_telegram(*, token: str, chat_id: str, text: str) -> None:
    """텔레그램 봇 메시지 전송. 실패 시 RuntimeError."""
    url = TELEGRAM_API.format(token=token)
    resp = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"텔레그램 발송 실패 ({resp.status_code}): {resp.text[:200]}")
