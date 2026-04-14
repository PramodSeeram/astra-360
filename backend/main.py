import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

from routes.auth import router as auth_router
from routes.user import router as user_router
from routes.onboarding import router as onboarding_router

app = FastAPI(title="Astra 360 Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(user_router)
app.include_router(onboarding_router)


@app.get("/")
def root():
    return {"status": "Astra 360 Backend Running"}


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    print(f"Starting server on {host}:{port} loaded from .env...")
    uvicorn.run("main:app", host=host, port=port, reload=True)
