
from fastapi import Response

from paai import auth
from paai.config import settings


def _refresh_set_cookie(monkeypatch, base_url: str) -> str:
    monkeypatch.setattr(settings, "base_url", base_url)
    response = Response()
    auth.set_auth_cookies(response, "access-token", "refresh-token")
    headers = response.headers.getlist("set-cookie")
    return next(h for h in headers if h.startswith(f"{auth.REFRESH_COOKIE}="))


def test_refresh_cookie_path_behind_proxy(monkeypatch):
    header = _refresh_set_cookie(monkeypatch, "https://paai.vercel.app/api")
    assert "Path=/api/auth" in header


def test_refresh_cookie_path_direct(monkeypatch):
    header = _refresh_set_cookie(monkeypatch, "http://localhost:8000")
    assert "Path=/auth" in header


def test_access_cookie_is_site_wide(monkeypatch):
    monkeypatch.setattr(settings, "base_url", "https://paai.vercel.app/api")
    response = Response()
    auth.set_auth_cookies(response, "access-token", "refresh-token")
    access = next(
        h for h in response.headers.getlist("set-cookie")
        if h.startswith(f"{auth.ACCESS_COOKIE}=")
    )
    assert "Path=/;" in access or access.endswith("Path=/")