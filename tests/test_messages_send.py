"""消息发送 API 回归：匿名 / 非法 token / 默认对话（需 LLM）。"""
from __future__ import annotations

import pytest


def test_send_message_invalid_bearer_returns_401(api_client):
    r = api_client.post(
        "/api/sessions",
        json={"title": "t", "current_mode": "default_conversation"},
    )
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    r2 = api_client.post(
        f"/api/messages/{sid}",
        json={"content": "hi", "mode": "default_conversation"},
        headers={"Authorization": "Bearer invalid.token.value"},
    )
    assert r2.status_code == 401, r2.text
    body = r2.json()
    assert "detail" in body


@pytest.mark.integration
def test_send_message_default_conversation_anonymous_ok(api_client):
    """调用真实 LLM，需配置 DEEPSEEK_API_KEY 等；无密钥时可能 502。"""
    r = api_client.post(
        "/api/sessions",
        json={"title": "pytest", "current_mode": "default_conversation"},
    )
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    r2 = api_client.post(
        f"/api/messages/{sid}",
        json={"content": ".", "mode": "default_conversation"},
    )
    assert r2.status_code in (200, 502), r2.text
    if r2.status_code == 200:
        data = r2.json()
        assert "message_id" in data
        assert isinstance(data.get("content"), str)
