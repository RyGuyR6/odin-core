from fastapi import APIRouter

from .repositories import router as repositories_router
from .branches import router as branches_router
from .pull_requests import router as pull_requests_router
from .workflow import router as workflow_router

router = APIRouter()

router.include_router(repositories_router)
router.include_router(branches_router)
router.include_router(pull_requests_router)
router.include_router(workflow_router)