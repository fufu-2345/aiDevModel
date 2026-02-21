from sqlmodel import Session, select
from database import engine 
from models import users   
import bcrypt # 1. Import bcrypt โดยตรงแทน passlib

# 2. สร้างฟังก์ชันเข้ารหัสด้วย bcrypt
def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed_password.decode('utf-8')

def create_admin():
    with Session(engine) as session:
        statement = select(users).where(users.email == "admin@gmail.com")
        existing_user = session.exec(statement).first()

        # ดักมี admin อยู่แล้ว
        if existing_user:
            print("Admin already exists.")
            return

        # 3. นำรหัสผ่าน "admin" มาผ่านฟังก์ชันเข้ารหัส
        hashed_password = get_password_hash("admin")

        new_admin = users(
            email="admin@gmail.com",
            password=hashed_password,
            role="admin"
        )
        try:
            session.add(new_admin)
            session.commit()
            print("Admin user created successfully!")
        except Exception as e:
            session.rollback()
            print(f"err: {e}")

if __name__ == "__main__":
    create_admin()