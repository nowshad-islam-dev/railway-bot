from fastapi import FastAPI, Request
from app.state import otp_store
from loguru import logger

app = FastAPI()

@app.post("/otp-webhook")
async def receive_otp(request: Request):
    payload = await request.json()
    message = payload.get("message", "")
    
    # Simple regex to find 6 digits in the SMS body
    import re
    match = re.search(r'\d{6}', message)
    if match:
        otp_store["code"] = match.group(0)
        logger.info(f"OTP Received and Saved: {otp_store['code']}")
        return {"status": "success"}
    
    return {"status": "no code found"}

