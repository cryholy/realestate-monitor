---
description: realestate-monitor 온디맨드 트렌드 판독 (서울 9구 + 관심단지, 신호만). telegram 인자로 텔레그램 발송.
argument-hint: "[telegram]"
allowed-tools: mcp__plugin_supabase_supabase__execute_sql, Bash(curl:*), Bash(cd:*), Bash(wc:*), Bash(python3:*), Read
---

# /rem-trend — 온디맨드 트렌드 판독

서울 9개 구 실거래 + 관심단지(alert_rules)의 시장 판독문을 생성한다. **신호만 제시(중립), 판정 없음.**
정체성: **"잘 사기(안 비싸게·강한 걸로·칼 피해서) 도구"이지 사이클 타이밍 신탁이 아니다.**

사용자 입력: `$ARGUMENTS` (`telegram` 포함 시 텔레그램 발송, 아니면 터미널만)

## 원칙 (매번 지킬 것)
- 아래 SQL은 **원문 그대로** 실행. **즉흥 변경 금지** — 순진한 급매/구중위 착시, cancel(취소 380건)·저층·직거래 오염 재발 방지가 이 커맨드의 존재 이유.
- project_id: `flsbxpjywjuhylfwnrby`
- 창은 `CURRENT_DATE` 기준 이동(라이브). 최근 45일은 신고지연 회피 버퍼.
- 필터: 매매 median은 `cancel_type IS DISTINCT FROM 'O'`. **①④는 정상매물**(`floor>=3 AND dealing_type='중개거래'`). ③ 전세는 `monthly_rent_만원=0`.
- ⑤는 **추가 SQL 없이** ①③④ 결과에 산술만 적용. 판정(검토/대기) 내리지 말 것 — 신호만.

## Step 1 — 4개 블록 SQL 실행 (`execute_sql`, project `flsbxpjywjuhylfwnrby`)

### 블록 ① 국면·상대강도
```sql
WITH recent AS (
  SELECT apt_seq, sgg_cd, PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_만원) AS m
  FROM sale_records WHERE size_label='84' AND cancel_type IS DISTINCT FROM 'O'
    AND floor>=3 AND dealing_type='중개거래'
    AND deal_date BETWEEN CURRENT_DATE-135 AND CURRENT_DATE-45 GROUP BY 1,2),
prior AS (
  SELECT apt_seq, PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_만원) AS m
  FROM sale_records WHERE size_label='84' AND cancel_type IS DISTINCT FROM 'O'
    AND floor>=3 AND dealing_type='중개거래'
    AND deal_date BETWEEN CURRENT_DATE-225 AND CURRENT_DATE-135 GROUP BY 1),
paired AS (SELECT r.sgg_cd, (r.m-p.m)/p.m*100 AS pct FROM recent r JOIN prior p ON r.apt_seq=p.apt_seq)
SELECT d.name AS 구, COUNT(*) AS 단지수,
  ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY pct)::numeric,1) AS 변화_pct
FROM paired JOIN districts d ON paired.sgg_cd=d.sgg_cd
GROUP BY d.name ORDER BY 변화_pct DESC;
```

### 블록 ② 거래량 (9구 합산 월별 매매, 최근 13개월)
```sql
SELECT to_char(DATE_TRUNC('month', deal_date),'YYYY-MM') AS 월, COUNT(*) AS 매매
FROM sale_records
WHERE cancel_type IS DISTINCT FROM 'O'
  AND deal_date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '12 months'
GROUP BY 1 ORDER BY 1;
```

### 블록 ③ 전세가율 (구별 84㎡, 최근 수준 + 6개월 방향)
```sql
WITH u AS (
  SELECT sgg_cd, price_만원 AS v, 's' AS src,
    CASE WHEN deal_date BETWEEN CURRENT_DATE-135 AND CURRENT_DATE-45 THEN 'r'
         WHEN deal_date BETWEEN CURRENT_DATE-225 AND CURRENT_DATE-135 THEN 'p' END AS win
  FROM sale_records WHERE size_label='84' AND cancel_type IS DISTINCT FROM 'O'
    AND deal_date BETWEEN CURRENT_DATE-225 AND CURRENT_DATE-45
  UNION ALL
  SELECT sgg_cd, deposit_만원, 'j',
    CASE WHEN contract_date BETWEEN CURRENT_DATE-135 AND CURRENT_DATE-45 THEN 'r'
         WHEN contract_date BETWEEN CURRENT_DATE-225 AND CURRENT_DATE-135 THEN 'p' END
  FROM rent_records WHERE size_label='84' AND monthly_rent_만원=0
    AND contract_date BETWEEN CURRENT_DATE-225 AND CURRENT_DATE-45)
, agg AS (
  SELECT sgg_cd,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY v) FILTER (WHERE src='s' AND win='r') s_r,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY v) FILTER (WHERE src='s' AND win='p') s_p,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY v) FILTER (WHERE src='j' AND win='r') j_r,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY v) FILTER (WHERE src='j' AND win='p') j_p
  FROM u GROUP BY sgg_cd)
SELECT d.name 구, ROUND((j_r/s_r)::numeric,3) 전세가율_최근,
  ROUND(((j_r/s_r)-(j_p/s_p))::numeric,3) 방향_6개월
FROM agg JOIN districts d ON agg.sgg_cd=d.sgg_cd ORDER BY 전세가율_최근 DESC;
```

### 블록 ④ 관심단지 (구 포함, cancel+정상매물 대칭)
```sql
WITH r AS (SELECT DISTINCT apt_seq, display_name FROM alert_rules WHERE enabled),
deals AS (
  SELECT s.apt_seq, s.sgg_cd, s.size_label, s.price_만원, s.deal_date
  FROM sale_records s JOIN r ON s.apt_seq=r.apt_seq
  WHERE s.deal_date >= CURRENT_DATE-180 AND s.cancel_type IS DISTINCT FROM 'O'
    AND s.floor>=3 AND s.dealing_type='중개거래'),
dom AS (SELECT apt_seq, size_label, ROW_NUMBER() OVER (PARTITION BY apt_seq ORDER BY COUNT(*) DESC) rn
        FROM deals GROUP BY apt_seq, size_label),
med AS (SELECT d.apt_seq, d.size_label, PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY d.price_만원) med, COUNT(*) n
        FROM deals d JOIN dom ON d.apt_seq=dom.apt_seq AND d.size_label=dom.size_label AND dom.rn=1
        GROUP BY d.apt_seq, d.size_label),
rd AS (SELECT DISTINCT ON (d.apt_seq) d.apt_seq, d.sgg_cd, d.price_만원, d.deal_date
       FROM deals d JOIN dom ON d.apt_seq=dom.apt_seq AND d.size_label=dom.size_label AND dom.rn=1
       ORDER BY d.apt_seq, d.deal_date DESC)
SELECT r.display_name 단지, dd.name 구, med.size_label 평형, med.n 표본,
  ROUND((med.med/10000.0)::numeric,1) 중위_억, rd.deal_date 최근거래,
  ROUND((rd.price_만원/10000.0)::numeric,1) 최근가_억,
  ROUND(((rd.price_만원-med.med)/med.med*100)::numeric,1) 편차_pct
FROM r LEFT JOIN med ON r.apt_seq=med.apt_seq LEFT JOIN rd ON r.apt_seq=rd.apt_seq
LEFT JOIN districts dd ON rd.sgg_cd=dd.sgg_cd
ORDER BY 편차_pct NULLS LAST;
```

### 데이터 신선도
```sql
SELECT MAX(deal_date) AS 최신거래, (CURRENT_DATE - MAX(deal_date)) AS 경과일 FROM sale_records;
```

## Step 2 — ⑤ 후보 신호 병치 (산술만, 추가 SQL 없음)

④의 각 후보에 대해, ①(구별 변화_pct)·③(구별 전세가율_최근·방향)을 **후보의 구로 조인**해 신호를 붙인다:

- **편차 라벨**: 편차_pct ≤ −8 → `🔴급매` / ≥ +3 → `🔵고가` / 그 외 → `⚪평균`
  - 🔴급매 주석: "매수 신호 아님 — 왜 이 단지만 약한가 조사 신호"(backtest: 상승국면 회복 58%<91%)
- **칼(구 하락)**: 후보 구의 ① `변화_pct ≤ −3` → `⚠칼(구 {변화}%)`
- **쿠션**: 후보 구의 ③ `전세가율_최근 < 0.40 AND 방향_6개월 < 0` → `⚠쿠션 얇음({구} {전세가율}↓)` (표시용 캐비엇, 게이트 아님)
- **평형 불명확**: 평형 ∈ {other, any} → `평형 불명확({평형})·참고용` (median이 평형 혼합)
- **저신뢰**: 표본 n < 3 → `n{n} 저신뢰`
- **거래없음/orphan**: ④에서 편차_pct가 NULL이면 → 최근거래도 NULL이면 `거래없음(최근 180일)`; 후보 apt_seq가 sale_records에 아예 없어 구까지 NULL이면 `구 매핑 불가`(둘을 구분)

⑤는 판정을 내리지 않는다. 위 신호들을 한 줄에 병치만 한다.

**전환의심 스위치**(②에서): 최근 완결 2개월(마지막 2개월 제외한 그 앞 2개월) 평균 매매 < 직전 3개월 평균 × 0.7 → 거래량 국면을 `둔화(전환의심 — 상대강도 참고 주의)`로, 아니면 `정상`으로 표기.

## Step 3 — 판독문 조립 (출력 템플릿 고정)

**텔레그램은 비례폰트라 공백 컬럼 정렬이 어긋난다** → 정렬 테이블 금지, 아래 **요약
우선 + 그룹형** 템플릿을 쓴다. 그룹 규칙:
- ① 강세(변화 ≥ 0) = `▲`, 약세(변화 < 0) = `▼`. 각 그룹 내림차순, `구 +x.x`.
- ③ 두꺼움(전세가율 ≥ 0.40) / 얇음(< 0.40). 방향 화살표: Δ>+0.01 `↑`, Δ<−0.01 `↓`, 그 외 `→`. 소수 표기 `.50` 형태.
- ④ 편차 오름차순(급매→고가), 라벨 이모지 선두: `🔴급매`/`⚪평균`/`🔵고가`, 거래없음 `⬜`. **절대가·거래일·표본수는 항상 포함**: `(중위 {중위}→최근 {최근가}억, {거래일}, n{표본})`, 편차 0.0이면 단일가 `({최근가}억, {거래일}, n{표본})`. 꼬리에 있을 때만: `⚠쿠션`/`⚠칼`, 평형 other→`혼합`, n<3→`저신뢰`.
- ② 13행 나열 금지 → 저점→반등→최근 서사 1줄 + 국면.

```
📊 부동산 트렌드 판독 · {today}
최신거래 {최신거래}({경과일}일 전) · 동일단지·신고지연보정·중립(신호만)

🔎 요약 — 급매 {n}·고가 {n}·쿠션주의 {n}
{시장 한 줄: 강/약세 요지 + 거래량 국면}

🏠 관심단지 (편차 = 자기 180일 중위 대비)
{🔴/⚪/🔵/⬜} {단지} {구}·{평형}  {±편차}%  (중위 {중위}→최근 {최근가}억, {거래일}, n{표본}){ · 꼬리}
  … ④ 후보별, 급매→고가 순 …
→ 급매 없음/있음 · 후보 구 칼 없음/있음 · 저신뢰=표본<3

📈 구 국면·상대강도 (84㎡ 동일단지, 90일)
▲ 강세  {구 +x.x · …}
▼ 약세  {구 −x.x · …}
⚠ 표본<30 저신뢰: {구 목록}

🏦 전세가율 (하방쿠션 · 최근/6개월)
두꺼움  {구 .xx{↑↓→} · …}
얇음    {구 .xx{↑↓→} · …}

📉 거래량 (9구 월 매매)
{저점 →반등 →최근(신고지연) 서사} · 국면: {정상/둔화(전환의심)}

⚠ 14개월 데이터 — 국면·급매/고가는 읽어도 사이클(절대 고점/저점)은 못 봄.
신호만, 판단은 회원님. 긴급 임계는 monitor cron이 별도 푸시.
```

## Step 4 — 출력 / 발송

- **기본**: 위 판독문을 터미널에 출력.
- **`$ARGUMENTS`에 `telegram` 포함 시**: scratchpad에 파일로 쓴 뒤 시스템 curl로 발송(로컬 Python은 TLS 프록시에 막힘). 토큰은 출력하지 말 것. 4,096자 확인 후, 초과 시 요약본(①·② 헤드라인 + ⑤ 후보 신호만)으로 축약:
```bash
cd /Users/joel/personal-labs/realestate_monitor
MSG=<scratchpad에 쓴 판독문 파일>
wc -m < "$MSG"   # 4096 확인
set -a; . ./.env 2>/dev/null; set +a
curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
  --data-urlencode "text@${MSG}" \
  --data-urlencode "disable_web_page_preview=true" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('발송 ok:', d.get('ok'), '| msg_id:', d.get('result',{}).get('message_id'))"
```

## 에러 처리
- 블록 실패 시 해당 블록에 `— 조회 실패`를 표기하고 나머지 블록은 계속.
- ⑤는 의존 블록(①/③/④) 실패 시 해당 신호만 `판정불가`.
- 관심단지 0건(enabled 룰 없음) → ④에 `관심단지 없음`(에러 아님).
- 텔레그램 실패(`ok:false`/4096자 초과 후에도 실패) → 터미널 출력은 유지하고 실패 사유 보고.

## 검증 기준 (골든)
`realestate_monitor/docs/rem-trend-golden-2026-07-31.md` 대비:
- **계층 1(구조·날짜 무관)**: ①~④ 무에러 + 기대 컬럼 + 항상 출력분(① 9행, ④ 후보 N행, ⑤ 신호, 고정 문구).
- **계층 2(신호 로직·날짜 무관)**: 같은 날 재호출이면 골든 숫자·신호 라벨 재현. 다른 날이면 창 이동으로 숫자는 달라지므로 ⑤ 신호 산출 **로직** 일치만 확인.
- 천장: ①~④ SQL 수치 정확성은 못 잡음 → 스냅샷일 1회 수기 크로스체크(범위 밖 명시).
