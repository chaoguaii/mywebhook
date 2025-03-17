from fastapi import FastAPI, Request, HTTPException

app = FastAPI()

@app.post("/callback")
async def line_webhook(request: Request):
    payload = await request.json()
    print(payload)
    return {"status": "success"}
