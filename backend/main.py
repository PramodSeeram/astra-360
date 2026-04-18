import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()
from database import engine, Base
import models # Ensure models are loaded for metadata

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

from routes.auth import router as auth_router
from routes.user import router as user_router
from routes.onboarding import router as onboarding_router
from routes.dashboard import router as dashboard_router
from routes.rag_routes import router as rag_router
from routes.chat_routes import router as chat_router
from routes.insurance_routes import router as insurance_router
from routes.data import router as data_router
from routes.dev import router as dev_router


app = FastAPI(title="Astra 360 Backend", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(user_router)
app.include_router(onboarding_router)
app.include_router(dashboard_router)
app.include_router(rag_router)
app.include_router(chat_router)
app.include_router(insurance_router)
app.include_router(data_router)
app.include_router(dev_router)


@app.get("/")
def root():
    return {"status": "Astra 360 Backend Running"}


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    print(f"Starting server on {host}:{port} loaded from .env...")
    uvicorn.run("main:app", host=host, port=port, reload=True)
