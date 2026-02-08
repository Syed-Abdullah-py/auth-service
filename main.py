from fastapi import FastAPI
from app.api import auth, workspaces, users, cases
from app.db.session import engine, Base
import httpx
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

BASE_URL = "http://127.0.0.1:8000"

# Create tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Auth Service")

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(workspaces.router, tags=["workspaces"])
app.include_router(users.router, tags=["users"])
app.include_router(cases.router, tags=["cases"])

@app.get("/")
def read_root():
    return {"message": "Welcome to the Auth Service"}
