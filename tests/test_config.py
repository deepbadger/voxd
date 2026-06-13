
def test_aipp_provider_validation_resets_invalid():
    from voxd.core.config import AppConfig
    cfg = AppConfig()
    cfg.data["aipp_provider"] = "invalid"
    cfg._validate_aipp_config()
    assert cfg.data["aipp_provider"] in (
        "ollama", "openai", "openrouter", "anthropic", "xai", "llamacpp_server", "openai_compatible"
    )


def test_aipp_models_backfill_for_new_provider():
    """A config that predates a provider (missing or blank entry) should get its
    default model list/selection seeded, not left empty — otherwise the GUI model
    dropdown is blank and unselectable."""
    from voxd.core.config import AppConfig
    cfg = AppConfig()
    # Simulate an older config.yaml: openrouter absent, plus a stale empty entry.
    cfg.data["aipp_models"].pop("openrouter", None)
    cfg.data["aipp_selected_models"].pop("openrouter", None)
    cfg.data["aipp_models"]["openai"] = []
    cfg.data["aipp_selected_models"]["openai"] = ""
    cfg._validate_aipp_config()
    assert cfg.data["aipp_models"]["openrouter"]            # non-empty list
    assert cfg.data["aipp_selected_models"]["openrouter"]   # a default selection
    assert cfg.data["aipp_models"]["openai"]                # repaired blank list
    assert cfg.data["aipp_selected_models"]["openai"]


def test_llamacpp_status_flags_do_not_crash():
    from voxd.core.config import AppConfig
    cfg = AppConfig()
    status = cfg.validate_llamacpp_setup()
    assert {
        "server_available",
        "cli_available",
        "default_model_available",
    } <= set(status.keys())


