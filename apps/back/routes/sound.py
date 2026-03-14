import os
import json
import time
import requests
import re
import gc 
from typing import List, Dict, Optional, Any, Set
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlmodel import Session, select
from pydub import AudioSegment
from dotenv import load_dotenv
from database import get_session
from models import chunkContent, matcher

router = APIRouter(
    prefix="/sound",
    tags=["sound"]
)

load_dotenv(".env.local")

ollamaURL = os.getenv("ollamaURL")
OLLAMA_MODEL = "gemma3:12b"
F5_API_URL = os.getenv("F5_API_URL")

F5_REF_PATHS = {
    "narrator": "F5sound/male.wav",
    "male": "F5sound/male.wav",
    "female": "F5sound/female.wav"
}

F5_REF_TEXT = "เฮ้ยทุกคน เชื่อไหมว่าเดี๋ยวนี้ AI มันทำอะไรได้เยอะมากจริงๆ วันนี้ผมลองเล่นมาตัวนึง"

TTS_MAPPING = {
    "narrator": "narrator", 
    "male": "male",         
    "female": "female",     
    "unknown": "male"       
}

AUDIO_GAP_MS = 1000 

def _generate_via_f5_api(text: str, speaker_type: str) -> Optional[AudioSegment]:
    if not text.strip():
        return None
        
    mapped_key = TTS_MAPPING.get(speaker_type, "male")
    ref_audio_path = F5_REF_PATHS.get(mapped_key, "F5sound/male.wav")
    
    try:
        payload = {
            "text": text,
            "speaker_type": mapped_key,
            "ref_audio_path": ref_audio_path,
            "ref_text": F5_REF_TEXT
        }
        
        response = requests.post(F5_API_URL, data=payload, timeout=600)
        
        if response.status_code != 200:
            print(f"   [!] F5 API Error ({response.status_code}): {response.text}", flush=True)
            return None
            
        audio_data = BytesIO(response.content)
        return AudioSegment.from_file(audio_data, format="wav")
    except requests.exceptions.ConnectionError:
        print(f"   [!] Connection Refused: ไม่สามารถเชื่อมต่อ F5 ได้ที่พอร์ต 8001", flush=True)
        return None
    except Exception as e:
        print(f"   [!] F5 API Failed for '{text[:15]}...': {e}", flush=True)
        return None

def get_dialogue_genders_from_ai(context_text: str, dialogue_texts: List[str]) -> List[str]:
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
    2. Identify the speaker's gender based on particles/pronouns (e.g., Krub/Kha, Phom/Chan) and context.
    3. Return 'male', 'female', or 'unknown'.

    Return ONLY a JSON Object with a single list 'genders' containing exactly {len(dialogue_texts)} strings.
    Example: {{ "genders": ["male", "female", "male"] }}
    """
    
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }
    
    for delay in [1, 1, 1]:
        try:
            response = requests.post(OLLAMA_URL, json=payload, timeout=600)
            response.raise_for_status()
            
            result_json = response.json()
            content = result_json.get("response", "")
            
            clean_response = content.replace('```json', '').replace('```', '').strip()
            data = json.loads(clean_response)
            genders = data.get("genders", [])
            
            expected_count = len(dialogue_texts)
            if len(genders) < expected_count:
                genders.extend(["unknown"] * (expected_count - len(genders)))
            elif len(genders) > expected_count:
                genders = genders[:expected_count]
                
            return genders
        except Exception as e:
            time.sleep(delay)
            
    return ["unknown"] * len(dialogue_texts)

def extract_dialogue_and_gender(target_text: str, context_text: str) -> List[Dict[str, str]]:
    pattern = r'(“[^”]*”|"[^"]*")'
    raw_segments = re.split(pattern, target_text)
    
    segments = []
    dialogue_indices = [] 
    dialogue_texts = [] 
    
    for part in raw_segments:
        part = part.strip()
        if not part: continue
            
        is_quote = (part.startswith('“') and part.endswith('”')) or \
                   (part.startswith('"') and part.endswith('"'))
        
        segment = {"text": part, "type": "dialogue" if is_quote else "narrator"}
        
        if is_quote:
            dialogue_indices.append(len(segments))
            dialogue_texts.append(part)
        
        segments.append(segment)
    
    if not dialogue_indices:
        return segments
        
    genders = get_dialogue_genders_from_ai(context_text, dialogue_texts)
    
    for i, list_idx in enumerate(dialogue_indices):
        gender = "unknown"
        if i < len(genders):
            gender = genders[i]
        segments[list_idx]["type"] = gender

    return segments

@router.get("/{chapter_id}/analysis")
def get_chunks_analysis(
    chapter_id: int, 
    session: Session = Depends(get_session)
):
    # [UPDATE] ตรวจหาไฟล์ .wav เท่านั้น ไม่ใช้ mp3 แล้ว
    output_file_path = os.path.abspath(f"public/storage/sound/{chapter_id}.wav")
    if os.path.exists(output_file_path):
        return {
            "audio_status": "already_exists",
            "audio_file_path": output_file_path,
            "message": f"{chapter_id}.wav is already exist"
        }
    
    start_time = time.time()
    print(f"\n[Time] Processing started at: {time.strftime('%X')}", flush=True)
    
    statement = (
        select(chunkContent)
        .where(chunkContent.chapterId == chapter_id)
        .order_by(chunkContent.chunkNumber)
    )
    chunks = session.exec(statement).all()
    if not chunks:
        raise HTTPException(status_code=404, detail="No chunks found")
        
    total_chunks = len(chunks)
    all_chunks_data = {} 
    
    for index, chunk in enumerate(chunks):
        print(f"Analyze Chunk {chunk.chunkNumber}/{total_chunks}", flush=True)
        
        target_text = chunk.chunkDetail.replace('\n', ' ')
        target_text = re.sub(r'\s+', ' ', target_text).strip()
        start_idx = max(0, min(index - 1, total_chunks - 3))
        end_idx = min(total_chunks, start_idx + 3)
        context_chunks_list = chunks[start_idx:end_idx]
        context_text_raw = " ".join([c.chunkDetail for c in context_chunks_list])
        context_text = re.sub(r'\s+', ' ', context_text_raw.replace('\n', ' ')).strip()
        
        has_quotes = '"' in target_text or '“' in target_text or '”' in target_text
        if not has_quotes:
            segments = [{"text": target_text, "type": "narrator"}]
        else:
            segments = extract_dialogue_and_gender(target_text, context_text)
        all_chunks_data[chunk.chunkNumber] = segments
        
    print(f"\n[Phase 2] Generating Audio via F5...", flush=True)
    analysis_result = {}
    combined_audio = AudioSegment.empty()
    gap_segment = AudioSegment.silent(duration=AUDIO_GAP_MS)
    sorted_chunk_nums = sorted(all_chunks_data.keys())
    
    for chunk_num in sorted_chunk_nums:
        segments = all_chunks_data[chunk_num]
        print(f"   [Audio] Generating Chunk {chunk_num}...", flush=True)
        chunk_audio_duration_ms = 0
        
        for seg in segments:
            text_part = seg["text"]
            speaker_type = seg["type"]
            clean_text = text_part.replace('"', '').replace('“', '').replace('”', '')
            
            audio_seg = _generate_via_f5_api(clean_text, speaker_type)
            
            # [FIX] เช็คให้ชัวร์ว่า F5 ส่งเสียงกลับมาจริงๆ
            if audio_seg is not None:
                segment_duration = len(audio_seg) + len(gap_segment)
                chunk_audio_duration_ms += segment_duration
                
                combined_audio += audio_seg
                combined_audio += gap_segment
            else:
                print(f"      ⚠️ F5 สร้างเสียงประโยคนี้ไม่สำเร็จ ข้ามไป...", flush=True)
        
        analysis_result[str(chunk_num)] = {
            "segments": segments,
            "duration": chunk_audio_duration_ms / 1000.0
        }
        
    print(f"\n[Cleanup] Cleaning up unused variables...", flush=True)
    gc.collect()
    
    # [FIX] ดักจับการพัง 100% ถ้าไม่มีเสียงถูกเอามาต่อกันเลย ให้ยกเลิกการทำงานทั้งหมดทันที!
    if len(combined_audio) == 0:
        print("\n❌ ❌ [ERROR] F5 API ล้มเหลวทั้งหมด ไม่สามารถสร้างไฟล์เสียงได้ ยกเลิกการเซฟลง DB!", flush=True)
        raise HTTPException(status_code=500, detail="ไม่สามารถสร้างเสียงจาก F5 ได้เลย (โปรดเช็ค F5 API)")

    # [UPDATE] เซฟไฟล์เป็น .wav เพียงไฟล์เดียว
    output_dir = os.path.abspath("public/storage/sound")
    os.makedirs(output_dir, exist_ok=True)
    output_filename = f"{chapter_id}.wav"
    output_file_path = os.path.join(output_dir, output_filename)
    
    print(f"[+] Saving audio to: {output_file_path}", flush=True)
    try:
        combined_audio.export(output_file_path, format="wav")
        analysis_result["audio_status"] = "success"
        analysis_result["audio_file_path"] = output_file_path
    except Exception as e:
        analysis_result["audio_status"] = f"error_exporting: {str(e)}"
        
    chunk_id_map = {str(c.chunkNumber): c.id for c in chunks}

    try:
        old_matchers = session.exec(select(matcher).where(matcher.chapterId == chapter_id)).all()
        if old_matchers:
            for old_m in old_matchers:
                session.delete(old_m)
            session.commit()
            print(f"[Database] 🗑️ ลบ Matcher เก่า {len(old_matchers)} รายการ", flush=True)
    except Exception as e:
        session.rollback()
        print(f"[Database Error] Failed to delete old matchers: {e}", flush=True)

    try:
        for chunk_num_str, data in analysis_result.items():
            if chunk_num_str in ["audio_status", "audio_file_path"]: continue
            
            # [FIX] ถ้า Chunk นี้เจนเสียงไม่ผ่าน (เวลาเป็น 0) จะไม่เซฟลง Database 
            if isinstance(data, dict) and "duration" in data and data["duration"] > 0:
                chunk_id = chunk_id_map.get(chunk_num_str)
                print(f"Chunk {chunk_num_str}: {data['duration']}s | mapped chunkContentId: {chunk_id}", flush=True)
                new_matcher = matcher(
                    character="",
                    location="",
                    duration=float(data["duration"]),
                    chunkContentId=chunk_id,
                    chapterId=chapter_id
                )
                session.add(new_matcher)
        session.commit()
        print(f"[Database] Matcher records inserted successfully.", flush=True)
    except Exception as e:
        session.rollback()
        print(f"[Database Error] Failed to insert matcher: {e}", flush=True)
        
    end_time = time.time()
    analysis_result["total_processing_time_seconds"] = end_time - start_time
    print(f"Total processing time: {analysis_result['total_processing_time_seconds']:.2f} seconds", flush=True)

    return analysis_result

@router.get("/chunk/{chapter_id}")
def get_chapter_chunks(chapter_id: int, session: Session = Depends(get_session)):
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