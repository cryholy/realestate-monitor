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
    sale_median_12m: int | None
    jeonse_new_count_12m: int
    jeonse_new_median_12m: int | None
    sale_count_90d: int | None
    sale_median_90d: int | None
    jeonse_new_count_90d: int | None
    jeonse_new_median_90d: int | None
    gap_90d: int | None
    jeonse_ratio_90d: float | None
    jeonse_renewal_count_90d: int | None
    jeonse_renewal_median_90d: int | None
    renewal_right_use_rate_90d: float | None
    renewal_pct_change_median_90d: float | None
    new_minus_renewal_gap_90d: int | None
    sale_count_prev_90d: int | None
    sale_median_prev_90d: int | None
    jeonse_new_count_prev_90d: int | None
    jeonse_new_median_prev_90d: int | None
    gap_prev_90d: int | None
    jeonse_ratio_prev_90d: float | None
    renewal_right_use_rate_prev_90d: float | None
    reliability_label: str
    reliability_weight: float

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
            sale_median_12m=_optional_int(row.get("sale_median_12m")),
            jeonse_new_count_12m=int(row.get("jeonse_new_count_12m") or 0),
            jeonse_new_median_12m=_optional_int(row.get("jeonse_new_median_12m")),
            sale_count_90d=_optional_int(row.get("sale_count_90d")),
            sale_median_90d=_optional_int(row.get("sale_median_90d")),
            jeonse_new_count_90d=_optional_int(row.get("jeonse_new_count_90d")),
            jeonse_new_median_90d=_optional_int(row.get("jeonse_new_median_90d")),
            gap_90d=_optional_int(row.get("gap_90d")),
            jeonse_ratio_90d=_optional_float(row.get("jeonse_ratio_90d")),
            jeonse_renewal_count_90d=_optional_int(row.get("jeonse_renewal_count_90d")),
            jeonse_renewal_median_90d=_optional_int(row.get("jeonse_renewal_median_90d")),
            renewal_right_use_rate_90d=_optional_float(row.get("renewal_right_use_rate_90d")),
            renewal_pct_change_median_90d=_optional_float(row.get("renewal_pct_change_median_90d")),
            new_minus_renewal_gap_90d=_optional_int(row.get("new_minus_renewal_gap_90d")),
            sale_count_prev_90d=_optional_int(row.get("sale_count_prev_90d")),
            sale_median_prev_90d=_optional_int(row.get("sale_median_prev_90d")),
            jeonse_new_count_prev_90d=_optional_int(row.get("jeonse_new_count_prev_90d")),
            jeonse_new_median_prev_90d=_optional_int(row.get("jeonse_new_median_prev_90d")),
            gap_prev_90d=_optional_int(row.get("gap_prev_90d")),
            jeonse_ratio_prev_90d=_optional_float(row.get("jeonse_ratio_prev_90d")),
            renewal_right_use_rate_prev_90d=_optional_float(row.get("renewal_right_use_rate_prev_90d")),
            reliability_label=row.get("reliability_label") or "데이터 부족",
            reliability_weight=float(row.get("reliability_weight") or 0.0),
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

    @property
    def use_rate_delta(self) -> float | None:
        if self.renewal_right_use_rate_90d is None or self.renewal_right_use_rate_prev_90d is None:
            return None
        return self.renewal_right_use_rate_90d - self.renewal_right_use_rate_prev_90d

    @property
    def weighted_gap_delta(self) -> float | None:
        if self.gap_delta is None:
            return None
        return self.gap_delta * self.reliability_weight

    @property
    def weighted_ratio_delta(self) -> float | None:
        if self.ratio_delta is None:
            return None
        return self.ratio_delta * self.reliability_weight

    @property
    def weighted_use_rate_delta(self) -> float | None:
        if self.use_rate_delta is None:
            return None
        return self.use_rate_delta * self.reliability_weight


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


def format_eok_signed(value: int | float | None) -> str:
    if value is None:
        return "-"
    return f"{value / 10000:+.1f}억"


def format_ratio(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.1f}%"


def format_ratio_signed(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:+.1f}%"


def format_score(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:+.2f}"


def build_weekly_headline(rows: list[RadarRow]) -> str:
    """부모 페이지 '최신 주간 리포트' 영역에 들어갈 1줄 자동 요약."""
    high_rel = [r for r in rows if r.reliability_label == "신뢰도 높음"]
    gap_top = sorted(
        [r for r in high_rel if r.weighted_gap_delta is not None and r.weighted_gap_delta < 0],
        key=lambda r: r.weighted_gap_delta,
    )
    use_top = sorted(
        [r for r in high_rel if r.weighted_use_rate_delta is not None and r.weighted_use_rate_delta > 0],
        key=lambda r: r.weighted_use_rate_delta,
        reverse=True,
    )
    parts: list[str] = []
    if gap_top:
        r = gap_top[0]
        parts.append(
            f"{r.district_name} {r.apt_name} {r.size_label}의 갭 {format_eok_signed(r.gap_delta)} 축소가 가장 두드러졌고"
        )
    if use_top:
        r = use_top[0]
        parts.append(
            f"{r.district_name} {r.apt_name} {r.size_label}에서 갱신권 사용률이 {format_ratio_signed(r.use_rate_delta)} 상승했습니다"
        )
    if not parts:
        return "이번 주는 신뢰도 높음 항목에서 두드러진 변화 신호가 적었습니다. 상세는 리포트를 참고하세요."
    return "이번 주는 " + ", ".join(parts) + "."


def render_markdown_report(rows: list[RadarRow], *, report_date: str) -> str:
    rows = sorted(
        rows,
        key=lambda r: (r.lifestyle_area, r.district_name, r.district_rank, r.apt_name, r.size_label),
    )
    ratio_up_count = sum(1 for r in rows if r.ratio_delta is not None and r.ratio_delta > 0)
    gap_down_count = sum(1 for r in rows if r.gap_delta is not None and r.gap_delta < 0)
    use_rate_up_count = sum(1 for r in rows if r.use_rate_delta is not None and r.use_rate_delta > 0)
    high_reliability_count = sum(1 for r in rows if r.reliability_label == "신뢰도 높음")

    lines = [
        f"# 서울 한강권 대표단지 갭 레이더 - {report_date}",
        "",
        "## 이번 주 요약",
        "",
        f"- 분석 항목: 대표 `단지+평형` {len(rows)}개",
        f"- 신규 전세가율 상승 항목: {ratio_up_count}개",
        f"- 갭 축소 항목: {gap_down_count}개",
        f"- 갱신권 사용률 상승 항목: {use_rate_up_count}개",
        f"- 매매·신규전세 표본이 모두 5건 이상인 항목: {high_reliability_count}개 (신뢰도 높음)",
        "- 이 리포트는 매수 추천이나 투자 추천이 아니라 데이터 기반 관찰 자료입니다.",
        "",
        "## 갭 축소 Top 10",
        "",
    ]
    gap_candidates = [r for r in rows if r.weighted_gap_delta is not None]
    gap_top = sorted(gap_candidates, key=lambda r: r.weighted_gap_delta)[:10]
    lines.extend(_render_delta_table(gap_top, metric="gap"))

    lines.extend(["", "## 전세가율 상승 Top 10", ""])
    ratio_candidates = [r for r in rows if r.weighted_ratio_delta is not None]
    ratio_top = sorted(ratio_candidates, key=lambda r: r.weighted_ratio_delta, reverse=True)[:10]
    lines.extend(_render_delta_table(ratio_top, metric="ratio"))

    lines.extend([
        "",
        "## 갱신 압력 상승 Top 10",
        "",
        "> 갱신권 사용률이 오른 단지는 임차인의 과반이 갱신을 선택했다는 뜻 — 신규 시세가 갱신 5% 캡보다 높다는 시장 신호입니다.",
        "",
    ])
    use_candidates = [r for r in rows if r.weighted_use_rate_delta is not None]
    use_top = sorted(use_candidates, key=lambda r: r.weighted_use_rate_delta, reverse=True)[:10]
    lines.extend(_render_delta_table(use_top, metric="use_rate"))

    lines.extend([
        "",
        "## 구별 대표단지 레이더",
        "",
        "| 생활권 | 구 | 순위 | 단지 | 평형 | 매매 중위 | 신규 전세 | 갭 | 전세가율 | 갱신권 사용률 | 갱신 인상률 | 신뢰도 |",
        "|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ])
    for row in rows:
        lines.append(
            "| {lifestyle} | {district} | {rank} | {apt} | {size} | {sale} | {jeonse} | {gap} | {ratio} | {use_rate} | {pct_change} | {reliability} |".format(
                lifestyle=row.lifestyle_area,
                district=row.district_name,
                rank=row.district_rank,
                apt=row.apt_name,
                size=row.size_label,
                sale=format_eok(row.sale_median_90d),
                jeonse=format_eok(row.jeonse_new_median_90d),
                gap=format_eok(row.gap_90d),
                ratio=format_ratio(row.jeonse_ratio_90d),
                use_rate=format_ratio(row.renewal_right_use_rate_90d),
                pct_change=format_ratio(row.renewal_pct_change_median_90d),
                reliability=row.reliability_label,
            )
        )

    lines.extend([
        "",
        "## 데이터 신뢰도와 주의사항",
        "",
        "- 매매 중위가는 중개거래만으로 계산합니다 (직거래 제외).",
        "- 전세 시세는 신규 계약만 사용합니다. 갱신 계약은 갱신 압력 신호로 분리해 표시합니다.",
        "- 보정점수는 변동률의 절대값에 신뢰도 가중치(높음 1.0 / 주의 0.5 / 데이터 부족 0.0)를 곱한 값으로, 표본이 적은 변동의 영향을 자연스럽게 줄입니다. 갭 표는 억 단위, 비율 표는 pp 단위로 표시합니다.",
        "- 실거래 신고 지연으로 최근 거래는 뒤늦게 추가될 수 있습니다.",
        "- 이 리포트는 매수 추천이나 투자 추천이 아닙니다.",
        "",
    ])
    return "\n".join(lines)


def _render_delta_table(rows: list[RadarRow], *, metric: str) -> list[str]:
    if metric == "gap":
        header = "| 생활권 | 구 | 단지 | 평형 | 현재 갭 | 직전 갭 | 변화 | 보정점수(억) | 신뢰도 |"
        align = "|---|---|---|---:|---:|---:|---:|---:|---|"
    elif metric == "ratio":
        header = "| 생활권 | 구 | 단지 | 평형 | 현재 전세가율 | 직전 전세가율 | 변화 | 보정점수(pp) | 신뢰도 |"
        align = "|---|---|---|---:|---:|---:|---:|---:|---|"
    elif metric == "use_rate":
        header = "| 생활권 | 구 | 단지 | 평형 | 현재 사용률 | 직전 사용률 | 변화 | 신규-갱신 갭 | 보정점수(pp) | 신뢰도 |"
        align = "|---|---|---|---:|---:|---:|---:|---:|---:|---|"
    else:
        raise ValueError(f"unknown metric: {metric}")

    lines = [header, align]
    if not rows:
        lines.append("| - | - | - | - | - | - | - | - | - |" if metric != "use_rate" else "| - | - | - | - | - | - | - | - | - | - |")
        return lines

    for row in rows:
        if metric == "gap":
            current = format_eok(row.gap_90d)
            previous = format_eok(row.gap_prev_90d)
            delta = format_eok_signed(row.gap_delta)
            score = format_score(None if row.weighted_gap_delta is None else row.weighted_gap_delta / 10000)
            lines.append(
                f"| {row.lifestyle_area} | {row.district_name} | {row.apt_name} | {row.size_label} | "
                f"{current} | {previous} | {delta} | {score} | {row.reliability_label} |"
            )
        elif metric == "ratio":
            current = format_ratio(row.jeonse_ratio_90d)
            previous = format_ratio(row.jeonse_ratio_prev_90d)
            delta = format_ratio_signed(row.ratio_delta)
            score = format_score(None if row.weighted_ratio_delta is None else row.weighted_ratio_delta * 100)
            lines.append(
                f"| {row.lifestyle_area} | {row.district_name} | {row.apt_name} | {row.size_label} | "
                f"{current} | {previous} | {delta} | {score} | {row.reliability_label} |"
            )
        else:
            current = format_ratio(row.renewal_right_use_rate_90d)
            previous = format_ratio(row.renewal_right_use_rate_prev_90d)
            delta = format_ratio_signed(row.use_rate_delta)
            new_minus_renewal = format_eok(row.new_minus_renewal_gap_90d)
            score = format_score(None if row.weighted_use_rate_delta is None else row.weighted_use_rate_delta * 100)
            lines.append(
                f"| {row.lifestyle_area} | {row.district_name} | {row.apt_name} | {row.size_label} | "
                f"{current} | {previous} | {delta} | {new_minus_renewal} | {score} | {row.reliability_label} |"
            )
    return lines


def render_csv(rows: list[RadarRow]) -> str:
    """일반 독자 친화 CSV — 한국어 헤더 + 사람 읽기 좋은 단위."""
    out = StringIO()
    writer = csv.DictWriter(out, fieldnames=[
        "구",
        "단지",
        "평형",
        "생활권",
        "구별 순위",
        "대표성 점수",
        "12개월 매매 건수",
        "12개월 신규 전세 건수",
        "90일 매매 중위가",
        "90일 신규 전세 중위가",
        "90일 갱신 전세 중위가",
        "90일 갭",
        "신규-갱신 보증금 갭",
        "전세가율",
        "갱신권 사용률",
        "갱신 보증금 인상률 중위",
        "갭 변화",
        "전세가율 변화",
        "갱신권 사용률 변화",
        "신뢰도",
    ])
    writer.writeheader()
    for row in rows:
        writer.writerow({
            "구": row.district_name,
            "단지": row.apt_name,
            "평형": row.size_label,
            "생활권": row.lifestyle_area,
            "구별 순위": row.district_rank,
            "대표성 점수": f"{row.representative_score:.2f}",
            "12개월 매매 건수": row.sale_count_12m,
            "12개월 신규 전세 건수": row.jeonse_new_count_12m,
            "90일 매매 중위가": format_eok(row.sale_median_90d),
            "90일 신규 전세 중위가": format_eok(row.jeonse_new_median_90d),
            "90일 갱신 전세 중위가": format_eok(row.jeonse_renewal_median_90d),
            "90일 갭": format_eok(row.gap_90d),
            "신규-갱신 보증금 갭": format_eok(row.new_minus_renewal_gap_90d),
            "전세가율": format_ratio(row.jeonse_ratio_90d),
            "갱신권 사용률": format_ratio(row.renewal_right_use_rate_90d),
            "갱신 보증금 인상률 중위": format_ratio(row.renewal_pct_change_median_90d),
            "갭 변화": format_eok_signed(row.gap_delta),
            "전세가율 변화": format_ratio_signed(row.ratio_delta),
            "갱신권 사용률 변화": format_ratio_signed(row.use_rate_delta),
            "신뢰도": row.reliability_label,
        })
    return out.getvalue()


def summarize_counts(rows: list[RadarRow]) -> dict[str, int]:
    return {
        "total_rows": len(rows),
        "high_reliability": sum(1 for r in rows if r.reliability_label == "신뢰도 높음"),
        "ratio_up": sum(1 for r in rows if r.ratio_delta is not None and r.ratio_delta > 0),
        "gap_down": sum(1 for r in rows if r.gap_delta is not None and r.gap_delta < 0),
        "use_rate_up": sum(1 for r in rows if r.use_rate_delta is not None and r.use_rate_delta > 0),
    }
