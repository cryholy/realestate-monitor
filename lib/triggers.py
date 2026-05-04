"""edge 트리거 판정 — 가격 임계값 + 전세가율 임계값."""
from dataclasses import dataclass
from typing import Callable

from lib.matcher import match_alert_rules


@dataclass
class PriceCandidate:
    rule_id: str
    rule: dict
    record: dict
    dedup_key: str          # 'sale:<record.id>'
    alert_type: str = "price_threshold"


@dataclass
class JeonseCandidate:
    rule_id: str
    rule: dict
    dedup_key: str          # 'jeonse:YYYY-MM'
    ratio: float
    median_sale: int
    median_jeonse: int
    sample_count_sale: int
    sample_count_jeonse: int
    alert_type: str = "jeonse_ratio"


def evaluate_price_threshold(
    new_sale_records: list[dict],
    rules: list[dict],
) -> list[PriceCandidate]:
    """신규 매매 거래 × 룰 → 가격 임계값 도달 후보 리스트.

    매칭: rule.apt_seq == record.apt_seq AND rule.size_label IN (record.size_label, 'any')
    트리거: rule.max_price_만원 is not None AND record.price_만원 < rule.max_price_만원
    """
    candidates: list[PriceCandidate] = []
    for record in new_sale_records:
        matching_rules = match_alert_rules(record, rules)
        for rule in matching_rules:
            if rule.get("max_price_만원") is None:
                continue
            if record["price_만원"] >= rule["max_price_만원"]:
                continue
            candidates.append(PriceCandidate(
                rule_id=rule["id"],
                rule=rule,
                record=record,
                dedup_key=f"sale:{record['id']}",
            ))
    return candidates


def evaluate_jeonse_ratio(
    *,
    rules: list[dict],
    median_sale_fn: Callable,
    median_jeonse_fn: Callable,
    today: str,
    min_samples: int = 5,
    lookback_days: int = 90,
) -> list[JeonseCandidate]:
    """alert_rules 중 min_jeonse_ratio 설정된 룰을 평가.

    각 룰마다:
    - median_sale_fn / median_jeonse_fn 호출 → (median 값, 표본 수) 튜플
    - 표본 < min_samples면 skip
    - 전세가율 = median_jeonse / median_sale
    - 임계값 미달이면 skip
    - 그 외에는 후보 생성 (dedup_key = 'jeonse:YYYY-MM')

    호출자(collector.py)는 `partial(query_median_*, client)`로 client를 미리 주입.
    """
    month_key = today[:7]
    candidates: list[JeonseCandidate] = []

    for rule in rules:
        if rule.get("min_jeonse_ratio") is None:
            continue
        if not rule.get("enabled", True):
            continue

        median_sale, n_sale = median_sale_fn(
            apt_seq=rule["apt_seq"], size_label=rule["size_label"], days=lookback_days,
        )
        median_jeonse, n_jeonse = median_jeonse_fn(
            apt_seq=rule["apt_seq"], size_label=rule["size_label"], days=lookback_days,
        )

        if n_sale < min_samples or n_jeonse < min_samples:
            continue
        if not median_sale or median_jeonse is None:
            continue

        ratio = round(median_jeonse / median_sale, 4)
        if ratio < rule["min_jeonse_ratio"]:
            continue

        candidates.append(JeonseCandidate(
            rule_id=rule["id"], rule=rule,
            dedup_key=f"jeonse:{month_key}",
            ratio=ratio,
            median_sale=median_sale,
            median_jeonse=median_jeonse,
            sample_count_sale=n_sale,
            sample_count_jeonse=n_jeonse,
        ))

    return candidates
