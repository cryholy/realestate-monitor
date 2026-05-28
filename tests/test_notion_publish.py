"""notion_publish.py 단위 테스트 — Notion API는 mock."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.notion_publish import (  # noqa: E402
    PublishResult,
    archive_existing_same_date_page,
    markdown_to_blocks,
    publish_weekly_page,
)


def test_markdown_to_blocks_handles_headings_and_paragraphs():
    md = "# Title\n\n## Section\n\nFirst paragraph.\n\n- bullet a\n- bullet b\n"
    blocks = markdown_to_blocks(md)
    types = [b["type"] for b in blocks]
    assert types[0] == "heading_2"
    assert "paragraph" in types
    assert "bulleted_list_item" in types


def test_publish_weekly_page_creates_page_without_draft_suffix():
    fake_client = MagicMock()
    fake_client.blocks.children.list.return_value = {"results": [], "has_more": False}
    fake_client.pages.create.return_value = {"id": "abc123", "url": "https://www.notion.so/abc123"}
    result = publish_weekly_page(
        client=fake_client,
        public_parent_id="parent-id",
        report_date="2026-06-01",
        markdown_body="## 이번 주 요약\n\nbody",
    )
    assert isinstance(result, PublishResult)
    assert result.page_id == "abc123"
    call_kwargs = fake_client.pages.create.call_args.kwargs
    title_text = call_kwargs["properties"]["title"][0]["text"]["content"]
    assert title_text == "2026-06-01 서울 한강권 대표단지 갭 레이더"
    assert "(초안)" not in title_text


def test_archive_existing_same_date_page_archives_match():
    fake_client = MagicMock()
    fake_client.blocks.children.list.return_value = {
        "results": [
            {"id": "blk-1", "type": "child_page", "child_page": {"title": "소개 / 방법론"}},
            {"id": "blk-2", "type": "child_page", "child_page": {"title": "2026-06-01 서울 한강권 대표단지 갭 레이더"}},
            {"id": "blk-3", "type": "child_page", "child_page": {"title": "2026-05-25 서울 한강권 대표단지 갭 레이더"}},
        ],
        "has_more": False,
    }
    archived = archive_existing_same_date_page(
        client=fake_client,
        public_parent_id="parent-id",
        report_date="2026-06-01",
    )
    assert archived == ["blk-2"]
    fake_client.pages.update.assert_called_once()
    update_kwargs = fake_client.pages.update.call_args.kwargs
    assert update_kwargs["page_id"] == "blk-2"
    assert update_kwargs.get("in_trash") is True


def test_archive_existing_same_date_page_returns_empty_when_no_match():
    fake_client = MagicMock()
    fake_client.blocks.children.list.return_value = {
        "results": [
            {"id": "blk-1", "type": "child_page", "child_page": {"title": "소개 / 방법론"}},
        ],
        "has_more": False,
    }
    archived = archive_existing_same_date_page(
        client=fake_client,
        public_parent_id="parent-id",
        report_date="2026-06-01",
    )
    assert archived == []
    fake_client.pages.update.assert_not_called()


def test_publish_weekly_page_calls_archive_before_create():
    """idempotency: publish_weekly_page entry에서 archive 호출되는지."""
    fake_client = MagicMock()
    fake_client.blocks.children.list.return_value = {
        "results": [
            {"id": "blk-dup", "type": "child_page", "child_page": {"title": "2026-06-01 서울 한강권 대표단지 갭 레이더"}},
        ],
        "has_more": False,
    }
    fake_client.pages.create.return_value = {"id": "new-abc", "url": "https://www.notion.so/new-abc"}
    publish_weekly_page(
        client=fake_client,
        public_parent_id="parent-id",
        report_date="2026-06-01",
        markdown_body="## body",
    )
    # archive가 먼저 호출됐는지
    fake_client.pages.update.assert_called_once()
    archive_kwargs = fake_client.pages.update.call_args.kwargs
    assert archive_kwargs["page_id"] == "blk-dup"
    assert archive_kwargs.get("in_trash") is True
