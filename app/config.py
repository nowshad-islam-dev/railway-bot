import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    PHONE = os.getenv("RAILWAY_PHONE")
    PASSWORD = os.getenv("RAILWAY_PASS")
    BASE_URL = "https://eticket.railway.gov.bd"
    LOGIN_URL = f"{BASE_URL}/login"
    TICKET_URL=f"{BASE_URL}/booking/train/search"