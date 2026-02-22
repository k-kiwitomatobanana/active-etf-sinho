"""
시그널 분석 모듈.
SQLite에 날짜별로 저장된 ETF 구성종목 데이터를 기반으로
매수/매도 시그널, 중복 매수 분석, 비중 변화 추적을 수행한다.
"""

import logging
import sqlite3

from config import DB_PATH

logger = logging.getLogger(__name__)


def get_db_connection() -> sqlite3.Connection:
    """SQLite DB 연결을 반환한다."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_collect_dates(conn: sqlite3.Connection, limit: int = 30) -> list:
    """
    DB에 저장된 수집 날짜 목록을 최신순으로 반환한다.

    Args:
        conn: DB 연결
        limit: 최대 반환 개수

    Returns:
        날짜 문자열 리스트 (최신순)
    """
    rows = conn.execute(
        "SELECT DISTINCT collect_date FROM etf_holdings "
        "ORDER BY collect_date DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [r["collect_date"] for r in rows]


def get_top_buy_increase(days: int = 3, top_n: int = 20) -> list:
    """
    최근 N일간 액티브 ETF들에서 주식수가 증가한 종목을 집계한다.

    계산 로직:
    1. DB에서 최신 collect_date와 N일 전 collect_date를 확인
    2. 각 ETF별로 두 날짜의 구성종목 비교
    3. 주식수가 증가한 종목 추출 (새로 편입된 종목 포함)
    4. 전체 ETF에서 해당 종목의 증가분 합산
    5. 증가분 기준 내림차순 정렬 후 Top N 반환

    Args:
        days: 비교 기간 (일)
        top_n: 반환할 상위 종목 수

    Returns:
        [{"stock_name", "etf_count", "total_increase", "weight_change"}, ...]
    """
    conn = get_db_connection()
    try:
        dates = get_collect_dates(conn)
        if len(dates) < 2:
            return []

        latest_date = dates[0]
        # days 이전에 가장 가까운 날짜 찾기
        older_date = dates[min(days, len(dates) - 1)]

        # 최신일 구성종목
        latest = conn.execute(
            "SELECT etf_code, stock_name, stock_count, weight "
            "FROM etf_holdings WHERE collect_date = ?",
            (latest_date,),
        ).fetchall()

        # 이전일 구성종목
        older = conn.execute(
            "SELECT etf_code, stock_name, stock_count, weight "
            "FROM etf_holdings WHERE collect_date = ?",
            (older_date,),
        ).fetchall()

        # 이전일 데이터를 딕셔너리로 변환
        older_map = {}
        for r in older:
            key = (r["etf_code"], r["stock_name"])
            older_map[key] = {"stock_count": r["stock_count"], "weight": r["weight"]}

        # 종목별 증가분 집계
        stock_increases = {}
        for r in latest:
            key = (r["etf_code"], r["stock_name"])
            old = older_map.get(key)

            if old is None:
                # 신규 편입
                increase = r["stock_count"] or 0
                w_change = r["weight"] or 0
            else:
                increase = (r["stock_count"] or 0) - (old["stock_count"] or 0)
                w_change = (r["weight"] or 0) - (old["weight"] or 0)

            if increase > 0:
                name = r["stock_name"]
                if name not in stock_increases:
                    stock_increases[name] = {
                        "stock_name": name,
                        "etf_count": 0,
                        "total_increase": 0,
                        "weight_change": 0.0,
                    }
                stock_increases[name]["etf_count"] += 1
                stock_increases[name]["total_increase"] += increase
                stock_increases[name]["weight_change"] += round(w_change, 2)

        result = sorted(
            stock_increases.values(),
            key=lambda x: (-x["total_increase"], -x["etf_count"]),
        )
        return result[:top_n]

    finally:
        conn.close()


def get_top_sell_increase(days: int = 3, top_n: int = 20) -> list:
    """
    최근 N일간 액티브 ETF들에서 완전히 제거된(청산) 종목을 집계한다.

    계산 로직:
    1. DB에서 최신 collect_date와 N일 전 collect_date를 확인
    2. 각 ETF별로 N일 전에는 있었지만 최신일에는 없는 종목 추출
    3. 전체 ETF에서 해당 종목의 청산 건수 합산
    4. 청산 건수 기준 내림차순 정렬 후 Top N 반환

    Args:
        days: 비교 기간 (일)
        top_n: 반환할 상위 종목 수

    Returns:
        [{"stock_name", "etf_count", "total_decrease", "prev_weight"}, ...]
    """
    conn = get_db_connection()
    try:
        dates = get_collect_dates(conn)
        if len(dates) < 2:
            return []

        latest_date = dates[0]
        older_date = dates[min(days, len(dates) - 1)]

        # 최신일 구성종목
        latest = conn.execute(
            "SELECT etf_code, stock_name, stock_count, weight "
            "FROM etf_holdings WHERE collect_date = ?",
            (latest_date,),
        ).fetchall()

        # 이전일 구성종목
        older = conn.execute(
            "SELECT etf_code, stock_name, stock_count, weight "
            "FROM etf_holdings WHERE collect_date = ?",
            (older_date,),
        ).fetchall()

        # 최신일 데이터를 set으로 변환
        latest_set = {(r["etf_code"], r["stock_name"]) for r in latest}

        # 이전일에 있었지만 최신일에 없는 종목 = 청산
        stock_sells = {}
        for r in older:
            key = (r["etf_code"], r["stock_name"])
            if key not in latest_set:
                name = r["stock_name"]
                if name not in stock_sells:
                    stock_sells[name] = {
                        "stock_name": name,
                        "etf_count": 0,
                        "total_decrease": 0,
                        "prev_weight": 0.0,
                    }
                stock_sells[name]["etf_count"] += 1
                stock_sells[name]["total_decrease"] += r["stock_count"] or 0
                stock_sells[name]["prev_weight"] += round(r["weight"] or 0, 2)

        result = sorted(
            stock_sells.values(),
            key=lambda x: (-x["etf_count"], -x["total_decrease"]),
        )
        return result[:top_n]

    finally:
        conn.close()


def get_overlapping_stocks(top_n: int = 30) -> list:
    """
    최신일 기준 여러 액티브 ETF가 동시에 보유한 종목을 분석한다.

    계산 로직:
    1. DB에서 최신 collect_date의 모든 ETF 구성종목 조회
    2. 종목별로 보유 ETF 수 카운트
    3. 2개 이상 ETF가 보유한 종목만 필터
    4. 보유 ETF 수 기준 내림차순, 동률 시 총 비중합 기준 정렬

    Args:
        top_n: 반환할 상위 종목 수

    Returns:
        [{"stock_name", "etf_count", "etf_names", "total_weight", "avg_weight"}, ...]
    """
    conn = get_db_connection()
    try:
        dates = get_collect_dates(conn, limit=1)
        if not dates:
            return []

        latest_date = dates[0]

        rows = conn.execute(
            "SELECT h.stock_name, h.etf_code, h.weight, m.etf_name "
            "FROM etf_holdings h "
            "LEFT JOIN etf_master m ON h.etf_code = m.etf_code "
            "WHERE h.collect_date = ?",
            (latest_date,),
        ).fetchall()

        # 종목별 집계
        stock_map = {}
        for r in rows:
            name = r["stock_name"]
            if name not in stock_map:
                stock_map[name] = {
                    "stock_name": name,
                    "etf_count": 0,
                    "etf_names": [],
                    "total_weight": 0.0,
                }
            stock_map[name]["etf_count"] += 1
            etf_display = r["etf_name"] or r["etf_code"]
            stock_map[name]["etf_names"].append(etf_display)
            stock_map[name]["total_weight"] += r["weight"] or 0

        # 2개 이상 보유 필터 + 평균 비중 계산
        result = []
        for s in stock_map.values():
            if s["etf_count"] >= 2:
                s["total_weight"] = round(s["total_weight"], 2)
                s["avg_weight"] = round(s["total_weight"] / s["etf_count"], 2)
                s["etf_names"] = sorted(s["etf_names"])
                result.append(s)

        result.sort(key=lambda x: (-x["etf_count"], -x["total_weight"]))
        return result[:top_n]

    finally:
        conn.close()


def get_weight_increase_signals(top_n: int = 30) -> list:
    """
    최신일 기준 비중 증가 시그널을 계산한다.

    계산 로직:
    1. DB에서 최근 수집된 날짜들 조회
    2. 연속 날짜 간 종목별 비중 변화량 계산
    3. 비중 증가합 = 모든 ETF에서 해당 종목의 비중 증가분 합산
    4. 증가 ETF 수 = 해당 종목의 비중이 증가한 ETF 개수
    5. 연속 증가일 = 최신일부터 역순으로 비중이 연속 증가한 일수

    Args:
        top_n: 반환할 상위 종목 수

    Returns:
        [{"stock_name", "weight_increase", "etf_count", "consecutive_days"}, ...]
    """
    conn = get_db_connection()
    try:
        dates = get_collect_dates(conn, limit=10)
        if len(dates) < 2:
            return []

        latest_date = dates[0]
        prev_date = dates[1]

        # 최신일과 직전일의 비중 변화 계산
        latest_data = conn.execute(
            "SELECT etf_code, stock_name, weight "
            "FROM etf_holdings WHERE collect_date = ?",
            (latest_date,),
        ).fetchall()

        prev_data = conn.execute(
            "SELECT etf_code, stock_name, weight "
            "FROM etf_holdings WHERE collect_date = ?",
            (prev_date,),
        ).fetchall()

        prev_map = {}
        for r in prev_data:
            prev_map[(r["etf_code"], r["stock_name"])] = r["weight"] or 0

        # 종목별 비중 증가 집계
        stock_signals = {}
        for r in latest_data:
            key = (r["etf_code"], r["stock_name"])
            curr_weight = r["weight"] or 0
            prev_weight = prev_map.get(key, 0)
            delta = curr_weight - prev_weight

            if delta > 0:
                name = r["stock_name"]
                if name not in stock_signals:
                    stock_signals[name] = {
                        "stock_name": name,
                        "weight_increase": 0.0,
                        "etf_count": 0,
                        "consecutive_days": 0,
                    }
                stock_signals[name]["weight_increase"] += round(delta, 4)
                stock_signals[name]["etf_count"] += 1

        # 연속 증가일 계산
        for stock_name in stock_signals:
            stock_signals[stock_name]["consecutive_days"] = _calc_consecutive_days(
                conn, stock_name, dates, direction="up"
            )
            stock_signals[stock_name]["weight_increase"] = round(
                stock_signals[stock_name]["weight_increase"], 2
            )

        result = sorted(
            stock_signals.values(),
            key=lambda x: (-x["weight_increase"], -x["etf_count"]),
        )
        return result[:top_n]

    finally:
        conn.close()


def get_weight_decrease_signals(top_n: int = 30) -> list:
    """
    최신일 기준 비중 감소 시그널을 계산한다.

    계산 로직: 비중 증가 시그널과 동일하되 감소 방향.

    Args:
        top_n: 반환할 상위 종목 수

    Returns:
        [{"stock_name", "weight_decrease", "etf_count", "consecutive_days"}, ...]
    """
    conn = get_db_connection()
    try:
        dates = get_collect_dates(conn, limit=10)
        if len(dates) < 2:
            return []

        latest_date = dates[0]
        prev_date = dates[1]

        latest_data = conn.execute(
            "SELECT etf_code, stock_name, weight "
            "FROM etf_holdings WHERE collect_date = ?",
            (latest_date,),
        ).fetchall()

        prev_data = conn.execute(
            "SELECT etf_code, stock_name, weight "
            "FROM etf_holdings WHERE collect_date = ?",
            (prev_date,),
        ).fetchall()

        prev_map = {}
        for r in prev_data:
            prev_map[(r["etf_code"], r["stock_name"])] = r["weight"] or 0

        stock_signals = {}
        for r in latest_data:
            key = (r["etf_code"], r["stock_name"])
            curr_weight = r["weight"] or 0
            prev_weight = prev_map.get(key, 0)
            delta = curr_weight - prev_weight

            if delta < 0:
                name = r["stock_name"]
                if name not in stock_signals:
                    stock_signals[name] = {
                        "stock_name": name,
                        "weight_decrease": 0.0,
                        "etf_count": 0,
                        "consecutive_days": 0,
                    }
                stock_signals[name]["weight_decrease"] += round(abs(delta), 4)
                stock_signals[name]["etf_count"] += 1

        for stock_name in stock_signals:
            stock_signals[stock_name]["consecutive_days"] = _calc_consecutive_days(
                conn, stock_name, dates, direction="down"
            )
            stock_signals[stock_name]["weight_decrease"] = round(
                stock_signals[stock_name]["weight_decrease"], 2
            )

        result = sorted(
            stock_signals.values(),
            key=lambda x: (-x["weight_decrease"], -x["etf_count"]),
        )
        return result[:top_n]

    finally:
        conn.close()


def _calc_consecutive_days(
    conn: sqlite3.Connection, stock_name: str, dates: list, direction: str
) -> int:
    """
    특정 종목의 비중이 연속으로 증가/감소한 일수를 계산한다.

    Args:
        conn: DB 연결
        stock_name: 종목명
        dates: 수집 날짜 리스트 (최신순)
        direction: "up" 또는 "down"

    Returns:
        연속 증가/감소 일수
    """
    consecutive = 0

    for i in range(len(dates) - 1):
        curr_date = dates[i]
        prev_date = dates[i + 1]

        # 현재 날짜의 해당 종목 평균 비중
        curr_row = conn.execute(
            "SELECT AVG(weight) as avg_w FROM etf_holdings "
            "WHERE stock_name = ? AND collect_date = ?",
            (stock_name, curr_date),
        ).fetchone()

        prev_row = conn.execute(
            "SELECT AVG(weight) as avg_w FROM etf_holdings "
            "WHERE stock_name = ? AND collect_date = ?",
            (stock_name, prev_date),
        ).fetchone()

        curr_avg = curr_row["avg_w"] if curr_row and curr_row["avg_w"] else 0
        prev_avg = prev_row["avg_w"] if prev_row and prev_row["avg_w"] else 0

        if direction == "up" and curr_avg > prev_avg:
            consecutive += 1
        elif direction == "down" and curr_avg < prev_avg:
            consecutive += 1
        else:
            break

    return consecutive


def get_etf_holdings(etf_code: str) -> list:
    """
    특정 ETF의 최신 구성종목을 조회한다.

    Args:
        etf_code: ETF 종목코드

    Returns:
        [{"stock_name", "stock_count", "weight"}, ...]
    """
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT MAX(collect_date) as latest_date "
            "FROM etf_holdings WHERE etf_code = ?",
            (etf_code,),
        ).fetchone()

        if not row or not row["latest_date"]:
            return []

        rows = conn.execute(
            "SELECT stock_name, stock_count, weight "
            "FROM etf_holdings WHERE etf_code = ? AND collect_date = ? "
            "ORDER BY weight DESC",
            (etf_code, row["latest_date"]),
        ).fetchall()

        return [dict(r) for r in rows]

    finally:
        conn.close()


def get_last_update_info() -> dict:
    """
    마지막 데이터 수집 정보를 반환한다.

    Returns:
        {"last_date": str, "etf_count": int, "stock_count": int}
    """
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT MAX(collect_date) as last_date FROM etf_holdings"
        ).fetchone()

        if not row or not row["last_date"]:
            return {"last_date": None, "etf_count": 0, "stock_count": 0}

        last_date = row["last_date"]

        etf_count = conn.execute(
            "SELECT COUNT(DISTINCT etf_code) as cnt "
            "FROM etf_holdings WHERE collect_date = ?",
            (last_date,),
        ).fetchone()["cnt"]

        stock_count = conn.execute(
            "SELECT COUNT(DISTINCT stock_name) as cnt "
            "FROM etf_holdings WHERE collect_date = ?",
            (last_date,),
        ).fetchone()["cnt"]

        return {
            "last_date": last_date,
            "etf_count": etf_count,
            "stock_count": stock_count,
        }

    finally:
        conn.close()
