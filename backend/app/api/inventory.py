from fastapi import APIRouter

router = APIRouter(
    prefix="/inventory",
    tags=["Inventory"],
)

@router.get("/")
def status():
    return {
        "feature":"Inventory",
        "status":"ok"
    }
