"""راه‌انداز سرور درمانیو داخل اندروید (Chaquopy). از Kotlin صدا زده می‌شود."""
import os
import secrets
import threading


def start_server(workdir, db_path):
    """سرور uvicorn را در یک ترد daemon اجرا می‌کند و سریع برمی‌گردد."""
    os.chdir(workdir)
    os.makedirs(os.path.join(workdir, "static", "uploads"), exist_ok=True)

    # کلید امضای نشست
    key_file = os.path.join(os.path.dirname(db_path), "secret.key")
    if not os.path.exists(key_file):
        with open(key_file, "w") as f:
            f.write(secrets.token_hex(32))
    with open(key_file) as f:
        os.environ["SECRET_KEY"] = f.read().strip()

    os.environ["DATABASE_URL"] = "sqlite:///" + db_path
    os.environ.setdefault("SMS_ENABLED", "false")
    os.environ.setdefault("SMS_DRY_RUN", "true")

    def _run():
        import uvicorn
        from app.main import app
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=8000,
            log_level="info",
            http="h11",
            ws="none",
            loop="asyncio",
            lifespan="on",
        )
        uvicorn.Server(config).run()

    t = threading.Thread(target=_run, daemon=True, name="uvicorn")
    t.start()
