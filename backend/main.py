from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def home():
    return {"message": "L.I.V.E backend is running"}