from fastapi import APIRouter
from app.models.runtime_dashboard import Agent, Dashboard, RuntimeStatus, Tasks
from app.services.runtime_dashboard import agents, dashboard, runtime_status

router = APIRouter(prefix="/runtime", tags=["runtime"])

@router.get("/dashboard", response_model=Dashboard)
def get_dashboard(): return dashboard()

@router.get("/status", response_model=RuntimeStatus)
def get_status(): return runtime_status()

@router.get("/agents", response_model=list[Agent])
def get_agents(): return agents()

@router.get("/tasks", response_model=Tasks)
def get_tasks(): return Tasks()

@router.get("/health")
def get_health(): return {"status": runtime_status().status}
