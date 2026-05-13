import os
from dotenv import load_dotenv

load_dotenv()


def get_members() -> list[dict]:
    return [
        {
            "name": os.getenv(f"MEMBER{i}_NAME", f"Member {i}"),
            "phone": os.getenv(f"MEMBER{i}_PHONE"),
            "password": os.getenv(f"MEMBER{i}_PASS"),
            "user_data_dir": f"./sessions/member{i}",
            "debugging_port": 9221 + i,  # 9222, 9223, 9224, 9225
        }
        for i in range(1, 3)
    ]
