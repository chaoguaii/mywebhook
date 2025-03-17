from fastapi import FastAPI, Request
import os
import requests
from google.cloud import bigquery
from datetime import datetime

# ✅ ตั้งค่า Service Account JSON
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "C:/Users/Guai/Downloads/line-bot-webhook-453815-4a536467597b.json"

app = FastAPI()

# ✅ โหลด Environment Variable
LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")
if not LINE_ACCESS_TOKEN:
    raise ValueError("❌ LINE_ACCESS_TOKEN is missing! Please set it in Cloud Run.")

# ✅ ตั้งค่า BigQuery
bq_client = bigquery.Client()
BQ_TABLE = "line-bot-webhook-453815.cost_calculations.orders"

# ✅ ค่าใช้จ่ายของวัสดุ (บาท/kg)
MATERIAL_COSTS = {
    "ABS": 200, "PC": 250, "Nylon": 350, "PP": 70, "PE": 60,
    "PVC": 90, "PET": 100, "PMMA": 150, "POM": 350, "PU": 400
}

# ✅ เก็บข้อมูลของผู้ใช้ระหว่างการคำนวณ
USER_SESSIONS = {}

@app.get("/")
def read_root():
    return {"message": "Hello from Cloud Run"}

@app.post("/callback")
async def line_webhook(request: Request):
    try:
        payload = await request.json()
        print("📩 Received Payload:", payload)

        if "events" not in payload:
            print("❌ No events found in payload")
            return {"status": "no events"}, 200  # ส่งคืน status code 200

        for event in payload["events"]:
            if "message" not in event or "text" not in event["message"]:
                print("❌ No message found in event")
                continue  

            user_id = event["source"]["userId"]
            reply_token = event["replyToken"]
            message_text = event["message"]["text"].strip()

            print(f"📩 User: {user_id} | Message: {message_text}")

            if message_text == "เริ่มคำนวณ":
                print("✅ Calling start_calculation()")
                start_calculation(reply_token, user_id)
            else:
                handle_response(reply_token, user_id, message_text)

        return {"status": "success"}, 200  # ส่งคืน status code 200

    except Exception as e:
        print(f"🔥 ERROR in line_webhook(): {e}")
        return {"status": "error", "message": str(e)}, 200  # ส่งคืน status code 200

def start_calculation(reply_token, user_id):
    """ เริ่มกระบวนการคำนวณ """
    USER_SESSIONS[user_id] = {"step": 1}
    print(f"✅ User {user_id} started calculation.")
    reply_message(reply_token, "กรุณาเลือกวัสดุที่ต้องการผลิต:\nABS, PC, Nylon, PP, PE, PVC, PET, PMMA, POM, PU")
    print("📩 Reply message sent to user")

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
            if quantity <= 0:
                raise ValueError
            session["quantity"] = quantity
            session["step"] = 4
            reply_message(reply_token, "❓ คุณต้องการยืนยันใบเสนอราคาหรือไม่? (พิมพ์ 'ใช่' เพื่อยืนยัน)")
        except ValueError:
            reply_message(reply_token, "❌ กรุณากรอกจำนวนที่ถูกต้อง เช่น 100")

    elif step == 4:
        if message_text in ["ใช่", "yes"]:
            material = session["material"]
            w, l, h = session["dimensions"]
            quantity = session["quantity"]
            volume = w * l * h
            density = 1.05
            weight_kg = (volume * density) / 1000
            total_cost = weight_kg * quantity * MATERIAL_COSTS.get(material, 0)

            print(f"📌 Saving data to BigQuery: {material}, {w}x{l}x{h}, {volume}, {weight_kg}, {quantity}, {total_cost}")
            save_order_to_bigquery(user_id, material, f"{w}x{l}x{h}", volume, weight_kg, quantity, total_cost)

            reply_message(reply_token, "✅ ข้อมูลของคุณถูกบันทึกเรียบร้อยแล้ว! ขอบคุณที่ใช้บริการ 😊")
            del USER_SESSIONS[user_id]  
        else:
            reply_message(reply_token, "❌ โปรดพิมพ์ 'ใช่' หากต้องการขอใบเสนอราคา")

def save_order_to_bigquery(user_id, material, size, volume, weight_kg, quantity, total_cost):
    """ บันทึกคำสั่งซื้อไปยัง BigQuery """
    
    row = [{
        "user_id": user_id,
        "material": material,
        "size": size,
        "volume": float(volume),
        "weight_kg": float(weight_kg),
        "quantity": int(quantity),
        "total_cost": float(total_cost),
        "timestamp": datetime.utcnow().isoformat()
    }]
    
    print(f"📤 Preparing to insert data into BigQuery: {row}")

    try:
        errors = bq_client.insert_rows_json(BQ_TABLE, row)
        if errors:
            print(f"❌ BigQuery Insert Error: {errors}")
        else:
            print("✅ Data inserted into BigQuery successfully.")
    except Exception as e:
        print(f"🔥 ERROR inserting into BigQuery: {e}")

def reply_message(reply_token, text):
    """ ส่งข้อความกลับไปที่ LINE """
    headers = {
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}]
    }
    response = requests.post("https://api.line.me/v2/bot/message/reply", headers=headers, json=data)
    print(f"📤 LINE Response Status: {response.status_code}")
    print(f"📤 LINE Response Body: {response.text}")
    if response.status_code != 200:
        print(f"❌ LINE API Error: {response.text}")
