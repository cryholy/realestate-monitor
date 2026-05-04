"""Supabase Postgres 클라이언트 래퍼."""
from typing import Optional

from supabase import Client, create_client


def get_client(url: str, service_role_key: str) -> Client:
    """Supabase service_role client 생성 (서버 전용, RLS 우회)."""
    return create_client(url, service_role_key)


def upsert_records(client: Client, table: str, records: list[dict]) -> None:
    """sale_records / rent_records UPSERT (id 충돌 시 무시).

    on_conflict='id' + ignore_duplicates=True로 ON CONFLICT DO NOTHING 동작.
    """
    if not records:
        return
    client.table(table).upsert(
        records,
        on_conflict="id",
        ignore_duplicates=True,
    ).execute()


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

    keys = [c["dedup_key"] for c in candidates]
    resp = client.table("alerts_sent").select("rule_id,dedup_key").in_("dedup_key", keys).execute()
    existing = {(row["rule_id"], row["dedup_key"]) for row in (resp.data or [])}

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
