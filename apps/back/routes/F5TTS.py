from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse
import uuid
import os
import traceback
import soundfile as sf

# --- HOTFIX: ป้องกัน Error OSError: No username set in the environment จาก PyTorch ---
if "USERNAME" not in os.environ and "USER" not in os.environ:
    os.environ["USERNAME"] = "local_user"
# ---------------------------------------------------------------------------------

# นำเข้าโมดูลจาก f5_tts_th (ไลบรารีของคนไทย)
try:
    from f5_tts_th.tts import TTS
except ImportError:
    print("⚠️ ไม่พบไลบรารี f5-tts-th กรุณาติดตั้งก่อนรันเซิร์ฟเวอร์")

# สร้าง Router แทนแอปพลิเคชันหลัก
router = APIRouter(
    prefix="/tts",
    tags=["tts"]
)

# ==========================================
# 🌟 โหลดโมเดล F5-TTS-THAI ไว้ล่วงหน้า (In-Memory)
# ==========================================
print("Loading Global F5-TTS-THAI Model...")
try:
    # คุณสามารถเปลี่ยน model="v1" เป็น "v2" ได้ถ้าในอนาคตเขามีอัปเดตโมเดลใหม่
    global_tts = TTS(model="v2") 
except Exception as e:
    print(f"⚠️ โหลดโมเดลไม่สำเร็จ: {e}")
    global_tts = None

@router.post("/generate_audio")
async def generate_audio(
    # เอา ref_text ออกจากพารามิเตอร์แล้ว
    gen_text: str = Form(..., description="ข้อความภาษาไทยที่ต้องการให้ AI พูด"),
    # เอา ref_audio_path ออกจากตรงนี้แล้ว
    step: int = Form(32, description="จำนวน Step (ยิ่งเยอะยิ่งเนียน แต่อาจจะช้าลง)"),
    cfg: float = Form(2.0, description="ค่า CFG Scale (ความแม่นยำในการทำตามข้อความ)"),
    speed: float = Form(1.0, description="ความเร็วในการพูด (1.0 คือปกติ)")
):
    """
    Endpoint สำหรับสร้างเสียงพากย์ภาษาไทย ด้วยไลบรารี f5-tts-th (ล็อกไฟล์เสียง narrator.mp3 ไว้แล้ว)
    """
    if global_tts is None:
        raise HTTPException(status_code=500, detail="ระบบยังไม่ได้โหลดโมเดล TTS โปรดตรวจสอบ Error ตอนเปิดเซิร์ฟเวอร์")

    # กำหนด Path ไฟล์ตายตัวไปที่ narrator.mp3 เลย
    # เนื่องจากคุณรันเซิร์ฟเวอร์ที่โฟลเดอร์ back และไฟล์เสียงก็อยู่ตรงนั้น สามารถใส่แค่ชื่อไฟล์ได้เลยครับ
    ref_audio_path = "narrator.mp3"
    
    # กำหนดข้อความของไฟล์เสียงต้นฉบับแบบตายตัว
    ref_text = "เฮ้ยทุกคน เชื่อไหมว่าเดี๋ยวนี้ AI มันทำอะไรได้เยอะมากจริงๆ วันนี้ผมลองเล่นตัวนึงมา แล้วรู้สึกว่ามันว้าวมาก เลยอยากจะรีบเอามาเล่าให้ฟังกันครับ"

    # เช็คก่อนว่ามีไฟล์เสียงต้นฉบับอยู่ในเครื่องจริงๆ หรือไม่
    if not os.path.exists(ref_audio_path):
        raise HTTPException(status_code=400, detail=f"ไม่พบไฟล์เสียงต้นฉบับที่ Path: {ref_audio_path}")

    session_id = str(uuid.uuid4())[:8]
    output_dir = "results"
    output_name = f"output_{session_id}.wav"
    
    os.makedirs(output_dir, exist_ok=True)

    try:
        print(f"[{session_id}] กำลังประมวลผลเสียงภาษาไทย...")

        # 2. เรียกใช้คำสั่ง infer จาก f5-tts-th โดยตรง (ส่ง Path ไฟล์เข้าไปเลย)
        wav = global_tts.infer(
            ref_audio=ref_audio_path,
            ref_text=ref_text,
            gen_text=gen_text,
            step=step,
            cfg=cfg,
            speed=speed
        )
        
        # 3. บันทึกไฟล์ผลลัพธ์ (Sample rate ของ F5-TTS คือ 24000)
        output_path = os.path.join(output_dir, output_name)
        sf.write(output_path, wav, 24000)
        
        # 4. ส่งไฟล์กลับ
        return FileResponse(
            path=output_path, 
            media_type="audio/wav", 
            filename=output_name
        )

    except Exception as e:
        error_msg = traceback.format_exc()
        print(f"Error: {error_msg}")
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาด: {str(e)}")