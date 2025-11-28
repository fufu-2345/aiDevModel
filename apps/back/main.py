from fastapi import FastAPI

app= FastAPI()

@app.get("/")
def root():
    return "server is worked 111"


@app.get("/test")
def root():
    return "test test 222"

@app.post("/")
def root():
    return "test post 333"
