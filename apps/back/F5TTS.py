import os
import sys
import torch 

# --- ลดการแย่งคิวกันทำงานของ CPU (ลดเหลือ 4-8 Threads พอครับ) ---
optimal_threads = 8 

os.environ["OMP_NUM_THREADS"] = str(optimal_threads)
os.environ["MKL_NUM_THREADS"] = str(optimal_threads)
os.environ["OPENBLAS_NUM_THREADS"] = str(optimal_threads)
os.environ["OMP_MAX_ACTIVE_LEVELS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
# -------------------------------------------------

os.environ["CACHED_PATH_CACHE_ROOT"] = os.path.abspath(os.path.join(os.getcwd(), ".cache", "cached_path"))
if sys.platform == "win32" and "USERPROFILE" not in os.environ:
    os.environ["USERPROFILE"] = os.path.abspath(os.getcwd())

# 🚨 กฎเหล็กสำหรับ CPU: บังคับใช้ทศนิยม 32-bit (FP32) เท่านั้น ป้องกันเสียงเงียบและเครื่องค้าง 🚨
torch.set_default_dtype(torch.float32)

torch.backends.mkldnn.enabled = False
torch.set_num_threads(optimal_threads) 
torch.set_num_interop_threads(1) 
torch.set_grad_enabled(False)

import uuid
import traceback
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from torch.nn.attention import SDPBackend, sdpa_kernel

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
    print(f"[Worker] ⏳ กำลังโหลดโมเดล F5-TTS... (ตั้งค่า CPU: {optimal_threads} Threads, โหมด FP32)")
    try:
        tts_model = TTS(model="v1") 
        # บังคับแปลงน้ำหนักโมเดลทั้งหมดให้เป็น Float32
        tts_model.model.to(torch.float32)
        if hasattr(tts_model, 'vocoder'):
            tts_model.vocoder.to(torch.float32)
            
        print("[Worker] ✅ โหลดโมเดลสำเร็จ พร้อมรับงานแล้ว!")
    except Exception as e:
        print(f"[Worker] ❌ โหลดโมเดลไม่สำเร็จ: {e}")

REF_AUDIO_PATH = "narrator.wav"
# ตัดข้อความอ้างอิงให้สั้นลง เพื่อไม่ให้ติด Warning "Audio is over 15s, clipping short"
REF_TEXT = "เฮ้ยทุกคน เชื่อไหมว่าเดี๋ยวนี้ AI มันทำอะไรได้เยอะมากจริงๆ"

@app.get("/test_clone")
def test_clone_browser():
    text = "สวัสดีครับ นี่คือเสียงที่ถูกสร้างขึ้นมาใหม่ โดยบังคับใช้การคำนวณแบบสามสิบสองบิทครับ"
    
    print(f"[Worker] 📥 ได้รับงานใหม่: {text}")
    
    if not has_f5 or tts_model is None:
        raise HTTPException(status_code=500, detail="ระบบโมเดล F5-TTS ยังไม่พร้อมทำงาน")
        
    if not os.path.exists(REF_AUDIO_PATH):
        raise HTTPException(status_code=500, detail=f"ไม่พบไฟล์เสียงต้นแบบที่: {REF_AUDIO_PATH}")

    output_filename = f"temp_output_{uuid.uuid4().hex[:8]}.wav"
    
    try:
        print(f"[Worker] ⚙️ กำลังเริ่มรัน AI (แก้บั๊กเสียงเงียบด้วย Float32)...")
        
        with torch.no_grad():
            with torch.inference_mode():
                # เกราะป้องกันชั้นที่ 2: บังคับ Autocast ให้เป็น Float32 ระหว่างคำนวณ
                with torch.autocast(device_type="cpu", dtype=torch.float32):
                    with sdpa_kernel(SDPBackend.MATH):
                        wav = tts_model.infer(
                            ref_audio=REF_AUDIO_PATH,
                            ref_text=REF_TEXT,
                            gen_text=text,
                            step=10, # ใช้ 10 รอบในการทดสอบ     
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