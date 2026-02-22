"""
Active ETF Analysis - Flask 메인 앱.
네이버 증권에서 한국 액티브 ETF 구성종목 데이터를 수집·분석하고
투자 시그널을 제공하는 웹 대시보드.
"""

import logging
import os
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, render_template, request

from analyzer.signal import (
    get_collect_dates,
    get_db_connection,
    get_etf_holdings,
    get_last_update_info,
    get_overlapping_stocks,
    get_top_buy_increase,
    get_top_sell_increase,
    get_weight_decrease_signals,
    get_weight_increase_signals,
)
from config import ETF_LIST, ETF_SECTORS, SECTOR_ORDER, HOST, PORT, SCHEDULE_HOUR, SCHEDULE_MINUTE
from crawler.naver_etf import collect_all_etf_data, init_db, seed_etf_master

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 수집 상태 관리
_collect_lock = threading.Lock()
_collect_running = False
_collect_progress = ""


def run_collection():
    """백그라운드에서 데이터 수집을 실행한다."""
    global _collect_running, _collect_progress
    with _collect_lock:
        if _collect_running:
            return
        _collect_running = True
        _collect_progress = "시작됨"

    try:
        results = collect_all_etf_data()
        saved = sum(1 for r in results if r["status"] == "saved")
        errors = sum(1 for r in results if r["status"] in ("error", "empty"))
        _collect_progress = f"완료: 저장 {saved}, 오류 {errors}"
    except Exception as e:
        logger.error("수집 중 오류: %s", e)
        _collect_progress = f"오류: {e}"
    finally:
        with _collect_lock:
            _collect_running = False


# --- 페이지 라우팅 ---

@app.route("/")
def index():
    """메인 대시보드 페이지."""
    # 섹터별 ETF 개수 계산
    sector_counts = {}
    for sector in SECTOR_ORDER:
        if sector == "전체":
            sector_counts[sector] = len(ETF_LIST)
        else:
            sector_counts[sector] = sum(1 for s in ETF_SECTORS.values() if s == sector)
    return render_template(
        "index.html",
        etf_list=ETF_LIST,
        etf_sectors=ETF_SECTORS,
        sector_order=SECTOR_ORDER,
        sector_counts=sector_counts,
    )


@app.route("/signals")
def signals():
    """시그널 대시보드 페이지."""
    return render_template("signals.html")


# --- 데이터 API ---

@app.route("/api/top-buy")
def api_top_buy():
    """매수 증가 Top N API."""
    days = request.args.get("days", 3, type=int)
    top_n = request.args.get("top_n", 20, type=int)
    return jsonify(get_top_buy_increase(days=days, top_n=top_n))


@app.route("/api/top-sell")
def api_top_sell():
    """매도 증가(청산) Top N API."""
    days = request.args.get("days", 3, type=int)
    top_n = request.args.get("top_n", 20, type=int)
    return jsonify(get_top_sell_increase(days=days, top_n=top_n))


@app.route("/api/holdings")
def api_holdings():
    """ETF별 보유종목 API."""
    etf_code = request.args.get("etf_code", "")
    if not etf_code:
        return jsonify([])
    return jsonify(get_etf_holdings(etf_code))


@app.route("/api/holdings-by-sector")
def api_holdings_by_sector():
    """섹터별 ETF 보유종목 일괄 조회 API."""
    sector = request.args.get("sector", "전체")
    result = []
    for etf_name, etf_code in ETF_LIST.items():
        if sector != "전체" and ETF_SECTORS.get(etf_name) != sector:
            continue
        holdings = get_etf_holdings(etf_code)
        result.append({
            "etf_name": etf_name,
            "etf_code": etf_code,
            "sector": ETF_SECTORS.get(etf_name, "기타"),
            "holdings": holdings,
        })
    return jsonify(result)


@app.route("/api/overlap")
def api_overlap():
    """중복 매수 종목 API."""
    top_n = request.args.get("top_n", 30, type=int)
    return jsonify(get_overlapping_stocks(top_n=top_n))


@app.route("/api/weight-increase")
def api_weight_increase():
    """비중 증가 시그널 API."""
    top_n = request.args.get("top_n", 30, type=int)
    return jsonify(get_weight_increase_signals(top_n=top_n))


@app.route("/api/weight-decrease")
def api_weight_decrease():
    """비중 감소 시그널 API."""
    top_n = request.args.get("top_n", 30, type=int)
    return jsonify(get_weight_decrease_signals(top_n=top_n))


@app.route("/api/dates")
def api_dates():
    """DB에 저장된 수집 날짜 목록 API."""
    conn = get_db_connection()
    try:
        dates = get_collect_dates(conn)
        return jsonify(dates)
    finally:
        conn.close()


@app.route("/api/last-update")
def api_last_update():
    """마지막 수집 일시 조회 API."""
    return jsonify(get_last_update_info())


# --- 관리 API ---

@app.route("/api/collect", methods=["POST"])
def api_collect():
    """수동 데이터 수집 실행 API."""
    global _collect_running
    with _collect_lock:
        if _collect_running:
            return jsonify({"status": "already_running"})

    thread = threading.Thread(target=run_collection, daemon=True)
    thread.start()
    return jsonify({"status": "started"})


@app.route("/api/collect-status")
def api_collect_status():
    """수집 상태 조회 API."""
    return jsonify({
        "running": _collect_running,
        "progress": _collect_progress,
    })


# --- 앱 시작 ---

if __name__ == "__main__":
    # DB 초기화
    os.makedirs(os.path.join(os.path.dirname(__file__), "db"), exist_ok=True)
    init_db()
    seed_etf_master()

    # APScheduler 설정 (매일 지정 시간에 자동 수집)
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=run_collection,
        trigger="cron",
        day_of_week="mon-fri",
        hour=SCHEDULE_HOUR,
        minute=SCHEDULE_MINUTE,
        id="daily_etf_collection",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("스케줄러 시작: 매일 %02d:%02d 자동 수집", SCHEDULE_HOUR, SCHEDULE_MINUTE)

    # Flask 앱 실행
    logger.info("서버 시작: http://%s:%d", HOST, PORT)
    app.run(host=HOST, port=PORT, debug=False)
