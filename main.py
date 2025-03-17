import os
import uuid
from datetime import datetime
from google.cloud import bigquery
from fastapi import FastAPI, Request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from linebot.exceptions import InvalidSignatureError
from linebot.models import FollowEvent

# ตั้งค่า Google Cloud Project
PROJECT_ID = "your_project_id"
DATASET_ID = "mold_plastic_db"

client = bigquery.Client(project=PROJECT_ID)

# ตั้งค่า LINE Messaging API
LINE_ACCESS_TOKEN = "your_line_channel_access_token"
LINE_SECRET = "your_line_channel_secret"

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)

app = FastAPI()

# เก็บข้อมูลลูกค้าชั่วคราว
customer_data = {}

# ฟังก์ชันดึงราคาสินค้าจาก BigQuery
def calculate_price(product_type, dimensions, quantity):
    query = f"""
        SELECT base_price FROM `{PROJECT_ID}.{DATASET_ID}.pricing_data`
        WHERE product_type = '{product_type}' AND size_range = '{dimensions}'
    """
    result = client.query(query).result()
    for row in result:
        return row.base_price * quantity
    return None

# ฟังก์ชันบันทึกใบเสนอราคา
def save_quotation_request(user_id, customer_name, product_type, dimensions, quantity):
    quotation_id = str(uuid.uuid4())
    estimated_price = calculate_price(product_type, dimensions, quantity)

    if estimated_price is None:
        return None

    data = [
        {
            "quotation_id": quotation_id,
            "customer_name": customer_name,
            "product_type": product_type,
            "dimensions": dimensions,
            "quantity": quantity,
            "estimated_price": estimated_price,
            "request_date": datetime.utcnow(),
        }
    ]

    table_ref = client.dataset(DATASET_ID).table("quotation_requests")
    client.insert_rows_json(table_ref, data)
    return quotation_id, estimated_price

# ฟังก์ชันตรวจสอบสถานะคำสั่งซื้อ
def check_order_status(order_id):
    query = f"""
        SELECT order_status, order_date FROM `{PROJECT_ID}.{DATASET_ID}.customer_orders`
        WHERE order_id = '{order_id}'
    """
    result = client.query(query).result()
    for row in result:
        return f"📦 คำสั่งซื้อ {order_id} สถานะ: {row.order_status} (วันที่: {row.order_date})"
    return "❌ ไม่พบคำสั่งซื้อ"

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
    text = event.message.text.strip()

    if text.lower().startswith("ขอราคาสินค้า"):
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณาระบุชนิดพลาสติก (เช่น ABS, PP, PET)"))
        customer_data[user_id] = {}

    elif user_id in customer_data:
        if "product_type" not in customer_data[user_id]:
            customer_data[user_id]["product_type"] = text
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณาระบุขนาด (เช่น 10x10 cm, 20x20 cm)"))

        elif "dimensions" not in customer_data[user_id]:
            customer_data[user_id]["dimensions"] = text
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณาระบุจำนวนที่ต้องการ"))

        elif "quantity" not in customer_data[user_id]:
            customer_data[user_id]["quantity"] = int(text)
            data = customer_data[user_id]
            estimated_price = calculate_price(data["product_type"], data["dimensions"], data["quantity"])

            if estimated_price:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"💰 ราคาประเมิน: {estimated_price:.2f} บาท\nต้องการขอใบเสนอราคาหรือไม่? (พิมพ์: 'ขอใบเสนอราคา')"))
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ ไม่พบข้อมูลสินค้า กรุณาตรวจสอบอีกครั้ง"))
                del customer_data[user_id]

    elif text.lower().startswith("ขอใบเสนอราคา"):
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณาพิมพ์ชื่อของคุณ"))

    elif "customer_name" not in customer_data[user_id]:
        customer_data[user_id]["customer_name"] = text
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณาพิมพ์อีเมลของคุณ"))

    elif "customer_email" not in customer_data[user_id]:
        customer_data[user_id]["customer_email"] = text
        data = customer_data[user_id]
        quotation_id, estimated_price = save_quotation_request(
            user_id, data["customer_name"], data["product_type"], data["dimensions"], data["quantity"]
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"✅ ขอใบเสนอราคาเรียบร้อย!\nหมายเลขใบเสนอราคา: {quotation_id}\nราคาประเมิน: {estimated_price:.2f} บาท"))
        del customer_data[user_id]

    elif text.lower().startswith("ติดตามคำสั่งซื้อ"):
        order_id = text.split(" ")[1]
        status = check_order_status(order_id)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=status))

@handler.add(FollowEvent)
def handle_follow(event):
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="👋 ยินดีต้อนรับ! พิมพ์ 'ขอราคาสินค้า' เพื่อเริ่มต้น"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
