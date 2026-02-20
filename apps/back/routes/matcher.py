import os
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlmodel import Session, select
from typing import List, Optional

# [UPDATE] เพิ่ม CompositeAudioClip เข้ามาเพื่อจัดการ Timeline ของเสียง
from moviepy import ImageClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips, CompositeVideoClip, vfx

from database import get_session
from models import matcher, chapterContent

# สร้าง Router ตามที่กำหนด
router = APIRouter(
    prefix="/matcher",
    tags=["matcher"]
)

# ---------------------------------------------------------
# ฟังก์ชันหลักสำหรับสร้างวิดีโอ (สามารถแยกไปเป็น Background Task ได้)
# ---------------------------------------------------------
def process_video_generation(chapter_id: int, session: Session):
    # 1. ดึงข้อมูล Chapter
    chapter = session.get(chapterContent, chapter_id)
    if not chapter:
        print(f"Error: ไม่พบ Chapter {chapter_id} ในระบบ")
        return

    # 2. ดึงข้อมูล Matcher เรียงตาม ID จากน้อยไปมาก
    statement = select(matcher).where(matcher.chapterId == chapter_id).order_by(matcher.id)
    matchers = session.exec(statement).all()
    
    if not matchers:
        print(f"Error: ไม่พบข้อมูล Matcher สำหรับ Chapter {chapter_id}")
        return
        
    scene_clips = []
    
    # กำหนดโฟลเดอร์หลักที่เก็บรูปภาพ (เปลี่ยนได้ถ้าไฟล์อยู่โฟลเดอร์อื่น เช่น "public/storage/pics")
    IMAGE_BASE_DIR = "public/storage/pic/"
    
    # 3. สร้าง Scene ย่อยๆ ตามลำดับของ Matcher
    for m in matchers:
        # ประกอบร่าง Path ให้สมบูรณ์
        loc_path = os.path.join(IMAGE_BASE_DIR, m.location)
        char_path = os.path.join(IMAGE_BASE_DIR, m.character)
        
        if not os.path.exists(loc_path) or not os.path.exists(char_path):
            print(f"Warning: ข้าม Scene ID {m.id} เนื่องจากหาไฟล์ภาพไม่พบ (loc: {loc_path}, char: {char_path})")
            continue
            
        # ระยะเวลา: Fade-in(0.4s) + Duration(ค้างภาพ) + Fade-out(0.4s)
        hold_duration = float(m.duration)
        total_duration = 0.4 + hold_duration + 0.4
        
        # --- สร้างพื้นหลัง (Location) ---
        # ใน MoviePy 2.x ใช้ .with_duration และ .with_effects สำหรับ fadein/out
        bg = ImageClip(loc_path).with_duration(total_duration)
        bg = bg.with_effects([vfx.FadeIn(0.4), vfx.FadeOut(0.4)])
        
        # --- สร้างตัวละคร (Character) ---
        char = ImageClip(char_path)
        bg_w, bg_h = bg.size
        char_w, char_h = char.size
        
        # ฟังก์ชันคำนวณพิกัด Y ให้ตัวละครลอยจากขอบจอบนลงมาตรงกลาง ในเวลา 0.4 วินาที
        def make_char_pos(bg_height, char_height):
            def char_pos(t):
                if t <= 0.4:
                    # ช่วง 0.4 วินาทีแรก: คำนวณพิกัดให้เลื่อนจากบนสุด ลงมาตรงกลาง
                    start_y = -char_height # เริ่มต้นนอกจอ (ด้านบน)
                    end_y = (bg_height - char_height) / 2 # จุดกึ่งกลางจอแนวตั้ง
                    current_y = start_y + (end_y - start_y) * (t / 0.4)
                    return ('center', current_y)
                # หลังจาก 0.4 วินาที: ให้อยู่ตรงกลางหน้าจอไปจนจบ Scene
                return ('center', 'center')
            return char_pos
            
        char = (char.with_duration(total_duration)
                   .with_position(make_char_pos(bg_h, char_h))
                   .with_effects([vfx.FadeIn(0.4), vfx.FadeOut(0.4)])) # ตัวละคร fade-in และ fade-out
                   
        # นำ Background กับ Character มาซ้อนกัน (Character อยู่บน)
        scene = CompositeVideoClip([bg, char])
        scene_clips.append(scene)
        
    if not scene_clips:
        print(f"Error: ไม่สามารถสร้าง Scene ได้เลยสำหรับ Chapter {chapter_id}")
        return

    # 4. เอาทุก Scene มาต่อกัน
    # method="compose" ช่วยให้การต่อคลิปที่มีขนาดต่างกันหรือมี alpha channel สมูทขึ้น
    final_video = concatenate_videoclips(scene_clips, method="compose")
    
    # 5. ใส่เสียงประกอบ .mp3
    audio_path = f"public/storage/sound/{chapter_id}.mp3"
    if os.path.exists(audio_path):
        audio = AudioFileClip(audio_path)
        
        # [UPDATE] เพิ่ม Delay ให้เสียงเริ่มช้าลง 1 วินาที
        delayed_audio = audio.with_start(1.0)
        
        # นำไปใส่ใน CompositeAudioClip เพื่อสร้างไทม์ไลน์ที่มีความเงียบ 1 วินาทีแรก
        final_audio = CompositeAudioClip([delayed_audio])
        
        # ตัดเสียงให้พอดีกับความยาววิดีโอ (ถ้าเสียงรวม delay แล้วยาวกว่า)
        if final_audio.duration > final_video.duration:
            final_audio = final_audio.subclip(0, final_video.duration)
        
        # ใน MoviePy 2.x ใช้ .with_audio
        final_video = final_video.with_audio(final_audio)
    else:
        print(f"Warning: ไม่พบไฟล์เสียงที่ {audio_path}")
        
    # 6. เตรียมโฟลเดอร์และบันทึกไฟล์วิดีโอ .mp4
    os.makedirs("public/storage/vdo", exist_ok=True)
    output_path = f"public/storage/vdo/{chapter_id}.mp4"
    
    # เริ่มเรนเดอร์วิดีโอ
    final_video.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac")
    final_video.close()
    
    # 7. อัปเดต Path ของวิดีโอลงใน Database
    chapter.vdoPath = output_path
    session.add(chapter)
    session.commit()
    print(f"Success: วิดีโอถูกสร้างและอัปเดต DB สำเร็จที่ {output_path}")


# ---------------------------------------------------------
# API Endpoint (GET Method)
# ---------------------------------------------------------
@router.get("/{chapter_id}")
def generate_chapter_video_endpoint(
    chapter_id: int, 
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session) # สมมติว่าใช้ Dependency ดึง Session
):
    # เช็คก่อนว่ามี Chapter นี้ในระบบหรือไม่
    chapter = session.get(chapterContent, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="ไม่พบ Chapter นี้ในระบบ")
        
    # โยนงานเข้าไปทำใน BackgroundTasks
    background_tasks.add_task(process_video_generation, chapter_id, session)
    
    # ตอบกลับผู้ใช้ทันทีว่าได้รับคำสั่งแล้ว
    return {
        "message": "ระบบกำลังเริ่มสร้างวิดีโอให้คุณในพื้นหลัง (Background Task) โปรดรอสักครู่",
        "chapter_id": chapter_id,
        "status": "processing"
    }