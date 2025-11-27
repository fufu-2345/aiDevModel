import torch
import json
import numpy as np
import soundfile as sf
from TTS.tts.models.vits import Vits  # ไม่มี dependency ของ coqui (ปรับแล้ว)
from TTS.tts.utils.text.tokenizer import TTSTokenizer

model_dir = "khanomtan/"

with open(model_dir + "config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

tokenizer = TTSTokenizer(config)

model = Vits.init_from_config(config)
model.load_checkpoint(config, model_dir + "model.pth", eval=True)

text = "ทดสอบ ทดสอบ โล่งอก หนึ่ง สอง สาม"

inputs = tokenizer.text_to_ids(text)
inputs = torch.tensor([inputs])

with torch.no_grad():
    wav = model.inference(inputs)

wav = wav.squeeze().cpu().numpy()

sf.write("output.wav", wav, config.get("sample_rate", 22050))
