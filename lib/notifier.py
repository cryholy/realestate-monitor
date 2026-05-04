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
