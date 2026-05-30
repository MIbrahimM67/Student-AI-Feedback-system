import asyncpg
import asyncio
import os
from dotenv import load_dotenv

async def make_admin():
    load_dotenv('i:/fyp implementation/backend/.env')
    db_url = os.environ.get('DATABASE_URL', 'postgresql://app_user:change_me@localhost:5432/feedback')
    db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')
    print(f"Connecting to {db_url}...")
    try:
        conn = await asyncpg.connect(db_url)
        # Update role to admin
        res = await conn.execute("UPDATE users SET role = 'admin' WHERE email = 'ibrahimzeb67@gmail.com'")
        print("Update result:", res)
        # If the user exists, also update their faculty_status just in case
        await conn.execute("UPDATE users SET faculty_status = 'approved' WHERE email = 'ibrahimzeb67@gmail.com'")
        await conn.close()
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(make_admin())
