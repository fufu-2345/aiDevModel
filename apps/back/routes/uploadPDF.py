from fastapi import Depends, HTTPException, APIRouter, UploadFile, File, Form
from diffusers import StableDiffusionPipeline, StableDiffusionXLPipeline
from sqlmodel import Session
from database import get_session
from models import movieTitle, chapterContent
from googletrans import Translator
from sqlmodel import Session, select, SQLModel
import fitz 
import re
import gc
import os
import time
import json
import httpx
import torch
import asyncio
from models import movieTitle, chapterContent, chunkContent, character, altCharacter, entity, altEntity
from dotenv import load_dotenv

load_dotenv(".env.local")
router = APIRouter(
    prefix="/uploadPDF",
    tags=["uploadPDF"]
)

translator = Translator()
ollamaURL = os.getenv("ollamaURL")
stabilityModel = os.getenv("stabilityModel")
extractModel = "gemma3:12b"

def clearASCII(text: str) -> str:
    if not text:
        return ""
    replace_dict = {
        '\uf700': 'ฐ', '\uf701': 'ญ', '\uf702': 'ฐ', '\uf703': 'ญ',
        '\uf704': 'ญ', '\uf705': 'ฐ', '\uf706': 'ญ', '\uf707': 'ฐ',
        '\uf708': 'ญ', '\uf709': 'ญ', '\uf70a': '่', '\uf70b': '้',
        '\uf70c': '๊', '\uf70d': '๋', '\uf70e': '์', '\uf70f': 'ํ',
        '\uf710': 'ั', '\uf711': '็', '\uf712': 'ิ', '\uf713': 'ี',
        '\uf714': 'ึ', '\uf715': 'ื', '\uf716': 'ุ', '\uf717': 'ู',
        '\uf718': 'ุ', '\uf719': 'ู', '\uf71a': '็',
    }
    clearedText = text
    for pua_char, std_char in replace_dict.items():
        clearedText = clearedText.replace(pua_char, std_char)
    return clearedText

def clearThaiTypeing(text: str) -> str:
    if not text:
        return ""
    corrections = {
        "เปิน": "เป็น",
        "เปญด": "เปิด",
        "ปฐ": "ปี",
        "ปญอม": "ป้อม",
        "ฝฐา": "ฝ่า",
        "ฝญก": "ฝึก",
        "ฝฐาย": "ฝ่าย",
        "ฝฐ": "ฝี",
        "ฟญน": "ฟืน",    
        "ฟญา": "ฟ้า",
        "เฟญง": "เฟิง",
        "ฝัีง": "ฝั่ง",
        "ต่ํา": "ต่ำ",
    }
    fixed_text = text
    for wrong_word, correct_word in corrections.items():
        fixed_text = fixed_text.replace(wrong_word, correct_word)    
    return fixed_text

GENERIC_NAMES = {
    "man", "woman", "boy", "girl", "child", "kid", "baby", "children",
    "uncle", "aunt", "father", "mother", "dad", "mom", "parent", "parents",
    "brother", "sister", "grandfather", "grandmother", "grandpa", "grandma",
    "stranger", "villager", "person", "people", "someone", "nobody", "anybody",
    "friend", "enemy", "everyone", "master", "disciple", "teacher", "student",
    "he", "she", "him", "her", "they", "them", "it", "that", "this"
}

def clearNewline(text: str) -> str:
    def replacer(match):
        found = match.group()
        if found.count('\n') > 1:
            return '\n'
        if ' \n' in found:
            return '\n'
        return ''
    pattern = r"[ ]*\n[ \n]*"
    return re.sub(pattern, replacer, text).strip()

# extractEntities ใช้
async def processChunk(chunk_text: str, client: httpx.AsyncClient, extractModel: str):
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

def parse_tags_to_set(tags_input):
    if not tags_input:
        return set()
    if isinstance(tags_input, str):
        return set(t.strip() for t in tags_input.split(',') if t.strip())
    return set()

# gen รูป entity ที่ยังไม่มีรูป
def generate_images_for_missing_refpaths(session: Session, movie_id: int):
    print(f"🎨 Starting Image Generation for Movie ID: {movie_id}")
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
    pipeline = None
    try:
        print("a")
        pipeline = load_image_pipe()
        print("b")
    except Exception as e:
        print(f"❌ Failed to load Image Pipeline: {e}")
        return
    os.makedirs("public/storage/characters", exist_ok=True)
    os.makedirs("public/storage/entities", exist_ok=True)
    try:
        for char_obj in chars_to_gen:
            try:
                desc = f"{char_obj.IdentityTags}, {char_obj.ModifierTags}"
                prompt = f"ancient chinese style, {desc}, front view, full body shot:1.3, looking directly at camera, neutral expression, soft studio lighting, no shadows on face, high quality, simple white background"
                negative_prompt = "shadows, harsh lighting, cropped, cinematic lighting, hands on face, distorted face, profile view, looking away, busy background, blurry, low quality, nsfw"
                print(f"Generating Character: {char_obj.name}...")
                image = pipeline(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    num_inference_steps=20,
                    height=832, 
                    width=1216,
                    guidance_scale=7.0
                ).images[0]
                filename = f"storage/characters/{char_obj.id}.png"
                image.save(f"public/{filename}")
                char_obj.refpath = filename
                session.add(char_obj)
                session.commit() 
            except Exception as e:
                print(f"❌ Error generating character {char_obj.name}: {e}")
        for ent_obj in ents_to_gen:
            try:
                desc = ent_obj.visual_tags
                e_type_lower = ent_obj.type.lower()
                
                if "item" in e_type_lower:
                    prompt = f"ancient chinese style object, {desc}, product photography, centered shot, isolated on white background, studio lighting, soft shadows, high detail, 8k, sharp focus, realistic texture, professional lighting"
                    negative_prompt = "human, hands, holding, fingers, person, messy background, text, watermark, blurry, low quality, distortion, nsfw, cropped, out of frame"
                else: # Location
                    prompt = f"ancient chinese architecture, {desc}, establishing shot, wide angle view, highly detailed, realistic, 8k, cinematic lighting, depth of field, interior design, atmosphere, sharp focus"
                    negative_prompt = "people, crowd, humans, animals, text, watermark, blurry, low quality, distortion, simple background, white background, flat lighting"
                print(f"Generating Entity ({ent_obj.type}): {ent_obj.name}...")
                image = pipeline(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    num_inference_steps=30,
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
        if pipeline:
            del pipeline
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

def load_image_pipe():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch_dtype = torch.float16 if device == "cuda" else torch.float32

    is_xl = "xl" in stabilityModel.lower()
    is_safetensors = stabilityModel.endswith(".safetensors")
    PipelineClass = StableDiffusionXLPipeline if is_xl else StableDiffusionPipeline

    if is_safetensors:
            pipe = PipelineClass.from_single_file(
            stabilityModel,
            local_files_only=True,
            use_safetensors=True,
            torch_dtype=torch_dtype
        )
    else:
        pipe = PipelineClass.from_pretrained(
            stabilityModel,
            local_files_only=True,
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
    print(torch_dtype)
    
    return pipe

def merge_tags(old_tags: str, new_tags: str) -> str:
    """Helper function to merge comma-separated tags and remove duplicates."""
    if not old_tags:
        return new_tags
    if not new_tags:
        return old_tags
    
    s1 = set(t.strip() for t in old_tags.split(',') if t.strip())
    s2 = set(t.strip() for t in new_tags.split(',') if t.strip())
    merged = s1.union(s2)
    return ", ".join(sorted(list(merged)))

def find_entity_by_any_name(session: Session, name: str, e_type: str, movie_id: int):
    stmt = select(entity).where(entity.name == name, entity.type == e_type, entity.movieId == movie_id)
    found = session.exec(stmt).first()
    if found:
        return found
    
    alt_stmt = (
        select(entity)
        .join(altEntity, altEntity.entityId == entity.id)
        .where(altEntity.altName == name, entity.type == e_type, entity.movieId == movie_id)
    )
    return session.exec(alt_stmt).first()

def find_character_by_any_name(session: Session, name: str, movie_id: int):
    stmt = select(character).where(character.name == name, character.movieId == movie_id)
    found = session.exec(stmt).first()
    if found:
        return found
    
    alt_stmt = (
        select(character)
        .join(altCharacter, altCharacter.entityId == character.id)
        .where(altCharacter.altName == name, character.movieId == movie_id)
    )
    return session.exec(alt_stmt).first()

def handle_alt_names(session: Session, alt_model: SQLModel, target_id: int, alt_names: list):
    for alt in alt_names:
        check_stmt = select(alt_model).where(
            alt_model.altName == alt,
            alt_model.entityId == target_id
        )
        if not session.exec(check_stmt).first():
            session.add(alt_model(altName=alt, entityId=target_id))
            
def save_extraction_result(session: Session, chapter_id: int, data: dict):
    chapter = session.get(chapterContent, chapter_id)
    if not chapter or not chapter.movieId:
        return False
    
    current_movie_id = chapter.movieId

    for char_data in data.get("characters", []):
        name = char_data["name"]
        existing_char = find_character_by_any_name(session, name, current_movie_id)

        if existing_char:
            existing_char.IdentityTags = merge_tags(existing_char.IdentityTags, char_data.get("IdentityTags", ""))
            existing_char.ModifierTags = merge_tags(existing_char.ModifierTags, char_data.get("ModifierTags", ""))
            session.add(existing_char)
            target_char_id = existing_char.id
        else:
            new_char = character(
                name=name,
                type="Character",
                IdentityTags=char_data.get("IdentityTags", ""),
                ModifierTags=char_data.get("ModifierTags", ""),
                movieId=current_movie_id
            )
            session.add(new_char)
            session.commit()
            session.refresh(new_char)
            target_char_id = new_char.id

        handle_alt_names(session, altCharacter, target_char_id, char_data.get("altNames", []))

    all_general_entities = data.get("locations", []) + data.get("items", [])

    for ent_data in all_general_entities:
        name = ent_data["name"]
        e_type = ent_data["type"]
        existing_ent = find_entity_by_any_name(session, name, e_type, current_movie_id)

        if existing_ent:
            existing_ent.visual_tags = merge_tags(existing_ent.visual_tags, ent_data.get("VisualTags", ""))
            session.add(existing_ent)
            target_ent_id = existing_ent.id
        else:
            new_ent = entity(
                name=name,
                type=e_type,
                visual_tags=ent_data.get("VisualTags", ""),
                movieId=current_movie_id
            )
            session.add(new_ent)
            session.commit()
            session.refresh(new_ent)
            target_ent_id = new_ent.id
        
        handle_alt_names(session, altEntity, target_ent_id, ent_data.get("altNames", []))

    chapter.isExtracted = True
    session.add(chapter)
    session.commit()
    return True

#--------------------------------------------------------------------

# อัพโหลดไฟล์ pdf
@router.post("/")
async def uploadPDF(
    title: str = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_session)
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="This is not a PDF file")
    start_time = time.perf_counter()
    file_content = await file.read()
    
    new_movie = movieTitle(movieTitle=title, episodeAmount=0, picPath="")
    session.add(new_movie)
    session.commit()
    session.refresh(new_movie) 
    
    try:
        found_chapters_data = []
        chapter_map = [] 

        with fitz.open(stream=file_content, filetype="pdf") as doc:
            total_pages = len(doc)
            for i, page in enumerate(doc):
                raw_text = page.get_text()
                if not raw_text or not raw_text.strip():
                    continue
                
                lines = raw_text.split('\n')
                
                for line in lines[:1]:
                    match = re.search(r'ตอนที่\s*(\d+)', line)
                    if match:
                        found_chap_num = int(match.group(1))
                        if not chapter_map or chapter_map[-1]['num'] != found_chap_num:
                            chapter_map.append({
                                'num': found_chap_num,
                                'start_page': i
                            })
                        break 
            for idx, chap in enumerate(chapter_map):
                start_p = chap['start_page']
                end_p = chapter_map[idx+1]['start_page'] - 1 if (idx + 1 < len(chapter_map)) else total_pages - 1
                chapter_full_content = []
                chapter_title_text = ""
                for p_idx in range(start_p, end_p + 1):
                    page = doc[p_idx]
                    page_text = clearASCII(page.get_text() or "")
                    page_text = clearThaiTypeing(page_text)
                    page_text = clearNewline(page_text)
                    if p_idx == start_p:
                        lines = page_text.split('\n')
                        header_found = False
                        
                        for line in lines:
                            if not header_found and re.search(r'ตอนที่\s*' + str(chap['num']), line):
                                title_match = re.search(r'ตอนที่\s*\d+\s*(.*)', line)
                                if title_match:
                                    chapter_title_text = title_match.group(1).strip()
                                header_found = True
                            else:
                                chapter_full_content.append(line)
                    else:
                        chapter_full_content.append(page_text)
                
                final_title = chapter_title_text if chapter_title_text else f"ตอนที่ {chap['num']}"
                
                new_chapter = chapterContent(
                    episodeNumber=float(chap['num']),
                    chapterTitle=final_title,
                    chapterDetail="\n".join(chapter_full_content).strip(),
                    movieId=new_movie.id
                )
                session.add(new_chapter)
                found_chapters_data.append(new_chapter)
            new_movie.episodeAmount = len(found_chapters_data)
            session.add(new_movie)
            session.commit()
            print(f"Upload time use: {time.perf_counter()-start_time:.3f} seconds", flush=True)
            return {
                "status": "success",
                "movie_id": new_movie.id,
                "total_chapters_found": len(found_chapters_data),
                "chapters": [c.chapterTitle for c in found_chapters_data],
            }

    except Exception as e:
        print(f"Error processing PDF: {e}")
        session.delete(new_movie)
        session.commit()
        raise HTTPException(status_code=500, detail=f"PDF Processing Error: {e}")

# ใช้ ai extract entity และสร้างภาพ entity และอัพลง DB (เหลือดักชื่อซ้ำ + promt ยาวไป)
@router.get("/extractEntities/{chapter_id}")
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
        chapterDetail = chapter_obj.chapterDetail
        lines = chapterDetail.split('\n')
        total_lines = len(lines)
        
        LINES_PER_CHUNK = 10  
        OVERLAP = 3          
        
        chunks = []
        if total_lines <= LINES_PER_CHUNK:
            chunks = [chapterDetail]
        else: 
            step = LINES_PER_CHUNK - OVERLAP
            for i in range(0, total_lines, step):
                chunk_lines = lines[i : i + LINES_PER_CHUNK]
                if len(chunk_lines) < 3 and len(chunks) > 0:
                    break
                chunk_text = "\n".join(chunk_lines)
                chunks.append(chunk_text)

        results = []
        translator = Translator()

        async with httpx.AsyncClient(timeout=1800.0) as client:
            for idx, chunk in enumerate(chunks):
                print(f"Chunk {idx+1}/{len(chunks)} (Length: {len(chunk)} chars)")
                translator = Translator()
                await asyncio.sleep(1) 

                text_to_process = chunk
                try:
                    translated = await translator.translate(chunk, src='th', dest='en')
                    if translated and translated.text:
                        text_to_process = translated.text
                except Exception as e:
                    print(f"Trans Warning Ch {idx+1}: {e}")

                res = await processChunk(text_to_process, client, extractModel) 
                if res:
                    results.append(res)
                else:
                    print(f"Chunk {idx+1} Failed")

        # ----------------------------------------------------------------
        # NEW SMART MERGE LOGIC (In-place) with GENERIC NAME FILTER
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

            # Parse Alts & Clean Generic Alts
            raw_alts = raw.get("altNames", [])
            current_alts = set()
            if isinstance(raw_alts, list):
                current_alts = {str(a).strip() for a in raw_alts if str(a).strip()}
            elif isinstance(raw_alts, str):
                current_alts = {raw_alts.strip()}
            
            # --- FILTER GENERIC ALTS ---
            # ลบ altName ที่เป็นคำทั่วไป เช่น 'boy', 'man'
            current_alts = {a for a in current_alts if a.lower() not in GENERIC_NAMES}

            # --- FILTER MAIN NAME ---
            # ถ้าชื่อหลักเป็นคำทั่วไป (เช่น 'Boy') พยายามหาชื่ออื่นใน altNames มาแทน
            if name.lower() in GENERIC_NAMES:
                if len(current_alts) > 0:
                    # ถ้ามี altName ดีๆ ให้เอามาใช้เป็นชื่อหลักแทน แล้วลบออกจาก set
                    # เลือกชื่อที่ยาวที่สุดน่าจะดีกว่า (เช่นเลือก 'Fat Boy' แทน 'Boy')
                    best_name = max(current_alts, key=len) 
                    name = best_name
                    current_alts.remove(best_name)
                else:
                    # ถ้าไม่มีชื่ออื่นเลย และชื่อหลักเป็น Generic -> ทิ้งตัวนี้ไปเลย
                    print(f"⚠️ Skipped generic entity: {name}")
                    continue

            # Parse Tags
            i_tags = parse_tags_to_set(raw.get("IdentityTags"))
            m_tags = parse_tags_to_set(raw.get("ModifierTags"))
            v_tags = parse_tags_to_set(raw.get("VisualTags"))

            current_compare_set = {name.lower()} | {a.lower() for a in current_alts}

            match_found = False
            for existing in merged_list:
                if existing["type"] != e_type:
                    continue
                
                existing_compare_set = {existing["name"].lower()} | {a.lower() for a in existing["altNames"]}
                
                if not current_compare_set.isdisjoint(existing_compare_set):
                    match_found = True
                    
                    if name.lower() != existing["name"].lower():
                        # ถ้าชื่อใหม่ไม่ใช่ Generic ให้เอาไปเก็บ (Logic นี้อาจต้องปรับตามหน้างาน)
                        if name.lower() not in GENERIC_NAMES:
                             existing["altNames"].add(name)
                             
                    existing["altNames"].update(current_alts)
                    existing["IdentityTags"].update(i_tags)
                    existing["ModifierTags"].update(m_tags)
                    existing["VisualTags"].update(v_tags)
                    break
            
            if not match_found:
                merged_list.append({
                    "type": e_type,
                    "name": name,
                    "altNames": current_alts,
                    "IdentityTags": i_tags,
                    "ModifierTags": m_tags,
                    "VisualTags": v_tags
                })

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
                formatted_data["IdentityTags"] = ", ".join(sorted(list(data["IdentityTags"])))
                formatted_data["ModifierTags"] = ", ".join(sorted(list(data["ModifierTags"])))
                final_output["characters"].append(formatted_data)
            else:
                formatted_data["VisualTags"] = ", ".join(sorted(list(data["VisualTags"])))
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