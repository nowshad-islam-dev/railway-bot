import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    BASE_URL = "https://eticket.railway.gov.bd"
    LOGIN_URL = f"{BASE_URL}/login"
    TICKET_URL = f"{BASE_URL}/booking/train/search"

    # Search config
    FROM_CITY = os.getenv("FROM_CITY")
    TO_CITY = os.getenv("TO_CITY")
    DATE_OF_JOURNEY = os.getenv("DATE_OF_JOURNEY")
    TICKET_CLASS = os.getenv("TICKET_CLASS")
    SEATS_PER_MEMBER = int(os.getenv("SEATS_PER_MEMBER", 4))
    PREFERRED_TRAIN = os.getenv("PREFERRED_TRAIN", None)  # None = auto pick most seats
