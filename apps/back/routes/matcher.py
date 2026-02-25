import os
import json
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlmodel import Session, select
from typing import List, Optional

from moviepy import ImageClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip, CompositeAudioClip, vfx

from database import get_session
from models import matcher, chapterContent

router = APIRouter(
    prefix="/matcher",
    tags=["matcher"]
)

# ฟังก์ชันเสริมสำหรับแกะข้อมูลชื่อไฟล์ตัวละคร (รองรับทั้งแบบ Array JSON และแบบคั่นด้วยลูกน้ำ)
def parse_characters(char_data):
    if not char_data: return []
    char_str = str(char_data).strip()
    if char_str.startswith('[') and char_str.endswith(']'):
        try:
            return json.loads(char_str)
        except:
            pass
    if ',' in char_str:
        return [c.strip() for c in char_str.split(',') if c.strip()]
    return [char_str]

def process_video_generation(chapter_id: int, session: Session):
    chapter = session.get(chapterContent, chapter_id)
    if not chapter:
        print(f"Error: ไม่พบ Chapter {chapter_id} ในระบบ")
        return

    statement = select(matcher).where(matcher.chapterId == chapter_id).order_by(matcher.id)
    matchers = session.exec(statement).all()
    
    if not matchers:
        print(f"Error: ไม่พบข้อมูล Matcher สำหรับ Chapter {chapter_id}")
        return
        
    scene_clips = []
    IMAGE_BASE_DIR = "public/storage/pic/"

    valid_matchers = []
    for m in matchers:
        loc_filename = str(m.location) if m.location else ""
        loc_path = os.path.join(IMAGE_BASE_DIR, loc_filename)

        if not os.path.isfile(loc_path):
            print(f"Warning: ข้าม Scene ID {m.id} เนื่องจากหาไฟล์ Background ไม่พบ")
            continue

        # ดึงรายชื่อตัวละครทั้งหมดและกรองเอาเฉพาะไฟล์ที่มีอยู่จริง + ตัดคนซ้ำออก
        char_files = parse_characters(m.character)
        valid_chars = []
        for cf in char_files:
            cp = os.path.join(IMAGE_BASE_DIR, cf)
            # ถ้ามีไฟล์จริง และยังไม่เคยถูกเพิ่มลงไปในฉากนี้ (ป้องกันแฝด)
            if os.path.isfile(cp) and cp not in valid_chars:
                valid_chars.append(cp)

        try:
            db_dur = float(m.duration) if m.duration else 0.0
        except (ValueError, TypeError):
            db_dur = 0.0
        
        current_dur = db_dur if db_dur >= 1.0 else 3.0

        if valid_matchers and valid_matchers[-1]["loc"] == loc_path and valid_matchers[-1]["chars"] == valid_chars:
            valid_matchers[-1]["duration"] += current_dur
            print(f"Info: ดักจับภาพซ้ำ - รวม Scene ID {m.id} เข้ากับฉากก่อนหน้าแล้ว")
        else:
            valid_matchers.append({
                "data": m,
                "loc": loc_path,
                "chars": valid_chars,  # เก็บเป็น Array ของตัวละครที่พร้อมใช้งาน
                "duration": current_dur
            })

    if not valid_matchers:
        print(f"Error: ไม่พบ Scene ที่รูปภาพครบถ้วนเลยสำหรับ Chapter {chapter_id}")
        return

    total_scenes = len(valid_matchers)
    
    for i, item in enumerate(valid_matchers):
        m = item["data"]
        loc_path = item["loc"]
        valid_chars = item["chars"][:3]  # จำกัดสูงสุดไม่เกิน 3 คน
        base_duration = item["duration"]

        is_last_scene = (i == total_scenes - 1)
        fade_dur = 1.0 if is_last_scene else 0.5
        hold_duration = base_duration
        
        if is_last_scene:
            hold_duration += 1.0
            
        total_duration = hold_duration
        
        bg = ImageClip(loc_path).with_duration(total_duration)
        bg = bg.with_effects([vfx.FadeIn(fade_dur), vfx.FadeOut(fade_dur)])
        
        ENABLE_CHARACTER_OVERLAY = True
        
        if ENABLE_CHARACTER_OVERLAY and valid_chars:
            N = len(valid_chars)
            char_names = [os.path.basename(c) for c in valid_chars]
            print(f"ฉากที่ {i+1} กำลังรวม Background: {m.location} กับ ตัวละคร {N} ตัว: {', '.join(char_names)}")
            
            char_clips = []
            bg_w, bg_h = bg.size
            
            for idx, cp in enumerate(valid_chars):
                char = ImageClip(cp)
                char_w, char_h = char.size
                
                # คำนวณตำแหน่งแกน X ตามจำนวนคน
                if N == 1:
                    target_x = (bg_w - char_w) / 2
                elif N == 2:
                    if idx == 0: target_x = (bg_w / 3) - (char_w / 2)
                    else: target_x = (bg_w * 2 / 3) - (char_w / 2)
                else:  # N == 3
                    if idx == 0: target_x = (bg_w / 4) - (char_w / 2)
                    elif idx == 1: target_x = (bg_w * 2 / 4) - (char_w / 2)
                    else: target_x = (bg_w * 3 / 4) - (char_w / 2)
                    
                end_y = (bg_h - char_h) / 2
                start_y = -char_h
                
                # ใช้ closure function แบบผูกค่าตัวแปร (Factory) ป้องกันบั๊กตำแหน่งเพี้ยน
                def make_char_pos(tx, sy, ey, anim_dur):
                    def char_pos(t):
                        if t <= anim_dur:
                            current_y = sy + (ey - sy) * (t / anim_dur)
                            return (tx, current_y)
                        return (tx, ey)
                    return char_pos
                    
                char = (char.with_duration(total_duration)
                           .with_position(make_char_pos(target_x, start_y, end_y, fade_dur))
                           .with_effects([vfx.FadeIn(fade_dur), vfx.FadeOut(fade_dur)]))
                           
                char_clips.append(char)
                
            scene = CompositeVideoClip([bg] + char_clips)
        else:
            print(f"ฉากที่ {i+1} ใช้แค่ Background: {m.location}")
            scene = bg
            
        scene_clips.append(scene)
        
    if not scene_clips:
        print(f"Error: ไม่สามารถสร้าง Scene ได้เลยสำหรับ Chapter {chapter_id}")
        return

    final_video = concatenate_videoclips(scene_clips, method="compose")
    
    print(f"\n==================================================")
    print(f"เตรียมเรนเดอร์วิดีโอ Chapter: {chapter_id}")
    print(f"จำนวน Scene ทั้งหมดที่ใช้ (หลังหักภาพซ้ำ): {total_scenes} ฉาก")
    print(f"ความยาววิดีโอรวมทั้งหมด (วินาที): {final_video.duration} วินาที")
    print(f"==================================================\n")

    audio_path = f"public/storage/sound/{chapter_id}.mp3"
    if os.path.exists(audio_path):
        audio = AudioFileClip(audio_path)
        max_audio_duration = final_video.duration - 1
        
        if max_audio_duration > 0:
            if audio.duration > max_audio_duration:
                audio = audio.subclipped(0, max_audio_duration)
            
            audio = audio.with_start(1)
            final_audio = CompositeAudioClip([audio]).with_duration(final_video.duration)
            final_video = final_video.with_audio(final_audio)
    else:
        print(f"Warning: ไม่พบไฟล์เสียงที่ {audio_path}")
        
    os.makedirs("public/storage/vdo", exist_ok=True)
    temp_output_path = f"public/storage/vdo/{chapter_id}_temp.mp4"
    output_path = f"public/storage/vdo/{chapter_id}.mp4"
    
    final_video = final_video.with_duration(final_video.duration)
    final_video.write_videofile(temp_output_path, fps=24, codec="libx264", audio_codec="aac")
    final_video.close()
    
    if os.path.exists(output_path):
        os.remove(output_path)
    os.rename(temp_output_path, output_path)
    
    chapter.vdoPath = output_path
    session.add(chapter)
    session.commit()
    print(f"Success: วิดีโอสำเร็จที่ {output_path}")

@router.get("/{chapter_id}")
def generate_chapter_video_endpoint(
    chapter_id: int, 
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    chapter = session.get(chapterContent, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="ไม่พบ Chapter นี้ในระบบ")
        
    background_tasks.add_task(process_video_generation, chapter_id, session)
    
    return {
        "message": "ระบบกำลังเริ่มสร้างวิดีโอให้คุณในพื้นหลัง โปรดรอสักครู่",
        "chapter_id": chapter_id,
        "status": "processing"
    }