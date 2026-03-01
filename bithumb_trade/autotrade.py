import os
import json
import time
import requests
import pymysql
import jwt
import uuid
import hashlib
import schedule
from urllib.parse import urlencode
import google.generativeai as genai
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

ACCESS_KEY = os.getenv("BITHUMB_ACCESS_KEY")
SECRET_KEY = os.getenv("BITHUMB_SECRET_KEY")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

genai.configure(api_key=GEMINI_API_KEY)

class BithumbV2:
    def __init__(self, access_key, secret_key):
        self.access_key = access_key
        self.secret_key = secret_key
        self.api_url = "https://api.bithumb.com/v1"

    def _get_header(self, query_params=None):
        payload = {
            "access_key": self.access_key,
            "nonce": str(uuid.uuid4()),
            "timestamp": int(time.time() * 1000)
        }

        if query_params:
            query_string = urlencode(query_params)
            m = hashlib.sha512()
            m.update(query_string.encode('utf-8'))
            query_hash = m.hexdigest()
            payload['query_hash'] = query_hash
            payload['query_hash_alg'] = 'SHA512'

        jwt_token = jwt.encode(payload, self.secret_key, algorithm="HS256")
        return {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json"
        }

    def get_balance(self):
        try:
            res = requests.get(f"{self.api_url}/accounts", headers=self._get_header())
            res.raise_for_status()
            data = res.json()

            krw, btc = 0.0, 0.0

            for wallet in data:
                if wallet.get('currency') == 'KRW':
                    krw = float(wallet.get('balance', 0))
                elif wallet.get('currency') == 'BTC':
                    btc = float(wallet.get('balance', 0))

            return krw, btc

        except Exception as e:
            print(f"잔고 조회 실패: {e}")
            return 0.0, 0.0

    def get_current_price(self, market="KRW-BTC"):
        try:
            url = f"{self.api_url}/ticker?markets={market}"
            res = requests.get(url)
            data = res.json()
            return float(data[0]['trade_price'])
        except:
            return 0

    def get_ohlcv(self, market="KRW-BTC", unit="minutes/60", count=24):
        try:
            if unit == "days":
                url = f"{self.api_url}/candles/days?market={market}&count={count}"
            else:
                url = f"{self.api_url}/candles/{unit}?market={market}&count={count}"

            res = requests.get(url)
            data = res.json()

            formatted_data = []
            for d in data:
                formatted_data.append({
                    "time": d['candle_date_time_kst'],
                    "open": d['opening_price'],
                    "high": d['high_price'],
                    "low": d['low_price'],
                    "close": d['trade_price'],
                    "volume": d['candle_acc_trade_volume']
                })

            return formatted_data[::-1]

        except Exception as e:
            print(f"차트 데이터 오류: {e}")
            return []

    def buy_market(self, market="KRW-BTC", price_krw=5000):
        params = {
            "market": market,
            "side": "bid",
            "ord_type": "price",
            "price": str(price_krw)
        }

        headers = self._get_header(params)

        try:
            res = requests.post(f"{self.api_url}/orders", json=params, headers=headers)
            return res.json()
        except Exception as e:
            return {"error": str(e)}

    def sell_market(self, market="KRW-BTC", volume_btc=0.0001):
        params = {
            "market": market,
            "side": "ask",
            "ord_type": "market",
            "volume": str(volume_btc)
        }

        headers = self._get_header(params)

        try:
            res = requests.post(f"{self.api_url}/orders", json=params, headers=headers)
            return res.json()
        except Exception as e:
            return {"error": str(e)}

def get_db_connection():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        db=DB_NAME,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

def init_db():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
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

def log_trade(decision, percentage, reason, btc, krw, price):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
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
                btc,
                krw,
                price
            ))
        conn.commit()
    except Exception as e:
        print(f"DB Log Error: {e}")
    finally:
        conn.close()

def get_recent_trades():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 5")
            return cursor.fetchall()
    except:
        return []
    finally:
        conn.close()

def get_bitcoin_news():
    if not SERPAPI_API_KEY:
        return []
    try:
        url = "https://serpapi.com/search.json"
        params = {
            "engine": "google_news",
            "q": "bitcoin",
            "api_key": SERPAPI_API_KEY
        }
        r = requests.get(url, params=params).json()
        return [
            {"title": i.get("title"), "date": i.get("date")}
            for i in r.get("news_results", [])[:5]
        ]
    except:
        return []

def ai_trading():
    print(f"\n[{datetime.now()}] AI Trading System Start...")

    bithumb = BithumbV2(ACCESS_KEY, SECRET_KEY)
    current_krw, current_btc = bithumb.get_balance()
    current_price = bithumb.get_current_price()

    short_term = bithumb.get_ohlcv("KRW-BTC", "minutes/60", 24)
    mid_term = bithumb.get_ohlcv("KRW-BTC", "minutes/240", 30)
    long_term = bithumb.get_ohlcv("KRW-BTC", "days", 30)

    news = get_bitcoin_news()
    recent_trades = get_recent_trades()

    data_payload = {
        "market_data": {
            "current_price": current_price,
            "short_term_chart": short_term,
            "mid_term_chart": mid_term,
            "long_term_chart": long_term
        },
        "news": news,
        "account": {
            "krw_balance": current_krw,
            "btc_balance": current_btc,
            "total_asset_krw": current_krw + (current_btc * current_price)
        },
        "recent_trades": recent_trades
    }

    model = genai.GenerativeModel("gemini-flash-latest")

    prompt = f"""
    You are a professional Bitcoin trader. Analyze the market data and make a trading decision.

    Current State:
    - KRW Balance: {current_krw:,.0f} KRW
    - BTC Balance: {current_btc:.8f} BTC
    - Current Price: {current_price:,.0f} KRW

    Goal: Maximize profit safely.

    Data:
    {json.dumps(data_payload, ensure_ascii=False)}

    Response strictly in JSON:
    {{"decision": "buy" or "sell" or "hold", "percentage": 1-100, "reason": "short explanation"}}
    """

    try:
        response = model.generate_content(prompt)
        text = response.text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text)
    except Exception as e:
        print(f"AI Error: {e}")
        result = {"decision": "hold", "percentage": 0, "reason": "AI Failed"}

    print(f"AI Decision: {result['decision'].upper()} ({result['percentage']}%) - {result['reason']}")

    executed = False

    if result['decision'] == "buy":
        buy_amount = current_krw * (result['percentage'] / 100) * 0.995
        if buy_amount >= 5000:
            print(f"Buying {buy_amount:,.0f} KRW...")
            order = bithumb.buy_market("KRW-BTC", buy_amount)
            if "uuid" in order:
                print(f"Buy Order Success (UUID: {order['uuid']})")
                executed = True
            else:
                print(f"Buy Failed: {order}")
        else:
            print("Skipped: Amount < 5000 KRW")

    elif result['decision'] == "sell":
        sell_volume = current_btc * (result['percentage'] / 100)
        if (sell_volume * current_price) >= 5000:
            print(f"Selling {sell_volume:.8f} BTC...")
            order = bithumb.sell_market("KRW-BTC", sell_volume)
            if "uuid" in order:
                print(f"Sell Order Success (UUID: {order['uuid']})")
                executed = True
            else:
                print(f"Sell Failed: {order}")
        else:
            print("Skipped: Value < 5000 KRW")

    time.sleep(1)

    new_krw, new_btc = bithumb.get_balance()

    log_trade(
        result['decision'],
        result['percentage'] if executed else 0,
        result['reason'],
        new_btc,
        new_krw,
        current_price
    )

    print("---------------------------------------------------")

if __name__ == "__main__":
    init_db()
    print("Auto Trading Bot Started (Bithumb v2 + Gemini)")
    ai_trading()
    schedule.every(1).hours.do(ai_trading)

    while True:
        schedule.run_pending()
        time.sleep(1)