"""단지 매칭 + 평형 라벨 계산."""


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


def match_alert_rules(record: dict, rules: list[dict]) -> list[dict]:
    """record(매매 또는 전월세 거래)에 매칭되는 활성 alert_rules 리스트.

    매칭 조건:
    - rule.enabled == True
    - rule.apt_seq == record.apt_seq
    - rule.size_label == record.size_label  OR  rule.size_label == 'any'
    """
    matched = []
    for r in rules:
        if not r.get("enabled", True):
            continue
        if r["apt_seq"] != record["apt_seq"]:
            continue
        if r["size_label"] != record["size_label"] and r["size_label"] != "any":
            continue
        matched.append(r)
    return matched
