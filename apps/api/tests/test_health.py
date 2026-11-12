from fastapi.testclient import TestClient

from apps.api.main import create_app
from quantlab import __version__
from quantlab.common.settings import Settings, get_settings


def _client(settings: Settings) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_health_reports_ok_and_research_only_by_default() -> None:
    response = _client(Settings(_env_file=None)).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "QUANTLAB",
        "version": __version__,
        "environment": "development",
        "execution_mode": "RESEARCH_ONLY",
    }


def test_health_does_not_expose_configuration_secrets() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://user:s3cret-value@db:5432/quantlab",
    )

    body = _client(settings).get("/api/v1/health").text

    assert "s3cret-value" not in body
    assert "postgresql" not in body


def test_no_order_placement_route_is_exposed() -> None:
    paths = _client(Settings(_env_file=None)).get("/openapi.json").json()["paths"]

    assert not [p for p in paths if "order" in p or "execution" in p]
