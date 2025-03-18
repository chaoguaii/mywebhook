from google.cloud import bigquery
from google.oauth2 import service_account

# ใช้ไฟล์ Service Account JSON ที่ดาวน์โหลดมา
credentials = service_account.Credentials.from_service_account_file(
    'moldplasticservicechatbot-8f96c6872051.json'
)

# สร้าง client สำหรับเชื่อมต่อกับ BigQuery
client = bigquery.Client(credentials=credentials, project=credentials.project_id)

# แก้ไข Project ID, Dataset ID, และ Table ID
query = "SELECT * FROM `moldplasticservicechatbot.moldplasticservicechatbot_dataset.PriceCalculationRequests` LIMIT 10"
query_job = client.query(query)  # เรียกใช้คำสั่ง SQL

# แสดงผลลัพธ์
rows = query_job.result()  # ดึงผลลัพธ์
row_count = sum(1 for _ in rows)  # นับจำนวนแถว
print(f"จำนวนแถวที่ได้จากการ query: {row_count}")

# แสดงข้อมูล (ถ้ามี)
if row_count > 0:
    for row in query_job:
        print(row)
else:
    print("ไม่มีข้อมูลในตารางที่ระบุ")
