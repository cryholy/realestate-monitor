"""Notion 공식 API로 갭 레이더 주간 리포트를 공개 부모 페이지 아래에 자동 발행.

흐름:
1. 공개 부모(`📡 서울 한강권 대표단지 갭 레이더`) 아래에 주간 리포트 페이지 생성
2. 부모 페이지의 3개 영역 자동 갱신
   - "최신 주간 리포트": 새 페이지 링크 + 자동 요약 1줄
   - "이번 주 핵심 숫자": 5줄 카운트
   - "지난 리포트": 새 페이지 링크를 맨 위에 누적
3. 텔레그램 알림(공개 URL) 별도 단계로 전달
"""
from __future__ import annotations

import argparse
import json
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


_WEEKLY_TITLE_RE = re.compile(r"^\s*(\d{4}-\d{2}-\d{2})\s+서울 한강권 대표단지 갭 레이더\s*$")


def archive_existing_same_date_page(
    *,
    client,
    public_parent_id: str,
    report_date: str,
) -> list[str]:
    """공개 부모 페이지 아래에 같은 날짜의 주간 리포트 child_page가 이미 있으면
    archive(in_trash=true). 같은 날짜로 cron이 두 번 돌아도 페이지 중복을 막는다.

    Returns: archive한 page id 목록.
    """
    archived: list[str] = []
    cursor: str | None = None
    while True:
        kwargs = {"block_id": public_parent_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = client.blocks.children.list(**kwargs)
        for block in resp.get("results", []):
            if block.get("type") != "child_page":
                continue
            title = block.get("child_page", {}).get("title", "")
            match = _WEEKLY_TITLE_RE.match(title)
            if match and match.group(1) == report_date:
                try:
                    client.pages.update(page_id=block["id"], in_trash=True)
                    archived.append(block["id"])
                    print(f"archived existing page for {report_date}: {block['id']}", file=sys.stderr)
                except Exception as exc:
                    print(f"failed to archive {block['id']}: {exc}", file=sys.stderr)
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return archived


@dataclass(frozen=True)
class PublishResult:
    page_id: str
    url: str


def _text_rich_text(content: str) -> list[dict]:
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
    """간단한 Markdown → Notion blocks 변환기. 첫 번째 H1은 title로 사용되므로 본문에서 제외."""
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


def publish_weekly_page(
    *,
    client,
    public_parent_id: str,
    report_date: str,
    markdown_body: str,
    csv_public_url: str | None = None,
) -> PublishResult:
    """공개 부모 페이지 아래에 주간 리포트 페이지를 생성한다 (초안 표식 없음).

    같은 날짜 child_page가 이미 있으면 archive(in_trash) 후 새로 생성한다.
    """
    archive_existing_same_date_page(
        client=client,
        public_parent_id=public_parent_id,
        report_date=report_date,
    )
    title = f"{report_date} 서울 한강권 대표단지 갭 레이더"
    body = markdown_body
    if csv_public_url:
        body = body.rstrip() + (
            f"\n\n전체 데이터 다운로드: [{report_date}.csv]({csv_public_url})\n"
        )
    blocks = markdown_to_blocks(body)
    head, tail = blocks[:100], blocks[100:]

    response = client.pages.create(
        parent={"page_id": public_parent_id},
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


def update_parent_summary(
    *,
    client,
    public_parent_id: str,
    report_date: str,
    page_url: str,
    headline: str,
    counts: dict,
) -> None:
    """부모 페이지의 3개 영역 자동 갱신.

    - "최신 주간 리포트" : 새 페이지 링크 + headline 1줄
    - "이번 주 핵심 숫자" : 5줄 카운트
    - "지난 리포트" : 새 페이지 링크를 맨 위에 누적

    구현 메모: section 갱신은 delete + 단일 append (children 배열 한번에) 으로 처리한다.
    block 1개씩 따로 append + after 갱신은 Notion API에서 위치가 의도와 다르게 결정되어 본문이
    page 끝(child_page 뒤)으로 표류한다. 또한 각 section 처리 후 페이지 children list가 변경되니
    매 section마다 다시 fetch한다.
    """
    parent_blocks = _list_all_children(client, public_parent_id)
    _replace_section(
        client=client,
        parent_page_id=public_parent_id,
        parent_blocks=parent_blocks,
        section_heading="최신 주간 리포트",
        new_blocks=[
            _bullet_block_with_link(
                f"{report_date} 서울 한강권 대표단지 갭 레이더",
                page_url,
            ),
            _paragraph_block(headline),
        ],
    )

    parent_blocks = _list_all_children(client, public_parent_id)
    _replace_section(
        client=client,
        parent_page_id=public_parent_id,
        parent_blocks=parent_blocks,
        section_heading="이번 주 핵심 숫자",
        new_blocks=[
            _bullet_block(f"분석 항목: 대표 `단지+평형` {counts['total_rows']}개 (평형 84/59/mid)"),
            _bullet_block(f"신규 전세가율 상승 항목: {counts['ratio_up']}개"),
            _bullet_block(f"갭 축소 항목: {counts['gap_down']}개"),
            _bullet_block(f"갱신권 사용률 상승 항목: {counts['use_rate_up']}개"),
            _bullet_block(f"매매·신규전세 표본이 모두 5건 이상인 항목: {counts['high_reliability']}개 (신뢰도 높음)"),
        ],
    )

    parent_blocks = _list_all_children(client, public_parent_id)
    _prepend_to_section(
        client=client,
        parent_page_id=public_parent_id,
        parent_blocks=parent_blocks,
        section_heading="지난 리포트",
        new_blocks=[
            _bullet_block_with_link(
                f"{report_date} 서울 한강권 대표단지 갭 레이더",
                page_url,
            ),
        ],
        placeholder_text="아직 발행된 리포트가 없습니다.",
        duplicate_guard_text=f"{report_date} 서울 한강권 대표단지 갭 레이더",
    )


def _bullet_block_with_link(text: str, url: str) -> dict:
    """clickable link가 포함된 bullet."""
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": text, "link": {"url": url}},
                }
            ]
        },
    }


def _list_all_children(client, page_id: str) -> list[dict]:
    """페이지의 모든 child block을 가져온다 (페이지네이션 처리)."""
    blocks = []
    cursor = None
    while True:
        kwargs = {"block_id": page_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = client.blocks.children.list(**kwargs)
        blocks.extend(resp.get("results", []))
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return blocks


def _find_section_range(blocks: list[dict], heading_text: str) -> tuple[int, int] | None:
    """heading_2 블록 중 텍스트가 heading_text와 일치하는 섹션의 [start, end) 범위.

    start: heading 다음 블록 인덱스
    end: 다음 heading_2(또는 heading_1) 인덱스, 또는 끝
    찾지 못하면 None.
    """
    start = None
    for i, b in enumerate(blocks):
        if b.get("type") == "heading_2":
            text = "".join(rt.get("text", {}).get("content", "") for rt in b["heading_2"].get("rich_text", []))
            if text.strip() == heading_text:
                start = i + 1
                continue
        if start is not None and b.get("type") in ("heading_1", "heading_2"):
            return (start, i)
    if start is not None:
        return (start, len(blocks))
    return None


def _replace_section(
    *,
    client,
    parent_page_id: str,
    parent_blocks: list[dict],
    section_heading: str,
    new_blocks: list[dict],
) -> None:
    """섹션 본문(헤더 다음~다음 헤더 전)을 통째로 교체한다. children은 단일 append 호출.

    child_page 블록은 보존(삭제 시도 X). 그 외 block delete 실패는 stderr 로깅 후 계속 진행.
    """
    rng = _find_section_range(parent_blocks, section_heading)
    if rng is None:
        print(f"SECTION_NOT_FOUND: {section_heading}", file=sys.stderr)
        return
    start, end = rng
    for block in parent_blocks[start:end]:
        if block.get("type") == "child_page":
            continue
        try:
            client.blocks.delete(block_id=block["id"])
        except Exception as exc:
            print(f"failed to delete block {block['id']} ({block.get('type')}): {exc}", file=sys.stderr)
    heading_block_id = parent_blocks[start - 1]["id"]
    client.blocks.children.append(
        block_id=parent_page_id,
        children=new_blocks,
        after=heading_block_id,
    )


def _prepend_to_section(
    *,
    client,
    parent_page_id: str,
    parent_blocks: list[dict],
    section_heading: str,
    new_blocks: list[dict],
    placeholder_text: str,
    duplicate_guard_text: str | None = None,
) -> None:
    """섹션 본문 맨 앞에 new_blocks 추가. placeholder가 있으면 삭제 후 추가.

    `duplicate_guard_text`가 주어지면 기존 블록 중 그 텍스트를 포함하는 줄이 있으면
    중복 추가하지 않는다 (재실행 idempotency).
    """
    rng = _find_section_range(parent_blocks, section_heading)
    if rng is None:
        print(f"SECTION_NOT_FOUND: {section_heading}", file=sys.stderr)
        return
    start, end = rng

    for block in parent_blocks[start:end]:
        text = ""
        for kind in ("paragraph", "bulleted_list_item"):
            if block.get("type") == kind:
                text = "".join(rt.get("text", {}).get("content", "") for rt in block[kind].get("rich_text", []))
                break
        if placeholder_text and placeholder_text in text:
            try:
                client.blocks.delete(block_id=block["id"])
            except Exception as exc:
                print(f"failed to delete placeholder block {block['id']}: {exc}", file=sys.stderr)
        if duplicate_guard_text and duplicate_guard_text in text:
            print(f"duplicate guard hit for '{duplicate_guard_text}' — skipping prepend", file=sys.stderr)
            return

    heading_block_id = parent_blocks[start - 1]["id"]
    client.blocks.children.append(
        block_id=parent_page_id,
        children=new_blocks,
        after=heading_block_id,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="리포트 날짜. YYYY-MM-DD")
    parser.add_argument("--markdown", required=True, help="발행할 Markdown 본문 파일 경로")
    parser.add_argument("--summary", required=True, help="counts + headline JSON 파일 경로")
    parser.add_argument("--csv-url", default="", help="(선택) CSV 부록 공개 URL")
    args = parser.parse_args()

    env_path = ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    notion_token = os.environ.get("NOTION_API_KEY", "").strip()
    public_parent_id = os.environ.get("NOTION_PUBLIC_PARENT_ID", "").strip()
    missing = [name for name, value in [
        ("NOTION_API_KEY", notion_token),
        ("NOTION_PUBLIC_PARENT_ID", public_parent_id),
    ] if not value]
    if missing:
        print(f"필수 환경변수 누락: {', '.join(missing)}", file=sys.stderr)
        return 2

    markdown_path = Path(args.markdown)
    summary_path = Path(args.summary)
    if not markdown_path.exists():
        print(f"Markdown 파일을 찾을 수 없습니다: {markdown_path}", file=sys.stderr)
        return 2
    if not summary_path.exists():
        print(f"Summary 파일을 찾을 수 없습니다: {summary_path}", file=sys.stderr)
        return 2

    markdown_body = markdown_path.read_text(encoding="utf-8")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    client = Client(auth=notion_token)
    result = publish_weekly_page(
        client=client,
        public_parent_id=public_parent_id,
        report_date=args.date,
        markdown_body=markdown_body,
        csv_public_url=args.csv_url or None,
    )
    print(f"Page ID: {result.page_id}")
    print(f"URL: {result.url}")

    update_parent_summary(
        client=client,
        public_parent_id=public_parent_id,
        report_date=args.date,
        page_url=result.url,
        headline=summary.get("headline", ""),
        counts=summary.get("counts", {}),
    )
    print("Parent summary updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
