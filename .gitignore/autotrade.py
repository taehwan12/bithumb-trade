import os
import json
import requests
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
import python_bithumb
import google.generativeai as genai
import time
import schedule

# ===============================
# 환경 변수 로드
# ===============================
load_dotenv()

SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Gemini 설정 (전역 1회)
genai.configure(api_key=GEMINI_API_KEY)

# ===============================
# DB 관련 함수
# ===============================
def init_db():
    conn = sqlite3.connect("bitcoin_trading.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            decision TEXT,
            percentage INTEGER,
            reason TEXT,
            btc_balance REAL,
            krw_balance REAL,
            btc_price REAL
        )
    """)
    conn.commit()
    return conn


def log_trade(conn, decision, percentage, reason, btc_balance, krw_balance, btc_price):
    c = conn.cursor()
    c.execute("""
        INSERT INTO trades 
        (timestamp, decision, percentage, reason, btc_balance, krw_balance, btc_price)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().isoformat(),
        decision,
        percentage,
        reason,
        btc_balance,
        krw_balance,
        btc_price
    ))
    conn.commit()


def get_recent_trades(limit=5):
    conn = sqlite3.connect("bitcoin_trading.db")
    c = conn.cursor()
    c.execute("""
        SELECT timestamp, decision, percentage, reason, btc_balance, krw_balance, btc_price
        FROM trades
        ORDER BY timestamp DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()

    keys = ["timestamp", "decision", "percentage", "reason", "btc_balance", "krw_balance", "btc_price"]
    return [dict(zip(keys, row)) for row in rows]


# ===============================
# 뉴스 수집
# ===============================
def get_bitcoin_news(api_key, query="bitcoin", num_results=5):
    if not api_key:
        return []

    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google_news",
        "q": query,
        "api_key": api_key
    }

    r = requests.get(url, params=params)
    r.raise_for_status()
    data = r.json()

    news = []
    for item in data.get("news_results", [])[:num_results]:
        news.append({
            "title": item.get("title"),
            "date": item.get("date")
        })
    return news


# ===============================
# AI 판단 (Gemini)
# ===============================
def ai_trading():
    # 차트 데이터
    short_df = python_bithumb.get_ohlcv("KRW-BTC", interval="minute60", count=24)
    mid_df = python_bithumb.get_ohlcv("KRW-BTC", interval="minute240", count=30)
    long_df = python_bithumb.get_ohlcv("KRW-BTC", interval="day", count=30)

    # 뉴스
    news = get_bitcoin_news(SERPAPI_API_KEY)

    # 빗썸 잔고
    bithumb = python_bithumb.Bithumb(
        os.getenv("BITHUMB_ACCESS_KEY"),
        os.getenv("BITHUMB_SECRET_KEY")
    )

    krw = bithumb.get_balance("KRW")
    btc = bithumb.get_balance("BTC")
    price = python_bithumb.get_current_price("KRW-BTC")

    recent_trades = get_recent_trades()

    data_payload = {
        "short_term": json.loads(short_df.to_json()) if short_df is not None else None,
        "mid_term": json.loads(mid_df.to_json()) if mid_df is not None else None,
        "long_term": json.loads(long_df.to_json()) if long_df is not None else None,
        "news": news,
        "balance": {
            "krw": krw,
            "btc": btc,
            "btc_price": price,
            "total_value": krw + btc * price
        },
        "recent_trades": recent_trades
    }

    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        generation_config={
            "temperature": 0.2,
            "response_mime_type": "application/json"
        }
    )

    prompt = f"""
You are an expert Bitcoin trader.

Rules:
- Never lose money.
- Decide BUY, SELL, or HOLD.

Respond ONLY in JSON:
{{"decision":"buy|sell|hold","percentage":0-100,"reason":"..."}}

DATA:
{json.dumps(data_payload)}
"""

    response = model.generate_content(prompt)

    try:
        result = json.loads(response.text)
    except Exception:
        result = {"decision": "hold", "percentage": 0, "reason": "JSON parse error"}

    return result


# ===============================
# 매매 실행
# ===============================
def execute_trade():
    conn = init_db()
    print(f"[{datetime.now()}] Trading start")

    result = ai_trading()
    print("AI Decision:", result)

    bithumb = python_bithumb.Bithumb(
        os.getenv("BITHUMB_ACCESS_KEY"),
        os.getenv("BITHUMB_SECRET_KEY")
    )

    krw = bithumb.get_balance("KRW")
    btc = bithumb.get_balance("BTC")
    price = python_bithumb.get_current_price("KRW-BTC")

    executed = False

    if result["decision"] == "buy":
        amount = krw * result["percentage"] / 100 * 0.997
        if amount > 5000:
            bithumb.buy_market_order("KRW-BTC", amount)
            executed = True

    elif result["decision"] == "sell":
        btc_amount = btc * result["percentage"] / 100 * 0.997
        if btc_amount * price > 5000:
            bithumb.sell_market_order("KRW-BTC", btc_amount)
            executed = True

    time.sleep(1)

    log_trade(
        conn,
        result["decision"],
        result["percentage"] if executed else 0,
        result["reason"],
        bithumb.get_balance("BTC"),
        bithumb.get_balance("KRW"),
        python_bithumb.get_current_price("KRW-BTC")
    )

    conn.close()
    print(f"[{datetime.now()}] Trading end")


# ===============================
# 스케줄러
# ===============================
def run_scheduler():
    init_db()
    print("Auto Trading Started (Gemini)")

    schedule.every().day.at("09:00").do(execute_trade)
    schedule.every().day.at("15:00").do(execute_trade)
    schedule.every().day.at("21:00").do(execute_trade)

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    run_scheduler()
