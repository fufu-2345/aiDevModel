from sqlmodel import Session, select
from database import engine 
from models import users   

def create_admin():
    with Session(engine) as session:
        statement = select(users).where(users.email == "admin@gmail.com")
        existing_user = session.exec(statement).first()

        # ดักมี admin อยู่แล้ว
        if existing_user:
            return

        new_admin = users(
            email="admin@gmail.com",
            password="admin",
            role="admin"
        )
        try:
            session.add(new_admin)
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"err: {e}")

if __name__ == "__main__":
    create_admin()