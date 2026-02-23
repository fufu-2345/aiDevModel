import os
import torch
import soundfile as sf
from transformers import VitsModel, VitsTokenizer, AutoTokenizer

def download_and_test_models():
    models_to_process = {
        "male2": "VIZINTZOR/MMS-TTS-THAI-MALEV2",
        "male1": "VIZINTZOR/MMS-TTS-THAI-MALE-NARRATOR",
        "female2": "VIZINTZOR/MMS-TTS-THAI-FEMALEV2"
    }

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[*] กำลังเริ่มการทำงานผ่าน: {device.upper()}\n")

    for local_dir, model_id in models_to_process.items():
        print(f"--- กำลังจัดการโมเดล: {model_id} ---")
        if os.path.exists(local_dir):
            print(f"[*] พบโมเดลในเครื่องแล้วที่: {local_dir} (กำลังโหลดเข้า Memory...)")
            tokenizer = AutoTokenizer.from_pretrained(local_dir)
            model = VitsModel.from_pretrained(local_dir)
        else:
            print(f"[!] ไม่พบในเครื่อง... กำลังดาวน์โหลดจาก Hugging Face")
            tokenizer = AutoTokenizer.from_pretrained(model_id)
            model = VitsModel.from_pretrained(model_id)
            
            # บันทึกลงเครื่องทันที
            tokenizer.save_pretrained(local_dir)
            model.save_pretrained(local_dir)
            print(f"✅ บันทึกโมเดลลงเครื่องสำเร็จที่: {local_dir}")

        # 3. ทดสอบสร้างเสียงสั้นๆ (Inference) สำหรับโมเดลที่โหลดมา
        # (เราจะทดสอบเฉพาะตัวสุดท้ายหรือทุกตัวก็ได้ ในที่นี้ผมทำตัวอย่างให้ลองพูดสั้นๆ ครับ)
        try:
            model.to(device)
            test_text = f"โหลดโมเดล {local_dir} สำเร็จแล้วค่ะ"
            inputs = tokenizer(test_text, return_tensors="pt").to(device)
            
            with torch.no_grad():
                output = model(**inputs).waveform
            
            # บันทึกไฟล์เสียงทดสอบ (แยกชื่อตามโฟลเดอร์)
            output_filename = f"test_{local_dir}.wav"
            sampling_rate = model.config.sampling_rate
            sf.write(output_filename, output[0].cpu().numpy(), sampling_rate)
            
            print(f"✨ ทดสอบเสียงสำเร็จ: {output_filename}")
        except Exception as e:
            print(f"❌ เกิดข้อผิดพลาดในการทดสอบเสียง: {e}")
        
        print("-" * 50)

    print("\n🎉 ภารกิจเสร็จสิ้น! โหลดครบทั้ง 3 โมเดลแล้วครับ")

if __name__ == "__main__":
    try:
        download_and_test_models()
    except Exception as e:
        print(f"🔴 เกิดข้อผิดพลาดร้ายแรง: {e}")
        print("กรุณาตรวจสอบว่าติดตั้ง library ครบ: pip install transformers torch soundfile")