# ใช้ Python 3.9 เป็น base image
FROM python:3.9

# ตั้งค่าโฟลเดอร์ทำงานภายใน container
WORKDIR /app

# คัดลอกไฟล์ทั้งหมดไปยัง container
COPY . /app

# ติดตั้ง dependencies จาก requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# กำหนดพอร์ตที่ container ต้องฟัง
EXPOSE 8080

# ใช้ uvicorn เป็น default command
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
