"""upload_csv.py 단위 테스트 — Supabase storage는 mock."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.upload_csv import build_storage_key, upload


def test_build_storage_key_pattern():
    assert build_storage_key("2026-06-01") == "r/2026-06-01.csv"
    assert build_storage_key("2026-12-31") == "r/2026-12-31.csv"


def test_upload_calls_storage_with_upsert_and_returns_public_url():
    fake_client = MagicMock()
    fake_client.storage.from_.return_value.get_public_url.return_value = (
        "https://example.supabase.co/storage/v1/object/public/reports/r/2026-06-01.csv"
    )
    public_url = upload(
        client=fake_client,
        storage_key="r/2026-06-01.csv",
        csv_bytes=b"a,b\n1,2\n",
    )
    upload_call = fake_client.storage.from_.return_value.upload.call_args
    assert upload_call.kwargs["path"] == "r/2026-06-01.csv"
    assert upload_call.kwargs["file"] == b"a,b\n1,2\n"
    assert upload_call.kwargs["file_options"]["upsert"] == "true"
    assert upload_call.kwargs["file_options"]["content-type"].startswith("text/csv")
    assert public_url.endswith("/reports/r/2026-06-01.csv")
