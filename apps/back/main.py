from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .ollama import generate_text

app= FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return "server is worked 111"

@app.get("/test")
def root():
    return "test test 222"

@app.post("/")
def root():
    return "test post 333"

@app.get("/ollama")
def query():
    result = generate_text("this is ollama")
    return {"response": result}