"""단지 매칭 + 평형 라벨 계산."""

# (label, low, high) — 면적 범위 정의 (참고용 상수, 외부에서 참조 가능)
SIZE_LABELS = [
    ("59", 58.0, 60.5),
    ("mid", 60.500001, 82.999999),  # 60.5 < x < 83.0
    ("84", 83.0, 85.5),
]


def compute_size_label(area: float) -> str:
    """전용면적(㎡) → '59' / 'mid' / '84' / 'other'.

    경계값: 60.5는 '59', 83.0은 '84'.
    """
    if 58.0 <= area <= 60.5:
        return "59"
    if 60.5 < area < 83.0:
        return "mid"
    if 83.0 <= area <= 85.5:
        return "84"
    return "other"
