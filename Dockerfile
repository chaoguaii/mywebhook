# ใช้ Python 3.11 เป็น Base Image
FROM python:3.11

# ตั้งค่า Working Directory
WORKDIR /app

# คัดลอกไฟล์ทั้งหมดไปที่ Container
COPY . /app

# ติดตั้ง Dependencies
RUN pip install --no-cache-dir -r requirements.txt

# เปิดพอร์ต 8080 ให้ Container ใช้งาน
EXPOSE 8080

# รันแอปด้วย Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
