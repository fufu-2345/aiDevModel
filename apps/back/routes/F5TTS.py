# from fastapi import APIRouter, HTTPException, Query
# from fastapi.responses import FileResponse
# import uuid
# import os
# import traceback
# import soundfile as sf
# import torchaudio
# import torch
# import subprocess

# # ==========================================
# # 🔍 เช็คเวอร์ชันของระบบเพื่อความชัวร์ (Diagnostics)
# # ==========================================
# print("\n" + "="*60)
# print("🔍 ตรวจสอบเวอร์ชันของระบบและไลบรารี (System Check)")
# print(f"PyTorch version: {torch.__version__}")
# print(f"Torchaudio version: {torchaudio.__version__}")
# print(f"Soundfile version: {sf.__version__}")

# try:
#     import torchcodec
#     print(f"Torchcodec version: {torchcodec.__version__} ⚠️ (อาจทำให้เกิด DLL Error)")
# except ImportError:
#     print("Torchcodec: ไม่ได้ติดตั้ง (✅ ปลอดภัยจากปัญหา DLL)")

# try:
#     # เช็คเวอร์ชัน FFmpeg ที่ติดตั้งอยู่ใน Windows
#     ffmpeg_v = subprocess.check_output(["ffmpeg", "-version"], text=True, stderr=subprocess.STDOUT).split('\n')
#     print(f"System FFmpeg: {ffmpeg_v}")
# except FileNotFoundError:
#     print("System FFmpeg: ❌ ไม่พบในระบบ (หรือยังไม่ได้ตั้งค่า Environment PATH)")
# except Exception as e:
#     print(f"System FFmpeg: ⚠️ เกิดข้อผิดพลาดในการเช็ค ({e})")
# print("="*60 + "\n")

# # ==========================================
# # 🛑 บังคับ PyTorch ให้ใช้ soundfile เป็นตัวอ่านเสียง
# # เพื่อข้ามปัญหา torchcodec เวอร์ชันไม่ตรงกับ FFmpeg ในเครื่อง
# # ==========================================
# try:
#     torchaudio.set_audio_backend("soundfile")
#     print("✅ บังคับใช้ Soundfile เป็น Audio Backend สำเร็จ (ข้ามปัญหา torchcodec)")
# except Exception as e:
#     print(f"⚠️ ไม่สามารถตั้งค่า Audio Backend ได้: {e}")
# # ==========================================

# # นำเข้าโมดูลจาก f5_tts_th (ไลบรารีของคนไทย)
# try:
#     from f5_tts_th.tts import TTS
# except ImportError:
#     print("⚠️ ไม่พบไลบรารี f5-tts-th กรุณาติดตั้งก่อนรันเซิร์ฟเวอร์")

# # สร้าง Router แทนแอปพลิเคชันหลัก
# router = APIRouter(
#     prefix="/tts",
#     tags=["tts"]
# )

# # ==========================================
# # 🌟 โหลดโมเดล F5-TTS-THAI ไว้ล่วงหน้า (In-Memory)
# # ==========================================
# print("Loading Global F5-TTS-THAI Model...")
# try:
#     global_tts = TTS(model="v2") 
# except Exception as e:
#     print(f"⚠️ โหลดโมเดลไม่สำเร็จ: {e}")
#     global_tts = None

# # นำ gen_text ออกจากการรับค่าผ่าน URL
# @router.get("/")
# async def generate_audio(
#     step: int = Query(32, description="จำนวน Step (ยิ่งเยอะยิ่งเนียน แต่อาจจะช้าลง)"),
#     cfg: float = Query(2.0, description="ค่า CFG Scale (ความแม่นยำในการทำตามข้อความ)"),
#     speed: float = Query(1.0, description="ความเร็วในการพูด (1.0 คือปกติ)")
# ):
#     """
#     Endpoint สำหรับสร้างเสียงพากย์ภาษาไทย ด้วยไลบรารี f5-tts-th
#     """
#     if global_tts is None:
#         raise HTTPException(status_code=500, detail="ระบบยังไม่ได้โหลดโมเดล TTS โปรดตรวจสอบ Error ตอนเปิดเซิร์ฟเวอร์")

#     ref_audio_wav = "narrator.wav"
#     ref_audio_mp3 = "narrator.mp3"
    
#     # 🛑 ระบบแปลงไฟล์อัตโนมัติ (mp3 -> wav) โดยใช้ไลบรารี soundfile 
#     # (ทำเผื่อไว้ในกรณีที่ torchaudio มีปัญหาในการอ่าน mp3 โดยตรง)
#     if not os.path.exists(ref_audio_wav):
#         if os.path.exists(ref_audio_mp3):
#             print("🔄 ตรวจพบไฟล์ .mp3 กำลังแปลงเป็น .wav อัตโนมัติ...")
#             try:
#                 data, samplerate = sf.read(ref_audio_mp3)
#                 sf.write(ref_audio_wav, data, samplerate)
#                 print("✅ แปลงไฟล์เป็น narrator.wav สำเร็จ!")
#             except Exception as e:
#                 raise HTTPException(
#                     status_code=500, 
#                     detail=f"โปรแกรมพยายามแปลงไฟล์ mp3 เป็น wav อัตโนมัติแต่ไม่สำเร็จ ({str(e)}) กรุณาแปลงไฟล์ด้วยตัวเองผ่านเว็บ"
#                 )
#         else:
#             raise HTTPException(
#                 status_code=400, 
#                 detail="⚠️ ไม่พบไฟล์เสียงต้นฉบับ กรุณานำไฟล์ narrator.wav หรือ narrator.mp3 มาวางไว้ในโฟลเดอร์โปรเจกต์"
#             )

#     # บังคับให้ AI ใช้ไฟล์ .wav (ชัวร์สุด ปัญหาน้อยสุดบน Windows)
#     ref_audio_path = ref_audio_wav
    
#     # กำหนดข้อความของไฟล์เสียงต้นฉบับแบบตายตัว
#     ref_text = "เฮ้ยทุกคน เชื่อไหมว่าเดี๋ยวนี้ AI มันทำอะไรได้เยอะมากจริงๆ วันนี้ผมลองเล่นตัวนึงมา แล้วรู้สึกว่ามันว้าวมาก เลยอยากจะรีบเอามาเล่าให้ฟังกันครับ"
    
#     # 🌟 กำหนดข้อความที่ต้องการให้ AI พูด (แก้ไขตรงนี้ได้เลย)
#     gen_text = "สวัสดีครับ วันนี้ผมจะมาทดสอบระบบเอไอพากย์เสียงนะครับ"

#     session_id = str(uuid.uuid4())[:8]
#     output_dir = "results"
#     output_name = f"output_{session_id}.wav"
    
#     os.makedirs(output_dir, exist_ok=True)

#     try:
#         print(f"[{session_id}] กำลังประมวลผลเสียงภาษาไทย... (อ้างอิงจากไฟล์: {ref_audio_path})")

#         # เรียกใช้คำสั่ง infer จาก f5-tts-th
#         wav = global_tts.infer(
#             ref_audio=ref_audio_path,
#             ref_text=ref_text,
#             gen_text=gen_text,
#             step=step,
#             cfg=cfg,
#             speed=speed
#         )
        
#         # บันทึกไฟล์ผลลัพธ์
#         output_path = os.path.join(output_dir, output_name)
#         sf.write(output_path, wav, 24000)
        
#         # ส่งไฟล์กลับ
#         return FileResponse(
#             path=output_path, 
#             media_type="audio/wav", 
#             filename=output_name
#         )

#     except Exception as e:
#         error_msg = traceback.format_exc()
#         print(f"Error: {error_msg}")
#         raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาด: {str(e)}")