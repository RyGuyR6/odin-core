from fastapi import FastAPI

from app.core.odin import Odin

app = FastAPI(
    title="Odin Core",
    version="0.0.1",
)

odin = Odin()


@app.get("/")
def root():
    return odin.status()