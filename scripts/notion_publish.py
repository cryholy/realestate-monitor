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
    """공개 부모 페이지 아래에 주간 리포트 페이지를 생성한다 (초안 표식 없음)."""
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
    - "이번 주 핵심 숫자" : 5줄 카운트 (사용자가 5/26에 다듬은 '평형 84/59/mid' 라벨 유지)
    - "지난 리포트" : 새 페이지 링크를 맨 위에 누적
    """
    parent_blocks = _list_all_children(client, public_parent_id)

    _replace_section(
        client=client,
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

    _replace_section(
        client=client,
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

    _prepend_to_section(
        client=client,
        parent_blocks=parent_blocks,
        section_heading="지난 리포트",
        new_blocks=[
            _bullet_block_with_link(
                f"{report_date} 서울 한강권 대표단지 갭 레이더",
                page_url,
            ),
        ],
        placeholder_text="아직 발행된 리포트가 없습니다.",
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
    parent_blocks: list[dict],
    section_heading: str,
    new_blocks: list[dict],
) -> None:
    """섹션 본문(헤더 다음~다음 헤더 전)을 통째로 교체한다."""
    rng = _find_section_range(parent_blocks, section_heading)
    if rng is None:
        return
    start, end = rng
    for block in parent_blocks[start:end]:
        try:
            client.blocks.delete(block_id=block["id"])
        except Exception:
            pass
    # 추가할 위치: 헤더 블록 바로 뒤. Notion API는 children.append + after 파라미터로 가능.
    heading_block_id = parent_blocks[start - 1]["id"]
    # after 미지원 시 단순 append 후 위치 수동 정렬 필요. 일단 단순 append.
    page_id = parent_blocks[0]["parent"].get("page_id") if parent_blocks else None
    # 더 안전: section_heading 직후 위치 지정 append는 blocks.children.append + after.
    # notion-client는 'after' 파라미터를 지원.
    after_id = heading_block_id
    for block in new_blocks:
        resp = client.blocks.children.append(
            block_id=_resolve_parent_id(parent_blocks),
            children=[block],
            after=after_id,
        )
        # 다음 블록도 같은 위치 뒤에 붙이기 위해 마지막 추가된 block id 갱신
        last = resp.get("results", [])
        if last:
            after_id = last[-1]["id"]


def _prepend_to_section(
    *,
    client,
    parent_blocks: list[dict],
    section_heading: str,
    new_blocks: list[dict],
    placeholder_text: str,
) -> None:
    """섹션 본문 맨 앞에 new_blocks 추가. placeholder 문장이 있으면 삭제 후 추가."""
    rng = _find_section_range(parent_blocks, section_heading)
    if rng is None:
        return
    start, end = rng

    # placeholder 텍스트가 본문에 있으면 그것만 정리하고 첫 자리에 누적
    for block in parent_blocks[start:end]:
        if block.get("type") == "paragraph":
            text = "".join(rt.get("text", {}).get("content", "") for rt in block["paragraph"].get("rich_text", []))
            if placeholder_text in text:
                try:
                    client.blocks.delete(block_id=block["id"])
                except Exception:
                    pass

    heading_block_id = parent_blocks[start - 1]["id"]
    after_id = heading_block_id
    for block in new_blocks:
        resp = client.blocks.children.append(
            block_id=_resolve_parent_id(parent_blocks),
            children=[block],
            after=after_id,
        )
        last = resp.get("results", [])
        if last:
            after_id = last[-1]["id"]


def _resolve_parent_id(parent_blocks: list[dict]) -> str:
    """block list에서 부모 page id 추출."""
    for b in parent_blocks:
        parent = b.get("parent", {})
        if parent.get("type") == "page_id":
            return parent["page_id"]
    raise RuntimeError("could not resolve parent page id from block list")


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
