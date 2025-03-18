# ใช้ Python 3.9 เป็น base image
FROM python:3.9

# กำหนด Working Directory
WORKDIR /app

# คัดลอกไฟล์ทั้งหมดเข้า container
COPY . /app

# ติดตั้ง dependencies
RUN pip install --no-cache-dir -r requirements.txt

# เปิดพอร์ต 8080
EXPOSE 8080

# คำสั่งรัน FastAPI
CMD ["uvicorn", "chatbot_line:app", "--host", "0.0.0.0", "--port", "8080"]
