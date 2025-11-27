from pythaitts import TTS

tts = TTS(pretrained='khanomtan', mode='last_checkpoint', version='1.0', device='cpu')

text = "สวัสดีครับ นี่คือตัวอย่างการใช้ KhanomTan"
tts.tts_to_file(text, file_path="output.wav", speaker="Tsyncone", language="th-th")