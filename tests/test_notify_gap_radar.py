"""notify_gap_radar.py 단위 테스트 — Telegram API는 mock."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.notify_gap_radar import build_success_message, build_failure_message


def test_build_success_message_includes_url_and_counts():
    msg = build_success_message(
        report_date="2026-06-01",
        page_url="https://www.notion.so/abc",
        total_rows=92,
        high_reliability=46,
        ratio_up=58,
        gap_down=55,
        use_rate_up=33,
    )
    assert "2026-06-01" in msg
    assert "https://www.notion.so/abc" in msg
    assert "분석 항목 92" in msg
    assert "신뢰도 높음 46" in msg
    assert "전세가율 상승 58" in msg
    assert "갭 축소 55" in msg
    assert "갱신권 사용률 상승 33" in msg
    assert "초안" in msg


def test_build_failure_message_includes_reason():
    msg = build_failure_message(
        report_date="2026-06-01",
        reason="Supabase view returned 0 rows",
    )
    assert "2026-06-01" in msg
    assert "실패" in msg
    assert "Supabase view returned 0 rows" in msg
