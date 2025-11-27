import os
import sys
import json
import logging
import io
import random  # ★ランダム機能を追加
from fastapi import FastAPI, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, ImageMessage, TextMessage, TextSendMessage,
    FlexSendMessage
)
import google.generativeai as genai
from PIL import Image
from dotenv import load_dotenv
from a2wsgi import ASGIMiddleware

load_dotenv()

# --- 設定値 ---
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
AMAZON_ASSOCIATE_TAG = os.getenv("AMAZON_ASSOCIATE_TAG", "dummy-tag-22")

# --- 初期化 ---
_app = FastAPI()
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
line_handler = WebhookHandler(LINE_CHANNEL_SECRET)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 関数 ---
def analyze_book_image(image_bytes):
    try:
        image = Image.open(io.BytesIO(image_bytes))

        # ★★★ ここが「AI感」を消すための新機能 ★★★
        # 5つの異なる「攻め方（アングル）」を用意し、毎回ランダムに1つ選びます。
        
        strategies = [
            {
                "angle": "【Aパターン：盲点の指摘】",
                "instruction": """
                ・読者が信じている「常識」や「思い込み」を真っ向から否定することから始めてください。
                ・「良かれと思ってやっていることが、実は逆効果だとしたら？」という切り口で攻める。
                ・解決策はこの本にしか書かれていない「裏のロジック」であることを匂わせる。
                """
            },
            {
                "angle": "【Bパターン：未来の損失暗示】",
                "instruction": """
                ・「このまま今のやり方を続けるとどうなるか」という最悪の未来を静かに、しかし残酷に想像させる。
                ・「能力不足ではなく、道具（知識）を持っていないだけ」と逃げ道を用意し、救いとしてこの本を提示する。
                ・焦燥感を煽るトーンで書く。
                """
            },
            {
                "angle": "【Cパターン：秘密の共有】",
                "instruction": """
                ・「実は、一部の成功者だけが知っている事実があります」という、秘密を打ち明けるトーンで書く。
                ・核心部分はあえて隠し（寸止め）、「知りたければ中身を見るしかない」という飢餓状態を作る。
                ・ささやくような、静かで重みのある文章にする。
                """
            },
            {
                "angle": "【Dパターン：他者との比較】",
                "instruction": """
                ・「なぜあの人はうまくいっていて、あなたは苦労しているのか？」という劣等感を刺激する。
                ・その決定的な差（ボトルネック）が、この本に書かれている「たった一つのこと」であると断言する。
                ・悔しさをバネに行動させるトーン。
                """
            },
            {
                "angle": "【Eパターン：投資対効果の提示】",
                "instruction": """
                ・この本の価格（千数百円）と、それによって得られるリターン（一生モノのスキル）の非対称性を強調する。
                ・「ランチ一回分で人生が変わるとしたら、安い投資ですよね？」という理詰めのアプローチ。
                ・冷静かつ論理的に、買わない理由を潰す。
                """
            }
        ]

        # ランダムに1つ選ぶ
        selected_strategy = random.choice(strategies)

        prompt = f"""
        あなたは「人間の行動心理を熟知したプロのコピーライター」です。
        送られてきた本の表紙から内容を特定し、以下の【選ばれた戦略】に基づいて紹介文を作成してください。
        
        【今回選ばれた戦略】: {selected_strategy['angle']}
        {selected_strategy['instruction']}

        【共通ルール】
        1. 冒頭で「読む理由（ベネフィット）」を明確に示す。
        2. 核心（答え）は絶対に書かない。「寸止め」して続きを気にさせる。
        3. 「〜です」「〜ます」調の単調な説明文は禁止。リズム感のある、人間味のある文章にする。
        4. 毎回同じような定型文（「この本は〜」）から始めないこと。

        必ず以下のJSONフォーマットのみを出力してください。
        {{
          "title": "正式なタイトル",
          "author": "著者名",
          "catchphrase": "20文字以内の、選ばれた戦略に基づいた鋭いキャッチコピー",
          "description": "選ばれた戦略のトーン＆マナーを忠実に守った文章（150文字程度）。AIっぽさを消し、人間が語りかけているような生々しさを出す。",
          "search_keyword": "Amazon検索用キーワード（タイトル 著者名）"
        }}
        """
        
        response = model.generate_content([prompt, image])
        response_text = response.text.replace("```json", "").replace("```", "").strip()
        # JSONパース前に不要な文字がないか確認・掃除
        if "{" not in response_text: raise Exception("Not JSON")
        
        return json.loads(response_text)
    except Exception as e:
        logger.error(f"AI Error: {e}")
        return None

def create_flex_message(data):
    import urllib.parse
    query = urllib.parse.quote(data['search_keyword'])
    amazon_url = f"https://www.amazon.co.jp/s?k={query}&tag={AMAZON_ASSOCIATE_TAG}"
    
    # デザイン：知的なネイビー
    bubble_json = {
        "type": "bubble",
        "header": { 
            "type": "box", 
            "layout": "vertical", 
            "contents": [
                { "type": "text", "text": "THE SOLUTION", "weight": "bold", "color": "#FFFFFF", "size": "xxs", "align": "center", "letterSpacing": "2px" },
                { "type": "text", "text": "現状打破の1冊", "weight": "bold", "color": "#FFFFFF", "size": "sm", "align": "center", "margin": "xs" }
            ], 
            "backgroundColor": "#1A237E"
        },
        "hero": { 
            "type": "image", 
            "url": "https://cdn-icons-png.flaticon.com/512/3389/3389081.png", 
            "size": "xs", 
            "aspectRatio": "1:1", 
            "aspectMode": "cover", 
            "action": {"type": "uri", "uri": amazon_url},
            "margin": "md"
        },
        "body": { 
            "type": "box", 
            "layout": "vertical", 
            "contents": [
                { "type": "text", "text": data['title'], "weight": "bold", "size": "lg", "wrap": True, "align": "center", "color": "#1A237E" },
                { "type": "separator", "margin": "lg", "color": "#EEEEEE" },
                { "type": "text", "text": f"“ {data['catchphrase']} ”", "weight": "bold", "size": "md", "color": "#333333", "wrap": True, "margin": "lg", "align": "center", "style": "italic" },
                { "type": "text", "text": data['description'], "size": "sm", "color": "#555555", "wrap": True, "margin": "lg", "lineSpacing": "6px" }
            ] 
        },
        "footer": { 
            "type": "box", 
            "layout": "vertical", 
            "spacing": "sm", 
            "contents": [
                { "type": "button", "style": "primary", "height": "sm", "color": "#1A237E", "action": {"type": "uri", "label": "答えを確認する ➤", "uri": amazon_url} },
                { "type": "text", "text": "※Amazon詳細ページへ移動します", "size": "xxs", "color": "#aaaaaa", "align": "center", "margin": "md" }
            ] 
        }
    }
    return FlexSendMessage(alt_text=f"【提案】{data['title']}", contents=bubble_json)

# --- エンドポイント ---
@_app.post("/api/index")
async def callback(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    try:
        line_handler.handle(body.decode("utf-8"), signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    return "OK"

@line_handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="本の表紙を送ってください。\nその「課題」の正体を分析します。"))

@line_handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    message_id = event.message.id
    message_content = line_bot_api.get_message_content(message_id)
    image_bytes = message_content.content
    book_data = analyze_book_image(image_bytes)
    if not book_data:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="解析できませんでした。別の角度から撮影してください。"))
        return
    flex_message = create_flex_message(book_data)
    line_bot_api.reply_message(event.reply_token, flex_message)

app = ASGIMiddleware(_app)