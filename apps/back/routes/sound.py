import os
import json
import time
import requests
import re
import numpy as np
import gc 
import torch
from typing import List, Dict, Optional, Any, Set
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlmodel import Session, select
from pydub import AudioSegment

from database import get_session
from models import chunkContent

router = APIRouter(
    prefix="/sound",
    tags=["sound"]
)

# ตั้งค่า Ollama API
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "gemma3:12b"

# --- TTS CONFIGURATION ---
TTS_MODE = "LOCAL" 

# กรณีใช้ API
TTS_API_URL = "http://localhost:5000/tts"

# กรณีใช้ Local Files
TTS_LOCAL_PATHS = {
    "narrator": "sound/new/male1",
    "male": "sound/new/male2",
    "female": "sound/new/female2"
}

# Mapping ประเภทเสียง
TTS_MAPPING = {
    "narrator": "narrator", 
    "male": "male",         
    "female": "female",     
    "unknown": "male"       
}

AUDIO_GAP_MS = 1000  # ช่องว่าง 1 วินาที

# [REMOVED] ลบ Global Cache ออก เพื่อไม่ให้กิน RAM ค้าง
# loaded_models = {} 
# loaded_tokenizers = {}

def load_specific_models(needed_keys: Set[str]) -> tuple:
    """
    โหลดโมเดลเฉพาะที่จำเป็นต้องใช้ในรอบนั้นๆ และคืนค่ากลับไปเป็น Dict
    """
    if TTS_MODE != "LOCAL":
        return {}, {}

    print(f"[Init] Loading specific TTS models: {needed_keys}...", flush=True)
    
    # Lazy Import
    try:
        from transformers import VitsModel, AutoTokenizer
    except ImportError:
        print("[Error] transformers or torch not installed.", flush=True)
        return {}, {}
    
    models = {}
    tokenizers = {}
    
    try:
        for key in needed_keys:
            path = TTS_LOCAL_PATHS.get(key)
            if not path:
                continue

            abs_path = os.path.abspath(path)
            if not os.path.exists(abs_path):
                print(f"   [!] Model path not found: {abs_path}", flush=True)
                continue
                
            print(f"   ... Loading {key} from {abs_path}", flush=True)
            tokenizers[key] = AutoTokenizer.from_pretrained(abs_path)
            models[key] = VitsModel.from_pretrained(abs_path)
            
        print("[Init] Models loaded successfully.", flush=True)
        return models, tokenizers
    except Exception as e:
        print(f"   [!] Error loading models: {e}", flush=True)
        return {}, {}

def generate_tts_with_loaded_models(
    text: str, 
    speaker_type: str, 
    models: Dict, 
    tokenizers: Dict
) -> Optional[AudioSegment]:
    """
    สร้างเสียงโดยใช้โมเดลที่ส่งเข้ามา (ไม่ต้องพึ่ง Global)
    """
    mapped_key = TTS_MAPPING.get(speaker_type, "male")
    
    if TTS_MODE == "API":
        return _generate_via_api(text, mapped_key)
    else:
        return _generate_via_local(text, mapped_key, models, tokenizers)

def _generate_via_api(text: str, model_key: str) -> Optional[AudioSegment]:
    model_id = f"mms-tts-tha-{model_key}-v1" if model_key == "narrator" else f"mms-tts-tha-{model_key}-v2"
    payload = {"text": text, "model_id": model_id, "lang": "tha"}
    
    try:
        response = requests.post(TTS_API_URL, json=payload, timeout=30)
        response.raise_for_status()
        audio_data = BytesIO(response.content)
        return AudioSegment.from_file(audio_data)
    except Exception as e:
        print(f"   [!] API TTS Failed: {e}", flush=True)
        return None

def _generate_via_local(text: str, model_key: str, models: Dict, tokenizers: Dict) -> Optional[AudioSegment]:
    if model_key not in models:
        print(f"   [!] Model '{model_key}' was not loaded for this batch.", flush=True)
        return None

    try:
        tokenizer = tokenizers[model_key]
        model = models[model_key]

        inputs = tokenizer(text, return_tensors="pt")

        with torch.no_grad():
            output = model(**inputs).waveform
        
        waveform = output[0].numpy()
        audio_data_int16 = (waveform * 32767).astype(np.int16)
        
        audio_segment = AudioSegment(
            audio_data_int16.tobytes(), 
            frame_rate=model.config.sampling_rate, 
            sample_width=2, 
            channels=1
        )
        
        return audio_segment

    except Exception as e:
        print(f"   [!] Local Inference Failed for '{text[:10]}...': {e}", flush=True)
        return None

def get_dialogue_genders_from_ai(context_text: str, dialogue_texts: List[str]) -> List[str]:
    # ... (ส่วน AI Code เดิม ไม่เปลี่ยนแปลง) ...
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
            print(f"   [!] AI Gender Analysis failed: {e}. Retrying in {delay}s...", flush=True)
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
        
        segment = {
            "text": part,
            "type": "dialogue" if is_quote else "narrator"
        }
        
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
    # [TIMER START]
    start_time = time.time()
    print(f"--------------------------------------------------", flush=True)
    print(f"[Time] Processing started at: {time.strftime('%X')}", flush=True)
    print(f"[Phase 1] Fetching Data & Analyzing Text (AI)...", flush=True)

    statement = (
        select(chunkContent)
        .where(chunkContent.chapterId == chapter_id)
        .order_by(chunkContent.chunkNumber)
    )
    chunks = session.exec(statement).all()
    
    if not chunks:
        raise HTTPException(status_code=404, detail="No chunks found")

    total_chunks = len(chunks)
    
    # ตัวแปรเก็บผลลัพธ์การวิเคราะห์ทั้งหมด
    all_chunks_data = {} 
    # Set เก็บว่าเราต้องใช้เสียงใครบ้าง (เพื่อไปโหลดโมเดลทีเดียว)
    required_speaker_types = set()

    # ---------------------------------------------------------
    # WAVE 1 & 2: แยกประโยค (Regex) และ วิเคราะห์เพศ (AI)
    # ---------------------------------------------------------
    for index, chunk in enumerate(chunks):
        print(f"   [Analyze] Chunk {chunk.chunkNumber}/{total_chunks}...", flush=True)
        
        target_text = chunk.chunkDetail.replace('\n', ' ')
        target_text = re.sub(r'\s+', ' ', target_text).strip()
        
        # Prepare Context
        start_idx = max(0, min(index - 1, total_chunks - 3))
        end_idx = min(total_chunks, start_idx + 3)
        context_chunks_list = chunks[start_idx:end_idx]
        context_text_raw = " ".join([c.chunkDetail for c in context_chunks_list])
        context_text = re.sub(r'\s+', ' ', context_text_raw.replace('\n', ' ')).strip()
        
        segments = []
        has_quotes = '"' in target_text or '“' in target_text or '”' in target_text
        
        if not has_quotes:
            segments = [{"text": target_text, "type": "narrator"}]
        else:
            segments = extract_dialogue_and_gender(target_text, context_text)
        
        # เก็บ segments ไว้ก่อน
        all_chunks_data[chunk.chunkNumber] = segments
        
        # เก็บว่าต้องใช้เสียงใครบ้าง
        for seg in segments:
            required_speaker_types.add(seg["type"])

    # ---------------------------------------------------------
    # WAVE 3: โหลดโมเดล -> สร้างเสียง -> คืน Memory
    # ---------------------------------------------------------
    print(f"\n[Phase 2] Loading required TTS models...", flush=True)
    
    # 1. หาว่าต้องใช้โมเดลไฟล์ไหนบ้าง
    needed_model_keys = set()
    for st in required_speaker_types:
        mapped = TTS_MAPPING.get(st, 'male') # unknown -> male
        needed_model_keys.add(mapped)
    
    # 2. โหลดโมเดล (Local Scope เท่านั้น)
    local_models, local_tokenizers = load_specific_models(needed_model_keys)
    
    print(f"\n[Phase 3] Generating Audio...", flush=True)
    analysis_result = {}
    combined_audio = AudioSegment.empty()
    gap_segment = AudioSegment.silent(duration=AUDIO_GAP_MS)
    generated_segments_count = 0

    # 3. วนลูปสร้างเสียงจากข้อมูลที่วิเคราะห์ไว้แล้ว
    # เรียงลำดับตาม chunkNumber
    sorted_chunk_nums = sorted(all_chunks_data.keys())
    
    for chunk_num in sorted_chunk_nums:
        segments = all_chunks_data[chunk_num]
        print(f"   [Audio] Generating Chunk {chunk_num}...", flush=True)
        
        chunk_audio_duration_ms = 0
        
        for seg in segments:
            text_part = seg["text"]
            speaker_type = seg["type"]
            clean_text = text_part.replace('"', '').replace('“', '').replace('”', '')
            
            # ส่ง local_models เข้าไป
            audio_seg = generate_tts_with_loaded_models(
                clean_text, speaker_type, local_models, local_tokenizers
            )
            
            if audio_seg:
                segment_duration = len(audio_seg) + len(gap_segment)
                chunk_audio_duration_ms += segment_duration
                
                combined_audio += audio_seg
                combined_audio += gap_segment
                generated_segments_count += 1
        
        analysis_result[str(chunk_num)] = {
            "segments": segments,
            "duration": chunk_audio_duration_ms / 1000.0
        }

    # 4. Clean up Memory ทันทีหลังสร้างเสียงเสร็จ
    print(f"\n[Cleanup] Unloading models to free RAM...", flush=True)
    del local_models
    del local_tokenizers
    gc.collect() # บังคับคืน RAM
    
    # ---------------------------------------------------------
    # SAVE FILE & FINISH
    # ---------------------------------------------------------
    if len(combined_audio) > 0:
        output_dir = os.path.abspath("public/storage/sound")
        os.makedirs(output_dir, exist_ok=True)
        output_filename = f"{chapter_id}.mp3"
        output_file_path = os.path.join(output_dir, output_filename)
        
        print(f"[+] Saving audio to: {output_file_path}", flush=True)
        try:
            combined_audio.export(output_file_path, format="mp3")
            if os.path.exists(output_file_path):
                analysis_result["audio_status"] = "success"
                analysis_result["audio_file_path"] = output_file_path
            else:
                analysis_result["audio_status"] = "error_file_missing"
        except Exception as e:
            analysis_result["audio_status"] = f"error_exporting: {str(e)}"
    else:
        analysis_result["audio_status"] = "no_audio_generated"

    # [TIMER END]
    end_time = time.time()
    total_duration = end_time - start_time
    print(f"--------------------------------------------------", flush=True)
    print(f"[Time] Total processing time: {total_duration:.2f} seconds", flush=True)
    print(f"--------------------------------------------------", flush=True)
    
    analysis_result["total_processing_time_seconds"] = total_duration

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