from lib.gap_radar import (
    RadarRow,
    build_weekly_headline,
    format_eok,
    format_ratio,
    render_csv,
    render_markdown_report,
    summarize_counts,
)


def sample_rows():
    return [
        RadarRow(
            district_rank=1,
            representative_score=96.3,
            apt_seq="11680-0001",
            apt_name="강남대표",
            sgg_cd="11680",
            district_name="강남구",
            lifestyle_area="강남권",
            size_label="84",
            sale_count_12m=18,
            sale_median_12m=210000,
            jeonse_new_count_12m=22,
            jeonse_new_median_12m=130000,
            sale_count_90d=6,
            sale_median_90d=208000,
            jeonse_new_count_90d=7,
            jeonse_new_median_90d=132000,
            gap_90d=76000,
            jeonse_ratio_90d=0.6346,
            jeonse_renewal_count_90d=12,
            jeonse_renewal_median_90d=125000,
            renewal_right_use_rate_90d=0.62,
            renewal_pct_change_median_90d=0.048,
            new_minus_renewal_gap_90d=7000,
            sale_count_prev_90d=5,
            sale_median_prev_90d=212000,
            jeonse_new_count_prev_90d=6,
            jeonse_new_median_prev_90d=128000,
            gap_prev_90d=84000,
            jeonse_ratio_prev_90d=0.6038,
            renewal_right_use_rate_prev_90d=0.55,
            reliability_label="신뢰도 높음",
            reliability_weight=1.0,
        ),
        RadarRow(
            district_rank=1,
            representative_score=92.1,
            apt_seq="11200-0001",
            apt_name="성동대표",
            sgg_cd="11200",
            district_name="성동구",
            lifestyle_area="마용성/동부권",
            size_label="mid",
            sale_count_12m=12,
            sale_median_12m=150000,
            jeonse_new_count_12m=4,
            jeonse_new_median_12m=90000,
            sale_count_90d=2,
            sale_median_90d=148000,
            jeonse_new_count_90d=1,
            jeonse_new_median_90d=91000,
            gap_90d=57000,
            jeonse_ratio_90d=0.6149,
            jeonse_renewal_count_90d=3,
            jeonse_renewal_median_90d=88000,
            renewal_right_use_rate_90d=0.67,
            renewal_pct_change_median_90d=0.050,
            new_minus_renewal_gap_90d=3000,
            sale_count_prev_90d=3,
            sale_median_prev_90d=151000,
            jeonse_new_count_prev_90d=2,
            jeonse_new_median_prev_90d=88000,
            gap_prev_90d=63000,
            jeonse_ratio_prev_90d=0.5828,
            renewal_right_use_rate_prev_90d=0.50,
            reliability_label="주의",
            reliability_weight=0.5,
        ),
    ]


def test_format_eok():
    assert format_eok(208000) == "20.8억"
    assert format_eok(76000) == "7.6억"
    assert format_eok(None) == "-"


def test_format_ratio():
    assert format_ratio(0.6346) == "63.5%"
    assert format_ratio(None) == "-"


def test_radar_row_delta_properties():
    rows = sample_rows()
    assert rows[0].gap_delta == 76000 - 84000
    assert rows[0].ratio_delta == 0.6346 - 0.6038
    assert abs(rows[0].use_rate_delta - 0.07) < 1e-9
    assert rows[0].weighted_gap_delta == (76000 - 84000) * 1.0
    assert rows[1].weighted_gap_delta == (57000 - 63000) * 0.5


def test_radar_row_from_db_handles_supabase_strings():
    row = RadarRow.from_db({
        "district_rank": 2,
        "representative_score": "88.5",
        "apt_seq": "11710-0001",
        "apt_name": "송파대표",
        "sgg_cd": "11710",
        "district_name": "송파구",
        "lifestyle_area": "강남권",
        "size_label": "84",
        "sale_count_12m": "10",
        "sale_median_12m": "190000",
        "jeonse_new_count_12m": "11",
        "jeonse_new_median_12m": "120000",
        "sale_count_90d": "5",
        "sale_median_90d": "188000",
        "jeonse_new_count_90d": "6",
        "jeonse_new_median_90d": "121000",
        "gap_90d": "67000",
        "jeonse_ratio_90d": "0.6436",
        "jeonse_renewal_count_90d": "5",
        "jeonse_renewal_median_90d": "118000",
        "renewal_right_use_rate_90d": "0.6000",
        "renewal_pct_change_median_90d": "0.0480",
        "new_minus_renewal_gap_90d": "3000",
        "sale_count_prev_90d": None,
        "sale_median_prev_90d": None,
        "jeonse_new_count_prev_90d": None,
        "jeonse_new_median_prev_90d": None,
        "gap_prev_90d": None,
        "jeonse_ratio_prev_90d": None,
        "renewal_right_use_rate_prev_90d": None,
        "reliability_label": "신뢰도 높음",
        "reliability_weight": "1.0",
    })
    assert row.district_rank == 2
    assert row.sale_median_90d == 188000
    assert row.renewal_right_use_rate_90d == 0.6
    assert row.reliability_weight == 1.0
    assert row.gap_delta is None
    assert row.use_rate_delta is None


def test_render_markdown_report_contains_sections_and_signals():
    md = render_markdown_report(sample_rows(), report_date="2026-06-01")
    assert "# 서울 한강권 대표단지 갭 레이더 - 2026-06-01" in md
    assert "## 이번 주 요약" in md
    assert "대표 `단지+평형` 2개" in md
    assert "갱신권 사용률 상승 항목" in md
    assert "## 갭 축소 Top 10" in md
    assert "## 전세가율 상승 Top 10" in md
    assert "## 갱신 압력 상승 Top 10" in md
    assert "갱신권 사용률이 오른 단지" in md
    assert "| 생활권 | 구 | 순위 | 단지 | 평형 | 매매 중위 | 신규 전세 | 갭 | 전세가율 | 갱신권 사용률 | 갱신 인상률 | 신뢰도 |" in md
    assert " mid |" in md
    assert "보정점수(억)" in md
    assert "보정점수(pp)" in md
    assert "## 데이터 신뢰도와 주의사항" in md
    assert "매수 추천이나 투자 추천이 아닙니다" in md


def test_render_markdown_report_top_tables_sorted_by_weighted_delta():
    md = render_markdown_report(sample_rows(), report_date="2026-06-01")
    gap_section = md.split("## 갭 축소 Top 10")[1].split("## 전세가율 상승 Top 10")[0]
    gangnam_pos = gap_section.find("강남대표")
    seongdong_pos = gap_section.find("성동대표")
    assert gangnam_pos != -1 and seongdong_pos != -1
    assert gangnam_pos < seongdong_pos


def test_render_csv_uses_korean_headers_and_human_units():
    csv_text = render_csv(sample_rows())
    assert "구,단지,평형,생활권" in csv_text
    assert "90일 매매 중위가" in csv_text
    assert "전세가율" in csv_text
    assert "갱신권 사용률" in csv_text
    assert "신규-갱신 보증금 갭" in csv_text
    assert "weighted_gap_delta" not in csv_text
    assert "reliability_weight" not in csv_text
    assert "apt_seq" not in csv_text
    assert "강남구,강남대표,84" in csv_text
    assert "성동구,성동대표,mid" in csv_text
    assert "20.8억" in csv_text
    assert "13.2억" in csv_text
    assert "63.5%" in csv_text
    assert "62.0%" in csv_text
    assert "-0.8억" in csv_text
    assert "+3.1%" in csv_text


def test_summarize_counts():
    counts = summarize_counts(sample_rows())
    assert counts["total_rows"] == 2
    assert counts["high_reliability"] == 1
    assert counts["ratio_up"] == 2
    assert counts["gap_down"] == 2
    assert counts["use_rate_up"] == 2


def test_build_weekly_headline_quotes_top_signals():
    headline = build_weekly_headline(sample_rows())
    assert "강남구 강남대표 84" in headline
    assert "갭" in headline
    assert "갱신권 사용률" in headline


def test_write_report_csv_starts_with_utf8_bom(tmp_path):
    import sys
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[1]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts.generate_gap_radar_report import write_report
    write_report(sample_rows(), report_date="2026-06-01", output_dir=tmp_path)
    csv_path = tmp_path / "r" / "2026-06-01.csv"
    raw = csv_path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    decoded = raw[3:].decode("utf-8")
    assert "구,단지,평형" in decoded
