from fastapi import FastAPI

from config.db import get_db,Base,eng

app = FastAPI()

Base.metadata.create_all(bind = eng)

@app.get("/health")
async def health():
        return {
                "message":"status running"
        }




