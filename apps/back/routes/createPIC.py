import asyncio
import time
import os
import difflib 
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, create_engine, SQLModel 
import httpx
from dotenv import load_dotenv 

# Import Service
try:
    from .services.ai_engine import (
        analyze_script_content, 
        generate_location_prompt,
        unload_ollama, 
        flush_memory, 
        BGGenerator, 
        VNComposer
    )
except ImportError:
    from services.ai_engine import (
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

# ✅ ปรับ Path ตามที่ขอ
OUTPUT_DIR = "public/storage/pic/"
CHAR_DIR = "public/storage/characters/"
ENTITIES_DIR = "public/storage/entities/" # เก็บรูปสถานที่ตาม ID
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(ENTITIES_DIR, exist_ok=True)

# ==========================================
# 2. PATH HELPERS
# ==========================================

def resolve_file_path(db_path: str) -> Optional[str]:
    """
    แปลง Path จาก DB (storage/...) ให้เป็น System Path ที่ Python อ่านได้ (public/storage/...)
    """
    if not db_path: return None
    
    # 1. เช็ค Path ตรงๆ
    if os.path.exists(db_path): return db_path
    
    # 2. ถ้าไม่มี public/ ให้ลองเติมดู
    if not db_path.startswith("public/"):
        public_path = os.path.join("public", db_path)
        if os.path.exists(public_path): return public_path
        
    return None

# ==========================================
# 3. SMART DB HELPERS (Fuzzy Logic)
# ==========================================

def find_smart_location(session: Session, movie_id: int, loc_name: str) -> Optional[entity]:
    if not loc_name: return None
    
    # 1. Exact Match
    exact_loc = session.exec(select(entity).where(
        entity.movieId == movie_id, 
        entity.type == "Location",
        entity.name.ilike(loc_name)
    )).first()
    if exact_loc: return exact_loc

    # 2. Fuzzy Match
    all_locs = session.exec(select(entity).where(
        entity.movieId == movie_id,
        entity.type == "Location"
    )).all()
    
    loc_map = {l.name.lower(): l for l in all_locs}
    matches = difflib.get_close_matches(loc_name.lower(), loc_map.keys(), n=1, cutoff=0.7)
    
    if matches:
        matched_name = matches[0]
        print(f"      💡 Fuzzy Matched: '{loc_name}' -> '{matched_name}'")
        return loc_map[matched_name]
        
    return None

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
# 4. MAIN BATCH PROCESS
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
    tasks_to_do = [] 
    missing_locations = {} # {loc_name: {prompt, db_entity}}

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
            loc_entity = find_smart_location(session, movie_id, loc_name)
            
            # เช็คว่ามีไฟล์จริงไหม (ใช้ resolve_file_path ช่วยเช็ค)
            real_path = resolve_file_path(loc_entity.refpath) if loc_entity else None
            has_file = real_path is not None
            
            if not has_file and loc_name not in missing_locations:
                print(f"   ❓ Missing BG for: '{loc_name}'")
                
                bg_prompt = await generate_location_prompt(loc_name, text_input, client)
                missing_locations[loc_name] = {
                    "prompt": bg_prompt,
                    "db_entity": loc_entity, # ส่ง Entity เดิมไปถ้ามี
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
                
                # 1. เตรียม Entity & ID เพื่อตั้งชื่อไฟล์
                loc_entity = data['db_entity']
                if not loc_entity:
                    print(f"      💾 Creating New DB Location: {loc_name}")
                    loc_entity = entity(
                        type="Location",
                        name=loc_name,
                        visual_tags=data['prompt'],
                        movieId=movie_id,
                        refpath="" # ใส่ว่างไว้ก่อน
                    )
                    session.add(loc_entity)
                    session.commit()
                    session.refresh(loc_entity) # ✅ ได้ ID มาแล้ว
                    data['db_entity'] = loc_entity
                
                # 2. ตั้งชื่อไฟล์ตาม ID
                entity_id = loc_entity.id
                filename = f"{entity_id}.png"
                fs_path = os.path.join(ENTITIES_DIR, filename)       # path จริงในเครื่อง
                db_refpath = f"storage/entities/{filename}"          # path ที่เก็บใน DB
                
                # 3. Generate Image
                success = await asyncio.to_thread(bg_gen.generate_bg, data['prompt'], fs_path)
                
                if success:
                    data['refpath'] = fs_path # เก็บ Path จริงไว้ใช้ใน Phase 3
                    
                    # 4. Update DB
                    print(f"      💾 Updating DB Refpath: {db_refpath}")
                    loc_entity.refpath = db_refpath
                    session.add(loc_entity)
                    session.commit()
            
            del bg_gen
            flush_memory()

        # Phase 3: Composition
        print("🟣 [PHASE 3] Compositing Scenes...")
        composer = VNComposer()
        success_count = 0

        for task in tasks_to_do:
            loc_name = task['location_name']
            
            bg_path = None
            
            # 1. เช็คจากคิวที่เพิ่งเจน (Path จริง)
            if loc_name in missing_locations and missing_locations[loc_name]['refpath']:
                bg_path = missing_locations[loc_name]['refpath']
            
            # 2. ถ้าไม่มี ให้หาจาก DB แล้วแปลงเป็น Path จริง
            if not bg_path:
                loc_entity = find_smart_location(session, movie_id, loc_name)
                if loc_entity:
                    bg_path = resolve_file_path(loc_entity.refpath)

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