from unittest.mock import patch

import pytest

from monitor import format_message, send_telegram


def test_format_message_with_gap():
    match = {
        "complex_display": "서울숲푸르지오",
        "size_label": "84",
        "거래금액": 198000,
        "층": 15,
        "거래일": "2026-04-28",
    }
    gap_info = {
        "sample_count": 12,
        "median_보증금": 125000,
        "min_보증금": 115000,
        "max_보증금": 138000,
        "gap": 73000,
        "used_extended": False,
        "lookback_days_actual": 90,
    }
    msg = format_message(match, gap_info)

    assert "서울숲푸르지오 84㎡" in msg
    assert "19억 8,000" in msg
    assert "15층" in msg
    assert "2026-04-28" in msg
    assert "12억 5,000" in msg  # median
    assert "11억 5,000" in msg  # min
    assert "13억 8,000" in msg  # max
    assert "7억 3,000" in msg   # gap


def test_format_message_insufficient_rent_samples():
    match = {
        "complex_display": "옥수하이츠",
        "size_label": "84",
        "거래금액": 195000,
        "층": 10,
        "거래일": "2026-04-20",
    }
    gap_info = {
        "sample_count": 1,
        "median_보증금": None,
        "min_보증금": None,
        "max_보증금": None,
        "gap": None,
        "used_extended": True,
        "lookback_days_actual": 180,
    }
    msg = format_message(match, gap_info)
    assert "전세 데이터 부족" in msg
    assert "갭 계산 불가" in msg


@patch("monitor.requests.post")
def test_send_telegram_calls_bot_api(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"ok": True}

    send_telegram("DUMMY_TOKEN", "12345", "테스트 메시지")

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert "DUMMY_TOKEN" in args[0]
    assert kwargs["json"]["chat_id"] == "12345"
    assert kwargs["json"]["text"] == "테스트 메시지"


@patch("monitor.requests.post")
def test_send_telegram_raises_on_failure(mock_post):
    mock_post.return_value.status_code = 500
    mock_post.return_value.text = "Internal Server Error"

    with pytest.raises(RuntimeError, match="텔레그램"):
        send_telegram("DUMMY_TOKEN", "12345", "테스트")
