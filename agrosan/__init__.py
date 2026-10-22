"""Configuração, autenticação e proteções comuns."""

import os
import secrets
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, render_template
from flask_login import LoginManager, UserMixin
from flask_wtf.csrf import CSRFError, CSRFProtect


class User(UserMixin):
    def __init__(self, row):
        self.id = row["id"]
        self.username = row["username"]
        self.perfil = row["perfil"]


def create_app(config=None):
    load_dotenv()
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    production = os.getenv("APP_ENV") == "production"
    key = os.getenv("SECRET_KEY")
    if not key and production:
        raise RuntimeError("Defina SECRET_KEY para publicar o sistema.")
    if not key:
        # Chave aleatória persistente, fora do Git, para desenvolvimento local.
        key_path = Path(app.instance_path) / ".secret_key"
        try:
            with key_path.open("x", encoding="utf-8") as f:
                f.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        key = key_path.read_text(encoding="utf-8").strip()
    app.config.update(
        SECRET_KEY=key,
        DATABASE=os.getenv("DATABASE_PATH", str(Path(app.instance_path) / "agrosan.db")),
        DATABASE_URL=os.getenv("DATABASE_URL", ""),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=production,
        REMEMBER_COOKIE_SECURE=production,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=1024 * 1024,
        WTF_CSRF_TIME_LIMIT=8 * 60 * 60,
    )
    if config:
        app.config.update(config)
    CSRFProtect(app)
    manager = LoginManager(app)
    manager.login_view = "web.login"
    manager.login_message = "Entre para acessar o sistema."

    @manager.user_loader
    def load_user(uid):
        from .db import get_db

        try:
            uid = int(uid)
        except (TypeError, ValueError):
            return None
        row = get_db().execute("SELECT * FROM usuarios WHERE id = ?", (uid,)).fetchone()
        return User(row) if row else None

    from . import db

    db.init_app(app)
    from .routes import web

    app.register_blueprint(web)

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        return render_template(
            "error.html",
            message="A sessão do formulário expirou. Recarregue a página e tente novamente.",
        ), 400

    for code, message in [
        (400, "Os dados enviados são inválidos."),
        (403, "Você não tem permissão para esta ação."),
        (404, "Registro ou página não encontrado."),
        (405, "Ação não permitida."),
        (413, "O envio excedeu o tamanho permitido."),
    ]:
        app.register_error_handler(
            code,
            lambda error, message=message: (
                render_template("error.html", message=message),
                error.code,
            ),
        )

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
        )
        response.headers["Cache-Control"] = "no-store"
        if production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    return app
