import os
import uuid
from datetime import datetime
from fastapi import FastAPI, Request
from google.cloud import bigquery
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from linebot.exceptions import InvalidSignatureError

# ตั้งค่า Google Cloud Project
PROJECT_ID = "line-bot-webhook-453815"
DATASET_ID = "mold_plastic_db"

client = bigquery.Client(project=PROJECT_ID)

# ตั้งค่า LINE Messaging API (อ่านจาก Environment Variables)
LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")
LINE_SECRET = os.getenv("LINE_SECRET")

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)

app = FastAPI()

# เก็บข้อมูลผู้ใช้ชั่วคราว
user_data = {}

# ฟังก์ชันดึงราคาสินค้าจาก BigQuery
def get_price(product_type, size_range):
    query = f"""
        SELECT base_price FROM `{PROJECT_ID}.{DATASET_ID}.pricing_data`
        WHERE product_type = '{product_type}' AND size_range = '{size_range}'
    """
    result = client.query(query).result()
    for row in result:
        return row.base_price
    return None

@app.post("/callback")
async def callback(request: Request):
    signature = request.headers["X-Line-Signature"]
    body = await request.body()

    try:
        handler.handle(body.decode(), signature)
    except InvalidSignatureError:
        return {"error": "Invalid Signature"}

    return {"message": "OK"}

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip().lower()

    if text.startswith("ขอราคาสินค้า"):
        user_data[user_id] = {}
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณาระบุชนิดพลาสติก (เช่น ABS, PP, PET)"))

    elif text in ["abs", "pp", "pet"]:
        if user_id in user_data:
            user_data[user_id]["product_type"] = text.upper()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณาระบุขนาดสินค้า (เช่น 10x10 cm, 20x20 cm)"))

    elif "cm" in text:
        if user_id in user_data and "product_type" in user_data[user_id]:
            product_type = user_data[user_id]["product_type"]
            size_range = text
            price = get_price(product_type, size_range)

            if price:
                reply_text = f"💰 ราคาสำหรับ {product_type} ({size_range}) คือ {price} บาท/ชิ้น"
            else:
                reply_text = "❌ ไม่พบข้อมูล กรุณาลองอีกครั้ง"
            
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
            del user_data[user_id]  # ล้างข้อมูลของผู้ใช้หลังจากได้ราคาแล้ว

@app.get("/")
async def root():
    return {"message": "Hello, FastAPI is running!"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

