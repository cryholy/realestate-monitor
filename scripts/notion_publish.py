"""Notion 공식 API로 갭 레이더 주간 리포트 초안을 비공개 부모 페이지에 발행.

cron(workflow_dispatch 포함)에서 호출. 사용자는 검수 후 페이지를 공개 부모로
이동시키고 메인 페이지 영역을 갱신해 공개한다.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from notion_client import Client

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


MAX_TEXT_LEN = 1900  # Notion rich_text 셀당 2000자 제한 안전 마진


@dataclass(frozen=True)
class PublishResult:
    page_id: str
    url: str


def _text_rich_text(content: str) -> list[dict]:
    """긴 문자열을 안전한 길이로 잘라 rich_text 배열로 만든다."""
    if not content:
        return [{"type": "text", "text": {"content": ""}}]
    chunks = [content[i:i + MAX_TEXT_LEN] for i in range(0, len(content), MAX_TEXT_LEN)]
    return [{"type": "text", "text": {"content": c}} for c in chunks]


def _heading_block(level: int, text: str) -> dict:
    block_type = {1: "heading_1", 2: "heading_2", 3: "heading_3"}[min(level, 3)]
    return {
        "object": "block",
        "type": block_type,
        block_type: {"rich_text": _text_rich_text(text)},
    }


def _paragraph_block(text: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _text_rich_text(text)},
    }


def _bullet_block(text: str) -> dict:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _text_rich_text(text)},
    }


def _quote_block(text: str) -> dict:
    return {
        "object": "block",
        "type": "quote",
        "quote": {"rich_text": _text_rich_text(text)},
    }


def _code_block(text: str, language: str = "markdown") -> dict:
    return {
        "object": "block",
        "type": "code",
        "code": {
            "rich_text": _text_rich_text(text),
            "language": language,
        },
    }


def markdown_to_blocks(markdown: str) -> list[dict]:
    """간단한 Markdown → Notion blocks 변환기.

    지원: H1~H3, 단락, bullet(-), quote(>), Markdown 표(코드 블록으로 보존).
    표 데이터가 큰 리포트라서 Notion 네이티브 표로 변환하지 않고 코드 블록에 보존한다.
    첫 번째 H1은 페이지 title로 사용되므로 본문에서 제외한다.
    """
    blocks: list[dict] = []
    lines = markdown.splitlines()
    i = 0
    h1_seen = False

    table_re = re.compile(r"^\s*\|.+\|\s*$")

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if stripped.startswith("# "):
            if not h1_seen:
                h1_seen = True
                i += 1
                continue
            blocks.append(_heading_block(1, stripped[2:].strip()))
            i += 1
            continue

        if stripped.startswith("## "):
            blocks.append(_heading_block(2, stripped[3:].strip()))
            i += 1
            continue

        if stripped.startswith("### "):
            blocks.append(_heading_block(3, stripped[4:].strip()))
            i += 1
            continue

        if stripped.startswith("> "):
            blocks.append(_quote_block(stripped[2:].strip()))
            i += 1
            continue

        if stripped.startswith("- "):
            blocks.append(_bullet_block(stripped[2:].strip()))
            i += 1
            continue

        if table_re.match(stripped) and i + 1 < len(lines) and re.match(r"^\s*\|[\s\-:|]+\|\s*$", lines[i + 1]):
            table_lines = []
            while i < len(lines) and table_re.match(lines[i].strip()):
                table_lines.append(lines[i])
                i += 1
            blocks.append(_code_block("\n".join(table_lines), language="markdown"))
            continue

        blocks.append(_paragraph_block(stripped))
        i += 1

    return blocks


def publish_draft_page(
    *,
    client,
    staging_parent_id: str,
    report_date: str,
    markdown_body: str,
    csv_public_url: str | None = None,
) -> PublishResult:
    """비공개 부모 페이지 아래에 초안 페이지를 생성하고 결과 반환.

    `csv_public_url`이 주어지면 본문 끝에 "전체 데이터 다운로드: [YYYY-MM-DD.csv](url)"
    paragraph를 자동 추가한다. 사용자가 검수·공개 단계에서 본문 안에 그대로 노출되는
    형태이며, [[feedback-publish-no-version-marks]] 정책에 따라 파일명에는 v2 같은
    버전 표식을 붙이지 않는다.
    """
    title = f"{report_date} 서울 한강권 대표단지 갭 레이더 (초안)"
    body = markdown_body
    if csv_public_url:
        body = body.rstrip() + (
            f"\n\n전체 데이터 다운로드: [{report_date}.csv]({csv_public_url})\n"
        )
    blocks = markdown_to_blocks(body)

    head, tail = blocks[:100], blocks[100:]

    response = client.pages.create(
        parent={"page_id": staging_parent_id},
        icon={"emoji": "📊"},
        properties={
            "title": [{"type": "text", "text": {"content": title}}],
        },
        children=head,
    )
    page_id = response["id"]
    page_url = response["url"]

    for offset in range(0, len(tail), 100):
        client.blocks.children.append(
            block_id=page_id,
            children=tail[offset:offset + 100],
        )

    return PublishResult(page_id=page_id, url=page_url)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="리포트 날짜. YYYY-MM-DD 형식")
    parser.add_argument(
        "--markdown",
        required=True,
        help="발행할 Markdown 본문 파일 경로",
    )
    parser.add_argument(
        "--csv-url",
        default="",
        help="(선택) CSV 부록 공개 URL. 주어지면 본문 끝에 다운로드 링크 자동 추가",
    )
    args = parser.parse_args()

    env_path = ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    notion_token = os.environ.get("NOTION_API_KEY", "").strip()
    staging_parent_id = os.environ.get("NOTION_STAGING_PARENT_ID", "").strip()
    missing = [name for name, value in [
        ("NOTION_API_KEY", notion_token),
        ("NOTION_STAGING_PARENT_ID", staging_parent_id),
    ] if not value]
    if missing:
        print(f"필수 환경변수 누락: {', '.join(missing)}", file=sys.stderr)
        return 2

    markdown_path = Path(args.markdown)
    if not markdown_path.exists():
        print(f"Markdown 파일을 찾을 수 없습니다: {markdown_path}", file=sys.stderr)
        return 2

    markdown_body = markdown_path.read_text(encoding="utf-8")

    client = Client(auth=notion_token)
    result = publish_draft_page(
        client=client,
        staging_parent_id=staging_parent_id,
        report_date=args.date,
        markdown_body=markdown_body,
        csv_public_url=args.csv_url or None,
    )
    print(f"Page ID: {result.page_id}")
    print(f"URL: {result.url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
