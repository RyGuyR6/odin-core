from app.services.health_service import HealthService


def test_health_service():
    service = HealthService()
    result = service.get_status()

    assert result["status"] == "healthy"
