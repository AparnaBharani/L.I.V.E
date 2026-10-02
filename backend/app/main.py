from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List

from app import models, schemas
from app.database import get_db

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "L.I.V.E backend is running"}

@app.get("/experiences", response_model=List[schemas.ExperienceResponse])
def get_experiences(db: Session = Depends(get_db)):
    experiences = db.query(models.Experience).all()
    return experiences
