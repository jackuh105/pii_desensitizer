# src/pii_desensitizer/__init__.py
"""PII Desensitizer: Reversible PII desensitization proxy."""

__version__ = "0.1.0"


def main() -> None:
    """Run the API server."""
    import uvicorn

    from pii_desensitizer.api.app import create_app
    from pii_desensitizer.config import load_settings

    settings = load_settings()
    app = create_app()
    uvicorn.run(app, host=settings.host, port=settings.port)
