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


def test_markdown_to_blocks_keeps_markdown_table_as_code_block():
    md = "## Top\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
    blocks = markdown_to_blocks(md)
    code_blocks = [b for b in blocks if b["type"] == "code"]
    assert len(code_blocks) == 1
    text = "".join(rt["text"]["content"] for rt in code_blocks[0]["code"]["rich_text"])
    assert "| a | b |" in text
    assert "| 1 | 2 |" in text


def test_publish_weekly_page_creates_page_without_draft_suffix():
    fake_client = MagicMock()
    fake_client.pages.create.return_value = {
        "id": "abc123",
        "url": "https://www.notion.so/abc123",
    }
    result = publish_weekly_page(
        client=fake_client,
        public_parent_id="parent-id",
        report_date="2026-06-01",
        markdown_body="## 이번 주 요약\n\nbody",
    )
    assert isinstance(result, PublishResult)
    assert result.page_id == "abc123"
    assert result.url == "https://www.notion.so/abc123"
    call_kwargs = fake_client.pages.create.call_args.kwargs
    assert call_kwargs["parent"] == {"page_id": "parent-id"}
    title_text = call_kwargs["properties"]["title"][0]["text"]["content"]
    assert title_text == "2026-06-01 서울 한강권 대표단지 갭 레이더"
    # 자동 발행이므로 (초안) 표식이 절대 들어가서는 안 됨
    assert "(초안)" not in title_text


def test_publish_weekly_page_appends_csv_link_when_url_given():
    fake_client = MagicMock()
    fake_client.pages.create.return_value = {"id": "abc", "url": "https://www.notion.so/abc"}
    publish_weekly_page(
        client=fake_client,
        public_parent_id="parent-id",
        report_date="2026-06-01",
        markdown_body="## 이번 주 요약\n\nbody",
        csv_public_url="https://example.com/r/2026-06-01.csv",
    )
    children = fake_client.pages.create.call_args.kwargs["children"]
    # 마지막 paragraph block 안에 CSV 링크 텍스트가 포함되어야 함
    flat = "".join(
        "".join(rt.get("text", {}).get("content", "") for rt in b.get("paragraph", {}).get("rich_text", []))
        for b in children if b.get("type") == "paragraph"
    )
    assert "2026-06-01.csv" in flat
    assert "https://example.com/r/2026-06-01.csv" in flat
