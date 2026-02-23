import os
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
    IMAGE_BASE_DIR = "public/"
    
    total_scenes = len(matchers)
    
    for i, m in enumerate(matchers):
        loc_filename = str(m.location) if m.location else ""
        char_filename = str(m.character) if m.character else ""
        
        loc_path = os.path.join(IMAGE_BASE_DIR, loc_filename)
        char_path = os.path.join(IMAGE_BASE_DIR, char_filename)
        
        if not os.path.isfile(loc_path) or not os.path.isfile(char_path):
            print(f"--- Warning: ข้าม Scene ID {m.id} ---")
            print(f"    RAW DB ค่าจากฐานข้อมูล -> location: '{m.location}', character: '{m.character}'")
            print(f"    Path ที่โค้ดพยายามหา   -> loc: '{loc_path}', char: '{char_path}'")
            continue
        is_last_scene = (i == total_scenes - 1)
        fade_dur = 1.0 if is_last_scene else 0.5
        
        hold_duration = float(m.duration)
        if is_last_scene:
            hold_duration += 1.0
            
        total_duration = hold_duration
        
        bg = ImageClip(loc_path).with_duration(total_duration)
        bg = bg.with_effects([vfx.FadeIn(fade_dur), vfx.FadeOut(fade_dur)])
        
        char = ImageClip(char_path)
        bg_w, bg_h = bg.size
        char_w, char_h = char.size
        def make_char_pos(bg_height, char_height, anim_dur):
            def char_pos(t):
                if t <= anim_dur:
                    start_y = -char_height
                    end_y = (bg_height - char_height) / 2
                    current_y = start_y + (end_y - start_y) * (t / anim_dur)
                    return ('center', current_y)
                return ('center', 'center')
            return char_pos
            
        char = (char.with_duration(total_duration)
                   .with_position(make_char_pos(bg_h, char_h, fade_dur))
                   .with_effects([vfx.FadeIn(fade_dur), vfx.FadeOut(fade_dur)]))
                   
        scene = CompositeVideoClip([bg, char])
        scene_clips.append(scene)
        
    if not scene_clips:
        print(f"Error: ไม่สามารถสร้าง Scene ได้เลยสำหรับ Chapter {chapter_id}")
        return

    final_video = concatenate_videoclips(scene_clips, method="compose")
    
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
    output_path = f"public/storage/vdo/{chapter_id}.mp4"
    
    final_video.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac")
    final_video.close()
    
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