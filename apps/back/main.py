from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from sqlmodel import Session, select
from typing import List
from fastapi.staticfiles import StaticFiles
import asyncio
import requests
import json
import os
import time
import gc
import re
import httpx
import torch
from googletrans import Translator
from diffusers import StableDiffusionPipeline, StableDiffusionXLPipeline
from services import save_extraction_result

from database import create_db_and_tables, get_session
from models import movieTitle, chapterContent, chunkContent, character, altCharacter, entity, altEntity
# from PIL import Image, ImageDraw
# OUTPUT_DIR = "public/storage/pic"
from routes import movies, uploadPDF, createPic, extract, sound

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)
translator = Translator()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ollamaURL = "http://localhost:11434/api/generate"
extractModel = "gemma3:12b"
stabilityModel = "C:\\stability matrix\\Data\\Models\\StableDiffusion\\juggernautXL_ragnarokBy.safetensors"
# stabilityModel2 ="C:\\stability matrix\\Data\\Models\\StableDiffusion\\revAnimated_v2Rebirth.safetensors"
# lora = r"C:\stability matrix\Data\Models\Lora\Wuxia-PONY-PAseer.safetensors"
app.mount("/static", StaticFiles(directory="public"), name="static")

IMG_WIDTH = 1280
IMG_HEIGHT = 720
IP_ADAPTER_REPO = "h94/IP-Adapter" 
IP_ADAPTER_SUBFOLDER = "sdxl_models" 
IP_ADAPTER_FILENAME = "ip-adapter-plus-face_sdxl_vit-h.bin"

app.include_router(movies.router)
app.include_router(uploadPDF.router)
app.include_router(createPic.router)
app.include_router(extract.router)
app.include_router(sound.router)

def load_image_pipe():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch_dtype = torch.float16 if device == "cuda" else torch.float32
    
    is_xl = "xl" in stabilityModel.lower()
    is_safetensors = stabilityModel.endswith(".safetensors")
    PipelineClass = StableDiffusionXLPipeline if is_xl else StableDiffusionPipeline
    
    common_args = {
        "torch_dtype": torch_dtype,
        "low_cpu_mem_usage": True,
    }
    if is_safetensors:
        pipe = PipelineClass.from_single_file(
            stabilityModel,
            **common_args
        )
    else:
        pipe = PipelineClass.from_pretrained(
            stabilityModel,
            variant="fp16" if device == "cuda" else None,
            **common_args
        )
    if hasattr(pipe, "safety_checker"):
        pipe.safety_checker = None
    if hasattr(pipe, "requires_safety_checker"):
        pipe.requires_safety_checker = False
    if hasattr(pipe, "watermarker"):
        pipe.watermarker = None
    pipe.to(device, dtype=torch_dtype) 
    
    # if os.path.exists(loraPath):
    #     print(f"Loading LoRA: {loraPath}")
    #     pipe.load_lora_weights(loraPath)
        
    return pipe

#---------------------------------------
#---------------------------------------
#---------------------------------------

async def generate_image_from_text(prompt: str) -> str:
    try:
        # --- ตรงนี้คือส่วนที่คุณต้องใส่ Logic เชื่อมต่อ API ---
        # ตัวอย่าง: response = await client.images.generate(prompt=prompt, ...)
        # return response.data[0].url
        print(f"🎨 Generating image for: {prompt[:30]}...")
        return "https://example.com/generated-image.jpg" 
    except Exception as e:
        print(f"Error generating image: {e}")
        return ""
    
async def translate_text(text: str, retries=3) -> str:
    for attempt in range(retries):
        try:
            result = await translator.translate(text, src='th', dest='en')
            if result and result.text:
                return result.text
        except Exception as e:
            print(f"Translation error (Attempt {attempt+1}): {e}")
            await asyncio.sleep(1) # พักแป๊บนึงแล้วลองใหม่
    return text # ถ้าแปลไม่ได้จริงๆ ให้คืนค่าเดิมกลับไปกัน error

# ==========================================
# 4. API ENDPOINT
# ==========================================

# createchunks
@app.get("/create-chunks/{chapter_id}")
async def create_chunks_for_chapter(
    chapter_id: int, 
    session: Session = Depends(get_session)
):
    start_time = time.perf_counter()
    
    # 1. ดึงข้อมูล Chapter
    chapter = session.get(chapterContent, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    if not chapter.chapterDetail:
        return {"status": "failed", "reason": "No content in chapterDetail"}

    # ลบ Chunks เก่าทิ้งก่อน (ถ้ามี) เพื่อไม่ให้ข้อมูลซ้ำซ้อนเวลารันซ้ำ
    existing_chunks = session.exec(select(chunkContent).where(chunkContent.chapterId == chapter_id)).all()
    for old_chunk in existing_chunks:
        session.delete(old_chunk)
    session.commit()

    # 2. เริ่มหั่น (Chunking Logic)
    lines = chapter.chapterDetail.split('\n')
    total_lines = len(lines)
    
    LINES_PER_CHUNK = 5  
    OVERLAP = 1          
    
    raw_chunks = [] # เก็บ List ของ (text_thai)
    
    if total_lines <= LINES_PER_CHUNK:
        raw_chunks.append(chapter.chapterDetail)
    else: 
        step = LINES_PER_CHUNK - OVERLAP
        for i in range(0, total_lines, step):
            chunk_lines = lines[i : i + LINES_PER_CHUNK]
            
            # Logic เดิม: ถ้าเหลือน้อยกว่า 3 บรรทัดจะข้ามไป
            # (ระวังเนื้อหาตอนท้ายหาย หากประโยคสุดท้ายสั้นเกินไป)
            if len(chunk_lines) < 3 and len(raw_chunks) > 0:
                break 
            
            chunk_text = "\n".join(chunk_lines)
            raw_chunks.append(chunk_text)

    print(f"Processing Chapter {chapter_id}: Found {len(raw_chunks)} chunks.")

    # 3. Loop แปลและบันทึก
    saved_chunks_count = 0
    
    for idx, thai_text in enumerate(raw_chunks):
        print(f"Processing chunk {idx+1}/{len(raw_chunks)}...")

        # 1. แปลเป็น Eng
        eng_text = await translate_text(thai_text)
        
        # 2. สร้าง Object ลง DB (ตัดส่วน generate_image ออก)
        new_chunk = chunkContent(
            chunkNumber = idx + 1,
            chunkDetail = eng_text, 
            picRef = None,           # ไม่ใส่ URL รูปภาพแล้ว
            chapterId = chapter_id
        )
        
        session.add(new_chunk)
        saved_chunks_count += 1
        
        # พักหายใจสั้นๆ เพื่อป้องกัน Rate Limit ของ API แปลภาษา
        await asyncio.sleep(0.5) 

    # commit ทั้งหมดหลังจากจบ Loop
    session.commit()
    
    duration = time.perf_counter() - start_time
    
    return {
        "status": "success",
        "chapter_id": chapter_id,
        "total_chunks_created": saved_chunks_count,
        "duration_seconds": f"{duration:.2f}",
        "message": "Chunks have been translated and saved to chunkContent table."
    }

#-----------------------------------
#-----------------------------------
#-----------------------------------

# gen ปก(ยังไม่ RAG)
@app.get("/genPic/{chapterId}") 
def genPic(chapterId: int, session: Session = Depends(get_session)):
    start = time.perf_counter()
    try:
        chapter = session.get(chapterContent, chapterId)
        if not chapter:
            raise HTTPException(status_code=404, detail="Chapter not found")
        prompt = getattr(chapter, "chapterDetailEng", None)
        if not prompt:
            print("Warning: chapterDetailEng not found or empty, falling back to chapterTitle")
            prompt = chapter.chapterTitle
        if not prompt:
            print(f"Error: no promt for "+chapterId)
            raise HTTPException(status_code=500, detail=f"Error: no promt for "+chapterId)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        torch_dtype = torch.float16 if device == "cuda" else torch.float32
        is_xl = "xl" in stabilityModel.lower()
        is_safetensors = stabilityModel.endswith(".safetensors")
        PipelineClass = StableDiffusionXLPipeline if is_xl else StableDiffusionPipeline
        ################################################ ช้าถ้าเลือก model ได้แล้วอย่าลืมดึงออกไปไว้ global
        pipe = PipelineClass.from_single_file(
            stabilityModel,
            use_safetensors=is_safetensors,
            torch_dtype=torch_dtype
        )
        ################################################
        if hasattr(pipe, "safety_checker"):
            pipe.safety_checker = None
        if hasattr(pipe, "requires_safety_checker"):
            pipe.requires_safety_checker = False
        if hasattr(pipe, "watermarker"):
            pipe.watermarker = None
        pipe.to(device)
        negative_prompt = "blurry, low quality, distorted, text, watermark"
        image = pipe(
            prompt=prompt, 
            negative_prompt=negative_prompt, 
            num_inference_steps=20,
            height=640, # 640/2
            width=1280  # 1280/2
        ).images[0]
        outputFilename = f"storage/thumbnail/{chapterId}.png"
        image.save("public/"+outputFilename)
        chapter.picPath = outputFilename
        session.add(chapter)
        session.commit()
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Processing Error: {str(e)}")
    print(f"genPic Time: {time.perf_counter() - start:.3f} seconds")
    return {"status": "success", "path": outputFilename}

# -----------------------------------------------------------------
# -----------------------------------------------------------------
# -----------------------------------------------------------------

CHUNK_SIZE_LIMIT = 1000 
SLEEP_BETWEEN_CHUNKS = 1
DEFAULT_CHUNK_SIZE = 600.0

def smart_chunker(text: str, max_length: int) -> List[str]:
    paragraphs = text.split('\n')
    chunks = []
    current_chunk = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
            
        if len(current_chunk) + len(para) <= max_length:
            current_chunk += para + "\n\n"
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = para + "\n\n"
    
    if current_chunk:
        chunks.append(current_chunk.strip())
        
    return chunks

def clean_json_string(json_str: str) -> str:
    """
    ฟังก์ชันช่วยทำความสะอาด String ก่อนแปลงเป็น JSON
    (เผื่อ AI ตอบมามี markdown ```json ... ``` ติดมาด้วย)
    """
    pattern = r"```json(.*?)```"
    match = re.search(pattern, json_str, re.DOTALL)
    if match:
        return match.group(1).strip()
    return json_str.strip()

def call_ollama_via_http(prompt_text: str, model: str) -> str:
    system_prompt = (
        "You are an expert AI art director and Named Entity Recognition (NER) system. "
        "Analyze the following story segment. "
        "Perform two tasks:\n"
        "1. Generate 'visual_tags': A comma-separated Stable Diffusion prompt describing the scene visually (lighting, environment, style, character appearance).\n"
        "2. Extract 'entities': A list of specific names of characters (e.g., 'Alice', 'John') or unique named items present in the segment.\n\n"
        "IMPORTANT: You MUST return ONLY a raw JSON object. Do not add any markdown formatting or explanation.\n"
        "JSON Format example: { \"visual_tags\": \"1girl, sitting, cafe, sunset\", \"entities\": [\"Alice\"] }"
    )

    payload = {
        "model": model,
        "prompt": f"Story segment: {prompt_text}",
        "system": system_prompt,
        "stream": False,
        "format": "json"
    }
    try:
        response = requests.post(
            ollamaURL, 
            json=payload, 
            timeout=DEFAULT_CHUNK_SIZE
        )
        response.raise_for_status() 
        result_json = response.json()
        raw_response = result_json['response']
        try:
            cleaned_response = clean_json_string(raw_response)
            parsed_data = json.loads(cleaned_response)
            
            return {
                "visual_tags": parsed_data.get("visual_tags", ""),
                "entities": parsed_data.get("entities", [])
            }
        except json.JSONDecodeError:
            print(f"⚠️ JSON Parse Error. Raw: {raw_response}")
            return {
                "visual_tags": raw_response,
                "entities": []
            }
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Ollama Connection Error: {e}")
        raise e

@app.get("/generate-prompts/{chapter_id}")
async def generate_prompts(
    chapter_id: int,
    session: Session = Depends(get_session)
):  
    start=time.perf_counter()
    chapter = session.get(chapterContent, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail=f"Chapter ID {chapter_id} not found")
    text = chapter.chapterDetail
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="Chapter content is empty")
    chunks = smart_chunker(text, CHUNK_SIZE_LIMIT)
    print(f"Chunks: {len(chunks)}")
    final_results = []
    for index, chunk in enumerate(chunks):
        print(f"{index + 1}")
        chunk_result = {
            "chunk_id": index + 1,
            "thai_text": chunk,
            "english_text": "",
            "sd_prompt": "",
            "entities": [],
            "error": None
        }
        try:
            translation = await translator.translate(chunk, src='th', dest='en')
            english_text = translation.text
            # chunk_result["english_text"] = english_text
            ollama_data = call_ollama_via_http(english_text, extractModel)
            
            chunk_result["sd_prompt"] = ollama_data["visual_tags"]
            chunk_result["entities"] = ollama_data["entities"]
            time.sleep(SLEEP_BETWEEN_CHUNKS)
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            chunk_result["error"] = str(e)
            chunk_result["sd_prompt"] = "Error generating prompt"
        final_results.append(chunk_result)
        print("Time: ", time.perf_counter() - start)
    return final_results

@app.get("/")
def root():
    return "server is worked 111"

@app.get("/test")
def root():
    return "test test 222"

@app.post("/")
def root():
    return "test post 333"