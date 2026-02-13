window: "dev": ".\\.venv\\Scripts\\python.exe -m uvicorn main:app --reload --port 8000"  
linux: "dev": "./.venv/bin/python -m uvicorn main:app --reload --port 8000"

# Create venv

uv venv

upload -> extract -> gen -> done

extract:  
http://127.0.0.1:8000/extractEntities/{chapterID}

gen ภาพ:  
http://127.0.0.1:8000/createPic/generate-images/{chapter_id}

extract เสียง:
http://127.0.0.1:8000/sound/{chapter_id}/analysis
