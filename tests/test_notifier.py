from unittest.mock import patch

import pytest

from lib.notifier import (
    format_won,
    format_price_message,
    format_jeonse_message,
    format_summary_message,
    send_telegram,
)


def test_format_won_basic():
    assert format_won(198000) == "19억 8,000"
    assert format_won(200000) == "20억"
    assert format_won(7300) == "7,300"
    assert format_won(75000) == "7억 5,000"


def test_format_won_zero():
    assert format_won(0) == "0"


def test_format_price_message_includes_all_fields():
    rule = {"display_name": "예시단지A", "size_label": "84", "max_price_만원": 200000}
    record = {"price_만원": 198000, "floor": 15, "deal_date": "2026-04-28",
              "dealing_type": "중개거래"}
    msg = format_price_message(rule, record, median_sale=198000, median_jeonse=125000,
                                sample_count_jeonse=12)

    assert "예시단지A 84㎡" in msg
    assert "19억 8,000" in msg
    assert "15층" in msg
    assert "2026-04-28" in msg
    assert "12억 5,000" in msg
    assert "전세가율" in msg
    assert "63" in msg


def test_format_price_message_when_no_jeonse_data():
    rule = {"display_name": "예시단지F", "size_label": "84"}
    record = {"price_만원": 195000, "floor": 10, "deal_date": "2026-04-20"}
    msg = format_price_message(rule, record, median_sale=195000, median_jeonse=None,
                                sample_count_jeonse=0)

    assert "전세 데이터 부족" in msg


def test_format_jeonse_message():
    rule = {"display_name": "예시단지A", "size_label": "84", "min_jeonse_ratio": 0.65}
    msg = format_jeonse_message(rule, ratio=0.656, median_sale=195000, median_jeonse=128000,
                                 sample_count_sale=8, sample_count_jeonse=14, month_key="2026-05")

    assert "전세가율 임계값 도달" in msg
    assert "예시단지A 84㎡" in msg
    assert "65" in msg
    assert "19억 5,000" in msg
    assert "12억 8,000" in msg
    assert "2026-05" in msg


def test_format_summary_message_contains_key_stats():
    msg = format_summary_message(
        run_started_at="2026-05-14 14:30 KST",
        months=2,
        districts=9,
        sales_total=1234,
        sales_new=56,
        rents_total=987,
        rents_new=34,
        rules_active=12,
        price_alerts_sent=2,
        jeonse_alerts_sent=1,
    )

    assert "2026-05-14 14:30 KST" in msg, "실행 시각 누락"
    # 핵심 통계가 메시지에 포함돼야 함 — 본문 작성 시 자유롭게 포맷팅하되
    # 아래 숫자들은 어떤 형태로든 들어가야 보고로서 의미가 있음.
    assert "1234" in msg or "1,234" in msg, "sales_total 누락"
    assert "56" in msg, "sales_new 누락"
    assert "987" in msg, "rents_total 누락"
    assert "34" in msg, "rents_new 누락"
    assert "12" in msg, "rules_active 누락"
    # 알림 발송 건수 — price_sent=2, jeonse_sent=1
    assert "2" in msg and "1" in msg, "알림 건수 누락"


def test_format_summary_message_zero_alerts():
    """후보 0건이어도 발송돼야 하는 게 이 함수의 존재 이유."""
    msg = format_summary_message(
        run_started_at="2026-05-14 05:30 KST",
        months=2,
        districts=9,
        sales_total=800,
        sales_new=0,
        rents_total=600,
        rents_new=0,
        rules_active=10,
        price_alerts_sent=0,
        jeonse_alerts_sent=0,
    )
    assert isinstance(msg, str) and len(msg) > 0


@patch("lib.notifier.requests.post")
def test_send_telegram_success(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"ok": True}

    send_telegram(token="DUMMY_TOKEN", chat_id="12345", text="hello")

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert "DUMMY_TOKEN" in args[0]
    assert kwargs["json"]["chat_id"] == "12345"
    assert kwargs["json"]["text"] == "hello"


@patch("lib.notifier.requests.post")
def test_send_telegram_failure_raises(mock_post):
    mock_post.return_value.status_code = 500
    mock_post.return_value.text = "Server Error"

    with pytest.raises(RuntimeError, match="텔레그램"):
        send_telegram(token="X", chat_id="1", text="hi")
