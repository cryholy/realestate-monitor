# realestate_monitor

7개 단지(성동·광진구)의 매매가가 20억 미만으로 신고되면 직전 90일 전세 갭 정보와
함께 텔레그램으로 자동 알림을 보낸다. Claude 원격 에이전트(`schedule` 스킬)가
매일 09:00·18:00 KST에 실행한다.

## 사전 준비

### 1. 공공데이터포털 API 활용신청

- 사이트: https://www.data.go.kr/
- 신청할 API 2종:
  - 국토교통부_아파트매매 실거래가 상세 자료
  - 국토교통부_아파트 전월세 자료
- 두 API가 같은 서비스 키로 통하는 경우가 일반적이지만, 별도 신청이 필요할 수 있음.

### 2. 텔레그램 봇

이미 워크스페이스에 텔레그램 봇이 연결되어 있다면 같은 봇 토큰을 재사용할 수 있다.
새로 만드는 경우 BotFather(@BotFather)에서 `/newbot` 으로 생성.

#### chat_id 확인 방법

```bash
TOKEN="YOUR_BOT_TOKEN"
# 봇과 1:1 대화창에서 /start 또는 임의의 메시지 1회 전송 후
curl -s "https://api.telegram.org/bot${TOKEN}/getUpdates" | python3 -m json.tool
# 응답의 result[].message.chat.id 가 본인 chat_id
```

### 3. 환경 변수 설정

```bash
cp .env.example .env
# .env 편집해서 MOLIT_SERVICE_KEY, TELEGRAM_BOT_TOKEN 입력
```

### 4. config.json 편집

`telegram_chat_id`를 본인 값으로 교체.

### 5. 의존성 설치

```bash
cd /Users/joel/Claude/labs/realestate_monitor
python3.11 -m pip install --user -r requirements.txt
```

> Python 3.11+ 필수 (`str | None` 등 PEP 604 타입). macOS 기본 Python(3.9)은 사용 불가.

## 운영 전 검증 (필수, 1회성)

직전 6개월 데이터로 단지 매칭 패턴이 제대로 잡히는지 확인.

```bash
python3.11 monitor.py --backfill-months 6 --dry-run --report
```

출력에서 단지별 매칭 건수를 확인하고, 매칭 0건 또는 의심 매칭이 있으면
`config.json`의 `name_patterns` / `exclude_patterns`를 보정한다.

## 수동 실행

```bash
# 알림 발송 없이 매칭 결과만 콘솔 출력
python3.11 monitor.py --dry-run

# state 무시하고 강제 재발송 (디버그)
python3.11 monitor.py --no-dedup --dry-run

# 직전 N개월 백필
python3.11 monitor.py --backfill-months 6

# 운영 모드 (스케줄 에이전트가 실행)
python3.11 monitor.py --notify-on-error
```

## 스케줄 등록

### 옵션 A. macOS launchd (현재 사용 중)

노트북 ON 상태에서 매일 09:00·18:00 KST에 실행. plist 템플릿이 프로젝트에 포함되어 있다.

```bash
# 설치
cp com.joel.realestate-monitor.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.joel.realestate-monitor.plist

# 등록 확인
launchctl list | grep realestate

# 수동 실행 테스트
launchctl kickstart -p gui/$(id -u)/com.joel.realestate-monitor

# 로그
tail -f logs/launchd.err.log    # Python logging은 stderr로 출력됨

# 제거
launchctl unload ~/Library/LaunchAgents/com.joel.realestate-monitor.plist
```

**한계**: 노트북이 꺼져 있는 시각엔 실행되지 않는다. 이 시점에 실행되어야 했던 작업은 다음 부팅 후 자동 catch-up되지만, 시각이 정확히 9시·18시는 아니다.

### 옵션 B. GitHub Actions (laptop-independent, 향후 마이그레이션)

1. Private GitHub repo에 코드 push (state.json 포함, .env 제외)
2. GitHub Secrets에 `MOLIT_SERVICE_KEY`·`TELEGRAM_BOT_TOKEN` 등록
3. `.github/workflows/monitor.yml` 작성 (cron `0 0,9 * * *` UTC = 09:00·18:00 KST)
4. 워크플로 마지막에 state.json 변경 시 자동 commit & push

자세한 설정은 추후 별도 가이드.

## 단지·임계값 변경

`config.json` 직접 편집. 단지 추가 시:

```json
{
  "key": "<unique_key>",
  "display_name": "표시명",
  "lawd_cd": "5자리 시군구 코드",
  "법정동": "정확한 법정동명 (API 응답과 일치)",
  "name_patterns": ["매칭할 단지명들"],
  "exclude_patterns": ["배제할 키워드"]
}
```

추가 후 `--report` 실행으로 매칭 검증.

## 테스트

```bash
python3.11 -m pytest tests/ -v
```

## 로그 위치

- `logs/run-YYYY-MM-DD.log` — 실행 요약
- `logs/error.log` — 스택 트레이스
- 90일 이상 경과 `run-*.log` 자동 삭제
