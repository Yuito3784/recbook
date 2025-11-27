import os
import sys
import json
import logging
import io
from fastapi import FastAPI, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, ImageMessage, TextMessage, TextSendMessage,
    FlexSendMessage
)
import google.generativeai as genai
from PIL import Image
from mangum import Mangum

# --- 設定値 ---
# .envはVercel上では読まれないため、os.getenvで直接取ります
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
AMAZON_ASSOCIATE_TAG = os.getenv("AMAZON_ASSOCIATE_TAG", "dummy-tag-22")

# --- 初期化 ---
app = FastAPI()
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# Gemini設定（最新モデル）
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ヘルパー関数 ---
def analyze_book_image(image_bytes):
    try:
        image = Image.open(io.BytesIO(image_bytes))
        prompt = """
        あなたは「伝説の実演販売士」です。
        送られてきた本の画像の「タイトル」と「著者」を特定し、
        その本を今すぐ読みたくなるような、人間の欲望を刺激する紹介文を書いてください。
        
        必ず以下のJSONフォーマットのみを出力してください。Markdownのコードブロックは不要です。

        {
          "title": "正式なタイトル",
          "author": "著者名",
          "catchphrase": "20文字以内の衝撃的なキャッチコピー",
          "description": "読者が抱える悩みに寄り添い、この本がどう解決するかを訴求する文章（150文字程度）。最後は行動を促す言葉で。",
          "search_keyword": "Amazon検索用キーワード（タイトル 著者名）"
        }
        """
        response = model.generate_content([prompt, image])
        response_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(response_text)
    except Exception as e:
        logger.error(f"AI Error: {e}")
        return None

def create_flex_message(data):
    import urllib.parse
    query = urllib.parse.quote(data['search_keyword'])
    amazon_url = f"https://www.amazon.co.jp/s?k={query}&tag={AMAZON_ASSOCIATE_TAG}"
    
    bubble_json = {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "⚡ 激アツ書籍発見 ⚡",
                    "weight": "bold",
                    "color": "#FFD700",
                    "size": "sm",
                    "align": "center"
                }
            ],
            "backgroundColor": "#000000"
        },
        "hero": {
            "type": "image",
            "url": "https://cdn-icons-png.flaticon.com/512/3389/3389081.png",
            "size": "xs",
            "aspectRatio": "1:1",
            "aspectMode": "cover",
            "action": {"type": "uri", "uri": amazon_url}
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": data['title'],
                    "weight": "bold",
                    "size": "xl",
                    "wrap": True
                },
                {
                    "type": "text",
                    "text": data['catchphrase'],
                    "weight": "bold",
                    "size": "md",
                    "color": "#ff5555",
                    "wrap": True,
                    "margin": "md"
                },
                {
                    "type": "text",
                    "text": data['description'],
                    "size": "sm",
                    "color": "#555555",
                    "wrap": True,
                    "margin": "md"
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "height": "sm",
                    "color": "#FF9900",
                    "action": {"type": "uri", "label": "Amazonで今すぐ見る ➤", "uri": amazon_url}
                }
            ]
        }
    }
    return FlexSendMessage(alt_text=f"【要約】{data['title']}", contents=bubble_json)

# --- エンドポイント ---
# ★ファイル名が api/index.py なので、URLは /api/index になります
@app.post("/api/index")
async def callback(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    try:
        handler.handle(body.decode("utf-8"), signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="本の表紙写真を送ってください！📸")
    )

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    message_id = event.message.id
    message_content = line_bot_api.get_message_content(message_id)
    image_bytes = message_content.content
    
    book_data = analyze_book_image(image_bytes)
    if not book_data:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="解析失敗...もう一度試してください🙇‍♂️")
        )
        return

    flex_message = create_flex_message(book_data)
    line_bot_api.reply_message(event.reply_token, flex_message)

# ★重要：Vercel Serverless Functionのエントリーポイント
# Mangumを使って、FastAPIをVercel(Lambda)形式に変換します
handler = Mangum(app)