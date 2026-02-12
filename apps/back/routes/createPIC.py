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
from PIL import Image, ImageDraw, ImageFilter # ✅ เพิ่ม ImageFilter เพื่อเบลอขอบ
from dotenv import load_dotenv 

# --- STABLE DIFFUSION IMPORTS ---
import torch
from diffusers import (
    AutoPipelineForInpainting, 
    StableDiffusionXLPipeline, 
    StableDiffusionPipeline,
    StableDiffusionXLInpaintPipeline,
    StableDiffusionInpaintPipeline
)
from diffusers.utils import load_image
from transformers import CLIPVisionModelWithProjection 

# พยายาม import psutil เพื่อเช็ค RAM
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
CHAR_DIR = "public/storage/characters/" # 📂 โฟลเดอร์เก็บรูปตัวละคร
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 📉 ลดความละเอียดลงเล็กน้อยเพื่อประหยัด RAM
IMG_WIDTH = 768
IMG_HEIGHT = 512
NUM_STEPS = 20 # ✅ ลดเหลือ 20 Steps ตามที่ขอ

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
    if isinstance(text, list):
        text = ", ".join(text)
    if not isinstance(text, str):
        return ""
    text = re.sub(r"[\[\]\{\}\"']", "", text)
    text = re.sub(r"\w+\s*:\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def log_memory_usage(label=""):
    if psutil:
        mem = psutil.virtual_memory()
        print(f"   📊 RAM [{label}]: Used {mem.percent}% | Free {mem.available / 1024**3:.2f} GB")
        return mem.percent
    else:
        print(f"   📊 RAM [{label}]: (psutil not installed)")
        return 0

def flush_memory():
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

async def wait_for_memory(threshold=85):
    """
    รอให้ RAM ลดลงต่ำกว่า threshold
    เพิ่ม Logic การรอแบบ Exponential Backoff เพื่อไม่ให้ Spam Log
    """
    if not psutil: return
    print("   ⏳ Checking Memory...")
    
    # ถ้า RAM เกิน 90% ให้รอนานหน่อยก่อนเช็คครั้งแรก
    if log_memory_usage("Pre-Check") > 90:
        print("   ⚠️ Critical RAM usage detected. Waiting 10s for OS cleanup...")
        await asyncio.sleep(10)
        flush_memory()

    for i in range(10): # ลองเช็ค 10 รอบ (รอบละ 3-5 วินาที)
        mem_percent = log_memory_usage("Check")
        if mem_percent < threshold:
            print("   ✅ Memory safe.")
            return
        
        print(f"   ⚠️ RAM high ({mem_percent}%), waiting and cleaning... (Attempt {i+1}/10)")
        flush_memory()
        await asyncio.sleep(3)
        
    print("   ⚠️ Proceeding despite high RAM (Timeout waiting). Good luck.")

async def unload_ollama_model(client: httpx.AsyncClient):
    print("   ⬇️ Force Unloading Ollama...")
    try:
        await client.post(ollamaURL, json={"model": ollamaModel, "keep_alive": 0})
        # รอเพิ่มอีกนิดเพื่อให้มั่นใจว่า process ตายจริง
        await asyncio.sleep(5) 
        print("   ✅ Ollama Unloaded.")
    except Exception as e:
        print(f"   ⚠️ Failed to unload Ollama: {e}")

def load_image_pipe():
    if torch.cuda.is_available():
        device = "cuda"
        torch_dtype = torch.float16 
        print("   ✅ CUDA Detected. Using GPU.")
    else:
        device = "cpu"
        torch_dtype = torch.float32
        print("   ⚠️ CUDA NOT Detected! Using CPU with float32.")
    
    is_single_file = stabilityModel.endswith(".safetensors") or stabilityModel.endswith(".ckpt")
    is_xl = "xl" in stabilityModel.lower()

    if is_single_file:
        PipelineClass = StableDiffusionXLInpaintPipeline if is_xl else StableDiffusionInpaintPipeline
    else:
        PipelineClass = AutoPipelineForInpainting

    print(f"Loading Model: {stabilityModel} (dtype={torch_dtype})")
    
    image_encoder = None
    print("   Loading Image Encoder...")
    
    try:
        image_encoder = CLIPVisionModelWithProjection.from_pretrained(
            "h94/IP-Adapter", 
            subfolder="models/image_encoder", 
            torch_dtype=torch_dtype,
            local_files_only=True
        )
        print("   ✅ Loaded ViT-H from local cache.")
    except Exception:
        try:
            print("   ⬇️ Downloading ViT-H from HuggingFace...")
            image_encoder = CLIPVisionModelWithProjection.from_pretrained(
                "h94/IP-Adapter", 
                subfolder="models/image_encoder", 
                torch_dtype=torch_dtype
            )
        except Exception as e:
            print(f"   ⚠️ Failed to load h94 ViT-H: {e}")
            try:
                image_encoder = CLIPVisionModelWithProjection.from_pretrained(
                    "laion/CLIP-ViT-H-14-laion2B-s32B-b79K",
                    torch_dtype=torch_dtype,
                    local_files_only=True
                )
                print("   ✅ Loaded LAION ViT-H from local cache.")
            except Exception:
                try:
                    image_encoder = CLIPVisionModelWithProjection.from_pretrained(
                        "laion/CLIP-ViT-H-14-laion2B-s32B-b79K",
                        torch_dtype=torch_dtype
                    )
                except Exception as e2:
                    print(f"   ❌ Critical: Failed to load Image Encoder: {e2}")

    try:
        if is_single_file:
                pipe = PipelineClass.from_single_file(
                stabilityModel,
                torch_dtype=torch_dtype,
                image_encoder=image_encoder 
            )
        else:
            pipe = PipelineClass.from_pretrained(
                stabilityModel,
                torch_dtype=torch_dtype,
                use_safetensors=True,
                image_encoder=image_encoder 
            )
    except Exception as e:
        print(f"   ⚠️ Load failed, trying standard load... Error: {e}")
        try:
            pipe = PipelineClass.from_pretrained(
                stabilityModel,
                torch_dtype=torch_dtype,
                use_safetensors=False,
                image_encoder=image_encoder 
            )
        except Exception as e2:
            print(f"   ❌ Critical Load Error: {e2}")
            raise e2

    if hasattr(pipe, "safety_checker"): pipe.safety_checker = None
    if hasattr(pipe, "requires_safety_checker"): pipe.requires_safety_checker = False
    
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

def get_mask_coordinates(position_keyword, width=IMG_WIDTH, height=IMG_HEIGHT):
    p = position_keyword.upper()
    margin_top = int(height * 0.15) 
    
    if "LEFT" in p: return (0, margin_top, width // 2, height)
    elif "RIGHT" in p: return (width // 2, margin_top, width, height)
    elif "CENTER" in p: return (width // 4, margin_top, (width * 3) // 4, height)
    else: return (width // 4, margin_top, (width * 3) // 4, height) 

# ==========================================
# 4. STEP 1: SCENE ANALYSIS (LLM)
# ==========================================

async def analyze_scene_plan(chunk_text: str, client: httpx.AsyncClient):
    await wait_for_memory(threshold=85) 
    
    # 🇨🇳 Prompt สั่ง Ollama ให้ตอบสั้นๆ (Concise Keywords)
    prompt = f"""
    Role: AI Visual Director.
    Task: Create a VERY SHORT, keyword-based Visual Prompt for Stable Diffusion.
    
    Input Story:
    "{chunk_text}"

    Rules:
    1. 'environment': Short keywords only (max 10 words). Focus on visual style (e.g., "misty mountains, bamboo forest").
    2. 'characters': List characters. Use names from text.
    3. 'position': Assign [LEFT, CENTER, RIGHT, BACKGROUND].
    4. 'visual_action': Short keywords for action/clothes (max 5 words). **Ancient Chinese Robes (Hanfu) only.**

    Output JSON Format:
    {{
        "environment": "Misty mountain peak, ancient chinese style",
        "characters": [
            {{
                "name": "Han Li",
                "position": "LEFT",
                "visual_action": "wearing green hanfu, holding bottle"
            }}
        ]
    }}
    """

    payload = {
        "model": ollamaModel,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.3, "num_ctx": 4096}
    }

    print(f"   [Ollama] Analyzing text...")

    try:
        response = await client.post(ollamaURL, json=payload, timeout=300.0)
        response.raise_for_status() 
        result_text = response.json().get("response", "")
        
        clean_json = re.sub(r'```json\s*', '', result_text)
        clean_json = re.sub(r'```', '', clean_json)
        
        match = re.search(r'\{.*\}', clean_json, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        else:
            print(f"❌ JSON not found: {result_text[:100]}...")
            return None

    except Exception as e:
        print(f"❌ Scene Analysis Error: {e}")
        return None

# ==========================================
# 5. STEP 2: DB LOOKUP
# ==========================================

def find_character_refpath(session: Session, movie_id: int, name_query: str) -> Optional[str]:
    """
    ค้นหา Path รูปตัวละคร โดยดูทั้งจาก DB และ Folder ID
    """
    if not name_query: return None
    name_query = name_query.strip()

    def validate_path(p):
        if p and os.path.exists(p): 
            print(f"      ✅ Found: {os.path.abspath(p)}")
            return p
        return None

    # 1. ค้นหาจากชื่อหลัก
    char = session.exec(select(character).where(
        character.movieId == movie_id,
        character.name.ilike(f"%{name_query}%")
    )).first()

    if char:
        if res := validate_path(char.refpath): return res
        
        id_path_png = os.path.join(CHAR_DIR, f"{char.id}.png")
        if res := validate_path(id_path_png): return res
        
        id_path_jpg = os.path.join(CHAR_DIR, f"{char.id}.jpg")
        if res := validate_path(id_path_jpg): return res

    # 2. ค้นหาจากชื่อเล่น (AltNames)
    alt_char = session.exec(select(character).join(altCharacter).where(
        character.movieId == movie_id,
        altCharacter.altName.ilike(f"%{name_query}%")
    )).first()

    if alt_char:
        if res := validate_path(alt_char.refpath): return res
        
        id_path_png = os.path.join(CHAR_DIR, f"{alt_char.id}.png")
        if res := validate_path(id_path_png): return res
        
        id_path_jpg = os.path.join(CHAR_DIR, f"{alt_char.id}.jpg")
        if res := validate_path(id_path_jpg): return res

    return None

# ==========================================
# 6. STEP 3: IMAGE GENERATION (SDXL)
# ==========================================

def run_sd_pipeline(scene_plan: dict, movie_id: int, session: Session, output_path: str):
    # ฟังก์ชันนี้ถูกเรียกหลังจากเคลียร์ RAM แล้ว
    log_memory_usage("Start Gen SD") 
    print(f"🎨 Generating: {output_path}")
    
    width, height = IMG_WIDTH, IMG_HEIGHT
    people_to_gen = []
    character_prompts = [] 
    
    env_desc = clean_prompt(scene_plan.get('environment', 'scene'))
    
    STYLE_PROMPT = "Ancient Chinese Xianxia, Wuxia, Hanfu, dynasty era, sharp focus"
    NEGATIVE_PROMPT = "modern, western, low quality, ugly, deformed, blurry"

    # จัดการตัวละคร
    for char_info in scene_plan.get('characters', []):
        name = char_info.get('name')
        ref_path = find_character_refpath(session, movie_id, name)
        action = clean_prompt(char_info.get('visual_action', ''))
        
        if "hanfu" not in action.lower() and "robe" not in action.lower():
            action += ", wearing Hanfu"

        if ref_path and os.path.exists(ref_path):
            people_to_gen.append({
                "name": name,
                "refpath": ref_path,
                "position": char_info.get('position', 'CENTER'),
                "prompt": f"{STYLE_PROMPT}, {action}, {name}, masterpiece"
            })
        else:
            character_prompts.append(f"{name} {action}")
            print(f"   ⚠️ No ref for {name}, adding to text prompt.")

    if not people_to_gen and not character_prompts:
        print("   ⚠️ WARNING: No characters detected in scene plan! (Background only)")

    full_character_prompt = ", ".join(character_prompts)
    
    parts = [STYLE_PROMPT]
    if full_character_prompt: parts.append(full_character_prompt)
    parts.append(env_desc)
    parts.append("masterpiece, 4k")
    
    base_prompt = ", ".join(parts)
    print(f"   📝 Final Base Prompt: {base_prompt}")

    try:
        pipe = load_image_pipe()
        print(f"   Loading IP-Adapter from {IP_ADAPTER_REPO}...")
        subfolder_arg = IP_ADAPTER_SUBFOLDER if IP_ADAPTER_SUBFOLDER else None
        
        pipe.load_ip_adapter(
            IP_ADAPTER_REPO, 
            subfolder=subfolder_arg, 
            weight_name=IP_ADAPTER_FILENAME
        )
        
        pipe.set_ip_adapter_scale(0.0)
        
        init_bg = Image.new("RGB", (width, height), (128, 128, 128)) 
        init_mask = Image.new("L", (width, height), "white") 
        dummy_ref = Image.new("RGB", (224, 224), "black")

        print("   Generating base image...")
        base_image = pipe(
            prompt=base_prompt,
            negative_prompt=NEGATIVE_PROMPT, 
            image=init_bg,       
            mask_image=init_mask, 
            ip_adapter_image=dummy_ref, 
            height=height, width=width, 
            num_inference_steps=NUM_STEPS, 
            strength=1.0, 
            guidance_scale=7.5 
        ).images[0]

        # --- Inpainting Characters (Patching) ---
        for p in people_to_gen:
            print(f"   👤 Inpainting Character: {p.get('name')} at {p['position']}")
            
            coords = get_mask_coordinates(p['position'], width, height)
            mask = Image.new("L", (width, height), 0)
            draw = ImageDraw.Draw(mask)
            draw.rectangle(coords, fill=255)
            
            # ✅ BLUR MASK
            mask = mask.filter(ImageFilter.GaussianBlur(radius=20))
            
            ref_image = Image.open(p['refpath']).convert("RGB")
            
            pipe.set_ip_adapter_scale(0.7)
            base_image = pipe(
                prompt=p['prompt'],
                negative_prompt=NEGATIVE_PROMPT,
                image=base_image,
                mask_image=mask,
                ip_adapter_image=ref_image,
                num_inference_steps=NUM_STEPS, 
                strength=0.9, 
                guidance_scale=7.5
            ).images[0]

        # --- ✅ FINAL BLENDING PASS ---
        if people_to_gen:
            print("   🎨 Final blending pass...")
            pipe.set_ip_adapter_scale(0.0) 
            final_blend_mask = Image.new("L", (width, height), "white") 
            
            base_image = pipe(
                prompt=base_prompt,
                negative_prompt=NEGATIVE_PROMPT,
                image=base_image,   
                mask_image=final_blend_mask,
                ip_adapter_image=dummy_ref,
                num_inference_steps=NUM_STEPS,
                strength=0.15,
                guidance_scale=7.5
            ).images[0]

        base_image.save(output_path)
        print(f"✅ Saved to {output_path}")
        return True

    except Exception as e:
        print(f"❌ Error in SD Pipeline: {e}")
        traceback.print_exc()
        return False
    finally:
        if 'pipe' in locals(): del pipe
        flush_memory()
        log_memory_usage("After Cleanup")

# ==========================================
# 7. MAIN ENDPOINT (BATCHING VERSION)
# ==========================================

@router.get("/generate-images/{chapter_id}")
async def generate_images_for_chapter(
    chapter_id: int, 
    session: Session = Depends(get_session)
):
    chunks = session.exec(select(chunkContent).where(chunkContent.chapterId == chapter_id)).all()
    if not chunks:
        return {"status": "error", "message": "No chunks found. Run /create-chunks first."}
    
    chapter_info = session.get(chapterContent, chapter_id)
    if not chapter_info:
        raise HTTPException(status_code=404, detail="Chapter info not found")
    movie_id = chapter_info.movieId

    success_count = 0
    tasks_to_process = [] # เก็บงานที่จะทำ (chunk, plan)

    async with httpx.AsyncClient(timeout=120.0) as client:
        # --- PHASE 1: PLANNING (Ollama Only) ---
        print("🔵 [PHASE 1] Analyzing all chunks with Ollama...")
        for chunk in chunks:
            if chunk.picRef:
                print(f"Skipping Chunk {chunk.chunkNumber}: Already exists.")
                continue

            print(f"--- Analyzing Chunk {chunk.chunkNumber} ---")
            
            # ✅ ใช้ chunkDetailEng ตามที่ระบุ ถ้าไม่มีให้ Fallback เป็น chunkDetail
            text_to_analyze = chunk.chunkDetailEng if chunk.chunkDetailEng else chunk.chunkDetail
            if not text_to_analyze:
                print(f"Skipping Chunk {chunk.chunkNumber}: No text content found.")
                continue

            scene_plan = await analyze_scene_plan(text_to_analyze, client)
            
            if scene_plan:
                tasks_to_process.append((chunk, scene_plan))
            else:
                print(f"Skipping Chunk {chunk.chunkNumber}: Analysis failed.")

        # --- TRANSITION: CLEANUP ---
        if not tasks_to_process:
            return {"status": "completed", "message": "No new chunks to process."}

        print("🟡 [TRANSITION] Unloading Ollama and clearing RAM...")
        await unload_ollama_model(client)
        flush_memory()
        
        # รอให้ RAM ว่างจริงๆ ก่อนโหลด SDXL
        await wait_for_memory(threshold=85)

        # --- PHASE 2: GENERATION (SDXL Only) ---
        print("🟢 [PHASE 2] Generating Images with Stable Diffusion...")
        for chunk, scene_plan in tasks_to_process:
            print(f"--- Generating Chunk {chunk.chunkNumber} ---")
            
            filename = f"ch{chapter_id}_chunk{chunk.chunkNumber}_{int(time.time())}.png"
            full_path = os.path.join(OUTPUT_DIR, filename)
            
            # รัน SDXL แบบต่อเนื่อง (ไม่ต้องโหลด/unload ทุกรอบ เพราะเราเคลียร์ที่ไว้แล้ว)
            is_generated = await asyncio.to_thread(
                run_sd_pipeline, 
                scene_plan, 
                movie_id, 
                session, 
                full_path
            )
            
            if is_generated:
                chunk.picRef = full_path
                session.add(chunk)
                session.commit()
                success_count += 1
                
                # Cleanup เบาๆ ระหว่างรูป
                flush_memory() 
            else:
                print("Failed to generate image.")

    return {
        "status": "completed",
        "chapter_id": chapter_id,
        "images_generated": success_count,
        "output_directory": OUTPUT_DIR
    }