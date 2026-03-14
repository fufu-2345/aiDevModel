from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, BackgroundTasks, Response, Request
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
from database import engine 
from models import users    
from dotenv import load_dotenv 
import os

load_dotenv(".env.local")

SECRET_KEY = "your-super-secret-key-change-this-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")

class otp_codes(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True)
    otp: str
    expires_at: datetime

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

create_db_and_tables()

def get_session():
    with Session(engine) as session:
        yield session

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except ValueError as e:
        print(f"Bcrypt Verify Error: {e}")
        return False

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed_password.decode('utf-8')

def generate_otp():
    return ''.join(random.choices(string.digits, k=6))

def send_actual_email(receiver_email: str, otp: str):
    msg = EmailMessage()
    msg['Subject'] = 'รหัส OTP สำหรับยืนยันการสมัครสมาชิก'
    msg['From'] = SENDER_EMAIL
    msg['To'] = receiver_email
    msg.set_content(f"สวัสดีครับ,\n\nรหัส OTP สำหรับยืนยันอีเมลของคุณคือ: {otp}\nรหัสนี้จะหมดอายุภายใน 5 นาที\n\nหากคุณไม่ได้ทำรายการนี้ โปรดเพิกเฉยต่ออีเมลฉบับนี้")

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        print(f"Failed to send email: {e}")

def get_current_user(request: Request, session: Session = Depends(get_session)):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = token.replace("Bearer ", "")
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    user = session.exec(select(users).where(users.email == email)).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
        
    return user

class OTPRequest(BaseModel):
    email: str

class RegisterRequest(BaseModel):
    email: str
    password: str
    otp: str

class LoginRequest(BaseModel):
    email: str
    password: str

app = FastAPI(title="Auth API")
router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/request-otp")
def request_otp(data: OTPRequest, background_tasks: BackgroundTasks, session: Session = Depends(get_session)):
    existing_user = session.exec(select(users).where(users.email == data.email)).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    old_otps = session.exec(select(otp_codes).where(otp_codes.email == data.email)).all()
    for old_otp in old_otps:
        session.delete(old_otp)

    new_otp_code = generate_otp()
    expiration = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5)
    
    new_otp_record = otp_codes(email=data.email, otp=new_otp_code, expires_at=expiration)
    session.add(new_otp_record)
    session.commit()

    background_tasks.add_task(send_actual_email, data.email, new_otp_code)

    return {"success": True, "message": "OTP sent to your email. Valid for 5 minutes."}

@router.post("/register")
def register(data: RegisterRequest, session: Session = Depends(get_session)):
    statement = select(otp_codes).where(otp_codes.email == data.email).where(otp_codes.otp == data.otp)
    otp_record = session.exec(statement).first()

    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    
    if otp_record.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=400, detail="OTP has expired")

    existing_user = session.exec(select(users).where(users.email == data.email)).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_pw = get_password_hash(data.password)
    new_user = users(email=data.email, password=hashed_pw)
    session.add(new_user)
    
    session.delete(otp_record)
    session.commit()

    return {"success": True, "message": "User registered successfully"}

@router.post("/login")
def login(data: LoginRequest, response: Response, session: Session = Depends(get_session)):
    user = session.exec(select(users).where(users.email == data.email)).first()
    
    if not user or not verify_password(data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": user.email, "role": user.role, "exp": expire}
    access_token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=False 
    )
    
    return {
        "success": True,
        "message": "Login successful",
        "email": user.email,
        "role": user.role
    }

@router.get("/me")
def get_me(current_user: users = Depends(get_current_user)):
    return {
        "email": current_user.email,
        "role": current_user.role,
        "id": current_user.id
    }

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key="access_token")
    return {"success": True, "message": "Logged out successfully"}

app.include_router(router)