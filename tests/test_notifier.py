from unittest.mock import patch

import pytest

from lib.notifier import (
    format_won,
    format_price_message,
    format_jeonse_message,
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
    rule = {"display_name": "헬리오시티", "size_label": "84", "max_price_만원": 200000}
    record = {"price_만원": 198000, "floor": 15, "deal_date": "2026-04-28",
              "dealing_type": "중개거래"}
    msg = format_price_message(rule, record, median_sale=198000, median_jeonse=125000,
                                sample_count_jeonse=12)

    assert "헬리오시티 84㎡" in msg
    assert "19억 8,000" in msg
    assert "15층" in msg
    assert "2026-04-28" in msg
    assert "12억 5,000" in msg
    assert "전세가율" in msg
    assert "63" in msg


def test_format_price_message_when_no_jeonse_data():
    rule = {"display_name": "옥수하이츠", "size_label": "84"}
    record = {"price_만원": 195000, "floor": 10, "deal_date": "2026-04-20"}
    msg = format_price_message(rule, record, median_sale=195000, median_jeonse=None,
                                sample_count_jeonse=0)

    assert "전세 데이터 부족" in msg


def test_format_jeonse_message():
    rule = {"display_name": "헬리오시티", "size_label": "84", "min_jeonse_ratio": 0.65}
    msg = format_jeonse_message(rule, ratio=0.656, median_sale=195000, median_jeonse=128000,
                                 sample_count_sale=8, sample_count_jeonse=14, month_key="2026-05")

    assert "전세가율 임계값 도달" in msg
    assert "헬리오시티 84㎡" in msg
    assert "65" in msg
    assert "19억 5,000" in msg
    assert "12억 8,000" in msg
    assert "2026-05" in msg


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
