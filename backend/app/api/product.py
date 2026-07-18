from fastapi import APIRouter

router = APIRouter(
    prefix="/product",
    tags=["Product"],
)

@router.get("/")
def status():
    return {
        "feature":"Product",
        "status":"ok"
    }
