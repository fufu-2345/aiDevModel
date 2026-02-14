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
extractModel = "gemma3:12b" 

# Image Generation Config
stabilityModel = "stabilityai/stable-diffusion-xl-base-1.0" 
# loraPath removed

# Limits
MAX_TAGS = 20 

# Blocklist: คำทั่วไปที่ไม่ควรเป็นชื่อตัวละคร (เพิ่ม first, second, third...)
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
    "third uncle", "second uncle", "fourth uncle",
    "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth",
    "number one", "number two", "number three"
}

# Blocklist: Tag ที่ไม่มีประโยชน์ในการ Gen ภาพ หรือซ้ำซ้อนกับ Gender
BANNED_TAGS = {
    "person", "unknown", "man", "woman", "male", "female", "boy", "girl", 
    "human", "character", "someone", "people"
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

    if hasattr(pipe, "safety_checker"):
        pipe.safety_checker = None
    if hasattr(pipe, "requires_safety_checker"):
        pipe.requires_safety_checker = False
    if hasattr(pipe, "watermarker"):
        pipe.watermarker = None
        
    pipe.to(device)    
    
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
                # Prepare Tags
                i_tags_list = [t.strip() for t in char_obj.IdentityTags.split(',') if t.strip()]
                m_tags_list = [t.strip() for t in char_obj.ModifierTags.split(',') if t.strip()]
                
                # Combine and Deduplicate
                combined_tags = i_tags_list + m_tags_list
                seen = set()
                deduped_tags = []
                for t in combined_tags:
                    if t.lower() not in seen:
                        deduped_tags.append(t)
                        seen.add(t.lower())
                
                limited_desc = ", ".join(deduped_tags[:MAX_TAGS])
                desc = limited_desc if limited_desc else "character"
                
                # --- Prompt Engineering (Character) ---
                prompt = (
                    f"ancient chinese style, {desc}, full body shot, standing still, "
                    f"arms at sides, empty hands, looking directly at camera, "
                    f"neutral expression, soft studio lighting, no shadows on face, "
                    f"high quality, simple white background, solo, single person"
                )
                
                negative_prompt = (
                    "shadows, harsh lighting, cropped, cinematic lighting, hands on face, "
                    "distorted face, profile view, looking away, busy background, blurry, "
                    "low quality, nsfw, holding object, weapon, sword, multiple people, "
                    "group, extra limbs"
                )
                
                print(f"Generating Character: {char_obj.name}...")
                image = pipeline(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    num_inference_steps=20, 
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

        # Loop สร้างภาพ Entities
        for ent_obj in ents_to_gen:
            try:
                v_tags_list = [t.strip() for t in ent_obj.visual_tags.split(',') if t.strip()]
                seen = set()
                deduped_tags = []
                for t in v_tags_list:
                    if t.lower() not in seen:
                        deduped_tags.append(t)
                        seen.add(t.lower())

                desc = ", ".join(deduped_tags[:MAX_TAGS])
                e_type_lower = ent_obj.type.lower()
                
                if "item" in e_type_lower:
                    prompt = (
                        f"ancient chinese style object, {desc}, product photography, centered shot, "
                        f"isolated on white background, studio lighting, soft shadows, high detail, "
                        f"8k, sharp focus, realistic texture, professional lighting"
                    )
                    negative_prompt = (
                        "nsfw, nude, naked, 18+, human, hands, holding, fingers, person, "
                        "messy background, text, watermark, blurry, low quality, distortion, "
                        "cropped, out of frame, worst quality"
                    )
                else: 
                    prompt = (
                        f"ancient chinese architecture, {desc}, establishing shot, wide angle view, "
                        f"highly detailed, realistic, 8k, cinematic lighting, depth of field, "
                        f"interior design, atmosphere, sharp focus"
                    )
                    negative_prompt = (
                        "nsfw, nude, naked, 18+, people, crowd, humans, animals, text, watermark, "
                        "blurry, low quality, distortion, simple background, white background, "
                        "flat lighting, worst quality"
                    )

                print(f"Generating Entity ({ent_obj.type}): {ent_obj.name}...")
                image = pipeline(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    num_inference_steps=20, 
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
    print(f"Creating chunks for Chapter {chapter.id}...")
    
    existing_chunks = session.exec(select(chunkContent).where(chunkContent.chapterId == chapter.id)).all()
    for old_chunk in existing_chunks:
        session.delete(old_chunk)
    session.commit()

    lines = chapter.chapterDetail.split('\n')
    total_lines = len(lines)
    
    LINES_PER_CHUNK = 5  
    OVERLAP = 1          
    step = LINES_PER_CHUNK - OVERLAP
    
    raw_chunks_data = [] 
    
    if total_lines <= LINES_PER_CHUNK:
        raw_chunks_data.append((chapter.chapterDetail, chapter.chapterDetail))
    else: 
        for i in range(0, total_lines, step):
            # 1. ส่วน Overlap (สำหรับ AI)
            chunk_lines_overlap = lines[i : i + LINES_PER_CHUNK]
            if len(chunk_lines_overlap) < 3 and len(raw_chunks_data) > 0:
                break 
            text_overlap = "\n".join(chunk_lines_overlap)
            
            # 2. ส่วน No Overlap (สำหรับ DB)
            next_start_idx = i + step
            is_last_chunk = False
            if next_start_idx >= total_lines:
                is_last_chunk = True
            else:
                next_chunk_lines = lines[next_start_idx : next_start_idx + LINES_PER_CHUNK]
                if len(next_chunk_lines) < 3: 
                    is_last_chunk = True
            
            if is_last_chunk:
                chunk_lines_no_overlap = lines[i:]
            else:
                chunk_lines_no_overlap = lines[i : i + step]
            
            text_no_overlap = "\n".join(chunk_lines_no_overlap)
            raw_chunks_data.append((text_no_overlap, text_overlap))

    print(f"Processing Chapter {chapter.id}: Found {len(raw_chunks_data)} chunks.")

    final_eng_chunks = []
    
    for idx, (thai_no_overlap, thai_overlap) in enumerate(raw_chunks_data):
        print(f"Processing chunk {idx+1}/{len(raw_chunks_data)}...")

        # แปลเฉพาะส่วนที่มี Overlap
        eng_text = await translate_text(thai_overlap)
        final_eng_chunks.append(eng_text)
        
        new_chunk = chunkContent(
            chunkNumber = idx + 1,
            chunkDetail = thai_no_overlap,  # No Overlap
            chunkDetailEng = eng_text,      # With Overlap
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
    1. "IdentityTags": Fixed physical traits (hair color, eye color, race, gender).
    2. "ModifierTags": Changeable traits (clothing, emotions, dirt, poses).
    3. Use the "first appearance" for changing traits.
    4. Tags must be nouns/adjectives only. No verbs.
    5. English output only.

    Output JSON Format:
    {{
        "entities": [
            {{
                "type": "Character",
                "name": "Name",
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
        match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if match:
            json_str = match.group(0)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
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

            # CLEAN TAGS (Remove Banned, Dedupe)
            i_tags = parse_tags_to_set(raw.get("IdentityTags"))
            m_tags = parse_tags_to_set(raw.get("ModifierTags"))
            v_tags = parse_tags_to_set(raw.get("VisualTags"))
            
            i_tags = {t for t in i_tags if t.lower() not in BANNED_TAGS}
            m_tags = {t for t in m_tags if t.lower() not in BANNED_TAGS}
            # Remove tags in Modifier that are also in Identity
            m_tags = {t for t in m_tags if t.lower() not in {it.lower() for it in i_tags}}

            current_name_lower = " ".join(name.lower().split())
            
            # Note: Removed gender extraction from raw since user reverted prompt
            # Will default to "Unknown" if not in prompt, or use existing if merging
            gender = "Unknown" 

            match_found = False
            for existing in merged_list:
                if existing["type"] != e_type:
                    continue
                
                existing_name_lower = " ".join(existing["name"].lower().split())
                existing_alts_lower = {" ".join(a.lower().split()) for a in existing["altNames"]}
                
                # --- STRICT MERGE RULES ---
                is_name_match = current_name_lower == existing_name_lower
                is_new_in_old_alts = current_name_lower in existing_alts_lower
                current_alts_lower = {" ".join(a.lower().split()) for a in current_alts}
                is_old_in_new_alts = existing_name_lower in current_alts_lower
                # Substring check with stricter length > 5
                is_substring = (current_name_lower in existing_name_lower or existing_name_lower in current_name_lower) \
                               and len(current_name_lower) > 5 and len(existing_name_lower) > 5

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
                    
                    # Merge Tags
                    existing["IdentityTags"].update(i_tags)
                    existing["ModifierTags"].update(m_tags)
                    existing["VisualTags"].update(v_tags)
                    
                    # Gender merge logic removed as gender is not in prompt anymore
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
                # LIMIT TAGS
                i_list = sorted(list(data["IdentityTags"]))
                m_list = sorted(list(data["ModifierTags"]))
                
                final_i_tags = []
                final_m_tags = []
                current_count = 0
                
                for t in i_list:
                    if current_count < MAX_TAGS:
                        final_i_tags.append(t)
                        current_count += 1
                
                for t in m_list:
                    if current_count < MAX_TAGS:
                        final_m_tags.append(t)
                        current_count += 1
                
                formatted_data["gender"] = data.get("gender", "Unknown")
                formatted_data["IdentityTags"] = ", ".join(final_i_tags)
                formatted_data["ModifierTags"] = ", ".join(final_m_tags)
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