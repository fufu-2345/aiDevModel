import time
import json
import re
import asyncio
import os
import httpx
import torch 
import gc 
import importlib.util 
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from googletrans import Translator
from diffusers import StableDiffusionPipeline, StableDiffusionXLPipeline 

from database import get_session
from models import chapterContent, character, entity, chunkContent 
from services import save_extraction_result

router = APIRouter(
    prefix="/extractEntities",
    tags=["extractEntities"]
)

# --- Configuration ---
ollamaURL = "http://localhost:11434/api/generate"
extractModel = "gemma3:12b" # อัปเดต Model ตามที่ต้องการ

# Image Generation Config
stabilityModel = "stabilityai/stable-diffusion-xl-base-1.0" 
loraPath = r"C:\stability matrix\Data\Models\Lora\ClothingAdjuster3.safetensors" 

# Limits
MAX_TAGS = 20 # ปรับกลับเป็น 20 ตามที่ต้องการ

# Blocklist: คำทั่วไปที่ไม่ควรเป็นชื่อตัวละคร
GENERIC_NAMES = {
    "man", "woman", "boy", "girl", "child", "kid", "baby", "children",
    "uncle", "aunt", "father", "mother", "dad", "mom", "parent", "parents",
    "brother", "sister", "grandfather", "grandmother", "grandpa", "grandma",
    "stranger", "villager", "person", "people", "someone", "nobody", "anybody",
    "friend", "enemy", "everyone", "master", "disciple", "teacher", "student",
    "he", "she", "him", "her", "they", "them", "it", "that", "this", "i",
    "idiot", "fool", "bastard", "brat", "stupid", "crazy", "madman", "monster",
    "demon", "devil", "god", "immortal", "cultivator", "sect master", "elder",
    "senior", "junior", "fellow", "daoist", "clueless", "son of a bitch",
    "shixiong", "shidi", "shijie", "shimei", "boss", "chief", "leader",
    "younger brother", "older brother", "big brother", "little brother",
    "younger sister", "older sister", "big sister", "little sister",
    "third uncle", "second uncle", "fourth uncle" 
}

# --- Helper Functions ---

def parse_tags_to_set(tags_input):
    """แปลง Tags string/list ให้เป็น Set เพื่อตัดคำซ้ำ"""
    if not tags_input:
        return set()
    if isinstance(tags_input, str):
        return set(t.strip() for t in tags_input.split(',') if t.strip())
    if isinstance(tags_input, list):
        return set(str(t).strip() for t in tags_input if str(t).strip())
    return set()

def load_image_pipe():
    """โหลด Stable Diffusion Pipeline (Load on Demand)"""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch_dtype = torch.float16 if device == "cuda" else torch.float32
    
    is_xl = "xl" in stabilityModel.lower()
    is_safetensors = stabilityModel.endswith(".safetensors")
    PipelineClass = StableDiffusionXLPipeline if is_xl else StableDiffusionPipeline
    
    print(f"⏳ Loading Model: {stabilityModel}")
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

    # ปิดตัวช่วยความปลอดภัยเพื่อความเร็ว (Optional)
    if hasattr(pipe, "safety_checker"):
        pipe.safety_checker = None
    if hasattr(pipe, "requires_safety_checker"):
        pipe.requires_safety_checker = False
    if hasattr(pipe, "watermarker"):
        pipe.watermarker = None
        
    pipe.to(device)    
    
    # Load LoRA
    if os.path.exists(loraPath):
        print(f"✨ Loading LoRA: {loraPath}")
        try:
            if importlib.util.find_spec("peft") is None:
                 print("⚠️ 'peft' library not found. Skipping LoRA load.")
            else:
                 pipe.load_lora_weights(loraPath)
                 print("✅ LoRA loaded.")
        except Exception as e:
            print(f"⚠️ Failed to load LoRA: {e}")
        
    return pipe

def generate_images_for_missing_refpaths(session: Session, movie_id: int):
    """สร้างภาพให้ตัวละคร/สถานที่ที่ยังไม่มีภาพ (refpath ว่าง)"""
    print(f"🎨 Starting Image Generation for Movie ID: {movie_id}")
    
    # Query หาตัวที่ยังไม่มีรูป
    char_statement = select(character).where(
        character.movieId == movie_id,
        (character.refpath == "") | (character.refpath == None)
    )
    chars_to_gen = session.exec(char_statement).all()

    ent_statement = select(entity).where(
        entity.movieId == movie_id,
        (entity.refpath == "") | (entity.refpath == None)
    )
    ents_to_gen = session.exec(ent_statement).all()

    if not chars_to_gen and not ents_to_gen:
        print("✨ No missing images found.")
        return

    # Load Model
    pipeline = None
    try:
        pipeline = load_image_pipe()
    except Exception as e:
        print(f"❌ Failed to load Image Pipeline: {e}")
        return

    # สร้าง Folder
    os.makedirs("public/storage/characters", exist_ok=True)
    os.makedirs("public/storage/entities", exist_ok=True)

    try:
        # Loop สร้างภาพ Characters
        for char_obj in chars_to_gen:
            try:
                # Limit Tags ก่อนนำไปสร้าง Prompt เพื่อป้องกัน Error
                i_tags_list = [t.strip() for t in char_obj.IdentityTags.split(',') if t.strip()]
                m_tags_list = [t.strip() for t in char_obj.ModifierTags.split(',') if t.strip()]
                
                # ตัดให้เหลือแค่ MAX_TAGS ตัวแรก
                limited_desc = ", ".join(i_tags_list[:MAX_TAGS] + m_tags_list[:MAX_TAGS])
                
                desc = limited_desc if limited_desc else "character"
                
                # --- Prompt Engineering (Character) ---
                # Positive: เน้นหน้าตรง พื้นหลังขาว ไม่มีเงา แสงสตูดิโอ (Reference Sheet Style)
                prompt = (
                    f"ancient chinese style, {desc}, front view, head and shoulders portrait, "
                    f"looking directly at camera, passport photo style, neutral expression, "
                    f"soft studio lighting, evenly lit face, no shadows on face, bright, "
                    f"high quality, sharp focus, simple white background"
                )
                
                # Negative: ห้าม 18+ ห้ามเงา ห้ามมุมข้าง
                negative_prompt = (
                    "nsfw, nude, naked, 18+, sexual, erotic, porn, hentai, "
                    "boobs, cleavage, nipples, genitals, penis, vagina, sex, "
                    "shadows, harsh lighting, hands, hands on face, distorted face, "
                    "profile view, looking away, busy background, blurry, low quality, "
                    "worst quality, bad anatomy, deformed, malformed, mutation, "
                    "extra limbs, missing limbs, floating limbs, disconnected limbs, "
                    "lowres, low resolution, jpeg artifacts, dark, dim, monochromatic, grayscale"
                )
                
                print(f"Generating Character: {char_obj.name}...")
                image = pipeline(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    num_inference_steps=25,
                    height=1024, 
                    width=1024,
                    guidance_scale=7.0
                ).images[0]
                
                filename = f"storage/characters/{char_obj.id}.png"
                image.save(f"public/{filename}")
                
                char_obj.refpath = filename
                session.add(char_obj)
                session.commit() 
            except Exception as e:
                print(f"❌ Error generating character {char_obj.name}: {e}")

        # Loop สร้างภาพ Entities (Items/Locations)
        for ent_obj in ents_to_gen:
            try:
                # Limit Visual Tags
                v_tags_list = [t.strip() for t in ent_obj.visual_tags.split(',') if t.strip()]
                desc = ", ".join(v_tags_list[:MAX_TAGS])
                
                e_type_lower = ent_obj.type.lower()
                
                if "item" in e_type_lower:
                    # Positive: Product shot, white bg
                    prompt = (
                        f"ancient chinese style object, {desc}, product photography, centered shot, "
                        f"isolated on white background, studio lighting, soft shadows, high detail, "
                        f"8k, sharp focus, realistic texture, professional lighting"
                    )
                    # Negative
                    negative_prompt = (
                        "nsfw, nude, naked, 18+, human, hands, holding, fingers, person, "
                        "messy background, text, watermark, blurry, low quality, distortion, "
                        "cropped, out of frame, worst quality, lowres, low resolution, "
                        "jpeg artifacts, off-center, multiple views, split screen, bad lighting"
                    )
                else: # Location
                    # Positive: Wide angle, clean
                    prompt = (
                        f"ancient chinese architecture, {desc}, establishing shot, wide angle view, "
                        f"highly detailed, realistic, 8k, cinematic lighting, depth of field, "
                        f"interior design, atmosphere, sharp focus"
                    )
                    # Negative
                    negative_prompt = (
                        "nsfw, nude, naked, 18+, people, crowd, humans, animals, text, watermark, "
                        "blurry, low quality, distortion, simple background, white background, "
                        "flat lighting, worst quality, lowres, low resolution, "
                        "jpeg artifacts, close up, macro"
                    )

                print(f"Generating Entity ({ent_obj.type}): {ent_obj.name}...")
                image = pipeline(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    num_inference_steps=25,
                    height=1024, 
                    width=1024,
                    guidance_scale=7.0
                ).images[0]
                
                filename = f"storage/entities/{ent_obj.id}.png"
                image.save(f"public/{filename}")
                
                ent_obj.refpath = filename
                session.add(ent_obj)
                session.commit()
            except Exception as e:
                print(f"❌ Error generating entity {ent_obj.name}: {e}")
                
    finally:
        # Cleanup Memory
        print("🧹 Cleaning up model from memory...")
        if pipeline:
            del pipeline
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print("✅ RAM Freed.")

async def translate_text(text: str) -> str:
    """Helper แปลภาษาไทยเป็นอังกฤษ พร้อม Retry"""
    translator = Translator()
    retries = 3
    for i in range(retries):
        try:
            translated = await translator.translate(text, src='th', dest='en')
            if translated and translated.text:
                return translated.text
        except Exception as e:
            print(f"Translation Error (Attempt {i+1}): {e}")
            await asyncio.sleep(1)
    return text 

async def create_and_save_chunks(session: Session, chapter: chapterContent):
    """
    แบ่ง Chunk -> แปลภาษา -> Save ลง DB -> Return English Chunks
    """
    print(f"Creating chunks for Chapter {chapter.id}...")
    
    existing_chunks = session.exec(select(chunkContent).where(chunkContent.chapterId == chapter.id)).all()
    for old_chunk in existing_chunks:
        session.delete(old_chunk)
    session.commit()

    lines = chapter.chapterDetail.split('\n')
    total_lines = len(lines)
    
    LINES_PER_CHUNK = 5  
    OVERLAP = 1          
    
    raw_chunks_thai = [] 
    
    if total_lines <= LINES_PER_CHUNK:
        raw_chunks_thai.append(chapter.chapterDetail)
    else: 
        step = LINES_PER_CHUNK - OVERLAP
        for i in range(0, total_lines, step):
            chunk_lines = lines[i : i + LINES_PER_CHUNK]
            if len(chunk_lines) < 3 and len(raw_chunks_thai) > 0:
                break 
            
            chunk_text = "\n".join(chunk_lines)
            raw_chunks_thai.append(chunk_text)

    print(f"Processing Chapter {chapter.id}: Found {len(raw_chunks_thai)} raw chunks.")

    final_eng_chunks = []
    
    for idx, thai_text in enumerate(raw_chunks_thai):
        print(f"Processing chunk {idx+1}/{len(raw_chunks_thai)}...")

        # แปลเป็น Eng
        eng_text = await translate_text(thai_text)
        final_eng_chunks.append(eng_text)
        
        # Save ลง DB: thai_text -> chunkDetail, eng_text -> chunkDetailEng
        new_chunk = chunkContent(
            chunkNumber = idx + 1,
            chunkDetail = thai_text,      # ภาษาไทย (Overlap)
            chunkDetailEng = eng_text,    # ภาษาอังกฤษ (แปล)
            picRef = None,           
            chapterId = chapter.id
        )
        session.add(new_chunk)
        
        await asyncio.sleep(0.5) 

    session.commit()
    print("✅ Chunks translated and saved to DB.")
    return final_eng_chunks

async def processChunk(chunk_text: str, client: httpx.AsyncClient, extractModel: str):
    """ส่ง Text Chunk ไปให้ LLM Extract ข้อมูล"""
    prompt = f"""
    Role:
    You are an AI Visual Director.

    Task:
    Extract Entity information (Character, Location, Item) from the Input Text into a valid JSON format.

    Rules:
    1. "IdentityTags": Physical appearance traits (face, body, hair, eyes, skin, age). Format as comma-separated Stable Diffusion tags.
    2. "ModifierTags": Clothing, outfit, accessories, and current state. Format as comma-separated Stable Diffusion tags.
    3. Use the "first appearance" for changing traits.
    4. Tags must be nouns/adjectives only. No verbs.
    5. English output only.
    6. "gender": Identify as Male, Female, or Unknown.

    Output JSON Format:
    {{
        "entities": [
            {{
                "type": "Character",
                "name": "Name",
                "gender": "Male",
                "altNames": [],
                "IdentityTags": "tag1, tag2",
                "ModifierTags": "tag1, tag2"
            }},
            {{
                "type": "Location",
                "name": "Name",
                "altNames": [],
                "VisualTags": "tag1, tag2"
            }}
        ]
    }}

    Input Text:
    {chunk_text}
    """

    payload = {
        "model": extractModel,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_ctx": 4096, 
            "temperature": 0.5  
        },
        "format": "json"
    }

    try:
        response = await client.post(ollamaURL, json=payload)
        response.raise_for_status()
        result_text = response.json().get("response", "")
        # ใช้ Regex หา JSON block
        match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if match:
            json_str = match.group(0)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                # ลองซ่อม JSON แบบง่ายๆ (แก้ trailing commas)
                try:
                    corrected = re.sub(r',\s*([\]}])', r'\1', json_str)
                    return json.loads(corrected)
                except:
                    print(f"JSON Broken: {result_text[:50]}...")
                    return None
        else:
            print("No JSON found in response.")
            return None

    except Exception as e:
        print(f"Process Error: {e}")
        return None

# --- Main Endpoint ---

@router.get("/{chapter_id}")
async def extract_entities(chapter_id: int, session: Session = Depends(get_session)):
    start = time.perf_counter()
    chapter_obj = session.get(chapterContent, chapter_id)
    if not chapter_obj or not chapter_obj.chapterDetail:
        return {"result": "No content found."}
    
    current_movie_id = chapter_obj.movieId
    
    final_output = {
        "characters": [],
        "locations": [],
        "items": [],
        "status": "extracted"
    }

    if not chapter_obj.isExtracted:
        chunks_eng = await create_and_save_chunks(session, chapter_obj)
        results = []
        
        async with httpx.AsyncClient(timeout=1800.0) as client:
            for idx, chunk_text in enumerate(chunks_eng):
                print(f"Extracting entities from chunk {idx+1}/{len(chunks_eng)}...")
                res = await processChunk(chunk_text, client, extractModel) 
                if res:
                    results.append(res)
                else:
                    print(f"Chunk {idx+1} Failed Extraction")

        # ----------------------------------------------------------------
        # STRICT SMART MERGE LOGIC
        # ----------------------------------------------------------------
        merged_list = []
        all_raw_entities = []
        for res in results:
            if res and "entities" in res:
                all_raw_entities.extend(res["entities"])

        for raw in all_raw_entities:
            e_type = raw.get("type", "").strip().capitalize()
            name = raw.get("name", "").strip()
            if not e_type or not name:
                continue

            raw_alts = raw.get("altNames", [])
            current_alts = set()
            if isinstance(raw_alts, list):
                current_alts = {str(a).strip() for a in raw_alts if str(a).strip()}
            elif isinstance(raw_alts, str):
                current_alts = {raw_alts.strip()}
            
            gender = raw.get("gender", "Unknown").strip().capitalize()
            
            # Filter generic alts
            current_alts = {a for a in current_alts if a.lower() not in GENERIC_NAMES}

            # Filter generic main name
            if name.lower() in GENERIC_NAMES:
                if len(current_alts) > 0:
                    best_name = max(current_alts, key=len) 
                    name = best_name
                    current_alts.remove(best_name)
                else:
                    print(f"⚠️ Skipped generic entity: {name}")
                    continue

            i_tags = parse_tags_to_set(raw.get("IdentityTags"))
            m_tags = parse_tags_to_set(raw.get("ModifierTags"))
            v_tags = parse_tags_to_set(raw.get("VisualTags"))

            current_name_lower = " ".join(name.lower().split())
            
            match_found = False
            for existing in merged_list:
                if existing["type"] != e_type:
                    continue
                
                existing_name_lower = " ".join(existing["name"].lower().split())
                existing_alts_lower = {" ".join(a.lower().split()) for a in existing["altNames"]}
                
                is_name_match = current_name_lower == existing_name_lower
                is_new_in_old_alts = current_name_lower in existing_alts_lower
                current_alts_lower = {" ".join(a.lower().split()) for a in current_alts}
                is_old_in_new_alts = existing_name_lower in current_alts_lower
                is_substring = (current_name_lower in existing_name_lower or existing_name_lower in current_name_lower) \
                               and len(current_name_lower) > 3 and len(existing_name_lower) > 3

                if is_name_match or is_new_in_old_alts or is_old_in_new_alts or is_substring:
                    match_found = True
                    
                    if name.lower() != existing["name"].lower():
                        if name.lower() not in GENERIC_NAMES:
                             existing["altNames"].add(name)
                    
                    if existing["name"].lower() in GENERIC_NAMES and name.lower() not in GENERIC_NAMES:
                        existing["altNames"].add(existing["name"])
                        existing["name"] = name
                    elif len(name) > len(existing["name"]) and name.lower() not in GENERIC_NAMES:
                         if existing["name"].lower() in name.lower():
                             existing["altNames"].add(existing["name"])
                             existing["name"] = name

                    existing["altNames"].update(current_alts)
                    
                    if existing["gender"] == "Unknown" and gender != "Unknown":
                        existing["gender"] = gender
                    break
            
            if not match_found:
                new_entry = {
                    "type": e_type,
                    "name": name,
                    "altNames": current_alts,
                    "IdentityTags": i_tags,
                    "ModifierTags": m_tags,
                    "VisualTags": v_tags
                }
                if "Character" in e_type:
                    new_entry["gender"] = gender
                else:
                    new_entry["gender"] = "Unknown"
                    
                merged_list.append(new_entry)

        for data in merged_list:
            main_name_lower = data["name"].lower()
            data["altNames"] = {a for a in data["altNames"] if a.lower() != main_name_lower}
            
            formatted_data = {
                "type": data["type"],
                "name": data["name"],
                "altNames": sorted(list(data["altNames"]))
            }

            e_type_lower = data["type"].lower()
            if "character" in e_type_lower:
                i_list = sorted(list(data["IdentityTags"]))[:MAX_TAGS]
                m_list = sorted(list(data["ModifierTags"]))[:MAX_TAGS]
                
                formatted_data["gender"] = data.get("gender", "Unknown")
                formatted_data["IdentityTags"] = ", ".join(i_list)
                formatted_data["ModifierTags"] = ", ".join(m_list)
                final_output["characters"].append(formatted_data)
            else:
                v_list = sorted(list(data["VisualTags"]))[:MAX_TAGS]
                formatted_data["VisualTags"] = ", ".join(v_list)
                
                if "location" in e_type_lower:
                    final_output["locations"].append(formatted_data)
                else:
                    final_output["items"].append(formatted_data)

        print(f"Extract Entities Time: {time.perf_counter() - start:.3f} seconds")

        try:
            saved_status = save_extraction_result(session, chapter_id, final_output)
            if saved_status:
                print("✅ Data successfully saved/updated in Database.")
                
                session.refresh(chapter_obj)
                if not chapter_obj.isExtracted:
                    chapter_obj.isExtracted = True
                    session.add(chapter_obj)
                    session.commit()
                    print("✅ Updated chapter.isExtracted to True.")
            else:
                print("⚠️ Failed to save data to Database.")
        except Exception as e:
            print(f"❌ Error saving to database: {e}")
            
    else:
        print(f"⚠️ Chapter {chapter_id} is already extracted. Skipping extraction logic, proceeding to image checks.")
        final_output["status"] = "skipped_extraction"

    if current_movie_id:
        print("💤 Sleeping 1 sec before image generation...")
        await asyncio.sleep(1)
        try:
            generate_images_for_missing_refpaths(session, current_movie_id)
        except Exception as e:
            print(f"❌ Error during image generation: {e}")

    return final_output