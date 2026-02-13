import os
import json
import time
import requests
import re
from typing import List, Dict, Optional, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from database import get_session
from models import chunkContent

router = APIRouter(
    prefix="/sound",
    tags=["sound"]
)

# ตั้งค่า Ollama API
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "gemma3:12b"

def get_dialogue_genders_from_ai(context_text: str, dialogue_texts: List[str]) -> List[str]:
    """
    ส่งรายการบทสนทนาที่ Regex ตัดมาแล้ว ไปให้ AI ระบุเพศทีละอัน เพื่อป้องกันลำดับผิดพลาด
    context_text: เนื้อหาบริบท 3 Chunks รวมกัน
    """
    # สร้างรายการคำถามแบบระบุข้อชัดเจน
    dialogue_list_str = "\n".join([f"{i+1}. {text}" for i, text in enumerate(dialogue_texts)])
    
    prompt = f"""
    You are an expert at analyzing Thai novels. 
    I have extracted specific dialogues from the text below. 
    Your task is to identify the gender of the speaker for EACH dialogue in the provided list.

    Full Text (Context):
    "{context_text}"

    List of Dialogues to Classify (in order):
    {dialogue_list_str}

    Instructions:
    1. Look at the "Full Text" to find the context for each dialogue in the list.
    2. Identify the speaker's gender based on:
       - Polite particles inside the quote (e.g., "Krub/Kub" = male, "Kha/Ja" = female).
       - Pronouns (e.g., "Phom/Krapom" = male, "Chan/Dichan" = female).
       - Speaker names/descriptions in the narrator text immediately before or after the quote (e.g., "Han Li said", "Zhang Tie asked").
       - Common Thai male names (e.g., Han Li, Zhang Tie, Lung Sam) -> male.
    3. Return 'male', 'female', or 'unknown'.

    Return ONLY a JSON Object with a single list 'genders' containing exactly {len(dialogue_texts)} strings corresponding to the numbered list.
    Example: {{ "genders": ["male", "female", "male"] }}
    """
    
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }
    
    # Retry logic: ลองใหม่ 3 ครั้ง โดยรอครั้งละ 1 วินาทีเสมอ
    for delay in [1, 1, 1]:
        try:
            # เพิ่ม Timeout เป็น 600 วินาที
            response = requests.post(OLLAMA_URL, json=payload, timeout=600)
            response.raise_for_status()
            
            result_json = response.json()
            content = result_json.get("response", "")
            
            clean_response = content.replace('```json', '').replace('```', '').strip()
            data = json.loads(clean_response)
            
            genders = data.get("genders", [])
            
            # Validation: ถ้าจำนวนไม่ครบ ให้เติม unknown ต่อท้าย หรือตัดส่วนเกิน
            expected_count = len(dialogue_texts)
            if len(genders) < expected_count:
                genders.extend(["unknown"] * (expected_count - len(genders)))
            elif len(genders) > expected_count:
                genders = genders[:expected_count]
                
            return genders
            
        except Exception as e:
            print(f"   [!] AI Gender Analysis failed: {e}. Retrying in {delay}s...")
            time.sleep(delay)
            
    return ["unknown"] * len(dialogue_texts)

def extract_dialogue_and_gender(target_text: str, context_text: str) -> List[Dict[str, str]]:
    """
    ใช้ Regex แยกประโยคเพื่อความแม่นยำ แล้วส่ง List บทสนทนาไปให้ AI ระบุเพศ
    target_text: เนื้อหาเฉพาะ chunk ปัจจุบัน (สำหรับตัดคำ)
    context_text: เนื้อหาบริบท 3 chunks (สำหรับส่ง AI)
    """
    # Regex Pattern: จับข้อความในเครื่องหมายคำพูด "" หรือ “”
    pattern = r'(“[^”]*”|"[^"]*")'
    
    # ใช้ Regex แยกส่วนจาก Target Text (Chunk ปัจจุบัน)
    raw_segments = re.split(pattern, target_text)
    
    segments = []
    dialogue_indices = [] 
    dialogue_texts = [] # เก็บเฉพาะข้อความบทสนทนาเพื่อส่งให้ AI
    
    for part in raw_segments:
        # CLEANUP: ตัดช่องว่างหน้าหลัง
        part = part.strip()
        
        if not part: 
            continue
            
        is_quote = (part.startswith('“') and part.endswith('”')) or \
                   (part.startswith('"') and part.endswith('"'))
        
        segment = {
            "text": part,
            "type": "dialogue" if is_quote else "narrator"
        }
        
        if is_quote:
            dialogue_indices.append(len(segments))
            dialogue_texts.append(part)
        
        segments.append(segment)
    
    # ถ้าไม่มีบทสนทนาเลย ก็คืนค่าเลย
    if not dialogue_indices:
        return segments
        
    # ส่ง List บทสนทนาพร้อม Context รวม 3 Chunk ไปให้ AI
    genders = get_dialogue_genders_from_ai(context_text, dialogue_texts)
    
    # เอาผลลัพธ์จาก AI มาใส่คืนใน segments ตาม index ที่เก็บไว้
    for i, list_idx in enumerate(dialogue_indices):
        gender = "unknown"
        if i < len(genders):
            gender = genders[i]
        
        # อัปเดต type
        segments[list_idx]["type"] = gender

    return segments

@router.get("/{chapter_id}/analysis")
def get_chunks_analysis(chapter_id: int, session: Session = Depends(get_session)):
    # 1. ดึงข้อมูลจาก Database
    statement = (
        select(chunkContent)
        .where(chunkContent.chapterId == chapter_id)
        .order_by(chunkContent.chunkNumber)
    )
    chunks = session.exec(statement).all()
    
    if not chunks:
        print(f"[-] No chunks found for chapter_id: {chapter_id}")
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูล Chunk สำหรับ Chapter นี้")

    total_chunks = len(chunks)
    print(f"[+] Found {total_chunks} chunks for chapter_id: {chapter_id}. Starting analysis...")

    analysis_result = {}

    # 2. วนลูปเช็คทีละ Chunk
    for index, chunk in enumerate(chunks):
        # index เริ่มที่ 0 ใน loop นี้
        print(f"[{index + 1}/{total_chunks}] Processing Chunk {chunk.chunkNumber}...")
        
        # CLEANUP Target Text
        target_text = chunk.chunkDetail.replace('\n', ' ')
        target_text = re.sub(r'\s+', ' ', target_text).strip()
        
        # --- CONTEXT LOGIC (3 Chunks) ---
        # คำนวณช่วง Index ของ Context [start:end]
        # Logic: พยายามเอา window ขนาด 3 ที่ครอบคลุม index ปัจจุบัน
        # start_idx จะถูก clamp ไม่ให้ต่ำกว่า 0 และไม่ให้เกิน total_chunks - 3 (กรณี chunk ท้ายๆ)
        start_idx = max(0, min(index - 1, total_chunks - 3))
        end_idx = min(total_chunks, start_idx + 3)
        
        # ดึง Chunk สำหรับ Context
        context_chunks_list = chunks[start_idx:end_idx]
        
        # รวม Text และ Clean
        context_text_raw = " ".join([c.chunkDetail for c in context_chunks_list])
        context_text = context_text_raw.replace('\n', ' ')
        context_text = re.sub(r'\s+', ' ', context_text).strip()
        
        segments = []

        has_quotes = '"' in target_text or '“' in target_text or '”' in target_text
        
        if not has_quotes:
            print(f"   -> No quotes found. Marking as 100% Narrator.")
            segments = [{
                "text": target_text,
                "type": "narrator"
            }]
        else:
            print(f"   -> Quotes found. Using Regex Split + AI Context (Window: {start_idx+1}-{end_idx})...")
            # ส่งทั้ง target (ตัดคำ) และ context (AI อ่าน)
            segments = extract_dialogue_and_gender(target_text, context_text)
            print(f"   -> Analysis complete.")
        
        analysis_result[str(chunk.chunkNumber)] = segments

    print(f"[+] Analysis for chapter {chapter_id} completed successfully.")
    return analysis_result

@router.get("/chunk/{chapter_id}")
def get_chapter_chunks(chapter_id: int, session: Session = Depends(get_session)):
    """
    ดึงข้อมูล Chunk ทั้งหมดของ Chapter นั้นๆ เพื่อตรวจสอบความถูกต้อง (เฉพาะ Chunk Detail)
    """
    statement = (
        select(chunkContent)
        .where(chunkContent.chapterId == chapter_id)
        .order_by(chunkContent.chunkNumber)
    )
    chunks = session.exec(statement).all()
    
    if not chunks:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูล Chunk สำหรับ Chapter นี้")
        
    return {
        str(chunk.chunkNumber): re.sub(r'\s+', ' ', chunk.chunkDetail.replace('\n', ' ')).strip() 
        for chunk in chunks
    }