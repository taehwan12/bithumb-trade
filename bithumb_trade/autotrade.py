import os
import json
import requests
import pymysql # sqlite3 대신 pymysql 사용
from datetime import datetime
from dotenv import load_dotenv
import pybithumb
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import time
import schedule

# ===============================
# 환경 변수 로드
# ===============================
load_dotenv()

SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Gemini 설정
genai.configure(api_key=GEMINI_API_KEY)

# ===============================
# DB 관련 함수 (MySQL 적용)
# ===============================
def get_db_connection():
    return pymysql.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        db=os.getenv("DB_NAME"),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor # 데이터를 딕셔너리로 받기 위해 설정
    )

def init_db():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # MySQL 문법에 맞게 AUTO_INCREMENT 사용
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    timestamp VARCHAR(50),
                    decision VARCHAR(10),
                    percentage INT,
                    reason TEXT,
                    btc_balance DOUBLE,
                    krw_balance DOUBLE,
                    btc_price DOUBLE
                )
            """)
        conn.commit()
    finally:
        conn.close()

def log_trade(decision, percentage, reason, btc_balance, krw_balance, btc_price):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # pymysql에서는 placeholder가 '?'가 아니라 '%s' 입니다.
            sql = """
                INSERT INTO trades 
                (timestamp, decision, percentage, reason, btc_balance, krw_balance, btc_price)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (
                datetime.now().isoformat(),
                decision,
                percentage,
                reason,
                btc_balance,
                krw_balance,
                btc_price
            ))
        conn.commit()
    except Exception as e:
        print(f"DB Log Error: {e}")
    finally:
        conn.close()

def get_recent_trades(limit=5):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT timestamp, decision, percentage, reason, btc_balance, krw_balance, btc_price
                FROM trades
                ORDER BY timestamp DESC
                LIMIT %s
            """
            cursor.execute(sql, (limit,))
            result = cursor.fetchall() # DictCursor 덕분에 딕셔너리 리스트로 반환됨
            return result
    except Exception as e:
        print(f"DB Fetch Error: {e}")
        return []
    finally:
        conn.close()

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

    try:
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
    except Exception as e:
        print(f"News Error: {e}")
        return []

# ===============================
# AI 판단 (Gemini)
# ===============================
def ai_trading():
    # 1. 차트 데이터
    try:
        short_df = pybithumb.get_ohlcv("KRW-BTC", interval="minute60", count=24)
        mid_df = pybithumb.get_ohlcv("KRW-BTC", interval="minute240", count=30)
        long_df = pybithumb.get_ohlcv("KRW-BTC", interval="day", count=30)
    except Exception as e:
        print(f"Chart Data Error: {e}")
        return {"decision": "hold", "percentage": 0, "reason": "Chart data fetch failed"}

    # 2. 뉴스
    news = get_bitcoin_news(SERPAPI_API_KEY)

    # 3. 빗썸 잔고 조회
    bithumb = pybithumb.Bithumb(
        os.getenv("BITHUMB_ACCESS_KEY"),
        os.getenv("BITHUMB_SECRET_KEY")
    )
    
    balance = bithumb.get_balance("BTC") 
    current_btc = balance[0]
    current_krw = balance[2]
    current_price = pybithumb.get_current_price("KRW-BTC")

    recent_trades = get_recent_trades()

    # 데이터 페이로드 구성
    data_payload = {
        "short_term": json.loads(short_df.to_json()) if short_df is not None else None,
        "mid_term": json.loads(mid_df.to_json()) if mid_df is not None else None,
        "long_term": json.loads(long_df.to_json()) if long_df is not None else None,
        "news": news,
        "balance": {
            "krw": current_krw,
            "btc": current_btc,
            "btc_price": current_price,
            "total_value": current_krw + (current_btc * current_price)
        },
        "recent_trades": recent_trades
    }

    # Gemini 모델 설정
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        generation_config={
            "temperature": 0.1,
            "response_mime_type": "application/json"
        },
        safety_settings={
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
    )

    prompt = f"""
    You are an expert Bitcoin trader using technical analysis and news sentiment.

    Rules:
    1. Goal: Maximize profit, minimize loss (Rule No.1: Never lose money).
    2. Analyze the provided chart data, news, and recent trade history.
    3. Output strictly in JSON format.

    Data:
    {json.dumps(data_payload)}

    Response Format:
    {{"decision": "buy" or "sell" or "hold", "percentage": (integer 1-100), "reason": "brief explanation"}}
    """

    try:
        response = model.generate_content(prompt)
        
        response_text = response.text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
            
        result = json.loads(response_text)
    except Exception as e:
        print(f"Gemini Error: {e}")
        result = {"decision": "hold", "percentage": 0, "reason": "AI Error"}

    return result

# ===============================
# 매매 실행
# ===============================
def execute_trade():
    # DB 테이블 존재 여부 확인 (최초 1회 안전장치)
    init_db()
    
    print(f"\n[{datetime.now()}] Trading logic start")

    result = ai_trading()
    print(f"### AI Decision: {result.get('decision', 'hold').upper()} ( {result.get('percentage', 0)}% ) ###")
    print(f"### Reason: {result.get('reason', 'None')} ###")

    bithumb = pybithumb.Bithumb(
        os.getenv("BITHUMB_ACCESS_KEY"),
        os.getenv("BITHUMB_SECRET_KEY")
    )
    
    balance = bithumb.get_balance("BTC")
    current_btc = balance[0]
    current_krw = balance[2]
    current_price = pybithumb.get_current_price("KRW-BTC")

    executed = False

    if result["decision"] == "buy":
        amount = current_krw * (result["percentage"] / 100) * 0.997
        if amount >= 5000:
            try:
                print(f"Trying to BUY: {amount:,.0f} KRW")
                bithumb.buy_market_order("KRW-BTC", amount)
                executed = True
            except Exception as e:
                print(f"Buy Error: {e}")
        else:
            print("Buy skipped: Amount < 5000 KRW")

    elif result["decision"] == "sell":
        btc_amount = current_btc * (result["percentage"] / 100)
        if (btc_amount * current_price) >= 5000:
            try:
                print(f"Trying to SELL: {btc_amount} BTC")
                bithumb.sell_market_order("KRW-BTC", btc_amount)
                executed = True
            except Exception as e:
                print(f"Sell Error: {e}")
        else:
            print("Sell skipped: Value < 5000 KRW")

    time.sleep(1)

    new_balance = bithumb.get_balance("BTC")
    
    # MySQL에 로그 저장
    log_trade(
        result["decision"],
        result["percentage"] if executed else 0,
        result["reason"],
        new_balance[0], 
        new_balance[2], 
        pybithumb.get_current_price("KRW-BTC")
    )

    print(f"[{datetime.now()}] Trading cycle completed\n")

# ===============================
# 스케줄러
# ===============================
def run_scheduler():
    # 시작 전 DB 연결 테스트 및 테이블 생성
    init_db()
    print("=== Auto Trading Started (Gemini + MySQL) ===")
    
    schedule.every().day.at("09:00").do(execute_trade)
    schedule.every().day.at("15:00").do(execute_trade)
    schedule.every().day.at("21:00").do(execute_trade)

    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    run_scheduler()