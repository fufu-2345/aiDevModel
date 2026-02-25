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
from models import chunkContent, matcher

router = APIRouter(
    prefix="/sound",
    tags=["sound"]
)

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "gemma3:12b"
TTS_MODE = "LOCAL" 
TTS_API_URL = "http://localhost:5000/tts"

TTS_LOCAL_PATHS = {
    "narrator": "sound/new/male1",
    "male": "sound/new/male2",
    "female": "sound/new/female2"
}
TTS_MAPPING = {
    "narrator": "narrator", 
    "male": "male",         
    "female": "female",     
    "unknown": "male"       
}

AUDIO_GAP_MS = 1000 

def load_specific_models(needed_keys: Set[str]) -> tuple:
    """
    โหลดโมเดลเฉพาะที่จำเป็นต้องใช้ในรอบนั้นๆ และคืนค่ากลับไปเป็น Dict
    """
    if TTS_MODE != "LOCAL":
        return {}, {}

    print(f"[Init] Loading specific TTS models: {needed_keys}...", flush=True)

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
            device = "cuda" if torch.cuda.is_available() else "cpu"
            tokenizers[key] = AutoTokenizer.from_pretrained(abs_path)
            print(device)
            models[key] = VitsModel.from_pretrained(abs_path).to(device)
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

        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(device)
        inputs = tokenizer(text, return_tensors="pt").to(device)

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
    output_file_path = os.path.abspath(f"public/storage/sound/{chapter_id}.mp3")
    if os.path.exists(output_file_path):
        # print(f"{chapter_id}.mp3 is already exist", flush=True)
        return {
            "audio_status": "already_exists",
            "audio_file_path": output_file_path,
            "message": f"{chapter_id}.mp3 is already exist"
        }
    
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
    all_chunks_data = {} 
    required_speaker_types = set()
    for index, chunk in enumerate(chunks):
        print(f"   [Analyze] Chunk {chunk.chunkNumber}/{total_chunks}...", flush=True)
        
        target_text = chunk.chunkDetail.replace('\n', ' ')
        target_text = re.sub(r'\s+', ' ', target_text).strip()
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
        all_chunks_data[chunk.chunkNumber] = segments
        for seg in segments:
            required_speaker_types.add(seg["type"])
    print(f"\n[Phase 2] Loading required TTS models...", flush=True)
    needed_model_keys = set()
    for st in required_speaker_types:
        mapped = TTS_MAPPING.get(st, 'male') 
        needed_model_keys.add(mapped)
    local_models, local_tokenizers = load_specific_models(needed_model_keys)
    print(f"\n[Phase 3] Generating Audio...", flush=True)
    analysis_result = {}
    combined_audio = AudioSegment.empty()
    gap_segment = AudioSegment.silent(duration=AUDIO_GAP_MS)
    generated_segments_count = 0
    sorted_chunk_nums = sorted(all_chunks_data.keys())
    for chunk_num in sorted_chunk_nums:
        segments = all_chunks_data[chunk_num]
        print(f"   [Audio] Generating Chunk {chunk_num}...", flush=True)
        chunk_audio_duration_ms = 0
        for seg in segments:
            text_part = seg["text"]
            speaker_type = seg["type"]
            clean_text = text_part.replace('"', '').replace('“', '').replace('”', '')
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
    print(f"\n[Cleanup] Unloading models to free RAM...", flush=True)
    del local_models
    del local_tokenizers
    gc.collect()
    
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
    print(f"[Database] Inserting duration data to matcher table...", flush=True)
    chunk_id_map = {str(c.chunkNumber): c.id for c in chunks}
    print(f"[Debug] chunk_id_map: {chunk_id_map}", flush=True)

    try:
        for chunk_num_str, data in analysis_result.items():
            if chunk_num_str in ["audio_status", "audio_file_path", "total_processing_time_seconds"]: 
                continue
            if isinstance(data, dict) and "duration" in data:
                chunk_id = chunk_id_map.get(chunk_num_str)
                print(f"   [DB] Chunk {chunk_num_str}: {data['duration']}s | mapped chunkContentId: {chunk_id}", flush=True)
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