from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# 🔹 ใช้ Environment Variables
LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")
GAS_URL = os.getenv("GAS_URL")  # ใช้เชื่อม Google Sheets ถ้าต้องการบันทึกข้อมูล

# 🔹 Dictionary เก็บข้อมูลชั่วคราว
USER_SESSIONS = {}

# 🔹 ตารางราคาพลาสติก (หน่วย: บาท/kg)
MATERIAL_COSTS = {
    "ABS": 200,
    "PC": 250,
    "Nylon": 350,
    "PP": 70,
    "PE": 60,
    "PVC": 90,
    "PET": 100,
    "PMMA": 150,
    "POM": 350,
    "PU": 400
}

@app.route("/", methods=["GET"])
def home():
    """ ตรวจสอบว่าเซิร์ฟเวอร์ทำงาน """
    return "LINE Webhook is running", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    """ รับ Webhook Event จาก LINE """
    if request.method == "POST":
        data = request.json
        print("📩 Received:", data)

        for event in data.get("events", []):
            user_id = event["source"]["userId"]
            if "message" in event:
                message_text = event["message"]["text"].strip()
                print(f"📩 ข้อความจาก {user_id}: {message_text}")

                if message_text.lower() == "เริ่มคำนวณ":
                    start_questionnaire(user_id)
                else:
                    process_response(user_id, message_text)

        return jsonify({"status": "ok"}), 200
    else:
        return jsonify({"error": "Method Not Allowed"}), 405

def start_questionnaire(user_id):
    """ เริ่มต้นถามข้อมูล """
    USER_SESSIONS[user_id] = {"step": 1}
    send_message(user_id, "กรุณาเลือกวัสดุที่ต้องการผลิต:\nABS, PC, Nylon, PP, PE, PVC, PET, PMMA, POM, PU")

def process_response(user_id, message_text):
    """ จัดการคำตอบของลูกค้า """
    if user_id not in USER_SESSIONS:
        send_message(user_id, "⚠️ กรุณาเริ่มคำนวณโดยพิมพ์ 'เริ่มคำนวณ'")
        return

    step = USER_SESSIONS[user_id]["step"]

    if step == 1:
        if message_text not in MATERIAL_COSTS:
            send_message(user_id, "❌ วัสดุไม่ถูกต้อง กรุณาเลือกจาก:\nABS, PC, Nylon, PP, PE, PVC, PET, PMMA, POM, PU")
            return
        USER_SESSIONS[user_id]["material"] = message_text
        USER_SESSIONS[user_id]["step"] = 2
        send_message(user_id, "กรุณากรอกขนาดชิ้นงาน (กว้างxยาวxสูง) cm เช่น 10x15x5")

    elif step == 2:
        USER_SESSIONS[user_id]["size"] = message_text
        USER_SESSIONS[user_id]["step"] = 3
        send_message(user_id, "กรุณากรอกจำนวนที่ต้องการผลิต (ตัวเลข)")

    elif step == 3:
        try:
            USER_SESSIONS[user_id]["quantity"] = int(message_text)
            USER_SESSIONS[user_id]["step"] = 4
            send_message(user_id, "✅ ข้อมูลครบถ้วน! กำลังคำนวณต้นทุน...")
            calculate_cost(user_id)
        except ValueError:
            send_message(user_id, "❌ กรุณากรอกจำนวนที่ถูกต้อง เช่น 100")

def calculate_cost(user_id):
    """ คำนวณต้นทุนและบันทึกลง Google Sheets """
    material = USER_SESSIONS[user_id]["material"]
    size = USER_SESSIONS[user_id]["size"]
    quantity = USER_SESSIONS[user_id]["quantity"]

    # 🔹 แปลงขนาดชิ้นงานเป็น cm³
    try:
        dimensions = list(map(int, size.split("x")))
        volume = dimensions[0] * dimensions[1] * dimensions[2]  # คำนวณปริมาตร
    except:
        send_message(user_id, "❌ ขนาดชิ้นงานไม่ถูกต้อง โปรดใช้รูปแบบ เช่น 10x15x5")
        return

    # 🔹 คำนวณต้นทุน
    material_cost_per_kg = MATERIAL_COSTS.get(material, 150)  # ดึงราคาตามวัสดุ
    density = 1.05  # ค่าความหนาแน่นโดยประมาณ (g/cm³)
    weight_kg = (volume * density) / 1000  # คำนวณน้ำหนักจากปริมาตร (kg)
    total_cost = weight_kg * quantity * material_cost_per_kg

    # 🔹 บันทึกลง Google Sheets ผ่าน GAS
    if GAS_URL:
        data = {
            "user_id": user_id,
            "material": material,
            "size": size,
            "quantity": quantity,
            "volume_cm3": volume,
            "weight_kg": weight_kg,
            "total_cost": total_cost
        }
        requests.post(GAS_URL, json=data)

    # 🔹 ส่งผลลัพธ์ให้ผู้ใช้
    result_text = f"""✅ คำนวณต้นทุนสำเร็จ:
📌 วัสดุ: {material}
📌 ขนาด: {size} cm³
📌 ปริมาตร: {volume} cm³
📌 น้ำหนักโดยประมาณ: {weight_kg:.2f} kg
📌 จำนวน: {quantity} ชิ้น
📌 ต้นทุนรวม: {total_cost:,.2f} บาท
"""
    send_message(user_id, result_text)
    del USER_SESSIONS[user_id]

def send_message(user_id, text):
    """ ส่งข้อความกลับไปที่ LINE User """
    headers = {
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    message = {
        "to": user_id,
        "messages": [{"type": "text", "text": text}]
    }
    response = requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=message)

    print(f"📤 ส่งข้อความไปที่ {user_id}: {text}")
    print(f"📡 LINE Response: {response.status_code} {response.text}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
