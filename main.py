from fastapi import FastAPI, Request
import requests
import os

app = FastAPI()

LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")

USER_SESSIONS = {}
MATERIAL_COSTS = {
    "ABS": 200, "PC": 250, "Nylon": 350, "PP": 70, "PE": 60,
    "PVC": 90, "PET": 100, "PMMA": 150, "POM": 350, "PU": 400
}

@app.post("/callback")
async def line_webhook(request: Request):
    payload = await request.json()

    for event in payload["events"]:
        user_id = event["source"]["userId"]
        message_text = event["message"]["text"].strip()

        if message_text == "เริ่มคำนวณ":
            start_calculation(user_id)
        else:
            handle_response(user_id, message_text)

    return {"status": "success"}

def start_calculation(user_id):
    USER_SESSIONS[user_id] = {"step": 1}
    send_message(user_id, "กรุณาเลือกวัสดุที่ต้องการผลิต:\nABS, PC, Nylon, PP, PE, PVC, PET, PMMA, POM, PU")

def handle_response(user_id, message_text):
    session = USER_SESSIONS.get(user_id, {})
    step = session.get("step", 0)

    if step == 1:
        material = message_text.upper()
        if material not in MATERIAL_COSTS:
            send_message(user_id, "❌ วัสดุไม่ถูกต้อง กรุณาเลือกจากรายการที่ให้ไว้")
            return
        session["material"] = material
        session["step"] = 2
        send_message(user_id, "กรุณากรอกขนาดชิ้นงาน (กว้างxยาวxสูง) cm เช่น 10.5x15.5x5.5")

    elif step == 2:
        try:
            dimensions = list(map(float, message_text.lower().replace(' ', '').split('x')))
            if len(dimensions) != 3:
                raise ValueError
            session["dimensions"] = dimensions
            session["step"] = 3
            send_message(user_id, "กรุณากรอกจำนวนที่ต้องการผลิต (ตัวเลข)")
        except ValueError:
            send_message(user_id, "❌ รูปแบบขนาดไม่ถูกต้อง กรุณากรอกใหม่ เช่น 10.5x15.5x5.5")

    elif step == 3:
        try:
            quantity = int(message_text)
            if quantity <= 0:
                raise ValueError
            session["quantity"] = quantity
            calculate_and_show_result(user_id)
        except ValueError:
            send_message(user_id, "❌ กรุณากรอกจำนวนที่ถูกต้อง เช่น 100")

def calculate_and_show_result(user_id):
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
        f"📌 ปริมาตร: {volume:.2f} cm³\n"
        f"📌 น้ำหนักโดยประมาณ: {weight_kg:.2f} kg\n"
        f"📌 จำนวน: {quantity} ชิ้น\n"
        f"📌 ต้นทุนรวม: {total_cost:,.2f} บาท\n\n"
        f"ต้องการขอใบเสนอราคาไหม"
    )

    send_message(user_id, response_message)
    session["step"] = 4

def send_message(user_id, text):
    headers = {
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json={
        "to": user_id,
        "messages": [{"type": "text", "text": text}]
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
