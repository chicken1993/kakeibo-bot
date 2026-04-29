# ======================
# Flask（Webサーバー）
# → LINEと通信する入口
# ======================
from flask import Flask, request, send_file

# ======================
# LINE Bot SDK
# → LINEに返信するためのライブラリ
# ======================
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    ImageSendMessage
)

# ======================
# 環境変数（トークンなど）
# ======================
import os
from dotenv import load_dotenv

# ======================
# DB・文字処理
# ======================
import re
import psycopg2

# ======================
# グラフ用
# ======================
import matplotlib.pyplot as plt
import io

load_dotenv()

app = Flask(__name__)

# ======================
# LINE認証
# ======================
CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# ======================
# DB接続
# ======================
def get_conn():
    return psycopg2.connect(
        os.getenv("DATABASE_URL"),
        sslmode="require"
    )

# ======================
# テーブル作成
# ======================
def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # 支出データ保存用テーブル
    cur.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id SERIAL PRIMARY KEY,
            user_id TEXT,
            amount INTEGER,
            category TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    cur.close()
    conn.close()

init_db()

# ======================
# 支出保存
# ======================
def save_expense(user_id, amount, category):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO expenses (user_id, amount, category) VALUES (%s, %s, %s)",
        (user_id, amount, category)
    )

    conn.commit()
    cur.close()
    conn.close()

# ======================
# 円グラフ生成
# ======================
def create_pie_chart(user_id):
    conn = get_conn()
    cur = conn.cursor()

    # カテゴリごとの合計取得
    cur.execute("""
        SELECT category, SUM(amount)
        FROM expenses
        WHERE user_id=%s
        GROUP BY category
    """, (user_id,))

    data = cur.fetchall()

    cur.close()
    conn.close()

    if not data:
        return None

    labels = [row[0] for row in data]
    sizes = [row[1] for row in data]

    # グラフ作成
    plt.figure()
    plt.pie(sizes, labels=labels, autopct='%1.1f%%')

    # 画像として保存（メモリ上）
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)

    return buf

# ======================
# グラフURL
# → ここにアクセスすると画像が返る
# ======================
@app.route("/chart/<user_id>")
def chart(user_id):
    img = create_pie_chart(user_id)

    if img:
        return send_file(img, mimetype='image/png')
    else:
        return "no data"

# ======================
# LINEからの受信口
# ======================
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)

    handler.handle(body, signature)
    return 'OK', 200

# ======================
# メイン処理
# ======================
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):

    text = event.message.text
    user_id = event.source.user_id

    try:
        text_clean = text.strip()

        # ======================
        # 📊 グラフ表示
        # ======================
        if "グラフ" in text:
            image_url = f"https://your-app.onrender.com/chart/{user_id}"

            line_bot_api.reply_message(
                event.reply_token,
                ImageSendMessage(
                    original_content_url=image_url,
                    preview_image_url=image_url
                )
            )
            return

        # ======================
        # 💰 支出入力
        # 例：ラーメン900
        # ======================
        match = re.search(r'(.+?)[にで]?(\d+)', text_clean)

        if match:
            category = match.group(1)
            price = int(match.group(2))

            save_expense(user_id, price, category)

            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"{category} {price}円記録")
            )
            return

        # ======================
        # デフォルト
        # ======================
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="そのまま金額送るか『グラフ』って送って")
        )

    except Exception as e:
        print(e)