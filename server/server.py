from flask import Flask, jsonify
from flask_cors import CORS
import pymysql
import os
from dotenv import load_dotenv

app = Flask(__name__)
CORS(app)

# [중요] .env 파일 경로 수정
# 현재 파일(server.py) 위치를 기준으로 옆 폴더(bithumb_trade)의 .env를 찾습니다.
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '..', 'bithumb_trade', '.env')
load_dotenv(dotenv_path=env_path)

# DB 접속 설정
db_config = {
    'host': 'localhost',
    'user': 'bot_user',
    'password': os.getenv('DB_PASSWORD'), # 이제 경로를 잘 찾아서 비번을 가져올 겁니다
    'db': 'bit_web',
    'charset': 'utf8',
    'cursorclass': pymysql.cursors.DictCursor
}

# ... (나머지 API 코드는 똑같습니다) ...
@app.route('/api/trades')
def get_trades():
    # ... (생략) ...
    return jsonify(result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)