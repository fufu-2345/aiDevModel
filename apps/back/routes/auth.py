from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlmodel import Field, Session, SQLModel, create_engine, select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
import random
import string
import smtplib
from email.message import EmailMessage
from models import users

# ==========================================
# 1. Config & Security Setup
# ==========================================
SECRET_KEY = "your-super-secret-key-change-this-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# ==========================================
# 1.5 Email Setup (ตั้งค่าสำหรับการส่งอีเมลจริง)
# ==========================================
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
# เปลี่ยนเป็นอีเมล Gmail ของคุณที่จะใช้ส่ง
SENDER_EMAIL = "your_email@gmail.com" 
# เปลี่ยนเป็นรหัสผ่าน App Password 16 หลัก (ไม่ใช่รหัสผ่านล็อคอินปกติ)
SENDER_PASSWORD = "your_app_password_here" 

# ==========================================
# 2. Database Models (SQLModel)
# ==========================================

# ตารางสำหรับเก็บ OTP ชั่วคราว
class otp_codes(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True)
    otp: str
    expires_at: datetime

# ==========================================
# 3. Database Engine & Session
# ==========================================
# นำเข้า engine จากไฟล์ database.py ที่คุณตั้งค่า PostgreSQL เอาไว้
from database import engine

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

# ย้ายการเรียกสร้างตารางมาไว้ตรงนี้ เพื่อให้ทำงานทันทีเมื่อไฟล์ถูก import
# ป้องกันปัญหา "no such table" เมื่อไฟล์นี้ถูกเรียกใช้ผ่าน router
create_db_and_tables()

def get_session():
    with Session(engine) as session:
        yield session

# ==========================================
# 4. Helper Functions
# ==========================================
def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        # ใช้ bcrypt ตรวจสอบรหัสผ่านโดยตรง
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except ValueError as e:
        print(f"🚨 [DEBUG] Bcrypt Verify Error: {e}")
        return False

def get_password_hash(password: str) -> str:
    # ใช้ bcrypt สร้าง Hash โดยตรง
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed_password.decode('utf-8')

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def generate_otp():
    return ''.join(random.choices(string.digits, k=6)) # สร้าง OTP 6 หลัก

def send_actual_email(receiver_email: str, otp: str):
    """ฟังก์ชันสำหรับส่งอีเมลจริงผ่าน SMTP"""
    msg = EmailMessage()
    msg['Subject'] = 'รหัส OTP สำหรับยืนยันการสมัครสมาชิก'
    msg['From'] = SENDER_EMAIL
    msg['To'] = receiver_email
    
    # เนื้อหาอีเมล
    msg.set_content(f"สวัสดีครับ,\n\nรหัส OTP สำหรับยืนยันอีเมลของคุณคือ: {otp}\nรหัสนี้จะหมดอายุภายใน 5 นาที\n\nหากคุณไม่ได้ทำรายการนี้ โปรดเพิกเฉยต่ออีเมลฉบับนี้")

    try:
        # เชื่อมต่อกับ SMTP Server ของ Gmail
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls() # เปิดโหมดรักษาความปลอดภัย
            server.login(SENDER_EMAIL, SENDER_PASSWORD) # ล็อคอิน
            server.send_message(msg) # ส่งอีเมล
        print(f"✅ [SUCCESS] Email sent to {receiver_email}")
    except Exception as e:
        print(f"❌ [ERROR] Failed to send email: {e}")

# ==========================================
# 5. Pydantic Schemas (สำหรับรับข้อมูลจาก Frontend)
# ==========================================
class OTPRequest(BaseModel):
    email: str

class RegisterRequest(BaseModel):
    email: str
    password: str
    otp: str

class LoginRequest(BaseModel):
    email: str
    password: str

# ==========================================
# 6. FastAPI App & Endpoints
# ==========================================
app = FastAPI(title="Auth API with OTP")

# ประกาศใช้งาน APIRouter
router = APIRouter(
    prefix="/auth",
    tags=["auth"]
)

# 6.1 ขอ OTP สำหรับสมัครสมาชิก
@router.post("/request-otp")
def request_otp(data: OTPRequest, background_tasks: BackgroundTasks, session: Session = Depends(get_session)):
    # เช็คว่ามี email นี้ในระบบแล้วหรือยัง
    existing_user = session.exec(select(users).where(users.email == data.email)).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # ลบ OTP เก่าของ email นี้ (ถ้ามี)
    old_otps = session.exec(select(otp_codes).where(otp_codes.email == data.email)).all()
    for old_otp in old_otps:
        session.delete(old_otp)

    # สร้าง OTP ใหม่ (หมดอายุใน 5 นาที)
    new_otp_code = generate_otp()
    expiration = datetime.now(timezone.utc) + timedelta(minutes=5)
    
    new_otp_record = otp_codes(email=data.email, otp=new_otp_code, expires_at=expiration)
    session.add(new_otp_record)
    session.commit()

    # สั่งให้ทำงานเบื้องหลัง
    background_tasks.add_task(send_actual_email, data.email, new_otp_code)

    return {"success": True, "message": "OTP sent to your email. Valid for 5 minutes."}

# 6.2 สมัครสมาชิก (ยืนยัน OTP)
@router.post("/register")
def register(data: RegisterRequest, session: Session = Depends(get_session)):
    # ตรวจสอบ OTP
    statement = select(otp_codes).where(otp_codes.email == data.email).where(otp_codes.otp == data.otp)
    otp_record = session.exec(statement).first()

    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    
    if otp_record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="OTP has expired")

    # เช็คอีกครั้งว่ามี email หรือยัง
    existing_user = session.exec(select(users).where(users.email == data.email)).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # สร้าง User ใหม่และเข้ารหัส Password
    hashed_pw = get_password_hash(data.password)
    new_user = users(email=data.email, password=hashed_pw)
    session.add(new_user)
    
    # ลบ OTP ทิ้งหลังใช้เสร็จ
    session.delete(otp_record)
    session.commit()

    return {"success": True, "message": "User registered successfully"}

# 6.3 เข้าสู่ระบบ (เพิ่ม Debug Print ที่นี่)
@router.post("/login")
def login(data: LoginRequest, session: Session = Depends(get_session)):
    print(f"\n{'='*40}")
    print(f"🔍 [DEBUG] Login Attempt for: {data.email}")
    print(f"🔍 [DEBUG] Plain text password received: {data.password}")
    
    user = session.exec(select(users).where(users.email == data.email)).first()
    
    if not user:
        print(f"❌ [DEBUG] Result: User NOT FOUND in database!")
        print(f"{'='*40}\n")
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    print(f"✅ [DEBUG] Result: User FOUND in database.")
    print(f"🔍 [DEBUG] Hashed password from DB: {user.password}")

    # ตรวจสอบรหัสผ่าน
    is_password_valid = verify_password(data.password, user.password)
    print(f"🔍 [DEBUG] Is Password Valid?: {is_password_valid}")
    print(f"{'='*40}\n")

    if not is_password_valid:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # สร้าง JWT Token
    access_token = create_access_token(data={"sub": user.email, "role": user.role})
    
    return {
        "success": True,
        "message": "Login successful",
        "access_token": access_token,
        "token_type": "bearer",
        "user_role": user.role
    }

# นำ router ไปผูกเข้ากับ app
app.include_router(router)