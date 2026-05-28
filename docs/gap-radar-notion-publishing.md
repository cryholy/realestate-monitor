# 서울 한강권 대표단지 갭 레이더 Notion 발행 가이드

## 흐름 요약

```
[자동 — 일요일 22:30 KST]
GitHub Actions cron (.github/workflows/gap_radar_weekly.yml)
  ├ python scripts/generate_gap_radar_report.py --date <다음 월요일>
  ├ python scripts/notion_publish.py  →  📡 서울 한강권 대표단지 갭 레이더 / 📊 ...
  └ python scripts/notify_gap_radar.py --mode success  →  텔레그램 알림

[수동 — 월요일 아침]
사용자
  └ 텔레그램 알림에서 URL 확인 → 공개 페이지 확인
```

## 운영 원칙

- 광고/결제 없음
- 무료 공개 Notion Site (검색 인덱싱 ON)
- 매주 리포트 아카이브 누적 (자동)
- 리포트 생성·발행: 일요일 22:30 KST (자동)
- 사용자 검수: 텔레그램 알림 확인 (즉시 공개)
- 공개 방식: 메인 페이지의 "최신 주간 리포트" / "이번 주 핵심 숫자" / "지난 리포트" 영역이 발행 시 자동 갱신

## 필요 환경 변수 (GitHub Secrets)

| 이름 | 용도 |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | view SELECT 권한 |
| `NOTION_API_KEY` | Notion Integration token (Internal type 권장) |
| `NOTION_PUBLIC_PARENT_ID` | `📡 서울 한강권 대표단지 갭 레이더` 부모 페이지 ID |
| `TELEGRAM_BOT_TOKEN` | 기존 봇 재사용 |
| `TELEGRAM_CHAT_ID` | 알림 받을 chat_id |

`SUPABASE_*`, `TELEGRAM_*`는 `monitor.yml`에서도 사용 중인 기존 secrets.

## 메인 페이지 구조

```text
📡 서울 한강권 대표단지 갭 레이더 (공개)
├─ 📘 소개 / 방법론
├─ 📊 YYYY-MM-DD 주간 리포트 (← 최신, 자동 생성)
├─ 📊 YYYY-MM-DD 주간 리포트 (← 이전들 누적, 자동)
└─ (향후) 업데이트 알림 안내
```

## 메인 페이지 필수 섹션

1. 상품 소개
2. 대상 지역: 강남, 서초, 송파, 성동, 광진, 마포, 용산, 동작, 강동
3. 대표단지 선정 기준: 거래 유동성 50%, 가격 레벨 30%, 신규 전세 유동성 20%
4. 최신 주간 리포트 링크
5. 이번 주 핵심 숫자 (5개)
6. 지난 리포트 아카이브
7. 데이터 출처와 주의사항

## 수동 실행 (긴급/검증용)

cron 외에 수동 실행이 필요하면:

```bash
gh workflow run gap_radar_weekly.yml -f report_date=2026-06-01
```

또는 로컬에서:

```bash
cd realestate_monitor
python3.11 scripts/generate_gap_radar_report.py --date 2026-06-01
python3.11 scripts/notion_publish.py \
  --date 2026-06-01 \
  --markdown reports/gap-radar/2026-06-01.md \
  --summary reports/gap-radar/2026-06-01-summary.json \
  --csv-url "https://flsbxpjywjuhylfwnrby.supabase.co/storage/v1/object/public/reports/r/2026-06-01.csv"
# 알림 발송은 선택적
python3.11 scripts/notify_gap_radar.py \
  --mode success \
  --date 2026-06-01 \
  --page-url "<위에서 받은 URL>" \
  --total-rows NN --high-reliability NN --ratio-up NN --gap-down NN --use-rate-up NN
```

같은 날짜로 재실행하면 기존 페이지를 archive 후 새로 생성한다 (idempotency 가드).

## SEO 제목 원칙 (사용자 공개 단계)

주간 페이지 제목 예시:

- 좋은 예: `2026-06-01 서울 한강권 대표단지 갭 레이더`
- 피할 예: `이번 주 부동산`, `좋은 단지 정리`, `매수 타이밍`

## 표현 원칙

사용할 표현: 관찰 후보, 신규 시세, 갱신권 사용률 상승, 신규-갱신 압력 확대, 거래수 기준 신뢰도, 데이터상 변화가 큰 단지

피할 표현: 매수 추천, 투자 추천, 저평가 확정, 상승 예상, 급등 임박, 전세 폭등, 무조건 사야 할 단지

## 발행 후 확인 체크리스트

- 메인 페이지의 "이번 주 핵심 숫자" 5줄이 새 데이터로 갱신됐는지
- "최신 주간 리포트" 링크가 새 페이지를 가리키는지
- 새 주간 리포트 페이지가 "📡 서울 한강권 대표단지 갭 레이더" 하위에 있고 외부에서 접근 가능한지
- "📥 발행 대기실"이 외부에 노출되지 않는지
- 데이터 주의사항 섹션이 포함되어 있는지
