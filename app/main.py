from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import models
from database import engine


# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="MindMate", description="AI-Powered Mental Wellness Journal")

@app.get("/")
async def root():
    return {"message": "Welcome to MindMate API", "status": "running"}

if __name__ == "__main__":
    import uvicorn
