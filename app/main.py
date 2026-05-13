import asyncio
from app.bot import run_member
from app.members import get_members


async def main():
    members = get_members()
    await asyncio.gather(*[run_member(member) for member in members])


if __name__ == "__main__":
    asyncio.run(main())
