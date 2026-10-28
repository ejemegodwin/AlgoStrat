"""CORS behavior (ADR-013): the SPA origin is allowlisted explicitly;
unknown origins get no access-control headers, so browsers block them.
"""

ALLOWED_ORIGIN = "http://localhost:5173"  # default when CORS_ORIGINS is unset
DISALLOWED_ORIGIN = "https://evil.example"


def test_preflight_from_the_allowed_origin_is_accepted(client):
    response = client.options(
        "/",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


def test_preflight_from_an_unknown_origin_is_rejected(client):
    response = client.options(
        "/",
        headers={
            "Origin": DISALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_simple_request_from_an_unknown_origin_gets_no_cors_headers(client):
    # Non-preflighted requests still run (CORS is enforced by the
    # browser, not the server) but without the headers the browser
    # refuses to expose the response to the calling page's JS.
    response = client.get("/", headers={"Origin": DISALLOWED_ORIGIN})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
