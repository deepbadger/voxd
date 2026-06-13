def test_get_final_text_disabled(monkeypatch):
    from voxd.core.aipp import get_final_text
    class Cfg:
        def __init__(self):
            self.data = {"aipp_enabled": False}
    cfg = Cfg()
    assert get_final_text("hello", cfg) == "hello"


def test_get_final_text_enabled_routes(monkeypatch):
    from voxd.core import aipp
    class Cfg:
        def __init__(self):
            self.data = {
                "aipp_enabled": True,
                "aipp_provider": "ollama",
                "aipp_active_prompt": "default",
                "aipp_prompts": {"default": "Rewrite:"},
            }
            self.get_aipp_selected_model = lambda prov=None: "llama3.2:latest"

    cfg = Cfg()
    monkeypatch.setattr(aipp, "run_ollama_aipp", lambda prompt, model: "OK")
    out = aipp.get_final_text("hello", cfg)
    assert out == "OK"


def test_get_final_text_routes_openrouter(monkeypatch):
    from voxd.core import aipp
    class Cfg:
        def __init__(self):
            self.data = {
                "aipp_enabled": True,
                "aipp_provider": "openrouter",
                "aipp_active_prompt": "default",
                "aipp_prompts": {"default": "Rewrite:"},
            }
            self.get_aipp_selected_model = lambda prov=None: "openai/gpt-4o-mini"

    cfg = Cfg()
    captured = {}
    def fake_run(prompt, model):
        captured["prompt"] = prompt
        captured["model"] = model
        return "OR-OK"
    monkeypatch.setattr(aipp, "run_openrouter_aipp", fake_run)
    out = aipp.get_final_text("hello", cfg)
    assert out == "OR-OK"
    assert captured["model"] == "openai/gpt-4o-mini"
    assert "Rewrite:" in captured["prompt"] and "hello" in captured["prompt"]


def test_run_openrouter_aipp_sends_key_and_model(monkeypatch):
    from voxd.core import aipp
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-secret")

    captured = {}

    class FakeResp:
        ok = True
        def json(self):
            return {"choices": [{"message": {"content": "  routed  "}}]}

    def fake_post(url, headers=None, data=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["data"] = data
        return FakeResp()

    monkeypatch.setattr(aipp.requests, "post", fake_post)
    out = aipp.run_openrouter_aipp("hi", "anthropic/claude-3.5-sonnet")
    assert out == "routed"
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer or-secret"
    import json as _json
    assert _json.loads(captured["data"])["model"] == "anthropic/claude-3.5-sonnet"


def test_get_final_text_routes_gigachat(monkeypatch):
    from voxd.core import aipp
    class Cfg:
        def __init__(self):
            self.data = {
                "aipp_enabled": True,
                "aipp_provider": "gigachat",
                "aipp_active_prompt": "default",
                "aipp_prompts": {"default": "Rewrite:"},
            }
            self.get_aipp_selected_model = lambda prov=None: "GigaChat-2-Max"

    cfg = Cfg()
    captured = {}
    def fake_run(prompt, model):
        captured["prompt"] = prompt
        captured["model"] = model
        return "GIGA-OK"
    monkeypatch.setattr(aipp, "run_gigachat_aipp", fake_run)
    out = aipp.get_final_text("hello", cfg)
    assert out == "GIGA-OK"
    assert captured["model"] == "GigaChat-2-Max"
    assert "Rewrite:" in captured["prompt"] and "hello" in captured["prompt"]


def test_get_final_text_routes_openai_compatible(monkeypatch):
    from voxd.core import aipp
    class Cfg:
        def __init__(self):
            self.data = {
                "aipp_enabled": True,
                "aipp_provider": "openai_compatible",
                "aipp_active_prompt": "default",
                "aipp_prompts": {"default": "Rewrite:"},
                "aipp_openai_compatible_base_url": "https://api.claudexia.tech/v1",
                "aipp_openai_compatible_api_key": "test-key",
            }
            self.get_aipp_selected_model = lambda prov=None: "claude-sonnet-4.5"

    cfg = Cfg()
    captured = {}
    def fake_run(prompt, model, base_url=None, api_key=None):
        captured["prompt"] = prompt
        captured["model"] = model
        captured["base_url"] = base_url
        captured["api_key"] = api_key
        return "COMPAT-OK"
    monkeypatch.setattr(aipp, "run_openai_aipp", fake_run)
    out = aipp.get_final_text("hello", cfg)
    assert out == "COMPAT-OK"
    assert captured["model"] == "claude-sonnet-4.5"
    assert captured["base_url"] == "https://api.claudexia.tech/v1"
    assert captured["api_key"] == "test-key"
    assert "Rewrite:" in captured["prompt"] and "hello" in captured["prompt"]


def test_get_final_text_routes_openai_compatible_missing_config(monkeypatch):
    from voxd.core import aipp
    class Cfg:
        def __init__(self):
            self.data = {
                "aipp_enabled": True,
                "aipp_provider": "openai_compatible",
                "aipp_active_prompt": "default",
                "aipp_prompts": {"default": "Rewrite:"},
                "aipp_openai_compatible_base_url": "",
                "aipp_openai_compatible_api_key": "",
            }
            self.get_aipp_selected_model = lambda prov=None: "custom-model"

    cfg = Cfg()
    # Should fall back to returning raw text when config is incomplete
    out = aipp.get_final_text("hello", cfg)
    assert out == "hello"


def test_run_gigachat_aipp_missing_creds(monkeypatch):
    from voxd.core import aipp
    monkeypatch.delenv("GIGACHAT_CREDENTIALS", raising=False)
    import pytest
    with pytest.raises(RuntimeError, match="GIGACHAT_CREDENTIALS"):
        aipp.run_gigachat_aipp("test prompt", "GigaChat-2-Max")


def test_run_gigachat_aipp_caches_client(monkeypatch):
    from voxd.core import aipp
    monkeypatch.setenv("GIGACHAT_CREDENTIALS", "fake-creds")
    aipp._gigachat_clients.clear()

    class FakeResult:
        content = "answer"

    instances = []
    class FakeGigaChat:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            instances.append(self)
        def invoke(self, prompt):
            return FakeResult()

    import sys, types
    fake_chat_models = types.ModuleType("langchain_gigachat.chat_models")
    fake_chat_models.GigaChat = FakeGigaChat
    fake_pkg = types.ModuleType("langchain_gigachat")
    fake_pkg.chat_models = fake_chat_models
    monkeypatch.setitem(sys.modules, "langchain_gigachat", fake_pkg)
    monkeypatch.setitem(sys.modules, "langchain_gigachat.chat_models", fake_chat_models)

    out1 = aipp.run_gigachat_aipp("p1", "GigaChat-2-Max")
    out2 = aipp.run_gigachat_aipp("p2", "GigaChat-2-Max")
    assert out1 == "answer" and out2 == "answer"
    # Same (model, scope, verify, creds) tuple → one client reused across calls
    assert len(instances) == 1
    assert instances[0].kwargs["credentials"] == "fake-creds"
    assert instances[0].kwargs["scope"] == "GIGACHAT_API_PERS"
    assert instances[0].kwargs["verify_ssl_certs"] is True

