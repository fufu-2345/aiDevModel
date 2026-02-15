import asyncio
import json
import re
import time
import os
import gc
import traceback
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, create_engine, SQLModel 
import httpx
from PIL import Image, ImageDraw, ImageFilter 
from dotenv import load_dotenv 

# --- STABLE DIFFUSION IMPORTS ---
import torch
from diffusers import (
    AutoPipelineForInpainting, 
    StableDiffusionXLInpaintPipeline, 
    StableDiffusionInpaintPipeline
)
from transformers import CLIPVisionModelWithProjection 

# พยายาม import psutil
try:
    import psutil
except ImportError:
    psutil = None

# ==========================================
# 1. IMPORTS & SETUP
# ==========================================
try:
    from models import (
        movieTitle,
        chapterContent,
        chunkContent,
        entity,
        altEntity,
        character,
        altCharacter
    )
except ImportError:
    try:
        from .models import (
            movieTitle,
            chapterContent,
            chunkContent,
            entity,
            altEntity,
            character,
            altCharacter
        )
    except ImportError:
        print("Error: models.py not found.")

# DB Setup
load_dotenv()

postgres_user = os.getenv("POSTGRES_USER")
postgres_password = os.getenv("POSTGRES_PASSWORD")
postgres_server = os.getenv("POSTGRES_SERVER", "localhost")
postgres_port = os.getenv("POSTGRES_PORT", "5432")
postgres_db = os.getenv("POSTGRES_DB")

pg_url = f"postgresql://{postgres_user}:{postgres_password}@{postgres_server}:{postgres_port}/{postgres_db}"
engine = create_engine(pg_url)

def get_session():
    with Session(engine) as session:
        yield session

router = APIRouter(
    prefix="/createPic",
    tags=["createPic"]
)

@router.on_event("startup")
def on_startup():
    try:
        SQLModel.metadata.create_all(engine)
    except Exception as e:
        print(f"Database connection error: {e}")

# ==========================================
# 2. CONFIGURATION
# ==========================================

OUTPUT_DIR = "public/storage/pic/"
CHAR_DIR = "public/storage/characters/" 
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 📉 คงความละเอียดนี้ไว้ เพื่อประหยัด RAM
IMG_WIDTH = 768
IMG_HEIGHT = 512
NUM_STEPS = 20 

# AI Models Configuration
ollamaURL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")
ollamaModel = os.getenv("OLLAMA_MODEL", "gemma3:12b")

# --- SDXL Configuration ---
stabilityModel = "C:\\stability matrix\\Data\\Models\\StableDiffusion\\juggernautXL_ragnarokBy.safetensors"

IP_ADAPTER_REPO = "h94/IP-Adapter" 
IP_ADAPTER_SUBFOLDER = "sdxl_models"
IP_ADAPTER_FILENAME = "ip-adapter-plus-face_sdxl_vit-h.bin"

# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================

def clean_prompt(text):
    """แปลงประโยคให้เป็น Tag สั้นๆ"""
    if isinstance(text, list): text = ", ".join(text)
    if not isinstance(text, str): return ""
    
    # ลบสัญลักษณ์พิเศษ
    text = re.sub(r"[\[\]\{\}\"']", "", text)
    text = re.sub(r"\w+\s*:\s*", "", text)
    
    # ลบคำเชื่อมภาษาอังกฤษ (Stop words) เพื่อให้เป็น Tag
    stop_words = [" a ", " an ", " the ", " is ", " are ", " with ", " on ", " in ", " of ", " to "]
    for word in stop_words:
        text = text.replace(word, ", ")
        
    # จัดระเบียบ comma และ space
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r",\s*,", ",", text)
    text = text.strip().strip(",")
    
    return text

def log_memory_usage(label=""):
    if psutil:
        mem = psutil.virtual_memory()
        print(f"   📊 RAM [{label}]: Used {mem.percent}% | Free {mem.available / 1024**3:.2f} GB")
        return mem.percent
    return 0

def flush_memory():
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

async def wait_for_memory(threshold=85):
    if not psutil: return
    print("   ⏳ Checking Memory...")
    if log_memory_usage("Pre-Check") > 90:
        await asyncio.sleep(10)
        flush_memory()

    for i in range(5): 
        mem_percent = log_memory_usage("Check")
        if mem_percent < threshold:
            print("   ✅ Memory safe.")
            return
        flush_memory()
        await asyncio.sleep(2)
    print("   ⚠️ Proceeding despite high RAM.")

async def unload_ollama_model(client: httpx.AsyncClient):
    print("   ⬇️ Force Unloading Ollama...")
    try:
        await client.post(ollamaURL, json={"model": ollamaModel, "keep_alive": 0})
        await asyncio.sleep(2) 
        print("   ✅ Ollama Unloaded.")
    except Exception as e:
        print(f"   ⚠️ Failed to unload Ollama: {e}")

def load_image_pipe():
    if torch.cuda.is_available():
        device = "cuda"
        torch_dtype = torch.float16 
        print("   ✅ CUDA Detected.")
    else:
        device = "cpu"
        torch_dtype = torch.float32
        print("   ⚠️ CUDA NOT Detected! Using CPU float32.")
    
    is_single_file = stabilityModel.endswith(".safetensors") or stabilityModel.endswith(".ckpt")
    is_xl = "xl" in stabilityModel.lower()

    if is_single_file:
        PipelineClass = StableDiffusionXLInpaintPipeline if is_xl else StableDiffusionInpaintPipeline
    else:
        PipelineClass = AutoPipelineForInpainting

    print(f"Loading Model: {stabilityModel}")
    
    image_encoder = None
    print("   Loading Image Encoder...")
    
    try:
        image_encoder = CLIPVisionModelWithProjection.from_pretrained(
            "h94/IP-Adapter", 
            subfolder="models/image_encoder", 
            torch_dtype=torch_dtype,
            local_files_only=True
        )
        print("   ✅ Loaded ViT-H (Local).")
    except:
        print("   ⬇️ Downloading ViT-H...")
        try:
            image_encoder = CLIPVisionModelWithProjection.from_pretrained(
                "h94/IP-Adapter", 
                subfolder="models/image_encoder", 
                torch_dtype=torch_dtype
            )
        except:
             image_encoder = CLIPVisionModelWithProjection.from_pretrained(
                "laion/CLIP-ViT-H-14-laion2B-s32B-b79K",
                torch_dtype=torch_dtype
            )

    try:
        if is_single_file:
                pipe = PipelineClass.from_single_file(
                stabilityModel,
                torch_dtype=torch_dtype,
                image_encoder=image_encoder,
                use_safetensors=True
            )
        else:
            pipe = PipelineClass.from_pretrained(
                stabilityModel,
                torch_dtype=torch_dtype,
                use_safetensors=True,
                image_encoder=image_encoder 
            )
    except Exception as e:
        print(f"   ⚠️ Load failed ({e}), trying standard load...")
        pipe = PipelineClass.from_pretrained(
            stabilityModel,
            torch_dtype=torch_dtype,
            use_safetensors=False,
            image_encoder=image_encoder 
        )

    if hasattr(pipe, "safety_checker"): pipe.safety_checker = None
    
    try: pipe.enable_vae_slicing()
    except: pass
    try: pipe.enable_vae_tiling() 
    except: pass

    if device == "cuda":
        try: pipe.enable_model_cpu_offload()
        except: pipe.to(device)
    else:
        pipe.to(device)  

    return pipe

def get_mask_coordinates_smart(position_keyword, depth, width, height):
    p = position_keyword.upper()
    d = depth.upper() 
    
    # Scale ตามระยะ (ลดขนาดลงอีกนิดไม่ให้ล้นเฟรม)
    if "FORE" in d: 
        scale_h = 0.80 
        scale_w = 0.35 
        y_start_ratio = 0.15 
    elif "MID" in d: 
        scale_h = 0.55 
        scale_w = 0.25 
        y_start_ratio = 0.35 
    else: # BACK
        scale_h = 0.35 
        scale_w = 0.15 
        y_start_ratio = 0.45 

    char_h = int(height * scale_h)
    char_w = int(width * scale_w)
    top_y = int(height * y_start_ratio)
    bottom_y = top_y + char_h
    
    if bottom_y > height - 10: bottom_y = height - 10

    if "LEFT" in p:
        start_x = int(width * 0.1)
        end_x = start_x + char_w
    elif "RIGHT" in p:
        end_x = int(width * 0.9)
        start_x = end_x - char_w
    else: # CENTER
        center_x = width // 2
        start_x = center_x - (char_w // 2)
        end_x = center_x + (char_w // 2)

    return (start_x, top_y, end_x, bottom_y)

# ==========================================
# 4. ANALYSIS & DB LOOKUP
# ==========================================

async def analyze_scene_plan(chunk_text: str, client: httpx.AsyncClient):
    # ✅ สั่ง LLM ชัดเจนว่าขอ Keywords, Comma separated
    prompt = f"""
    Role: AI Visual Director.
    Task: Create visual prompt tags for Stable Diffusion.
    Input Story: "{chunk_text}"
    Rules:
    1. 'environment': Keywords ONLY (comma separated). No sentences. Focus on visual style (e.g., "misty mountains, bamboo forest, ancient ruins").
    2. 'characters': Extract names.
    3. 'position': [LEFT, CENTER, RIGHT].
    4. 'depth': [FOREGROUND, MID_GROUND, BACKGROUND].
    5. 'visual_action': Keywords ONLY. Action + Clothing (e.g., "holding sword, green hanfu robe"). **Ancient Chinese Robes (Hanfu) only.**

    Output JSON: 
    {{ 
        "environment": "keyword1, keyword2, ...", 
        "characters": [ 
            {{ "name": "...", "position": "...", "depth": "MID_GROUND", "visual_action": "..." }} 
        ] 
    }}
    """
    
    try:
        print(f"   [Ollama] Analyzing...")
        response = await client.post(ollamaURL, json={
            "model": ollamaModel, "prompt": prompt, "stream": False, 
            "format": "json", "options": {"temperature": 0.2, "num_ctx": 2048}
        }, timeout=300.0)
        
        result_text = response.json().get("response", "")
        clean_json = re.sub(r'```json\s*', '', result_text).replace('```', '')
        match = re.search(r'\{.*\}', clean_json, re.DOTALL)
        return json.loads(match.group(0)) if match else None
    except Exception as e:
        print(f"❌ Scene Analysis Error: {e}")
        return None

def find_character_refpath(session: Session, movie_id: int, name_query: str) -> Optional[str]:
    if not name_query: return None
    name_query = name_query.strip()

    def validate_path(p):
        if p and os.path.exists(p): 
            print(f"      ✅ Found Ref: {os.path.basename(p)}")
            return p
        return None

    def check_id_paths(char_id):
        p_png = os.path.join(CHAR_DIR, f"{char_id}.png")
        if res := validate_path(p_png): return res
        p_jpg = os.path.join(CHAR_DIR, f"{char_id}.jpg")
        if res := validate_path(p_jpg): return res
        return None

    char = session.exec(select(character).where(
        character.movieId == movie_id,
        character.name.ilike(f"%{name_query}%")
    )).first()

    if char:
        if res := validate_path(char.refpath): return res
        if res := check_id_paths(char.id): return res

    alt = session.exec(select(character).join(altCharacter).where(
        character.movieId == movie_id,
        altCharacter.altName.ilike(f"%{name_query}%")
    )).first()

    if alt:
        if res := validate_path(alt.refpath): return res
        if res := check_id_paths(alt.id): return res

    return None

# ==========================================
# 5. GENERATION LOGIC
# ==========================================

def run_sd_pipeline(scene_plan: dict, movie_id: int, session: Session, output_path: str):
    log_memory_usage("Start Gen SD") 
    print(f"🎨 Generating: {output_path}")
    
    width, height = IMG_WIDTH, IMG_HEIGHT
    people_to_gen = []
    
    # ✅ 1. สร้าง Base Prompt (Environment Only)
    # ไม่เอาคนไปใส่ใน Base Prompt แล้ว เพื่อประหยัด Token และไม่ให้ฉากหลังเพี้ยนเป็นคน
    env_desc = clean_prompt(scene_plan.get('environment', 'scene'))
    
    STYLE = "Ancient Chinese Xianxia, Wuxia, Hanfu, dynasty era, sharp focus"
    NEG = "modern, western, low quality, ugly, deformed, blurry, deformed hands, missing limbs, text, watermark"

    # Base Prompt = Style + Environment + Quality
    base_prompt = f"{STYLE}, {env_desc}, masterpiece, best quality, 4k"
    print(f"   📝 Base Prompt (BG Only): {base_prompt[:100]}...")

    # เตรียมข้อมูลคน (แต่ยังไม่ใส่ใน Prompt หลัก)
    for char_info in scene_plan.get('characters', []):
        name = char_info.get('name')
        ref_path = find_character_refpath(session, movie_id, name)
        action = clean_prompt(char_info.get('visual_action', ''))
        
        if "hanfu" not in action.lower(): action += ", wearing Hanfu"
        full_action_prompt = f"{action}, full body shot"
        
        depth = char_info.get('depth', 'MID_GROUND') 

        people_to_gen.append({
            "name": name,
            "refpath": ref_path, # อาจเป็น None ได้
            "position": char_info.get('position', 'CENTER'),
            "depth": depth,
            # Prompt เฉพาะตัวละคร
            "prompt": f"{STYLE}, {full_action_prompt}, {name}, masterpiece"
        })

    try:
        pipe = load_image_pipe()
        print(f"   Loading IP-Adapter...")
        subfolder_arg = IP_ADAPTER_SUBFOLDER if IP_ADAPTER_SUBFOLDER else None
        
        pipe.load_ip_adapter(IP_ADAPTER_REPO, subfolder=subfolder_arg, weight_name=IP_ADAPTER_FILENAME)
        pipe.set_ip_adapter_scale(0.0) 
        
        init_bg = Image.new("RGB", (width, height), (128, 128, 128)) 
        init_mask = Image.new("L", (width, height), "white") 
        dummy_ref = Image.new("RGB", (224, 224), "black")

        # 1. Gen Background (ฉากเปล่าๆ หรือฉากที่มีคนลางๆ จาก Environment)
        print("   Generating Background...")
        base_image = pipe(
            prompt=base_prompt,
            negative_prompt=NEG, 
            image=init_bg,       
            mask_image=init_mask, 
            ip_adapter_image=dummy_ref, 
            height=height, width=width, 
            num_inference_steps=NUM_STEPS, 
            strength=1.0, 
            guidance_scale=7.5 
        ).images[0]

        # Sort: วาด Background -> Foreground
        def depth_sort_key(p):
            d = p['depth'].upper()
            if "BACK" in d: return 0
            if "MID" in d: return 1
            return 2 
        people_to_gen.sort(key=depth_sort_key)

        # 2. Inpaint Characters (ทีละคน)
        for p in people_to_gen:
            coords = get_mask_coordinates_smart(p['position'], p['depth'], width, height)
            print(f"   👤 Inpainting: {p.get('name')} ({p['depth']})")
            
            mask = Image.new("L", (width, height), 0)
            draw = ImageDraw.Draw(mask)
            draw.rectangle(coords, fill=255)
            
            # ✅ Blur Mask ให้มากขึ้น (20 -> 25) เพื่อให้ขอบเนียน
            mask = mask.filter(ImageFilter.GaussianBlur(radius=25))
            
            # ถ้ามีรูป Ref ให้ใช้ ถ้าไม่มีใช้ Dummy (แต่ปิด Scale เป็น 0 เองอัตโนมัติถ้าไม่มี Ref จริงๆ ก็ได้)
            if p['refpath'] and os.path.exists(p['refpath']):
                ref_image = Image.open(p['refpath']).convert("RGB")
                pipe.set_ip_adapter_scale(0.7)
            else:
                ref_image = dummy_ref
                pipe.set_ip_adapter_scale(0.0) # ปิด IP-Adapter ถ้าไม่มีรูป
            
            base_image = pipe(
                prompt=p['prompt'], # ใช้ Prompt เฉพาะตัวละคร
                negative_prompt=NEG,
                image=base_image,
                mask_image=mask,
                ip_adapter_image=ref_image,
                num_inference_steps=NUM_STEPS, 
                strength=1.0, 
                guidance_scale=7.5
            ).images[0]

        base_image.save(output_path)
        print(f"✅ Saved.")
        return True

    except Exception as e:
        print(f"❌ SD Error: {e}")
        traceback.print_exc()
        return False
    finally:
        if 'pipe' in locals(): del pipe
        flush_memory()

# ==========================================
# 6. MAIN ENDPOINT
# ==========================================

@router.get("/generate-images/{chapter_id}")
async def generate_images_for_chapter(
    chapter_id: int, 
    session: Session = Depends(get_session)
):
    chunks = session.exec(select(chunkContent).where(chunkContent.chapterId == chapter_id)).all()
    chapter_info = session.get(chapterContent, chapter_id)
    
    if not chunks or not chapter_info:
        return {"status": "error", "message": "No data found."}

    success_count = 0
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        for chunk in chunks:
            if chunk.picRef:
                print(f"Skipping Chunk {chunk.chunkNumber}: Exists.")
                continue

            print(f"\n--- Processing Chunk {chunk.chunkNumber} ---")
            
            try:
                await wait_for_memory(threshold=85)

                text_input = chunk.chunkDetailEng if chunk.chunkDetailEng else chunk.chunkDetail
                if not text_input: continue

                scene_plan = await analyze_scene_plan(text_input, client)
                
                await unload_ollama_model(client)
                flush_memory()
                
                if not scene_plan: continue

                await wait_for_memory(threshold=85)
                filename = f"ch{chapter_id}_chunk{chunk.chunkNumber}_{int(time.time())}.png"
                full_path = os.path.join(OUTPUT_DIR, filename)
                
                is_generated = await asyncio.to_thread(
                    run_sd_pipeline, 
                    scene_plan, 
                    chapter_info.movieId, 
                    session, 
                    full_path
                )
                
                if is_generated:
                    chunk.picRef = full_path
                    session.add(chunk)
                    session.commit()
                    success_count += 1
            
            except Exception as e:
                print(f"⚠️ Chunk {chunk.chunkNumber} Failed: {e}")
                traceback.print_exc()

    return {
        "status": "completed",
        "generated": success_count
    }