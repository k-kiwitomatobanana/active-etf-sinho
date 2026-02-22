# Active ETF Analysis

네이버 증권에서 한국 액티브 ETF 구성종목 데이터를 매일 수집하여, 매수/매도 시그널을 분석하고 웹 대시보드로 제공하는 Python 애플리케이션.

## 시스템 소개

### 주요 기능

- **ETF 구성종목 자동 수집**: 25개 액티브 ETF의 구성종목(종목명, 주식수, 비중)을 네이버 증권에서 매일 크롤링
- **매수/매도 시그널 분석**: 기간별(3일/5일/10일) 주식수 증가/청산 종목 Top N 분석
- **중복 매수 분석**: 여러 ETF가 동시에 보유한 종목 집계
- **비중 변화 시그널**: 비중 증가/감소 추이 및 연속 증가/감소일 추적
- **섹터별 보유종목 조회**: 반도체, 바이오, 배당/밸류업 등 섹터별 ETF 보유종목 한눈에 확인
- **자동 스케줄링**: 매일 20:00 자동 수집 (APScheduler)
- **웹 대시보드**: Bootstrap 5.3 기반 반응형 UI, 다크모드 지원

### 분석 대상 ETF (25개)

| 섹터 | ETF |
|------|-----|
| 반도체 | UNICORN SK하이닉스밸류체인, WON 반도체밸류체인, RISE 비메모리반도체, KoAct AI인프라, TIGER 코리아테크 |
| 바이오 | TIMEFOLIO K바이오, KoAct 바이오헬스케어, RISE 바이오TOP10 |
| 배당/밸류업 | KoAct 배당성장, TIMEFOLIO Korea플러스배당, TIMEFOLIO 코리아밸류업, KoAct 코리아밸류업, TRUSTON 코리아밸류업 |
| 신재생/2차전지 | KODEX 신재생에너지, TIMEFOLIO K신재생에너지, RISE 2차전지, TIMEFOLIO K이노베이션 |
| 로봇/우주/조선 | KODEX 친환경조선해운, KoAct K수출핵심기업TOP30, KODEX 로봇 |
| 소비/컬처 | VITA MZ소비, TIMEFOLIO K컬처 |
| 기타 | WON K-글로벌수급상위, TIMEFOLIO 코스피, KODEX 200 |

### 기술 스택

| 구분 | 기술 |
|------|------|
| 언어 | Python 3.10+ |
| 웹 프레임워크 | Flask |
| 데이터베이스 | SQLite |
| 프론트엔드 | Bootstrap 5.3 (CDN), Jinja2 |
| 스크래핑 | requests + BeautifulSoup4 |
| 스케줄링 | APScheduler (매일 20:00) |

## 사용 방법

### 1. 환경 설정

```bash
# 저장소 클론
git clone https://github.com/k-kiwitomatobanana/active-etf-sinho.git
cd active-etf-sinho

# 가상환경 생성 및 활성화
python3 -m venv venv
source venv/bin/activate   # Linux/Mac
# venv\Scripts\activate    # Windows

# 패키지 설치
pip install -r requirements.txt
```

### 2. 실행

```bash
source venv/bin/activate
python3 app.py
```

서버가 시작되면 브라우저에서 접속:
- **대시보드**: http://localhost:8787
- **시그널**: http://localhost:8787/signals

### 3. 데이터 수집

- **자동 수집**: 매일 20:00에 자동 실행
- **수동 수집**: 웹 대시보드 우측 상단 `수동 수집` 버튼 클릭

### 4. 웹 대시보드 사용법

#### 대시보드 (/)
- **기간 선택**: 3일/5일/10일 버튼으로 분석 기간 변경
- **매수 증가 Top N**: 선택 기간 동안 주식수가 증가한 종목 상위 20개
- **매도 증가(청산) Top N**: 선택 기간 동안 ETF에서 완전히 제거된 종목
- **섹터 탭**: 섹터별 ETF 보유종목을 카드 형태로 한눈에 확인, 상단에 중복 보유 Top 5 표시

#### 시그널 (/signals)
- **중복 매수 종목**: 여러 ETF가 동시에 보유한 종목 (보유 ETF 목록 포함)
- **비중 증가 시그널**: 비중이 증가한 종목 (연속 증가일 포함)
- **비중 감소 시그널**: 비중이 감소한 종목 (연속 감소일 포함)

## 프로젝트 구조

```
active-etf-sinho/
├── app.py                  # Flask 메인 앱 + 스케줄러
├── config.py               # ETF 목록, 섹터 분류, DB 설정
├── requirements.txt
├── README.md
├── CLAUDE.md               # Claude Code 프로젝트 컨텍스트
├── .gitignore
├── db/
│   └── active_etf.db       # SQLite DB (자동 생성, git 제외)
├── crawler/
│   ├── __init__.py
│   └── naver_etf.py        # 네이버 증권 크롤러
├── analyzer/
│   ├── __init__.py
│   └── signal.py           # 시그널 분석 로직
├── templates/
│   ├── base.html            # 공통 레이아웃
│   ├── index.html           # 메인 대시보드
│   └── signals.html         # 시그널 대시보드
└── static/css/
    └── custom.css           # 커스텀 스타일
```
