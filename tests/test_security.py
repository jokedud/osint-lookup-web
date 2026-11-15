import asyncio

import pytest
from fastapi.testclient import TestClient

import ghunt_check
import main


@pytest.fixture
def calls(monkeypatch):
    seen = {"commands": [], "emails": [], "usernames": []}

    async def fake_check_email(email):
        seen["emails"].append(email)
        return []

    async def fake_check_username(username):
        seen["usernames"].append(username)
        return []

    async def fake_ghunt(email):
        return {"status": "ok", "results": []}

    async def fake_run_command(command, timeout=90):
        seen["commands"].append(command)
        return {"status": "ok", "lines": []}

    monkeypatch.setattr(main, "check_email", fake_check_email)
    monkeypatch.setattr(main, "check_username", fake_check_username)
    monkeypatch.setattr(main, "run_ghunt", fake_ghunt)
    monkeypatch.setattr(main, "run_command", fake_run_command)
    return seen


client = TestClient(main.app)


@pytest.mark.parametrize("query", ["--version", "-h", "-oX", ".", "..", "_a"])
def test_username_rejects_flag_like_input(calls, query):
    r = client.get("/api/search", params={"type": "username", "query": query})
    assert r.status_code == 400
    assert calls["commands"] == []


@pytest.mark.parametrize("query", ["alice", "a.b-c_d", "A1"])
def test_username_accepts_normal_names(calls, query):
    r = client.get("/api/search", params={"type": "username", "query": query})
    assert r.status_code == 200
    assert calls["commands"] == [["sherlock", "--print-found", "--no-color", "--", query]]


@pytest.mark.parametrize("query", ["a/../x@y.com", "a&x=1@y.com", "a@y.com#x", "a?b@y.com", "a@y.com/x", "a@-y.com", "a@y.c0m", "a b@y.com"])
def test_email_rejects_url_breaking_input(calls, query):
    r = client.get("/api/search", params={"type": "email", "query": query})
    assert r.status_code == 400
    assert calls["emails"] == []


@pytest.mark.parametrize("query", ["first.last+tag@sub.example.co.uk", "john@gmail.com", "a_b%c-d@x-y.io"])
def test_email_accepts_normal_addresses(calls, query):
    r = client.get("/api/search", params={"type": "email", "query": query})
    assert r.status_code == 200
    assert calls["emails"] == [query]


def test_email_check_errors_are_not_sent_to_client(monkeypatch):
    async def boom(email):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(main, "check_email", boom)
    out = asyncio.run(main.run_email_checks("a@b.com"))
    assert out["status"] == "error"
    assert "secret internal detail" not in out["message"]


def test_command_stderr_is_not_sent_to_client():
    out = asyncio.run(main.run_command(["python3", "-c", "import sys; print('line'); sys.stderr.write('secret stderr')"]))
    assert out["lines"] == ["line"]
    assert "stderr" not in out
    assert "secret stderr" not in str(out)


def test_ghunt_errors_are_not_sent_to_client(monkeypatch):
    async def boom(email):
        raise RuntimeError("token aas_et/secret")

    monkeypatch.setattr(ghunt_check, "is_configured", lambda: True)
    monkeypatch.setattr(ghunt_check, "_lookup", boom)
    out = asyncio.run(ghunt_check.run_ghunt("a@b.com"))
    assert out["status"] == "error"
    assert "aas_et/secret" not in out["results"][0]["detail"]
    assert "RuntimeError" in out["results"][0]["detail"]
