# realestate_monitor

서울 9개 구(성동·광진·마포·서초·강남·송파·용산·동작·강동) 아파트 매매·전월세 거래를 매일 Supabase에 누적하고, 관심 매물의 가격·전세가율 임계값 도달 시 텔레그램으로 알림을 보낸다. 사이클·갭 분석은 Supabase Studio Reports에서 시각화.

## 인프라

- **GitHub Actions** (cron 매일 18:00 KST 1회, private repo)
- **Supabase** (PostgreSQL, 무료 500MB)
- **Metabase Cloud** (대시보드, 무료)
- **Telegram Bot** (알림)

비용: 0원.

## 셋업

### 1. 외부 계정 (사용자)

| 서비스 | 작업 | 메모 |
|---|---|---|
| 공공데이터포털 | 국토부 매매·전월세 API 활용신청 | service key 발급 |
| Telegram | BotFather에서 봇 생성 → token + chat_id | |
| GitHub | private repo `realestate-monitor` 생성 + 2FA | PAT 발급(`repo`, `workflow` scope) |
| Supabase | 새 프로젝트 + DB 비밀번호 + Service Role Key | |

### 2. 로컬 .env 작성

```bash
cp .env.example .env
# 편집: 5개 키 모두 입력
```

### 3. SQL 마이그레이션 적용 (Supabase Studio)

Studio → SQL Editor에서 순서대로 실행:
- `sql/001_initial_schema.sql`
- `sql/002_views.sql`

또는 Supabase MCP 자동 적용.

### 4. 로컬 의존성

```bash
python3.11 -m pip install --user -r requirements.txt
```

> Python 3.11+ 필수.

### 5. 백필 (1회성)

```bash
python3.11 scripts/backfill.py --months 12
# ~5분 소요, 9개 구 × 12개월 × 매매·전세 = 216 API 호출
```

### 6. 관심 매물 등록 (Supabase Studio)

```sql
-- 단지 검색
SELECT * FROM v_complexes
WHERE apt_name LIKE '%예시단지A%' AND sgg_cd = '11710';

-- alert_rules INSERT
INSERT INTO alert_rules (apt_seq, display_name, size_label, max_price_만원, min_jeonse_ratio)
VALUES ('11000-0001', '예시단지A', '84', 200000, 0.65);

-- 검증
SELECT * FROM v_alert_rules_check;
```

### 7. 백필된 거래에 dedup 키 미리 채우기

```bash
python3.11 scripts/seed_alerts_sent.py
```

### 8. GitHub Secrets 등록

```bash
gh secret set MOLIT_SERVICE_KEY
gh secret set TELEGRAM_BOT_TOKEN
gh secret set TELEGRAM_CHAT_ID
gh secret set SUPABASE_URL
gh secret set SUPABASE_SERVICE_ROLE_KEY
```

또는 GitHub repo → Settings → Secrets에서 수동 등록.

### 9. 수동 첫 실행

```bash
gh workflow run monitor.yml -f dry_run=true
gh run watch
```

로그·DB 검증 후 `dry_run=false`로 정식 가동.

### 10. Metabase 가동

1. metabase.com/cloud 가입
2. New Database → PostgreSQL → Supabase 연결
3. 대시보드 생성 (쿼리는 `docs/2026-05-04-system-design.md` 5절 참조)

## 운영

```bash
# 수동 실행
python3.11 collector.py --dry-run

# 단지 추가
# Supabase Studio → alert_rules 테이블에 row INSERT

# 워크플로 manual trigger
gh workflow run monitor.yml
```

## 테스트

```bash
python3.11 -m pytest tests/ -v
```

## 서울 한강권 대표단지 갭 레이더 (v2)

서울 한강권 9개 구의 대표 아파트 단지+평형을 데이터로 선별하고, 매주 갭·전세가율·갱신 압력 변화를 추적하는 무료 공개 Notion 리포트.

### 1. SQL view 적용

Supabase SQL Editor에서 두 파일 실행:

```text
sql/007_gap_radar_views.sql    (v1, 비교/롤백용)
sql/008_gap_radar_v2_views.sql (v2, 기본)
```

### 2. 리포트 생성

```bash
cd realestate_monitor
python3.11 scripts/generate_gap_radar_report.py --version v2 --date 2026-06-01
```

산출물:

```text
reports/gap-radar/2026-06-01-v2.md
reports/gap-radar/2026-06-01-v2.csv
```

마지막 줄에 `COUNTS total_rows=.. high_reliability=.. ratio_up=.. gap_down=.. use_rate_up=..` 형식의 요약 카운트가 출력된다.

### 3. Notion 비공개 발행

```bash
python3.11 scripts/notion_publish.py \
  --date 2026-06-01 \
  --markdown reports/gap-radar/2026-06-01-v2.md
```

`📥 발행 대기실` 아래에 `📊 2026-06-01 서울 한강권 대표단지 갭 레이더 (초안)` 페이지가 생성된다.

### 4. 텔레그램 알림 (선택)

cron이 자동 발송하지만 수동 실행 시:

```bash
python3.11 scripts/notify_gap_radar.py \
  --mode success \
  --date 2026-06-01 \
  --page-url "https://www.notion.so/..." \
  --total-rows 90 --high-reliability 33 --ratio-up 62 --gap-down 57 --use-rate-up 37
```

### 5. cron 운영

`.github/workflows/gap_radar_weekly.yml` — 매주 일요일 22:30 KST (UTC 13:30)에 1~4단계 자동 수행. workflow_dispatch로 수동 트리거 가능. 자세한 절차는 `docs/gap-radar-notion-publishing.md`.

운영 원칙:

- 광고/결제 없음
- 무료 공개 Notion Site (검색 인덱싱 ON)
- 매주 리포트 아카이브 누적
- 리포트 생성·발행: 일요일 22:30 KST (자동)
- 검수·공개: 월요일 아침 (사용자 수동)
- 공개 방식: 비공개 페이지 검수 후 메인 부모 페이지로 이동 + "최신 주간 리포트" 영역 갱신

### 6. v1 (legacy)

```bash
python3.11 scripts/generate_gap_radar_report.py --version v1 --date 2026-06-01
```

v1 view·코드 경로는 1~2주 운영 검증 후 별도 PR로 제거 예정.

### 추가 GitHub Secrets (v2)

기존 `SUPABASE_*`, `TELEGRAM_*` 외에:

```bash
gh secret set NOTION_API_KEY              # Notion Integration token
gh secret set NOTION_STAGING_PARENT_ID    # 📥 발행 대기실 페이지 ID
```

## 디렉토리

- `collector.py` — 메인 엔트리
- `lib/` — 모듈 (api, matcher, db, triggers, notifier)
- `sql/` — 스키마·view·MV·RPC
- `scripts/` — 백필·seed
- `.github/workflows/` — cron
- `tests/` — 단위 테스트
- `docs/` — 설계·plan 문서
