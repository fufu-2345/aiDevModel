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
from routes import movies, uploadPDF

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

def flush_memory():
    gc.collect()
    try:
        torch.cuda.empty_cache()
    except:
        pass

def load_image_pipe():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch_dtype = torch.float16 if device == "cuda" else torch.float32
    
    is_xl = "xl" in stabilityModel.lower()
    is_safetensors = stabilityModel.endswith(".safetensors")
    PipelineClass = StableDiffusionXLPipeline if is_xl else StableDiffusionPipeline
    
    if is_safetensors:
            pipe = PipelineClass.from_single_file(
            stabilityModel,
            use_safetensors=True,
            torch_dtype=torch_dtype
        )
    else:
        pipe = PipelineClass.from_pretrained(
            stabilityModel,
            torch_dtype=torch_dtype,
            use_safetensors=True
        )

    if hasattr(pipe, "safety_checker"):
        pipe.safety_checker = None
    if hasattr(pipe, "requires_safety_checker"):
        pipe.requires_safety_checker = False
    if hasattr(pipe, "watermarker"):
        pipe.watermarker = None
        
    pipe.to(device)    
    
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
    OVERLAP =  1          
    
    raw_chunks = [] # เก็บ List ของ (text_thai)
    
    if total_lines <= LINES_PER_CHUNK:
        raw_chunks.append(chapter.chapterDetail)
    else: 
        step = LINES_PER_CHUNK - OVERLAP
        for i in range(0, total_lines, step):
            chunk_lines = lines[i : i + LINES_PER_CHUNK]
            # ถ้าเหลือเศษบรรทัดน้อยเกินไป (เช่น 1-2 บรรทัด) ไม่ต้องแยกก้อนใหม่ ให้รวมกับก้อนสุดท้ายไปเลย (ถ้าทำได้) หรือ break ไป
            if len(chunk_lines) < 3 and len(raw_chunks) > 0:
                # จริงๆ ตรงนี้ logic เดิมของคุณคือ break ทิ้งไปเลย ซึ่งอาจทำให้เนื้อหาตอนจบหายได้
                # แต่ผมคง logic เดิมไว้ตามที่คุณให้มาครับ
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
        
        # 2. [เพิ่มใหม่] ส่ง Eng text ไปให้ AI วาดรูป
        # เรา await ตรงนี้เลย เพื่อให้ได้ URL ก่อนบันทึกลง DB
        image_url = await generate_image_from_text(eng_text)
        
        # 3. สร้าง Object ลง DB (ตอนนี้ picRef มีค่าแล้ว!)
        new_chunk = chunkContent(
            chunkNumber = idx + 1,
            chunkDetail = eng_text, 
            picRef = image_url,     # <--- ใส่ URL รูปที่ได้มาตรงนี้
            chapterId = chapter_id
        )
        
        session.add(new_chunk)
        saved_chunks_count += 1
        
        # พักหายใจ 1 วินาที (รวมกับเวลา Gen รูป Loop นึงอาจใช้เวลา 3-4 วิ)
        await asyncio.sleep(1) 

        # commit ทีเดียวนอก Loop หรือใน Loop ก็ได้ตาม Logic Transaction ที่วางไว้
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

# เหลือ test
def get_mask_coordinates(position_keyword, width=IMG_WIDTH, height=IMG_HEIGHT):
    """แปลง Keyword ตำแหน่ง เป็นพิกัดสำหรับ Mask"""
    p = position_keyword.upper()
    margin_top = 100 # เว้นที่ว่างด้านบนไว้หน่อย กันหัวขาด
    
    if "LEFT" in p:
        return (0, margin_top, width // 2, height)
    elif "RIGHT" in p:
        return (width // 2, margin_top, width, height)
    elif "CENTER" in p:
        return (width // 4, margin_top, (width * 3) // 4, height)
    else:
        return (width // 4, margin_top, (width * 3) // 4, height) # Default กลาง

# ==========================================
# 4. STEP 1: SCENE ANALYSIS (LLM)
# ==========================================

async def analyze_scene_plan(chunk_text: str, client: httpx.AsyncClient):
    """
    ให้ AI (LLM) อ่านเนื้อหา Chunk แล้วสร้าง 'Visual Prompt' และแผนผังตำแหน่ง
    """
    prompt = f"""
    Role: AI Visual Director.
    Task: Convert the story chunk into a structured Visual Prompt for Stable Diffusion.
    
    Input Story:
    "{chunk_text}"

    Rules:
    1. 'environment': Describe the background scene vividly (style, lighting, location).
    2. 'characters': List characters present. Keep names EXACTLY as in text.
    3. 'position': Assign [LEFT, CENTER, RIGHT, BACKGROUND].
    4. 'visual_action': Describe pose/action (e.g., "sitting on a chair", "holding a sword").

    Output JSON Format:
    {{
        "environment": "A dimly lit tavern with wooden tables, candlelight style",
        "characters": [
            {{
                "name": "Alice",
                "position": "LEFT",
                "visual_action": "looking surprised, hand on mouth"
            }},
            {{
                "name": "Bob",
                "position": "RIGHT",
                "visual_action": "standing confidently, arms crossed"
            }}
        ]
    }}
    """

    payload = {
        "model": extractModel,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.3, "num_ctx": 4096}
    }

    try:
        response = await client.post(ollamaURL, json=payload, timeout=60.0)
        response.raise_for_status()
        result_text = response.json().get("response", "")
        
        match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return None
    except Exception as e:
        print(f"❌ Scene Analysis Error: {e}")
        return None

# ==========================================
# 5. STEP 2: DB LOOKUP
# ==========================================

def find_character_refpath(session: Session, movie_id: int, name_query: str) -> Optional[str]:
    """หา Path รูปตัวละครจากชื่อ (รองรับชื่อเล่น)"""
    if not name_query: return None
    name_query = name_query.strip()

    # 1. หาจากชื่อจริง
    char = session.exec(select(character).where(
        character.movieId == movie_id,
        character.name.ilike(f"%{name_query}%")
    )).first()
    if char and char.refpath: return char.refpath

    # 2. หาจากชื่อเล่น (AltNames)
    alt = session.exec(select(character).join(altCharacter).where(
        character.movieId == movie_id,
        altCharacter.altName.ilike(f"%{name_query}%")
    )).first()
    if alt and alt.refpath: return alt.refpath

    return None

# ==========================================
# 6. STEP 3: IMAGE GENERATION (SDXL)
# ==========================================

def run_sdxl_pipeline(scene_plan: dict, movie_id: int, session: Session, output_path: str):
    """
    ฟังก์ชันหลักในการ Gen รูป (รันแบบ Synchronous เพราะ GPU ทำงานขนานไม่ได้)
    """
    print(f"🎨 Generating: {output_path}")
    
    # --- 6.1 Prepare Data ---
    # ใช้ Global Variables
    width, height = IMG_WIDTH, IMG_HEIGHT
    
    people_to_gen = []
    base_prompt = f"{scene_plan.get('environment', 'scene')}, masterpiece, best quality, 4k, 8k"
    
    # ตรวจสอบตัวละครและ Ref Path
    for char_info in scene_plan.get('characters', []):
        name = char_info.get('name')
        ref_path = find_character_refpath(session, movie_id, name)
        action = char_info.get('visual_action', '')
        
        if ref_path and os.path.exists(ref_path):
            people_to_gen.append({
                "refpath": ref_path,
                "position": char_info.get('position', 'CENTER'),
                "prompt": f"{action}, {name}, masterpiece"
            })
            print(f"   found ref for {name}: {ref_path}")
        else:
            # ไม่มี Ref ให้ใส่ใน Base Prompt แทน
            base_prompt += f", {name} {action}"

    # --- 6.2 Load Model (Using Custom Loader) ---
    try:
        # ใช้ฟังก์ชัน load_image_pipe ที่เราสร้างใหม่
        pipe = load_image_pipe()

        # Load IP-Adapter
        # ต้องโหลดหลังจากได้ pipe มาแล้ว
        print(f"   Loading IP-Adapter from {IP_ADAPTER_REPO}...")
        
        # ปรับแก้ให้รองรับทั้ง Local Path และ Repo Path
        # ถ้า IP_ADAPTER_SUBFOLDER เป็นค่าว่าง ให้ใส่เป็น None หรือไม่ใส่ argument subfolder ก็ได้
        # แต่เพื่อความง่าย เราใส่ None ไปเลยถ้าเป็น ""
        subfolder_arg = IP_ADAPTER_SUBFOLDER if IP_ADAPTER_SUBFOLDER else None
        
        pipe.load_ip_adapter(
            IP_ADAPTER_REPO, 
            subfolder=subfolder_arg, 
            weight_name=IP_ADAPTER_FILENAME
        )
        
        # --- 6.3 Generate Base Image ---
        pipe.set_ip_adapter_scale(0.0) # ปิด IP-Adapter ก่อน
        base_image = pipe(
            prompt=base_prompt, 
            height=height, width=width, 
            num_inference_steps=30
        ).images[0]

        # --- 6.4 Sequential Inpainting (Loop แปะคน) ---
        for p in people_to_gen:
            print(f"   Inpainting character at {p['position']}...")
            
            # สร้าง Mask
            coords = get_mask_coordinates(p['position'], width, height)
            mask = Image.new("L", (width, height), 0)
            draw = ImageDraw.Draw(mask)
            draw.rectangle(coords, fill=255)
            
            # โหลดรูป Ref
            ref_image = Image.open(p['refpath']).convert("RGB")
            
            # สั่ง Gen ทับลงไป
            pipe.set_ip_adapter_scale(0.7) # ความแรงหน้า (0.6-0.8)
            base_image = pipe(
                prompt=p['prompt'],
                image=base_image,
                mask_image=mask,
                ip_adapter_image=ref_image,
                num_inference_steps=30,
                strength=0.9 # แรงๆ เพื่อให้เปลี่ยนรูปทรงคนให้เข้ากับท่าทางใหม่
            ).images[0]

        # --- 6.5 Save ---
        base_image.save(output_path)
        print(f"✅ Saved to {output_path}")
        return True

    except Exception as e:
        print(f"❌ Error in SDXL: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Clear Memory ทันที
        if 'pipe' in locals(): del pipe
        flush_memory()

# ==========================================
# 7. MAIN ENDPOINT
# ==========================================

@app.post("/generate-images/{chapter_id}")
async def generate_images_for_chapter(
    chapter_id: int, 
    session: Session = Depends(get_session)
):
    """
    1. ดึง Chunks ของ Chapter นี้
    2. วนลูป Gen ทีละรูป
    3. Save ลง public/storage/pic/
    4. Update DB
    """
    # 1. Fetch chunks
    chunks = session.exec(select(chunkContent).where(chunkContent.chapterId == chapter_id)).all()
    if not chunks:
        return {"status": "error", "message": "No chunks found. Run /create-chunks first."}
    
    # Fetch Chapter info for Movie ID
    chapter_info = session.get(chapterContent, chapter_id)
    if not chapter_info:
        raise HTTPException(status_code=404, detail="Chapter info not found")
    movie_id = chapter_info.movieId

    success_count = 0
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        for chunk in chunks:
            # Skip ถ้ามีรูปแล้ว (หรือจะเอาออกถ้าอยาก Gen ทับ)
            if chunk.picRef:
                print(f"Skipping Chunk {chunk.chunkNumber}: Already exists.")
                continue

            print(f"--- Processing Chunk {chunk.chunkNumber} ---")
            
            # Step A: Get Vision Prompt from AI
            scene_plan = await analyze_scene_plan(chunk.chunkDetail, client)
            
            if not scene_plan:
                print("Failed to analyze scene. Skipping.")
                continue
                
            # Step B: Prepare Filename
            filename = f"ch{chapter_id}_chunk{chunk.chunkNumber}_{int(time.time())}.png"
            full_path = os.path.join(OUTPUT_DIR, filename)
            
            # Step C: Run SDXL (Run in thread pool to not block async loop)
            # เราใช้ asyncio.to_thread เพราะ run_sdxl_pipeline เป็น synchronous (Blocking)
            is_generated = await asyncio.to_thread(
                run_sdxl_pipeline, 
                scene_plan, 
                movie_id, 
                session, 
                full_path
            )
            
            if is_generated:
                # Step D: Update DB
                chunk.picRef = full_path
                session.add(chunk)
                session.commit()
                success_count += 1
            else:
                print("Failed to generate image.")

    return {
        "status": "completed",
        "chapter_id": chapter_id,
        "images_generated": success_count,
        "output_directory": OUTPUT_DIR
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

# --------------------------------------------------------------

import base64
import uuid

MODEL_PATH = r"C:\stability matrix\Data\Models\StableDiffusion\juggernautXL_ragnarokBy.safetensors"
STORAGE_DIR = "storage/thumbnail"

os.makedirs(STORAGE_DIR, exist_ok=True)

# Global Variables
pipe = None
startup_error = None # เพิ่มตัวแปรเก็บ Error เพื่อแจ้ง User
device = "cuda" if torch.cuda.is_available() else "cpu"

@app.on_event("startup")
def load_model_global():
    """
    โหลด Model ครั้งเดียวตอนเปิด Server (แก้ปัญหาช้า)
    เลียนแบบ Logic จากโค้ดเก่าของคุณ
    """
    global pipe, MODEL_PATH, startup_error
    
    print(f"\n⚙️  Starting System on: {device}")
    print(f"📂 Loading Model: {MODEL_PATH}")

    try:
        start_time = time.perf_counter()
        
        # 1. ตรวจสอบว่าเป็น SDXL หรือไม่ (ตาม Logic โค้ดเก่า)
        is_xl = "xl" in MODEL_PATH.lower()
        is_safetensors = MODEL_PATH.endswith(".safetensors")
        
        PipelineClass = StableDiffusionXLPipeline if is_xl else StableDiffusionPipeline
        torch_dtype = torch.float16 if device == "cuda" else torch.float32

        print(f"   Using Pipeline: {PipelineClass.__name__}")

        # 2. โหลด Model (ใช้ diffusers หาไฟล์เอง ไม่ต้องใช้ os.path เช็คดักหน้า)
        pipe = PipelineClass.from_single_file(
            MODEL_PATH,
            use_safetensors=is_safetensors,
            torch_dtype=torch_dtype,
            local_files_only=True # บังคับหาในเครื่องเท่านั้น
        )
        
        # 3. ปิด Safety Checker & Watermark (ตามโค้ดเก่าเพื่อความเร็ว)
        if hasattr(pipe, "safety_checker"):
            pipe.safety_checker = None
        if hasattr(pipe, "requires_safety_checker"):
            pipe.requires_safety_checker = False
        if hasattr(pipe, "watermarker"):
            pipe.watermarker = None

        # ย้ายไป GPU
        pipe.to(device)
        
        # เพิ่มเติม: เปิด Memory Efficient Attention ถ้าใช้ xformers ได้
        try:
            pipe.enable_xformers_memory_efficient_attention()
        except:
            pass

        print(f"✅ Model Loaded Successfully in {time.perf_counter() - start_time:.2f}s")
        startup_error = None # เคลียร์ Error ถ้าโหลดสำเร็จ

    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error Loading Model: {error_msg}")
        print("   (Server will start, but /generate will fail)")
        # เก็บ Error ไว้บอก User ตอนเรียก API
        startup_error = error_msg

@app.get("/generate")
def generate_image(prompt: str = "A futuristic city"):
    print("a")
    global pipe, startup_error
    
    if pipe is None:
        error_detail = "Model setup failed."
        if startup_error:
            error_detail += f" Reason: {startup_error}"
            print("b")
        else:
            error_detail += " Check console logs for more info."
            print("c")
            
        raise HTTPException(status_code=500, detail=error_detail)

    start = time.perf_counter()
    print(f"🎨 Generating: {prompt}")
    
    try:
        negative_prompt = "blurry, low quality, distorted, text, watermark"

        # ขนาดรูปตามโค้ดเก่าของคุณ (640x1280)
        # หมายเหตุ: SDXL แนะนำ 1024x1024 แต่ถ้าคุณชอบ Ratio นี้ก็ตามนี้ครับ
        image = pipe(
            prompt=prompt, 
            negative_prompt=negative_prompt, 
            num_inference_steps=20,
            height=1024, # ปรับเป็น 1024 เพื่อคุณภาพที่ดีที่สุดของ SDXL (หรือแก้กลับเป็น 640 ตามเดิมได้)
            width=1024   # ปรับเป็น 1024 (หรือแก้กลับเป็น 1280 ตามเดิมได้)
        ).images[0]
        
        filename = f"{uuid.uuid4()}.png"
        file_path = os.path.join(STORAGE_DIR, filename)
        
        image.save(file_path)
        
        print(f"✅ Done in {time.perf_counter() - start:.3f}s -> {file_path}")
        return FileResponse(file_path, media_type="image/png")

    except Exception as e:
        if "out of memory" in str(e).lower():
            torch.cuda.empty_cache()
            raise HTTPException(status_code=500, detail="GPU OOM")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/")
def root():
    return "server is worked 111"

@app.get("/test")
def root():
    return "test test 222"

@app.post("/")
def root():
    return "test post 333"