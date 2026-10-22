"""Acesso parametrizado, esquema e ferramentas de administração."""

import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import click
from flask import current_app, g

ROOT = Path(__file__).resolve().parent.parent


class Database:
    def __init__(self):
        self.postgres = bool(current_app.config["DATABASE_URL"])
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row

            self.conn = psycopg.connect(current_app.config["DATABASE_URL"], row_factory=dict_row)
        else:
            self.conn = sqlite3.connect(current_app.config["DATABASE"], timeout=15)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON")

    def execute(self, sql, params=()):
        return self.conn.execute(sql.replace("?", "%s") if self.postgres else sql, params)

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()


def get_db():
    if "db" not in g:
        g.db = Database()
    return g.db


def audit(action, details):
    from flask_login import current_user

    who = current_user.username if current_user and current_user.is_authenticated else "anônimo"
    get_db().execute(
        "INSERT INTO audit_log (acao, detalhes, usuario) VALUES (?, ?, ?)",
        (action, details, who),
    )


def initialize():
    db = get_db()
    ddl = (ROOT / "schema.sql").read_text(encoding="utf-8")
    if db.postgres:
        ddl = (
            ddl.replace("PRAGMA foreign_keys = ON;", "")
            .replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
            .replace("DEFAULT CURRENT_TIMESTAMP", "DEFAULT (CURRENT_TIMESTAMP::text)")
        )
        db.conn.execute(ddl, prepare=False)
        db.conn.execute(
            (ROOT / "sql/postgres_functions.sql").read_text(encoding="utf-8"),
            prepare=False,
        )
    else:
        db.conn.executescript(ddl)
        for table in ("animais", "lotes", "vacinacao", "manejo_sanitario"):
            for operation in ("INSERT", "UPDATE", "DELETE"):
                ref = "OLD" if operation == "DELETE" else "NEW"
                db.conn.execute(f"""CREATE TRIGGER IF NOT EXISTS trg_{table}_{operation.lower()}
                    AFTER {operation} ON {table} BEGIN
                    INSERT INTO audit_log (acao, detalhes) VALUES ('{operation}_{table}', 'Registro ID: ' || {ref}.id); END""")
    db.commit()


def integrity_errors():
    if get_db().postgres:
        import psycopg

        return (psycopg.IntegrityError,)
    return (sqlite3.IntegrityError,)


def init_app(app):
    @app.teardown_appcontext
    def close(error):
        db = g.pop("db", None)
        if db:
            db.conn.close()

    @app.cli.command("init-db")
    def init_db():
        """Cria as tabelas sem apagar registros existentes."""
        initialize()
        click.echo("Banco inicializado. Crie o administrador com create-user.")

    @app.cli.command("create-user")
    @click.option("--username", prompt="Usuário")
    @click.option("--perfil", type=click.Choice(["admin", "app_user"]), default="admin")
    @click.password_option(confirmation_prompt=True)
    def create_user(username, perfil, password):
        from werkzeug.security import generate_password_hash

        from .routes import password_error

        error = password_error(password)
        if error or not username.strip() or len(username) > 80:
            raise click.ClickException(error or "Usuário inválido.")
        db = get_db()
        try:
            db.execute(
                "INSERT INTO usuarios (username, senha, perfil) VALUES (?, ?, ?)",
                (username.strip(), generate_password_hash(password), perfil),
            )
            db.commit()
        except integrity_errors():
            db.rollback()
            raise click.ClickException("Usuário já existe.")
        click.echo("Usuário criado.")

    @app.cli.command("set-password")
    @click.option("--username", prompt="Usuário")
    @click.password_option(confirmation_prompt=True)
    def set_password(username, password):
        """Define uma nova senha localmente, sem imprimir ou salvar a senha em texto."""
        from werkzeug.security import generate_password_hash

        from .routes import password_error

        error = password_error(password)
        if error:
            raise click.ClickException(error)
        db = get_db()
        if not db.execute("SELECT id FROM usuarios WHERE username = ?", (username,)).fetchone():
            raise click.ClickException("Usuário não encontrado.")
        db.execute(
            "UPDATE usuarios SET senha = ? WHERE username = ?",
            (generate_password_hash(password), username),
        )
        db.execute("DELETE FROM login_attempts WHERE username = ?", (username,))
        db.execute(
            "INSERT INTO audit_log (acao, detalhes, usuario) VALUES (?, ?, ?)",
            ("ALTERAR_SENHA", f"Senha redefinida: {username}", "CLI"),
        )
        db.commit()
        click.echo(
            "Senha atualizada. Use a conta proprietária do banco para este comando no PostgreSQL."
        )

    @app.cli.command("backup-db")
    @click.option("--output", type=click.Path(path_type=Path), default=None)
    def backup_db(output):
        """Backup consistente SQLite ou dump PostgreSQL (requer pg_dump)."""
        output = output or Path(app.instance_path) / "backups" / datetime.now(UTC).strftime(
            "agrosan-%Y%m%d-%H%M%S-%f.dump"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            raise click.ClickException("O destino já existe; escolha outro nome.")
        db = get_db()
        if db.postgres:
            import os

            env = os.environ.copy()
            env["PGDATABASE"] = app.config["DATABASE_URL"]
            try:
                subprocess.run(
                    ["pg_dump", "--format=custom", "--file", str(output)],
                    env=env,
                    check=True,
                    capture_output=True,
                )
            except (OSError, subprocess.CalledProcessError):
                raise click.ClickException("Falha no pg_dump. Confira a instalação e a conexão.")
        else:
            with sqlite3.connect(output) as target:
                db.conn.backup(target)
        click.echo(f"Backup salvo: {output.resolve()}")

    from .legacy import import_legacy

    app.cli.add_command(import_legacy)
