from fastapi import FastAPI, Request
import requests
import os

app = FastAPI()

# ดึง LINE Access Token จาก Environment Variable
LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")

# เก็บข้อมูลของผู้ใช้ระหว่างการคำนวณ
USER_SESSIONS = {}
MATERIAL_COSTS = {
    "ABS": 200, "PC": 250, "Nylon": 350, "PP": 70, "PE": 60,
    "PVC": 90, "PET": 100, "PMMA": 150, "POM": 350, "PU": 400
}

@app.post("/callback")
async def line_webhook(request: Request):
    try:
        payload = await request.json()
        print("📩 Received Payload:", payload)

        if "events" not in payload:
            print("⚠️ No events found in payload!")
            return {"status": "no events"}

        for event in payload["events"]:
            print(f"🔍 Event Received: {event}")  # ✅ Log Event ที่ได้รับจาก LINE

            if "message" not in event or "text" not in event["message"]:
                print("⚠️ Event ไม่มีข้อความที่สามารถประมวลผลได้")
                continue  # ป้องกัน KeyError

            user_id = event["source"]["userId"]
            reply_token = event["replyToken"]
            message_text = event["message"]["text"].strip()

            print(f"📩 User: {user_id} | Message: {message_text}")  # ✅ Debugging

            if message_text == "เริ่มคำนวณ":
                reply_message(reply_token, "✅ เริ่มคำนวณ กรุณาเลือกวัสดุ")
            else:
                reply_message(reply_token, f"📩 คุณส่ง: {message_text}")

        return {"status": "success"}

    except Exception as e:
        print(f"🔥 ERROR: {e}")
        return {"status": "error", "message": str(e)}



def start_calculation(reply_token, user_id):
    """ เริ่มกระบวนการคำนวณ """
    USER_SESSIONS[user_id] = {"step": 1}
    reply_message(reply_token, "กรุณาเลือกวัสดุที่ต้องการผลิต:\nABS, PC, Nylon, PP, PE, PVC, PET, PMMA, POM, PU")


def handle_response(reply_token, user_id, message_text):
    """ จัดการการตอบกลับของผู้ใช้ในแต่ละขั้นตอน """
    session = USER_SESSIONS.get(user_id, {})
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
            dimensions = list(map(float, message_text.lower().replace(' ', '').split('x')))
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
            calculate_and_show_result(reply_token, user_id)
        except ValueError:
            reply_message(reply_token, "❌ กรุณากรอกจำนวนที่ถูกต้อง เช่น 100")


def calculate_and_show_result(reply_token, user_id):
    """ คำนวณต้นทุนผลิตภัณฑ์ """
    session = USER_SESSIONS[user_id]
    material = session["material"]
    w, l, h = session["dimensions"]
    quantity = session["quantity"]

    volume = w * l * h
    density = 1.05
    weight_kg = (volume * density) / 1000
    total_cost = weight_kg * quantity * MATERIAL_COSTS[material]

    response_message = (
        f"✅ คำนวณต้นทุนสำเร็จ:\n"
        f"📌 วัสดุ: {material}\n"
        f"📌 ขนาด: {w}x{l}x{h} cm³\n"
        f"📌 ปริมาตร: {volume:.2f} cm³\📌 น้ำหนักโดยประมาณ: {weight_kg:.2f} kg\n"
        f"📌 จำนวน: {quantity} ชิ้น\n"
        f"📌 ต้นทุนรวม: {total_cost:,.2f} บาท\n\n"
        f"ต้องการขอใบเสนอราคาไหม?"
    )

    reply_message(reply_token, response_message)
    session["step"] = 4


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
    
    print(f"📤 Sending to LINE: {data}")  # ✅ Debugging Request ก่อนส่ง

    response = requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers=headers,
        json=data
    )
    
    print(f"📤 LINE Response Status: {response.status_code}")  # ✅ ตรวจสอบ Response Code
    print(f"📤 LINE Response Body: {response.text}")  # ✅ ดู Response Body

    if response.status_code != 200:
        print(f"❌ LINE API Error: {response.text}")  # ✅ ถ้ามี Error ให้พิมพ์ออกมา


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

# ✅ ตรวจสอบว่า LINE_ACCESS_TOKEN ถูกต้องหรือไม่
LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")
if not LINE_ACCESS_TOKEN:
    raise ValueError("❌ LINE_ACCESS_TOKEN is missing! Please set it in Cloud Run.")
else:
    print(f"✅ LINE_ACCESS_TOKEN is set! Length: {len(LINE_ACCESS_TOKEN)} characters")

