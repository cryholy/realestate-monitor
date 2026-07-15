"""Supabase Postgres 클라이언트 래퍼."""
import logging
import time
from typing import Optional

from supabase import Client, create_client

logger = logging.getLogger(__name__)

UPSERT_RETRY_BACKOFFS = [1, 3, 10]


def get_client(url: str, service_role_key: str) -> Client:
    """Supabase service_role client 생성 (서버 전용, RLS 우회)."""
    return create_client(url, service_role_key)


def upsert_records(client: Client, table: str, records: list[dict]) -> None:
    """sale_records / rent_records UPSERT (id 충돌 시 갱신).

    on_conflict='id' + ignore_duplicates=False로 ON CONFLICT DO UPDATE 동작.
    cancel_date는 record_id 해시에 포함되지 않아 취소거래가 원거래와 같은 id를
    가지므로, DO NOTHING이면 나중에 들어온 '취소됨' 상태가 영영 반영되지 않는다.
    median RPC의 cancel_date IS NULL 필터가 실효를 가지려면 취소 상태가 갱신돼야 한다.
    # ponytail: 매 수집마다 재등장 record를 전량 재기록(write amplification) — 문제
    #   되면 cancel 관련 컬럼만 갱신하는 부분 upsert로 좁힐 것.
    Cloudflare 5xx 등 일시 장애 시 지수 백오프 재시도.
    """
    if not records:
        return

    # 단일 배치 내 중복 id는 ON CONFLICT DO UPDATE가 같은 행을 두 번 건드려
    # cardinality 위반(결정적 에러)을 낸다. upsert 전에 id로 dedupe한다.
    # 뒤에 온 레코드가 최신 상태(취소 반영 등)이므로 마지막 것을 남긴다.
    if len(records) > 1:
        records = list({r["id"]: r for r in records}.values())

    last_exc = None
    for delay in [0] + UPSERT_RETRY_BACKOFFS:
        if delay:
            time.sleep(delay)
        try:
            client.table(table).upsert(
                records,
                on_conflict="id",
                ignore_duplicates=False,
            ).execute()
            return
        except Exception as e:
            last_exc = e
            logger.warning("UPSERT 실패 (재시도): %s — %s", table, str(e)[:200])
            continue
    raise RuntimeError(f"UPSERT 실패 (4회 시도): {table} — {last_exc}")


def load_alert_rules(client: Client) -> list[dict]:
    """enabled = True인 alert_rules 모두 조회."""
    resp = client.table("alert_rules").select("*").eq("enabled", True).execute()
    return resp.data or []


def dedup_check(client: Client, candidates: list[dict]) -> list[dict]:
    """candidates: [{rule_id, dedup_key, ...}, ...]

    이미 alerts_sent에 존재하는 (rule_id, dedup_key) 조합을 제외한 신규 후보만 반환.
    """
    if not candidates:
        return []

    # PostgREST IN 쿼리는 URL query string이라 URL 길이 한도(~8KB)에 걸린다.
    # find_new_records와 동일하게 100건씩 chunk로 나눠 조회.
    keys = [c["dedup_key"] for c in candidates]
    BATCH = 100
    existing: set[tuple] = set()
    for i in range(0, len(keys), BATCH):
        chunk = keys[i:i + BATCH]
        resp = client.table("alerts_sent").select("rule_id,dedup_key").in_("dedup_key", chunk).execute()
        existing.update((row["rule_id"], row["dedup_key"]) for row in (resp.data or []))

    return [c for c in candidates if (c["rule_id"], c["dedup_key"]) not in existing]


def mark_alert_sent(client: Client, *, rule_id: str, dedup_key: str, alert_type: str) -> None:
    """alerts_sent에 발송 이력 INSERT."""
    client.table("alerts_sent").insert({
        "rule_id": rule_id,
        "dedup_key": dedup_key,
        "alert_type": alert_type,
    }).execute()


def query_median_sale_price(client: Client, *, apt_seq: str, size_label: str, days: int) -> tuple[Optional[int], int]:
    """직전 N일 매매 중위값과 표본 수 반환 (RPC median_sale_price 호출)."""
    resp = client.rpc("median_sale_price", {
        "p_apt_seq": apt_seq,
        "p_size_label": size_label,
        "p_days": days,
    }).execute()
    if not resp.data:
        return (None, 0)
    row = resp.data[0] if isinstance(resp.data, list) else resp.data
    return (row.get("median_price"), row.get("sample_count", 0))


def query_median_jeonse_deposit(client: Client, *, apt_seq: str, size_label: str, days: int) -> tuple[Optional[int], int]:
    """직전 N일 순수 전세 보증금 중위값과 표본 수 반환 (RPC median_jeonse_deposit)."""
    resp = client.rpc("median_jeonse_deposit", {
        "p_apt_seq": apt_seq,
        "p_size_label": size_label,
        "p_days": days,
    }).execute()
    if not resp.data:
        return (None, 0)
    row = resp.data[0] if isinstance(resp.data, list) else resp.data
    return (row.get("median_deposit"), row.get("sample_count", 0))
