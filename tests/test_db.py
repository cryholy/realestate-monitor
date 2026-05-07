from unittest.mock import MagicMock

import pytest

from lib.db import upsert_records, load_alert_rules, dedup_check, mark_alert_sent


@pytest.fixture
def mock_supabase():
    return MagicMock()


def test_upsert_records_calls_upsert_with_ignore(mock_supabase):
    records = [
        {"id": "abc", "apt_seq": "11000-0001", "price_만원": 198000},
        {"id": "def", "apt_seq": "11000-0001", "price_만원": 175000},
    ]
    mock_supabase.table.return_value.upsert.return_value.execute.return_value.data = records

    upsert_records(mock_supabase, "sale_records", records)

    mock_supabase.table.assert_called_with("sale_records")
    mock_supabase.table.return_value.upsert.assert_called_once()
    args, kwargs = mock_supabase.table.return_value.upsert.call_args
    assert args[0] == records
    assert kwargs.get("on_conflict") == "id"


def test_upsert_records_empty_returns_early(mock_supabase):
    upsert_records(mock_supabase, "sale_records", [])
    mock_supabase.table.assert_not_called()


def test_load_alert_rules_filters_enabled(mock_supabase):
    rules = [{"id": "r1", "apt_seq": "11000-0001", "enabled": True}]
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = rules

    result = load_alert_rules(mock_supabase)

    mock_supabase.table.assert_called_with("alert_rules")
    mock_supabase.table.return_value.select.assert_called_with("*")
    mock_supabase.table.return_value.select.return_value.eq.assert_called_with("enabled", True)
    assert result == rules


def test_dedup_check_returns_existing_keys(mock_supabase):
    mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
        {"rule_id": "r1", "dedup_key": "sale:abc"},
        {"rule_id": "r1", "dedup_key": "sale:def"},
    ]

    candidates = [
        {"rule_id": "r1", "dedup_key": "sale:abc"},
        {"rule_id": "r1", "dedup_key": "sale:def"},
        {"rule_id": "r1", "dedup_key": "sale:ghi"},
    ]

    new_alerts = dedup_check(mock_supabase, candidates)

    assert len(new_alerts) == 1
    assert new_alerts[0]["dedup_key"] == "sale:ghi"


def test_dedup_check_empty_candidates(mock_supabase):
    assert dedup_check(mock_supabase, []) == []
    mock_supabase.table.assert_not_called()


def test_mark_alert_sent_inserts_row(mock_supabase):
    mark_alert_sent(mock_supabase, rule_id="r1", dedup_key="sale:xyz", alert_type="price_threshold")

    mock_supabase.table.assert_called_with("alerts_sent")
    mock_supabase.table.return_value.insert.assert_called_once()
    args, _ = mock_supabase.table.return_value.insert.call_args
    payload = args[0]
    assert payload["rule_id"] == "r1"
    assert payload["dedup_key"] == "sale:xyz"
    assert payload["alert_type"] == "price_threshold"
