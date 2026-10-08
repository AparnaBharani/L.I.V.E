from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import experiences, interactions, users

app = FastAPI(title="L.I.V.E API")

app.add_middleware(
    CORSMiddleware,
    # The Next.js dev server, reachable under either local hostname.
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(experiences.router)
app.include_router(interactions.router)


@app.get("/")
def home():
    return {"message": "L.I.V.E backend is running"}
