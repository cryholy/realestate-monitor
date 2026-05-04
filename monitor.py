"""부동산 실거래가·전월세 모니터링."""
import json

REQUIRED_CONFIG_KEYS = {
    "complexes",
    "size_ranges",
    "max_price_만원",
    "rent_lookback_days",
    "rent_min_samples",
    "include_월세",
    "telegram_chat_id",
}


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)

    missing = REQUIRED_CONFIG_KEYS - set(cfg.keys())
    if missing:
        raise ValueError(f"config.json에 필수 키 누락: {sorted(missing)}")

    return cfg
