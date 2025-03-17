from fastapi import FastAPI, Request
import os
import requests
from google.cloud import bigquery
from datetime import datetime
import uvicorn

# ✅ ตั้งค่า Service Account JSON
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "C:/Users/Guai/Downloads/line-bot-webhook-453815-4a536467597b.json"

app = FastAPI()

# ✅ โหลด Environment Variable
LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")
BQ_TABLE_ORDERS = "line-bot-webhook-453815.cost_calculations.orders"
BQ_TABLE_QUOTES = "line-bot-webhook-453815.cost_calculations.quotation_requests"

# ✅ ค่าใช้จ่ายของวัสดุ (บาท/kg)
MATERIAL_COSTS = {
    "ABS": 200, "PC": 250, "Nylon": 350, "PP": 70, "PE": 60,
    "PVC": 90, "PET": 100, "PMMA": 150, "POM": 350, "PU": 400
}

# ✅ เก็บข้อมูลของผู้ใช้ระหว่างการคำนวณ
USER_SESSIONS = {}

@app.get("/")
def read_root():
    return {"message": "LINE Webhook is running"}

@app.post("/callback")
async def line_webhook(request: Request):
    """ รับ Webhook Event จาก LINE """
    payload = await request.json()
    print("📩 Received Payload:", payload)

    for event in payload["events"]:
        user_id = event["source"]["userId"]
        reply_token = event["replyToken"]
        message_text = event["message"]["text"].strip()

        print(f"📩 User: {user_id} | Message: {message_text}")

        if message_text == "เริ่มคำนวณ":
            start_calculation(reply_token, user_id)
        elif message_text == "ใช่":
            request_quotation(reply_token, user_id)
        elif message_text == "ขอใบเสนอราคา":
            request_customer_info(reply_token, user_id)
        else:
            handle_response(reply_token, user_id, message_text)

    return {"status": "success"}

def start_calculation(reply_token, user_id):
    """ เริ่มกระบวนการคำนวณ """
    USER_SESSIONS[user_id] = {"step": 1}
    reply_message(reply_token, "กรุณาเลือกวัสดุที่ต้องการผลิต:\nABS, PC, Nylon, PP, PE, PVC, PET, PMMA, POM, PU")

def handle_response(reply_token, user_id, message_text):
    """ จัดการการตอบกลับของผู้ใช้ในแต่ละขั้นตอน """
    if user_id not in USER_SESSIONS:
        reply_message(reply_token, "⚠️ กรุณาเริ่มคำนวณใหม่โดยพิมพ์ 'เริ่มคำนวณ'")
        return

    session = USER_SESSIONS[user_id]
    step = session.get("step", 0)

    if step == 1:
        material = message_text.upper()
        if material not in MATERIAL_COSTS:
            reply_message(reply_token, "❌ วัสดุไม่ถูกต้อง กรุณาเลือกจากรายการที่ให้ไว้")
            return
        session["material"] = material
        session["step"] = 2
        reply_message(reply_token, "กรุณากรอกขนาดชิ้นงาน (กว้างxยาวxสูง) cm เช่น 10.5x15.5x5.5")

    elif step == 2:
        try:
            dimensions = list(map(float, message_text.replace(' ', '').split('x')))
            if len(dimensions) != 3:
                raise ValueError
            session["dimensions"] = dimensions
            session["step"] = 3
            reply_message(reply_token, "กรุณากรอกจำนวนที่ต้องการผลิต (ตัวเลข)")
        except ValueError:
            reply_message(reply_token, "❌ รูปแบบขนาดไม่ถูกต้อง กรุณากรอกใหม่ เช่น 10.5x15.5x5.5")

    elif step == 3:
        try:
            quantity = int(message_text)
            session["quantity"] = quantity

            # ✅ คำนวณราคา
            material = session["material"]
            w, l, h = session["dimensions"]
            volume = w * l * h
            density = 1.05
            weight_kg = (volume * density) / 1000
            total_cost = weight_kg * quantity * MATERIAL_COSTS.get(material, 0)

            session["cost"] = total_cost
            session["step"] = 4

            reply_message(reply_token, f"""✅ คำนวณต้นทุนสำเร็จ:
📌 วัสดุ: {material}
📌 ขนาด: {w}x{l}x{h} cm³
📌 ปริมาตร: {volume:.2f} cm³
📌 น้ำหนักโดยประมาณ: {weight_kg:.2f} kg
📌 จำนวน: {quantity} ชิ้น
📌 ต้นทุนรวม: {total_cost:,.2f} บาท

ต้องการขอใบเสนอราคาไหม? (พิมพ์ 'ขอใบเสนอราคา' เพื่อยืนยัน)
""")
        except ValueError:
            reply_message(reply_token, "❌ กรุณากรอกจำนวนที่ถูกต้อง เช่น 100")

def request_quotation(reply_token, user_id):
    """ บันทึกคำสั่งซื้อไปยัง BigQuery และขอข้อมูลลูกค้า """
    session = USER_SESSIONS.get(user_id, {})
    if not session:
        reply_message(reply_token, "⚠️ ไม่มีข้อมูล กรุณาเริ่มคำนวณใหม่")
        return

    session["step"] = 5
    reply_message(reply_token, "กรุณากรอกข้อมูลของคุณ (ชื่อ, เบอร์โทร, Email)")

def request_customer_info(reply_token, user_id):
    """ ขอข้อมูลลูกค้าเพื่อบันทึกใบเสนอราคา """
    session = USER_SESSIONS.get(user_id, {})
    if not session:
        reply_message(reply_token, "⚠️ ไม่มีข้อมูล กรุณาเริ่มคำนวณใหม่")
        return

    session["step"] = 6
    reply_message(reply_token, "กรุณากรอกข้อมูลของคุณ (ชื่อ, เบอร์โทร, Email)")

def save_order_to_bigquery(user_id, material, size, volume, weight_kg, quantity, total_cost, name, phone, email):
    """ บันทึกข้อมูลลง BigQuery """
    row = [{
        "user_id": user_id,
        "material": material,
        "size": size,
        "volume": float(volume),
        "weight_kg": float(weight_kg),
        "quantity": int(quantity),
        "total_cost": float(total_cost),
        "name": name,
        "phone": phone,
        "email": email,
        "timestamp": datetime.utcnow().isoformat()
    }]

    try:
        bq_client = bigquery.Client()
        bq_client.insert_rows_json(BQ_TABLE_QUOTES, row)
        return True
    except Exception as e:
        print(f"🔥 ERROR inserting into BigQuery: {e}")
        return False

def reply_message(reply_token, text):
    """ ส่งข้อความกลับไปที่ LINE """
    headers = {
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {"replyToken": reply_token, "messages": [{"type": "text", "text": text}]}
    requests.post("https://api.line.me/v2/bot/message/reply", headers=headers, json=data)

if __name__ == "__main__":
    PORT = int(os.getenv("PORT", 8080))  # ใช้ PORT ที่ Cloud Run กำหนด
    uvicorn.run(app, host="0.0.0.0", port=PORT)