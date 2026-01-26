from flask import Flask, jsonify, render_template
from flask_cors import CORS
import pymysql
import os
from dotenv import load_dotenv

app = Flask(__name__)
CORS(app)  # 혹시 모를 접속 문제 방지

# 1. .env 파일 로드 (비밀번호 보안)
# 현재 server.py가 있는 폴더에서 한 단계 위(..)로 가서 bithumb_trade/.env를 찾음
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '..', 'bithumb_trade', '.env')
load_dotenv(dotenv_path=env_path)

# 2. DB 접속 설정
db_config = {
    'host': 'localhost',
    'user': 'bot_user',
    'password': os.getenv('DB_PASSWORD'),  # .env에서 가져옴
    'db': 'bit_web',
    'charset': 'utf8',
    'cursorclass': pymysql.cursors.DictCursor
}

# 3. 메인 페이지 (환희가 만든 HTML 보여주기)
@app.route('/')
def home():
    try:
        return render_template('index.html')
    except Exception as e:
        return f"<h3>설정 오류: templates 폴더에 index.html이 없습니다.<br>에러 내용: {e}</h3>"

# 4. API: 매매기록 데이터 (최신 20개)
@app.route('/api/trades')
def get_trades():
    try:
        conn = pymysql.connect(**db_config)
        cur = conn.cursor()
        cur.execute("SELECT * FROM trade_history ORDER BY created_at DESC LIMIT 20")
        result = cur.fetchall()
        conn.close()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)})

# 5. API: 자산 현황 데이터 (가장 최신 1개)
@app.route('/api/balance')
def get_balance():
    try:
        conn = pymysql.connect(**db_config)
        cur = conn.cursor()
        cur.execute("SELECT * FROM balance_history ORDER BY recorded_at DESC LIMIT 1")
        result = cur.fetchone()
        conn.close()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    # 외부 접속 허용 (0.0.0.0), 포트 5000
    app.run(host='0.0.0.0', port=5000)