import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.routers import experiences, interactions, recommendations, search, users

logger = logging.getLogger(__name__)

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
app.include_router(recommendations.router)
app.include_router(search.router)


@app.exception_handler(OperationalError)
def database_unavailable(request: Request, exc: OperationalError) -> JSONResponse:
    # Unhandled errors bypass the CORS middleware, and the browser would then report
    # "backend unreachable". A handled 503 reaches the frontend with an honest message.
    logger.error("Database unavailable during %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=503,
        content={"detail": "The database is unavailable. Please try again shortly."},
    )


@app.get("/")
def home():
    return {"message": "L.I.V.E backend is running"}
