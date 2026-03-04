import os
import sys
import torch 

# --- ยันต์กันค้าง (ANTI-DEADLOCK สำหรับ Windows) ---
# บังคับให้ไลบรารีคณิตศาสตร์เบื้องหลัง AI ใช้แค่ 1-2 Thread ต่อคอร์ 
# เพื่อป้องกันการแย่งกันจนเกิด Deadlock ตอนรันผ่านเซิร์ฟเวอร์
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

# แก้ปัญหา RuntimeError: Could not determine home directory. ตอนรัน uvicorn
os.environ["CACHED_PATH_CACHE_ROOT"] = os.path.abspath(os.path.join(os.getcwd(), ".cache", "cached_path"))
if sys.platform == "win32" and "USERPROFILE" not in os.environ:
    os.environ["USERPROFILE"] = os.path.abspath(os.getcwd())
# -------------------------------------------------

torch.set_num_threads(4) 

import uuid
import traceback
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

try:
    from f5_tts_th.tts import TTS
    import soundfile as sf
    has_f5 = True
except ImportError as e:
    has_f5 = False
    print(f"[Worker] ERROR: ไม่สามารถ import F5-TTS ได้: {e}")

app = FastAPI(title="F5-TTS Worker (รันบน Python 3.11)")

tts_model = None
if has_f5:
    print("[Worker] ⏳ กำลังโหลดโมเดล F5-TTS เข้าสู่หน่วยความจำ (รอสักครู่)...")
    try:
        tts_model = TTS(model="v1") 
        print("[Worker] ✅ โหลดโมเดลสำเร็จ พร้อมรับงานแล้ว!")
    except Exception as e:
        print(f"[Worker] ❌ โหลดโมเดลไม่สำเร็จ: {e}")

REF_AUDIO_PATH = "narrator.wav"
REF_TEXT = "เฮ้ยทุกคน เชื่อไหมว่าเดี๋ยวนี้ AI มันทำอะไรได้เยอะมากจริงๆ วันนี้ผมลองเล่นมาตัวนึง"

@app.get("/test_clone")
def test_clone_browser():
    text = "สวัสดีครับ นี่คือเสียงที่ถูกสร้างขึ้นมาใหม่ โดยใช้ค่าตัวแปรที่กำหนดไว้ล่วงหน้าทั้งหมดครับ"
    
    print(f"[Worker] 📥 ได้รับงานใหม่: {text}")
    
    if not has_f5 or tts_model is None:
        raise HTTPException(status_code=500, detail="ระบบโมเดล F5-TTS ยังไม่พร้อมทำงาน")
        
    if not os.path.exists(REF_AUDIO_PATH):
        raise HTTPException(status_code=500, detail=f"ไม่พบไฟล์เสียงต้นแบบที่: {REF_AUDIO_PATH}")

    output_filename = f"temp_output_{uuid.uuid4().hex[:8]}.wav"
    
    try:
        print("[Worker] ⚙️ กำลังเริ่มรัน AI...")
        
        # เพิ่ม inference_mode() เข้ามา เพื่อบอก PyTorch ว่า "เราแค่เอามาใช้เฉยๆ ไม่ได้เทรนโมเดล"
        # จะช่วยประหยัด RAM/VRAM และป้องกันการค้างได้ดีมาก
        with torch.inference_mode():
            wav = tts_model.infer(
                ref_audio=REF_AUDIO_PATH,
                ref_text=REF_TEXT,
                gen_text=text,
                step=32,       
                cfg=2.0,       
                speed=1.0      
            )
            
        print("[Worker] 💾 กำลังบันทึกไฟล์เสียง...")
        sf.write(output_filename, wav, 24000)
        
        print(f"[Worker] 🎉 เจนเสียงเสร็จแล้ว! กำลังส่งไฟล์ {output_filename} กลับไป")
        return FileResponse(output_filename, media_type="audio/wav")
        
    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"[Worker] ❌ เกิดข้อผิดพลาดตอนเจนเสียง:\n{error_trace}")
        raise HTTPException(status_code=500, detail=f"AI Error: {str(e)}")