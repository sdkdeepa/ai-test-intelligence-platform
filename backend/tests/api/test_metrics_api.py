from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_metrics_returns_200():
    response = client.get("/metrics")
    assert response.status_code == 200


def test_metrics_returns_prometheus_content_type():
    response = client.get("/metrics")
    assert "text/plain" in response.headers["content-type"]


def test_metrics_includes_known_metric_names():
    from app.observability.metrics import record_llm_invocation

    record_llm_invocation(
        provider="metrics-api-test-provider",
        model="metrics-api-test-model",
        engine_type="risk",
        input_tokens=1,
        output_tokens=1,
        latency_ms=1.0,
        estimated_cost=0.001,
    )

    response = client.get("/metrics")

    body = response.text
    assert "llm_invocations_total" in body
    assert "llm_tokens_total" in body
    assert "llm_latency_seconds" in body
    assert "llm_estimated_cost_usd_total" in body
    assert "metrics-api-test-provider" in body
