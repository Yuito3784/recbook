import os
import sys
import json
import logging
import io
import random
from fastapi import FastAPI, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, ImageMessage, TextMessage, TextSendMessage,
    FlexSendMessage, StickerMessage # スタンプ対応を追加
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
        # ... (中略: 前回と同じ戦略ロジック) ...
        strategies = [
            {"angle": "【A：裏ロジック】", "instruction": "常識の逆を行く成功法則として紹介する。"},
            {"angle": "【B：機会損失】", "instruction": "この知識がないとどれだけ損するかを強調する。"},
            {"angle": "【C：最短ルート】", "instruction": "遠回りをやめて、この本でショートカットしろと促す。"},
            {"angle": "【D：本質の暴露】", "instruction": "小手先のテクニックではなく、本質はここにあると断言する。"},
            {"angle": "【E：権威性】", "instruction": "トップ層はみんなこれを実践している、という比較をする。"}
        ]
        selected_strategy = random.choice(strategies)

        prompt = f"""
        あなたは「本の価値を最大化して伝えるプロの書評家」です。
        送られてきた本の表紙から内容を特定し、読者が「この具体的な知識が欲しい！」と強く思うような紹介文を作成してください。
        
        【選ばれた戦略】: {selected_strategy['angle']}
        {selected_strategy['instruction']}

        【出力ルール】
        1. 本の中に書かれている「具体的なキーワード」や「ノウハウ」を必ず抽出する。
        2. ただし、すべてを要約するのではなく「ここを知れば人生が変わる」というポイントを3つ抜き出す。
        3. 抽象的な言葉（すごい、やばい）は禁止。具体的な用語を使うこと。

        必ず以下のJSONフォーマットのみを出力してください。
        {{
          "title": "正式なタイトル",
          "author": "著者名",
          "catchphrase": "20文字以内の、戦略に基づいた鋭いキャッチコピー",
          "key_points": [
            "本書で学べる具体的なノウハウ1（例：〇〇の法則とは）",
            "本書で学べる具体的なノウハウ2（例：1日5分でできる〇〇）",
            "本書で学べる具体的なノウハウ3（例：失敗しないための〇〇思考）"
          ],
          "description": "上記3つのポイントを踏まえ、「なぜ今この本を読む必要があるのか」を論理的に説く文章（120文字程度）。最後は購入リンクへ誘導する言葉で締める。",
          "search_keyword": "Amazon検索用キーワード（タイトル 著者名）"
        }}
        """
        response = model.generate_content([prompt, image])
        response_text = response.text.replace("```json", "").replace("```", "").strip()
        if "{" not in response_text: raise Exception("Not JSON")
        return json.loads(response_text)
    except Exception as e:
        logger.error(f"AI Error: {e}")
        return None

def create_flex_message(data):
    # ... (中略: 前回と同じFlex Message作成ロジック) ...
    import urllib.parse
    query = urllib.parse.quote(data['search_keyword'])
    amazon_url = f"https://www.amazon.co.jp/s?k={query}&tag={AMAZON_ASSOCIATE_TAG}"
    
    points_contents = []
    for point in data['key_points']:
        points_contents.append({
            "type": "box",
            "layout": "baseline",
            "spacing": "sm",
            "contents": [
                { "type": "text", "text": "✔", "color": "#1A237E", "size": "sm", "flex": 1 },
                { "type": "text", "text": point, "color": "#555555", "size": "sm", "flex": 9, "wrap": True }
            ],
            "margin": "md"
        })

    bubble_json = {
        "type": "bubble",
        "header": { 
            "type": "box", "layout": "vertical", "backgroundColor": "#1A237E",
            "contents": [
                { "type": "text", "text": "THE SOLUTION", "weight": "bold", "color": "#FFFFFF", "size": "xxs", "align": "center", "letterSpacing": "2px" },
                { "type": "text", "text": "本書で手に入る武器", "weight": "bold", "color": "#FFFFFF", "size": "sm", "align": "center", "margin": "xs" }
            ]
        },
        "hero": { 
            "type": "image", "url": "https://cdn-icons-png.flaticon.com/512/3389/3389081.png", 
            "size": "xs", "aspectRatio": "1:1", "aspectMode": "cover", 
            "action": {"type": "uri", "uri": amazon_url}, "margin": "md"
        },
        "body": { 
            "type": "box", "layout": "vertical", 
            "contents": [
                { "type": "text", "text": data['title'], "weight": "bold", "size": "lg", "wrap": True, "align": "center", "color": "#1A237E" },
                { "type": "separator", "margin": "lg", "color": "#EEEEEE" },
                { "type": "text", "text": f"“ {data['catchphrase']} ”", "weight": "bold", "size": "md", "color": "#333333", "wrap": True, "margin": "lg", "align": "center", "style": "italic" },
                { "type": "box", "layout": "vertical", "margin": "lg", "contents": points_contents },
                { "type": "separator", "margin": "lg", "color": "#EEEEEE" },
                { "type": "text", "text": data['description'], "size": "xs", "color": "#777777", "wrap": True, "margin": "lg", "lineSpacing": "4px" }
            ] 
        },
        "footer": { 
            "type": "box", "layout": "vertical", "spacing": "sm", 
            "contents": [
                { "type": "button", "style": "primary", "height": "sm", "color": "#1A237E", "action": {"type": "uri", "label": "Amazonで詳細を見る ➤", "uri": amazon_url} }
            ] 
        }
    }
    return FlexSendMessage(alt_text=f"【要約】{data['title']}", contents=bubble_json)

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

# ★★★ 改善：テキストが送られた時の処理 ★★★
@line_handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    # ユーザーが何を言っても、使い方をガイドする
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="【使い方】\n\n気になっている本の「表紙」の写真を1枚送ってください📸\n\nAIがその本を読むべき理由と、具体的な学びを3つ抽出してプレゼンします。")
    )

# ★★★ 改善：スタンプが送られた時もガイドする ★★★
@line_handler.add(MessageEvent, message=StickerMessage)
def handle_sticker_message(event):
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="スタンプありがとうございます！\n本の写真を送ると、私が全力で解説しますよ📚")
    )

@line_handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    message_id = event.message.id
    message_content = line_bot_api.get_message_content(message_id)
    image_bytes = message_content.content
    
    # ユーザーに「解析中...」と伝える（簡易的）
    # ※Pushメッセージは有料になるリスクがあるので、ReplyTokenを使う必要があるが
    # LINEの仕様上、1つのReplyTokenで1回しか返信できない。
    # なので、ここはあえて「待たせる」か、もしくはLoading Animationを使う（高度な実装）。
    # 今回はシンプルに、解析失敗時だけ丁寧に返すようにします。

    book_data = analyze_book_image(image_bytes)
    
    if not book_data:
        # ★★★ 改善：解析失敗時のメッセージを丁寧に ★★★
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="すみません、うまく読み取れませんでした...💦\n\n・光が反射していないか\n・ブレていないか\n\nを確認して、もう一度正面から撮影してください🙇‍♂️")
        )
        return

    flex_message = create_flex_message(book_data)
    line_bot_api.reply_message(event.reply_token, flex_message)

app = ASGIMiddleware(_app)