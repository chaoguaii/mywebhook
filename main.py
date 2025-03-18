from flask import Flask, request, jsonify
import requests
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)

# 🔹 โหลด Environment Variables (สามารถตั้งค่าใน Google Cloud Run หรือใน Docker)
LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")  # path ไปยังไฟล์ JSON Credentials
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")  # Spreadsheet ID ของ Google Sheets
SHEET_NAME = os.getenv("SHEET_NAME", "Data")  # ชื่อ sheet ที่จะเขียนข้อมูล

print("LINE_ACCESS_TOKEN:", LINE_ACCESS_TOKEN)

# 🔹 เก็บข้อมูล session ของผู้ใช้
USER_SESSIONS = {}

# 🔹 ตารางราคาวัสดุ (บาท/kg)
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

                # เริ่มต้นการคำนวณ
                if message_text.lower() == "เริ่มคำนวณ":
                    start_questionnaire(user_id)
                else:
                    process_response(user_id, message_text)

        return jsonify({"status": "ok"}), 200
    else:
        return jsonify({"error": "Method Not Allowed"}), 405

def start_questionnaire(user_id):
    """ เริ่มต้นถามข้อมูลจากผู้ใช้ """
    USER_SESSIONS[user_id] = {"step": 1}
    send_message(user_id, "กรุณาเลือกวัสดุที่ต้องการผลิต:\nABS, PC, Nylon, PP, PE, PVC, PET, PMMA, POM, PU")

def process_response(user_id, message_text):
    """ จัดการคำตอบจากผู้ใช้ในแต่ละขั้นตอน """
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
            send_message(user_id, "ข้อมูลครบถ้วนแล้ว\nต้องการใบเสนอราคาหรือไม่? หากต้องการให้พิมพ์ 'ต้องการ'")
        except ValueError:
            send_message(user_id, "❌ กรุณากรอกจำนวนที่ถูกต้อง เช่น 100")

    elif step == 4:
        if message_text.strip() == "ต้องการ":
            calculate_cost(user_id)
        else:
            send_message(user_id, "ไม่ได้เลือกใบเสนอราคา หากต้องการใบเสนอราคาลองพิมพ์ 'ต้องการ' ใหม่")
            del USER_SESSIONS[user_id]

def calculate_cost(user_id):
    """ คำนวณต้นทุนและบันทึกข้อมูลลง Google Sheets """
    material = USER_SESSIONS[user_id]["material"]
    size = USER_SESSIONS[user_id]["size"]
    quantity = USER_SESSIONS[user_id]["quantity"]

    # คำนวณปริมาตร
    try:
        dimensions = list(map(int, size.split("x")))
        if len(dimensions) != 3:
            raise ValueError("Invalid dimensions")
        volume = dimensions[0] * dimensions[1] * dimensions[2]
    except Exception as e:
        send_message(user_id, "❌ ขนาดชิ้นงานไม่ถูกต้อง โปรดใช้รูปแบบ เช่น 10x15x5")
        return

    # คำนวณน้ำหนักและต้นทุน
    material_cost_per_kg = MATERIAL_COSTS.get(material, 150)
    density = 1.05  # g/cm³
    weight_kg = (volume * density) / 1000
    total_cost = weight_kg * quantity * material_cost_per_kg

    try:
        write_to_sheet(user_id, material, size, quantity, volume, weight_kg, total_cost)
    except Exception as e:
        print(f"⚠️ เกิดข้อผิดพลาดในการบันทึกข้อมูลลง Google Sheets: {e}")

    result_text = (
        f"✅ คำนวณต้นทุนสำเร็จ:\n"
        f"📌 วัสดุ: {material}\n"
        f"📌 ขนาด: {size} cm³\n"
        f"📌 ปริมาตร: {volume} cm³\n"
        f"📌 น้ำหนัก: {weight_kg:.2f} kg\n"
        f"📌 จำนวน: {quantity} ชิ้น\n"
        f"📌 ต้นทุนรวม: {total_cost:,.2f} บาท"
    )
    send_message(user_id, result_text)
    del USER_SESSIONS[user_id]

def write_to_sheet(user_id, material, size, quantity, volume, weight_kg, total_cost):
    """ บันทึกข้อมูลใบเสนอราคาไปยัง Google Sheets """
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    credentials = service_account.Credentials.from_service_account_file(
        GOOGLE_APPLICATION_CREDENTIALS, scopes=SCOPES)
    service = build('sheets', 'v4', credentials=credentials)

    values = [
        [user_id, material, size, quantity, volume, f"{weight_kg:.2f}", f"{total_cost:,.2f}"]
    ]
    body = {
        'values': values
    }
    range_name = f"{SHEET_NAME}!A1"
    result = service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=range_name,
        valueInputOption="RAW",
        body=body
    ).execute()
    updated_cells = result.get('updates', {}).get('updatedCells', 0)
    print(f"{updated_cells} cells appended to Google Sheets.")

def send_message(user_id, text):
    """ ส่งข้อความไปยัง LINE User """
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
    # ใช้พอร์ตที่กำหนดผ่าน Environment Variable หรือ 8080 เป็นค่าเริ่มต้น
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
