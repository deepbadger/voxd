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

