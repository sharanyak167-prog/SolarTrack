from app import config


def test_empty_env_values_fall_back_to_defaults(monkeypatch):
    for k in ("DATABASE_URL", "UPLOAD_DIR", "EXTRACTION_MODE", "GEMINI_MODEL"):
        monkeypatch.setenv(k, "")
    assert config.database_url().startswith("sqlite:///")
    assert config.upload_dir().name == "uploads"
    assert config.extraction_mode() == "gemini"
    assert config.gemini_model()
