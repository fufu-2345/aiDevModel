import asyncio
import time
import os
import difflib 
import shutil
from typing import List, Dict, Any, Optional
from PIL import Image

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, create_engine, SQLModel, Field
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

# อัปเดต Model Matcher 
class matcher(SQLModel, table=True):
    __table_args__ = {'extend_existing': True}
    id: Optional[int] = Field(default=None, primary_key=True)
    character: str
    location: str
    duration: float
    chunkContentId: Optional[int] = Field(default=None, foreign_key="chunkcontent.id")
    chapterId: Optional[int] = Field(default=None, foreign_key="chaptercontent.id")

try:
    from database import get_session
except ImportError:
    from ..database import get_session

router = APIRouter(prefix="/createPic", tags=["createPic"])

OUTPUT_DIR = "public/storage/pic/"
CHAR_DIR = "public/storage/characters/"
ENTITIES_DIR = "public/storage/entities/"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(ENTITIES_DIR, exist_ok=True)

def resolve_file_path(db_path: str) -> Optional[str]:
    if not db_path: return None
    if os.path.exists(db_path): return db_path
    if not db_path.startswith("public/"):
        public_path = os.path.join("public", db_path)
        if os.path.exists(public_path): return public_path
    return None

def find_smart_location(session: Session, movie_id: int, loc_name: str) -> Optional[entity]:
    if not loc_name: return None
    exact_loc = session.exec(select(entity).where(
        entity.movieId == movie_id, 
        entity.type == "Location",
        entity.name.ilike(loc_name)
    )).first()
    if exact_loc: return exact_loc

    all_locs = session.exec(select(entity).where(entity.movieId == movie_id, entity.type == "Location")).all()
    loc_map = {l.name.lower(): l for l in all_locs}
    matches = difflib.get_close_matches(loc_name.lower(), loc_map.keys(), n=1, cutoff=0.7)
    return loc_map[matches[0]] if matches else None

def find_character_path(session: Session, movie_id: int, char_name: str):
    if not char_name: return None
    def check(p): return p if p and os.path.exists(p) else None
    char = session.exec(select(character).where(character.movieId == movie_id, character.name.ilike(f"%{char_name}%"))).first()
    if not char:
        char = session.exec(select(character).join(altCharacter).where(character.movieId == movie_id, altCharacter.altName.ilike(f"%{char_name}%"))).first()
    if char:
        if p := check(char.refpath): return p
        if p := check(os.path.join(CHAR_DIR, f"{char.id}.png")): return p
        if p := check(os.path.join(CHAR_DIR, f"{char.id}.jpg")): return p
    return None

@router.get("/generate-images/{chapter_id}")
async def generate_images_for_chapter(
    chapter_id: int, 
    session: Session = Depends(get_session)
):
    all_chunks = session.exec(select(chunkContent).where(chunkContent.chapterId == chapter_id).order_by(chunkContent.chunkNumber)).all()
    chapter_info = session.get(chapterContent, chapter_id)
    if not all_chunks or not chapter_info:
        return {"status": "error", "message": "No data found."}

    movie_id = chapter_info.movieId
    tasks_to_do = [] 
    missing_locations = {}
    print("Analysing")
    async with httpx.AsyncClient(timeout=120.0) as client:
        for chunk in all_chunks:
            needs_final_pic = not bool(chunk.picRef)
            current_match = session.exec(select(matcher).where(matcher.chunkContentId == chunk.id)).first()
            needs_matcher = False
            
            if not current_match:
                needs_matcher = True
            else:
                if not current_match.character or not current_match.location:
                    needs_matcher = True
            if not needs_final_pic and not needs_matcher:
                continue 
            text_input = chunk.chunkDetailEng if chunk.chunkDetailEng else chunk.chunkDetail
            if not text_input: continue
            meta = await analyze_script_content(text_input, client)
            if not meta: continue
            loc_name = meta.get('location_name', 'Unknown Location')
            tasks_to_do.append({
                "chunk_obj": chunk,
                "location_name": loc_name,
                "characters": meta.get('characters', []),
                "text_context": text_input,
                "needs_final_pic": needs_final_pic,
                "needs_matcher": needs_matcher,
                "matcher_record": current_match 
            })

            loc_entity = find_smart_location(session, movie_id, loc_name)
            real_path = resolve_file_path(loc_entity.refpath) if loc_entity else None
            
            if not real_path and loc_name not in missing_locations:
                bg_prompt = await generate_location_prompt(loc_name, text_input, client)
                missing_locations[loc_name] = {"prompt": bg_prompt, "db_entity": loc_entity}

        await unload_ollama(client)
        flush_memory()
        if missing_locations:
            print(f"Generate {len(missing_locations)} Backgrounds...")
            bg_gen = BGGenerator()
            for loc_name, data in missing_locations.items():
                loc_entity = data['db_entity']
                if not loc_entity:
                    loc_entity = entity(type="Location", name=loc_name, visual_tags=data['prompt'], movieId=movie_id, refpath="")
                    session.add(loc_entity)
                    session.commit()
                    session.refresh(loc_entity)

                fs_path = os.path.join(ENTITIES_DIR, f"{loc_entity.id}.png")
                if await asyncio.to_thread(bg_gen.generate_bg, data['prompt'], fs_path):
                    loc_entity.refpath = f"storage/entities/{loc_entity.id}.png"
                    session.add(loc_entity)
            session.commit()
            del bg_gen
            flush_memory()
        print("Matching")
        for task in tasks_to_do:
            if not task['needs_matcher']:
                continue 
            chunk = task['chunk_obj']
            loc_name = task['location_name']
            chars = task['characters']
            current_match = task['matcher_record']
            if not current_match:
                current_match = matcher(
                    chapterId=chapter_id,
                    chunkContentId=chunk.id,
                    character="",
                    location="",
                    duration=0.0
                )
                session.add(current_match)
                session.commit()
                session.refresh(current_match)
            loca_filename = f"{chapter_id}_{chunk.chunkNumber}_loca.png"
            cha_filename = f"{chapter_id}_{chunk.chunkNumber}_cha.png"
            loc_entity = find_smart_location(session, movie_id, loc_name)
            bg_path = resolve_file_path(loc_entity.refpath) if loc_entity else None
            loca_filepath = os.path.join(OUTPUT_DIR, loca_filename) 
            if bg_path and os.path.exists(bg_path):
                shutil.copy(bg_path, loca_filepath)
            else:
                Image.new("RGB", (1024, 1024), (0, 0, 0)).save(loca_filepath)
            cha_filepath = os.path.join(OUTPUT_DIR, cha_filename)
            char_paths = []
            for char_name in chars:
                cp = find_character_path(session, movie_id, char_name)
                if cp: char_paths.append(cp)
            base_img = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0)) 
            if char_paths:
                num_chars = len(char_paths)
                for i, cp in enumerate(char_paths):
                    try:
                        c_img = Image.open(cp).convert("RGBA")
                        target_h = int(1024 * 0.8) 
                        target_w = int(c_img.width * (target_h / c_img.height))
                        c_img = c_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
                        
                        x_offset = (1024 // (num_chars + 1)) * (i + 1) - (target_w // 2)
                        y_offset = 1024 - target_h
                        
                        base_img.paste(c_img, (x_offset, y_offset), c_img)
                    except Exception as e:
                        print(f"      ⚠️ Error composing character for matcher: {e}")
            base_img.save(cha_filepath)
            current_match.location = loca_filename
            current_match.character = cha_filename
            session.add(current_match)
        session.commit()
        print("Save to DB")
        composer = VNComposer()
        success_count = 0
        for task in tasks_to_do:
            if not task['needs_final_pic']:
                continue
            loc_entity = find_smart_location(session, movie_id, task['location_name'])
            bg_path = resolve_file_path(loc_entity.refpath) if loc_entity else None
            char_paths = []
            for char_name in task['characters']:
                cp = find_character_path(session, movie_id, char_name)
                if cp: char_paths.append(cp)
            chunk = task['chunk_obj']
            final_path = os.path.join(OUTPUT_DIR, f"ch{chapter_id}_chunk{chunk.chunkNumber}_{int(time.time())}.png")
            if await asyncio.to_thread(composer.compose, bg_path, char_paths, final_path):
                chunk.picRef = final_path
                session.add(chunk)
                success_count += 1
        session.commit()
    return {
        "status": "completed",
        "generated_final_pics": success_count,
        "processed_tasks": len(tasks_to_do)
    }