import asyncio
import time
import os
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, create_engine, SQLModel 
import httpx
from dotenv import load_dotenv 

# Import Service
from .services.ai_engine import (
    analyze_script_content, 
    generate_location_prompt,
    unload_ollama, 
    flush_memory, 
    BGGenerator, 
    VNComposer
)

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
    print("Error: models.py not found.")

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

router = APIRouter(prefix="/createPic", tags=["createPic"])

OUTPUT_DIR = "public/storage/pic/"
CHAR_DIR = "public/storage/characters/"
BG_DIR = "public/storage/backgrounds/" 
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(BG_DIR, exist_ok=True)

# ==========================================
# 2. DB HELPERS
# ==========================================

def find_location_in_db(session: Session, movie_id: int, loc_name: str):
    """คืนค่า entity object หรือ None"""
    if not loc_name: return None
    # 1. Main
    loc = session.exec(select(entity).where(
        entity.movieId == movie_id, 
        entity.type == "Location",
        entity.name.ilike(f"%{loc_name}%")
    )).first()
    if loc: return loc
    # 2. Alt
    alt = session.exec(select(entity).join(altEntity).where(
        entity.movieId == movie_id,
        entity.type == "Location",
        altEntity.altName.ilike(f"%{loc_name}%")
    )).first()
    return alt

def find_character_path(session: Session, movie_id: int, char_name: str):
    if not char_name: return None
    def check(p): return p if p and os.path.exists(p) else None
    
    char = session.exec(select(character).where(
        character.movieId == movie_id, character.name.ilike(f"%{char_name}%")
    )).first()
    
    if not char:
        char = session.exec(select(character).join(altCharacter).where(
            character.movieId == movie_id, altCharacter.altName.ilike(f"%{char_name}%")
        )).first()

    if char:
        if p := check(char.refpath): return p
        if p := check(os.path.join(CHAR_DIR, f"{char.id}.png")): return p
        if p := check(os.path.join(CHAR_DIR, f"{char.id}.jpg")): return p
    return None

# ==========================================
# 3. MAIN BATCH PROCESS
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
    
    movie_id = chapter_info.movieId
    tasks_to_do = [] # [{chunk_id, location_name, characters}]
    missing_locations = {} # {location_name: {"prompt": str, "db_entity": obj or None}}

    print("🔵 [PHASE 1] Script Analysis (Ollama)...")
    async with httpx.AsyncClient(timeout=120.0) as client:
        for chunk in chunks:
            if chunk.picRef: 
                print(f"   Skipping Chunk {chunk.chunkNumber} (Exists)")
                continue
            
            text_input = chunk.chunkDetailEng if chunk.chunkDetailEng else chunk.chunkDetail
            if not text_input: continue

            # 1. Analyze Script
            meta = await analyze_script_content(text_input, client)
            if not meta: continue
            
            loc_name = meta.get('location_name', 'Unknown Location')
            chars = meta.get('characters', [])
            
            tasks_to_do.append({
                "chunk_obj": chunk,
                "location_name": loc_name,
                "characters": chars,
                "text_context": text_input
            })

            # 2. Check Location in DB
            loc_entity = find_location_in_db(session, movie_id, loc_name)
            
            # ถ้ามีใน DB แต่ไม่มีไฟล์ -> ต้องเจน
            # ถ้าไม่มีใน DB -> ต้องเจน และสร้าง DB ใหม่
            has_file = loc_entity and loc_entity.refpath and os.path.exists(loc_entity.refpath)
            
            if not has_file and loc_name not in missing_locations:
                print(f"   ❓ Missing BG for: {loc_name}")
                # Ask Ollama for visual prompt
                bg_prompt = await generate_location_prompt(loc_name, text_input, client)
                missing_locations[loc_name] = {
                    "prompt": bg_prompt,
                    "db_entity": loc_entity, # อาจเป็น None ถ้ายังไม่เคยมี record
                    "refpath": None
                }

        # จบ Phase 1: ปิด Ollama
        print("🟡 [TRANSITION] Unloading Ollama...")
        await unload_ollama(client)
        flush_memory()

        # Phase 2: Generate Missing Backgrounds
        if missing_locations:
            print(f"🟢 [PHASE 2] Generating {len(missing_locations)} Backgrounds...")
            bg_gen = BGGenerator()
            
            for loc_name, data in missing_locations.items():
                safe_name = "".join([c for c in loc_name if c.isalnum() or c in (' ','-','_')]).strip()
                bg_filename = f"bg_{movie_id}_{safe_name}_{int(time.time())}.png"
                bg_path = os.path.join(BG_DIR, bg_filename)
                
                # Generate SDXL (Run in thread)
                success = await asyncio.to_thread(bg_gen.generate_bg, data['prompt'], bg_path)
                
                if success:
                    data['refpath'] = bg_path
                    # Save/Update DB
                    if data['db_entity']:
                        # Update existing entity
                        data['db_entity'].refpath = bg_path
                        session.add(data['db_entity'])
                    else:
                        # Create new entity
                        new_loc = entity(
                            type="Location",
                            name=loc_name,
                            visual_tags=data['prompt'],
                            movieId=movie_id,
                            refpath=bg_path
                        )
                        session.add(new_loc)
                    session.commit()
            
            # Clear SDXL from memory
            del bg_gen
            flush_memory()

        # Phase 3: Composition
        print("🟣 [PHASE 3] Compositing Scenes...")
        composer = VNComposer()
        success_count = 0

        for task in tasks_to_do:
            loc_name = task['location_name']
            
            # หา BG Path (priority: เพิ่งเจนใหม่ -> ใน DB)
            bg_path = None
            if loc_name in missing_locations and missing_locations[loc_name]['refpath']:
                bg_path = missing_locations[loc_name]['refpath']
            else:
                loc_entity = find_location_in_db(session, movie_id, loc_name)
                if loc_entity and loc_entity.refpath:
                    bg_path = loc_entity.refpath

            # หา Character Paths
            char_paths = []
            for char_name in task['characters']:
                cp = find_character_path(session, movie_id, char_name)
                if cp: char_paths.append(cp)
            
            # Final Output Path
            chunk = task['chunk_obj']
            final_filename = f"ch{chapter_id}_chunk{chunk.chunkNumber}_{int(time.time())}.png"
            final_path = os.path.join(OUTPUT_DIR, final_filename)

            # Compose
            if await asyncio.to_thread(composer.compose, bg_path, char_paths, final_path):
                chunk.picRef = final_path
                session.add(chunk)
                success_count += 1
        
        session.commit()

    return {
        "status": "completed",
        "generated": success_count,
        "bg_created": len(missing_locations)
    }