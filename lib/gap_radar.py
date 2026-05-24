"""서울 한강권 대표단지 갭 레이더 리포트 렌더링 도우미."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO


@dataclass(frozen=True)
class RadarRow:
    district_rank: int
    representative_score: float
    apt_seq: str
    apt_name: str
    sgg_cd: str
    district_name: str
    lifestyle_area: str
    size_label: str
    sale_count_12m: int
    jeonse_count_12m: int
    sale_median_12m: int | None
    jeonse_median_12m: int | None
    sale_count_90d: int | None
    sale_median_90d: int | None
    jeonse_count_90d: int | None
    jeonse_median_90d: int | None
    gap_90d: int | None
    jeonse_ratio_90d: float | None
    sale_count_prev_90d: int | None
    sale_median_prev_90d: int | None
    jeonse_count_prev_90d: int | None
    jeonse_median_prev_90d: int | None
    gap_prev_90d: int | None
    jeonse_ratio_prev_90d: float | None

    @classmethod
    def from_db(cls, row: dict) -> "RadarRow":
        return cls(
            district_rank=int(row.get("district_rank") or 0),
            representative_score=float(row.get("representative_score") or 0),
            apt_seq=row.get("apt_seq") or "",
            apt_name=row.get("apt_name") or "",
            sgg_cd=row.get("sgg_cd") or "",
            district_name=row.get("district_name") or "",
            lifestyle_area=row.get("lifestyle_area") or "",
            size_label=row.get("size_label") or "",
            sale_count_12m=int(row.get("sale_count_12m") or 0),
            jeonse_count_12m=int(row.get("jeonse_count_12m") or 0),
            sale_median_12m=_optional_int(row.get("sale_median_12m")),
            jeonse_median_12m=_optional_int(row.get("jeonse_median_12m")),
            sale_count_90d=_optional_int(row.get("sale_count_90d")),
            sale_median_90d=_optional_int(row.get("sale_median_90d")),
            jeonse_count_90d=_optional_int(row.get("jeonse_count_90d")),
            jeonse_median_90d=_optional_int(row.get("jeonse_median_90d")),
            gap_90d=_optional_int(row.get("gap_90d")),
            jeonse_ratio_90d=_optional_float(row.get("jeonse_ratio_90d")),
            sale_count_prev_90d=_optional_int(row.get("sale_count_prev_90d")),
            sale_median_prev_90d=_optional_int(row.get("sale_median_prev_90d")),
            jeonse_count_prev_90d=_optional_int(row.get("jeonse_count_prev_90d")),
            jeonse_median_prev_90d=_optional_int(row.get("jeonse_median_prev_90d")),
            gap_prev_90d=_optional_int(row.get("gap_prev_90d")),
            jeonse_ratio_prev_90d=_optional_float(row.get("jeonse_ratio_prev_90d")),
        )

    @property
    def gap_delta(self) -> int | None:
        if self.gap_90d is None or self.gap_prev_90d is None:
            return None
        return self.gap_90d - self.gap_prev_90d

    @property
    def ratio_delta(self) -> float | None:
        if self.jeonse_ratio_90d is None or self.jeonse_ratio_prev_90d is None:
            return None
        return self.jeonse_ratio_90d - self.jeonse_ratio_prev_90d


def _optional_int(value) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_float(value) -> float | None:
    if value is None:
        return None
    return float(value)


def format_eok(value: int | None) -> str:
    if value is None:
        return "-"
    return f"{value / 10000:.1f}억"


def format_ratio(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.1f}%"


def reliability_label(sale_count_90d: int | None, jeonse_count_90d: int | None) -> str:
    sale_count = sale_count_90d or 0
    jeonse_count = jeonse_count_90d or 0
    if sale_count == 0 or jeonse_count == 0:
        return "데이터 부족"
    if sale_count >= 5 and jeonse_count >= 5:
        return "신뢰도 높음"
    return "주의"


def render_markdown_report(rows: list[RadarRow], *, report_date: str) -> str:
    rows = sorted(rows, key=lambda r: (r.lifestyle_area, r.district_name, r.district_rank, r.apt_name, r.size_label))
    gap_down_count = sum(1 for r in rows if r.gap_delta is not None and r.gap_delta < 0)
    ratio_up_count = sum(1 for r in rows if r.ratio_delta is not None and r.ratio_delta > 0)
    high_reliability_count = sum(
        1 for r in rows if reliability_label(r.sale_count_90d, r.jeonse_count_90d) == "신뢰도 높음"
    )

    lines = [
        f"# 서울 한강권 대표단지 갭 레이더 - {report_date}",
        "",
        "## 이번 주 요약",
        "",
        f"- 대표 `단지+평형` {len(rows)}개 항목 중 전세가율이 상승한 항목은 {ratio_up_count}개입니다.",
        f"- 대표 `단지+평형` {len(rows)}개 항목 중 갭이 축소된 항목은 {gap_down_count}개입니다.",
        f"- 최근 90일 매매와 전세 표본이 모두 5건 이상인 항목은 {high_reliability_count}개입니다.",
        "- 이 리포트는 매수 추천이나 투자 추천이 아니라 데이터 기반 관찰 자료입니다.",
        "",
        "## 갭 축소 Top 10",
        "",
    ]
    lines.extend(_render_delta_table(
        sorted([r for r in rows if r.gap_delta is not None], key=lambda r: r.gap_delta)[:10],
        metric="gap",
    ))
    lines.extend([
        "",
        "## 전세가율 상승 Top 10",
        "",
    ])
    lines.extend(_render_delta_table(
        sorted([r for r in rows if r.ratio_delta is not None], key=lambda r: r.ratio_delta, reverse=True)[:10],
        metric="ratio",
    ))
    lines.extend([
        "",
        "## 구별 대표단지 레이더",
        "",
        "| 생활권 | 구 | 순위 | 단지 | 평형 | 매매 중위 | 전세 중위 | 갭 | 전세가율 | 신뢰도 |",
        "|---|---|---:|---|---:|---:|---:|---:|---:|---|",
    ])
    for row in rows:
        lines.append(
            "| {lifestyle} | {district} | {rank} | {apt} | {size} | {sale} | {jeonse} | {gap} | {ratio} | {reliability} |".format(
                lifestyle=row.lifestyle_area,
                district=row.district_name,
                rank=row.district_rank,
                apt=row.apt_name,
                size=row.size_label,
                sale=format_eok(row.sale_median_90d),
                jeonse=format_eok(row.jeonse_median_90d),
                gap=format_eok(row.gap_90d),
                ratio=format_ratio(row.jeonse_ratio_90d),
                reliability=reliability_label(row.sale_count_90d, row.jeonse_count_90d),
            )
        )
    lines.extend([
        "",
        "## 데이터 신뢰도와 주의사항",
        "",
        "- 실거래 신고 지연으로 최근 거래는 뒤늦게 추가될 수 있습니다.",
        "- 최근 90일 거래가 적은 항목은 중위가와 갭이 흔들릴 수 있습니다.",
        "- 직거래, 취소거래, 단일 고가/저가 거래는 가격 해석을 왜곡할 수 있습니다.",
        "- 이 리포트는 매수 추천이나 투자 추천이 아닙니다.",
        "",
    ])
    return "\n".join(lines)


def _render_delta_table(rows: list[RadarRow], *, metric: str) -> list[str]:
    if metric == "gap":
        header = "| 생활권 | 구 | 단지 | 평형 | 현재 갭 | 직전 갭 | 변화 | 신뢰도 |"
        align = "|---|---|---|---:|---:|---:|---:|---|"
    elif metric == "ratio":
        header = "| 생활권 | 구 | 단지 | 평형 | 현재 전세가율 | 직전 전세가율 | 변화 | 신뢰도 |"
        align = "|---|---|---|---:|---:|---:|---:|---|"
    else:
        raise ValueError(f"unknown metric: {metric}")

    lines = [header, align]
    if not rows:
        lines.append("| - | - | - | - | - | - | - | - |")
        return lines

    for row in rows:
        if metric == "gap":
            current = format_eok(row.gap_90d)
            previous = format_eok(row.gap_prev_90d)
            delta = format_eok(row.gap_delta)
        else:
            current = format_ratio(row.jeonse_ratio_90d)
            previous = format_ratio(row.jeonse_ratio_prev_90d)
            delta = format_ratio(row.ratio_delta)
        lines.append(
            "| {lifestyle} | {district} | {apt} | {size} | {current} | {previous} | {delta} | {reliability} |".format(
                lifestyle=row.lifestyle_area,
                district=row.district_name,
                apt=row.apt_name,
                size=row.size_label,
                current=current,
                previous=previous,
                delta=delta,
                reliability=reliability_label(row.sale_count_90d, row.jeonse_count_90d),
            )
        )
    return lines


def render_csv(rows: list[RadarRow]) -> str:
    out = StringIO()
    writer = csv.DictWriter(out, fieldnames=[
        "district_name",
        "apt_name",
        "size_label",
        "lifestyle_area",
        "district_rank",
        "representative_score",
        "sale_count_12m",
        "jeonse_count_12m",
        "sale_median_90d",
        "jeonse_median_90d",
        "gap_90d",
        "jeonse_ratio_90d",
        "gap_delta",
        "ratio_delta",
        "reliability",
        "apt_seq",
    ])
    writer.writeheader()
    for row in rows:
        writer.writerow({
            "district_name": row.district_name,
            "apt_name": row.apt_name,
            "size_label": row.size_label,
            "lifestyle_area": row.lifestyle_area,
            "district_rank": row.district_rank,
            "representative_score": row.representative_score,
            "sale_count_12m": row.sale_count_12m,
            "jeonse_count_12m": row.jeonse_count_12m,
            "sale_median_90d": row.sale_median_90d,
            "jeonse_median_90d": row.jeonse_median_90d,
            "gap_90d": row.gap_90d,
            "jeonse_ratio_90d": row.jeonse_ratio_90d,
            "gap_delta": row.gap_delta,
            "ratio_delta": row.ratio_delta,
            "reliability": reliability_label(row.sale_count_90d, row.jeonse_count_90d),
            "apt_seq": row.apt_seq,
        })
    return out.getvalue()
