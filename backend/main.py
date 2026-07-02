from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db, load_encodings
from state import encodings_cache
from routes.auth import router as auth_router
from routes.websockets import router as ws_router

app = FastAPI()

app.add_middleware(CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:3000",
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    init_db()
    load_encodings(encodings_cache)

@app.get("/")
def root():
    return {"message": "Arena backend running"}

# Mount the modular routers
app.include_router(auth_router)
app.include_router(ws_router)