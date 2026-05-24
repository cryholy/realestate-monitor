from lib.gap_radar import (
    RadarRow,
    format_eok,
    format_ratio,
    reliability_label,
    render_csv,
    render_markdown_report,
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
            jeonse_count_12m=22,
            sale_median_12m=210000,
            jeonse_median_12m=130000,
            sale_count_90d=6,
            sale_median_90d=208000,
            jeonse_count_90d=7,
            jeonse_median_90d=132000,
            gap_90d=76000,
            jeonse_ratio_90d=0.6346,
            sale_count_prev_90d=5,
            sale_median_prev_90d=212000,
            jeonse_count_prev_90d=6,
            jeonse_median_prev_90d=128000,
            gap_prev_90d=84000,
            jeonse_ratio_prev_90d=0.6038,
        ),
        RadarRow(
            district_rank=1,
            representative_score=92.1,
            apt_seq="11200-0001",
            apt_name="성동대표",
            sgg_cd="11200",
            district_name="성동구",
            lifestyle_area="마용성/동부권",
            size_label="59",
            sale_count_12m=12,
            jeonse_count_12m=4,
            sale_median_12m=150000,
            jeonse_median_12m=90000,
            sale_count_90d=2,
            sale_median_90d=148000,
            jeonse_count_90d=1,
            jeonse_median_90d=91000,
            gap_90d=57000,
            jeonse_ratio_90d=0.6149,
            sale_count_prev_90d=3,
            sale_median_prev_90d=151000,
            jeonse_count_prev_90d=2,
            jeonse_median_prev_90d=88000,
            gap_prev_90d=63000,
            jeonse_ratio_prev_90d=0.5828,
        ),
    ]


def test_format_eok():
    assert format_eok(208000) == "20.8억"
    assert format_eok(76000) == "7.6억"
    assert format_eok(None) == "-"


def test_format_ratio():
    assert format_ratio(0.6346) == "63.5%"
    assert format_ratio(None) == "-"


def test_reliability_label():
    assert reliability_label(5, 5) == "신뢰도 높음"
    assert reliability_label(1, 5) == "주의"
    assert reliability_label(0, 3) == "데이터 부족"


def test_render_markdown_report_contains_summary_and_tables():
    markdown = render_markdown_report(sample_rows(), report_date="2026-06-01")

    assert "# 서울 한강권 대표단지 갭 레이더 - 2026-06-01" in markdown
    assert "## 이번 주 요약" in markdown
    assert "전세가율이 상승한 항목은 2개" in markdown
    assert "갭이 축소된 항목은 2개" in markdown
    assert "| 생활권 | 구 | 순위 | 단지 | 평형 | 매매 중위 | 전세 중위 | 갭 | 전세가율 | 신뢰도 |" in markdown
    assert "| 강남권 | 강남구 | 1 | 강남대표 | 84 | 20.8억 | 13.2억 | 7.6억 | 63.5% | 신뢰도 높음 |" in markdown
    assert "## 데이터 신뢰도와 주의사항" in markdown
    assert "매수 추천이나 투자 추천이 아닙니다." in markdown


def test_render_csv_contains_flat_rows():
    csv_text = render_csv(sample_rows())

    assert "district_name,apt_name,size_label" in csv_text
    assert "강남구,강남대표,84" in csv_text
    assert "성동구,성동대표,59" in csv_text
