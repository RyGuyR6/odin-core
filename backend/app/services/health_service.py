from app.services.base import BaseService


class HealthService(BaseService):
    name = "Health"

    def get_status(self):
        return {"status": "healthy"}
