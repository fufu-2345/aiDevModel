import asyncio
import json
import re
import time
import os
import gc
from typing import List, Optional

from fastapi import APIRouter, FastAPI, Depends, HTTPException
from sqlmodel import Session, select, create_engine
import httpx
from PIL import Image, ImageDraw
import torch
from diffusers import AutoPipelineForInpainting, StableDiffusionXLPipeline, StableDiffusionPipeline
from diffusers.utils import load_image

from models import (
    chapterContent,
    chunkContent,
    character,
    altCharacter
)
        
from models import movieTitle, chapterContent, chunkContent, entity, altEntity, character, altCharacter

router = APIRouter(
    prefix="/createPic",
    tags=["createPic"]
)

sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"
engine = create_engine(sqlite_url)

OUTPUT_DIR = "public/storage/pic/"
os.makedirs(OUTPUT_DIR, exist_ok=True)

ollamaURL = "http://localhost:11434/api/generate"
ollamaModel = "gemma3:12b"

stabilityModel = "C:\\stability matrix\\Data\\Models\\StableDiffusion\\juggernautXL_ragnarokBy.safetensors"
IMG_WIDTH = 1280
IMG_HEIGHT = 720

IP_ADAPTER_REPO = "../ipAdapter" 
IP_ADAPTER_SUBFOLDER = "" 
IP_ADAPTER_FILENAME = "ip-adapter-plus-face_sdxl_vit-h.bin"

def get_session():
    with Session(engine) as session:
        yield session
        
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
    PipelineClass = AutoPipelineForInpainting

    common_args = {
        "torch_dtype": torch_dtype,
        "low_cpu_mem_usage": True,
    }

    if is_safetensors:
        pipe = PipelineClass.from_single_file(
            stabilityModel,
            use_safetensors=True,
            **common_args
        )
    else:
        pipe = PipelineClass.from_pretrained(
            stabilityModel,
            variant="fp16" if device == "cuda" else None,
            use_safetensors=True,
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
        "model": ollamaModel,
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

#--------------------------------------------------------------------

@router.post("/generate-images/{chapter_id}")
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