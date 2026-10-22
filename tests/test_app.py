import os
import re
import sqlite3
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from agrosan import create_app
from agrosan.db import get_db, initialize


@pytest.fixture
def app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-only-key",
            "DATABASE": str(tmp_path / "test.db"),
            "DATABASE_URL": os.getenv("TEST_DATABASE_URL", ""),
        }
    )
    with app.app_context():
        initialize()
        if get_db().postgres:
            get_db().execute(
                "TRUNCATE usuarios, lotes, animais, vacinacao, manejo_sanitario, audit_log, login_attempts RESTART IDENTITY CASCADE"
            )
            get_db().commit()
        for username, perfil in [("admin", "admin"), ("operator", "app_user")]:
            get_db().execute(
                "INSERT INTO usuarios (username, senha, perfil) VALUES (?, ?, ?)",
                (username, generate_password_hash("ValidTest2026!"), perfil),
            )
        get_db().commit()
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def token(client, path="/login"):
    response = client.get(path)
    return re.search(rb'name="csrf-token" content="([^"]+)"', response.data).group(1).decode()


def login(client, username="admin"):
    csrf = token(client)
    return client.post(
        "/login",
        data={"username": username, "password": "ValidTest2026!", "csrf_token": csrf},
    )


def api(client, method, path, data=None):
    csrf = token(client, "/")
    return client.open(path, method=method, json=data, headers={"X-CSRFToken": csrf})


def seeds(client):
    lot = api(
        client,
        "POST",
        "/api/lotes",
        dict(
            codigo_lote="L-1",
            quantidade_animais=2,
            especie="Bovino",
            data_formacao="2020-01-01",
        ),
    ).json
    animal = api(
        client,
        "POST",
        "/api/animais",
        dict(
            identificacao="BR-001",
            especie="Bovino",
            raca="Nelore",
            sexo="F",
            data_nascimento="2020-01-01",
            lote_id=lot["id"],
        ),
    ).json
    return lot, animal


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/listagem",
        "/cadastro",
        "/lotes",
        "/vacinacao",
        "/manejo",
        "/auditoria",
        "/usuarios/novo",
        "/api/animais",
    ],
)
def test_authentication_required(client, path):
    assert client.get(path).status_code == 302


def test_full_crud_and_history(client, app):
    assert login(client).status_code == 302
    lot, animal = seeds(client)
    vaccination = dict(
        animal_id=animal["id"],
        vacina="Raiva",
        fabricante="Laboratório",
        lote_vacina="V-1",
        dose="2 ml",
        data_aplicacao="2021-01-01",
        proxima_dose="2022-01-01",
        responsavel="Responsável",
        observacoes="Observação",
        carencia_dias=30,
    )
    response = api(client, "POST", "/api/vacinacao", vaccination)
    assert response.status_code == 201
    vac = response.json
    assert all(vac[k] == v for k, v in vaccination.items())
    handling = dict(
        animal_id=animal["id"],
        tipo_manejo="Vermifugação",
        data_manejo="2021-01-01",
        produto="Produto",
        dose="2 ml",
        responsavel="Técnico",
        observacoes="Histórico",
        carencia_dias=10,
    )
    response = api(client, "POST", "/api/manejo_sanitario", handling)
    assert response.status_code == 201
    handle = response.json
    for entity, row, data in [
        (
            "lotes",
            lot,
            dict(
                codigo_lote="L-2",
                quantidade_animais=3,
                especie="Bovino",
                data_formacao="2020-01-01",
            ),
        ),
        (
            "animais",
            animal,
            dict(
                identificacao="BR-002",
                especie="Bovino",
                data_nascimento="2020-01-01",
                lote_id=lot["id"],
            ),
        ),
        ("vacinacao", vac, {**vaccination, "dose": "3 ml"}),
        ("manejo_sanitario", handle, {**handling, "dose": "3 ml"}),
    ]:
        assert client.get(f"/registros/{entity}/{row['id']}/editar").status_code == 200
        updated = api(client, "PUT", f"/api/{entity}/{row['id']}", data)
        assert updated.status_code == 200, updated.data
        assert updated.json.get("dose", "3 ml") == "3 ml"
        assert client.get(f"/api/{entity}/{row['id']}").status_code == 200
    listing = client.get("/listagem")
    assert b"Laborat" in listing.data and b"BR-002" in listing.data and b"Atrasada" in listing.data
    assert b"BR-002" in client.get("/").data
    assert api(client, "DELETE", f"/api/animais/{animal['id']}").status_code == 409
    assert api(client, "DELETE", f"/api/lotes/{lot['id']}").status_code == 409
    for entity, row in [
        ("vacinacao", vac),
        ("manejo_sanitario", handle),
        ("animais", animal),
        ("lotes", lot),
    ]:
        assert api(client, "DELETE", f"/api/{entity}/{row['id']}").status_code == 204
        assert client.get(f"/api/{entity}/{row['id']}").status_code == 404
    with app.app_context():
        actions = [r["acao"] for r in get_db().execute("SELECT acao FROM audit_log").fetchall()]
        assert (
            "INSERT_vacinacao" in actions
            and "UPDATE_animais" in actions
            and "DELETE_lotes" in actions
        )


@pytest.mark.parametrize(
    "entity,data",
    [
        (
            "lotes",
            dict(
                codigo_lote="x",
                quantidade_animais=-1,
                especie="Bovino",
                data_formacao="2020-01-01",
            ),
        ),
        ("animais", dict(identificacao="", especie="Bovino")),
        (
            "animais",
            dict(identificacao="X", especie="Bovino", data_nascimento="2020-02-30"),
        ),
        (
            "animais",
            dict(identificacao="X", especie="Bovino", data_nascimento="2999-01-01"),
        ),
        ("animais", dict(identificacao="X", especie="Bovino", lote_id=999)),
        ("animais", dict(identificacao=["invalid"], especie="Bovino")),
        ("animais", dict(identificacao="X" * 201, especie="Bovino")),
    ],
)
def test_invalid_input(client, entity, data):
    login(client)
    assert api(client, "POST", f"/api/{entity}", data).status_code == 400


def test_date_order_and_duplicates(client):
    login(client)
    lot, animal = seeds(client)
    assert (
        api(
            client,
            "POST",
            "/api/animais",
            dict(identificacao="BR-001", especie="Bovino"),
        ).status_code
        == 409
    )
    base = dict(
        animal_id=animal["id"],
        vacina="Vacina",
        dose="2 ml",
        responsavel="Técnico",
        carencia_dias=0,
    )
    assert (
        api(
            client,
            "POST",
            "/api/vacinacao",
            {**base, "data_aplicacao": "2021-01-01", "proxima_dose": "2020-01-01"},
        ).status_code
        == 400
    )
    assert (
        api(client, "POST", "/api/vacinacao", {**base, "data_aplicacao": "2019-01-01"}).status_code
        == 400
    )
    assert (
        api(
            client,
            "POST",
            "/api/vacinacao",
            {**base, "data_aplicacao": "2021-01-01", "animal_id": 999},
        ).status_code
        == 400
    )
    assert api(client, "POST", "/api/vacinacao", []).status_code == 400
    assert api(client, "POST", "/api/unknown", {}).status_code == 404


def test_permissions_csrf_and_logout(client):
    login(client, "operator")
    lot, animal = seeds(client)
    assert client.get("/auditoria").status_code == 403
    assert client.get("/usuarios/novo").status_code == 403
    assert api(client, "DELETE", f"/api/animais/{animal['id']}").status_code == 403
    assert (
        client.post("/cadastro", data={"identificacao": "X", "especie": "Bovino"}).status_code
        == 400
    )
    assert (
        client.put(f"/api/animais/{animal['id']}", json={"identificacao": "X"}).status_code == 400
    )
    assert client.get("/logout").status_code == 405
    assert client.post("/logout", data={"csrf_token": token(client, "/")}).status_code == 302
    assert client.get("/").status_code == 302


def test_lockout_and_expiry(client, app):
    for _ in range(5):
        response = client.post(
            "/login",
            data={
                "username": "admin",
                "password": "wrong",
                "csrf_token": token(client),
            },
        )
        assert response.status_code == 401
    assert login(client).status_code == 429
    with app.app_context():
        get_db().execute(
            "UPDATE login_attempts SET bloqueado_ate = 1 WHERE username = ?", ("admin",)
        )
        get_db().commit()
    assert login(client).status_code == 302


def test_user_creation(client):
    login(client)
    csrf = token(client, "/usuarios/novo")
    assert (
        client.post(
            "/usuarios/novo",
            data={"username": "new", "password": "weak", "csrf_token": csrf},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/usuarios/novo",
            data={
                "username": "new",
                "password": "StrongTest2026!",
                "perfil": "app_user",
                "csrf_token": csrf,
            },
        ).status_code
        == 302
    )
    assert (
        client.post(
            "/usuarios/novo",
            data={
                "username": "new",
                "password": "StrongTest2026!",
                "perfil": "admin",
                "csrf_token": csrf,
            },
        ).status_code
        == 400
    )


def test_headers_and_pages(client):
    login(client)
    for path in [
        "/",
        "/cadastro",
        "/lotes",
        "/vacinacao",
        "/manejo",
        "/listagem",
        "/auditoria",
        "/usuarios/novo",
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "form-action" in response.headers["Content-Security-Policy"]
        assert b'name="csrf-token"' in response.data


def test_backup_and_import(app, tmp_path):
    if app.config["DATABASE_URL"]:
        pytest.skip(
            "Backup PostgreSQL e permissões são verificados no teste de integração dedicado."
        )
    runner = app.test_cli_runner()
    target = tmp_path / "backup.db"
    result = runner.invoke(args=["backup-db", "--output", str(target)])
    assert result.exit_code == 0, result.output
    with sqlite3.connect(target) as db:
        assert db.execute("pragma integrity_check").fetchone()[0] == "ok"
        assert db.execute("select count(*) from usuarios").fetchone()[0] == 2
    assert runner.invoke(args=["backup-db", "--output", str(target)]).exit_code != 0
    source = Path(__file__).resolve().parents[1] / "database.db"
    if source.exists():
        before = source.read_bytes()
        result = runner.invoke(args=["import-legacy", str(source)])
        assert result.exit_code == 0, result.output
        assert source.read_bytes() == before
        assert runner.invoke(args=["import-legacy", str(source)]).exit_code != 0


def test_cli_no_default_password(app):
    runner = app.test_cli_runner()
    assert (
        runner.invoke(args=["create-user", "--username", "cli", "--password", "weak"]).exit_code
        != 0
    )
    result = runner.invoke(
        args=[
            "create-user",
            "--username",
            "cli",
            "--perfil",
            "app_user",
            "--password",
            "StrongCli2026!",
        ]
    )
    assert result.exit_code == 0, result.output


def test_history_filters(client):
    login(client)
    lot, animal = seeds(client)
    other = api(
        client, "POST", "/api/animais", {"identificacao": "OUTRO-ANIMAL", "especie": "Ovino"}
    )
    assert other.status_code == 201
    page = client.get(f"/listagem?lote_id={lot['id']}")
    assert page.status_code == 200
    # As opções do filtro incluem todos, mas as linhas respeitam o lote.
    assert b"BR-001</td>" in page.data
    assert b"OUTRO-ANIMAL</td>" not in page.data
    assert client.get("/listagem?lote_id=invalid").status_code == 400
    assert client.get("/listagem?animal_id=99999").status_code == 404
    assert client.get(f"/listagem?animal_id={animal['id']}").status_code == 200


def test_birth_cannot_invalidate_existing_history(client):
    login(client)
    lot, animal = seeds(client)
    payload = {
        "animal_id": animal["id"],
        "tipo_manejo": "Pesagem",
        "data_manejo": "2021-01-01",
        "responsavel": "Técnico",
        "carencia_dias": 0,
    }
    assert api(client, "POST", "/api/manejo_sanitario", payload).status_code == 201
    edit = {"identificacao": "BR-001", "especie": "Bovino", "data_nascimento": "2022-01-01"}
    assert api(client, "PUT", f"/api/animais/{animal['id']}", edit).status_code == 400


def test_initialization_is_repeatable(app):
    with app.app_context():
        previous = (
            get_db()
            .execute("SELECT senha FROM usuarios WHERE username = ?", ("admin",))
            .fetchone()["senha"]
        )
        initialize()
        assert (
            get_db()
            .execute("SELECT senha FROM usuarios WHERE username = ?", ("admin",))
            .fetchone()["senha"]
            == previous
        )


def test_legacy_failure_rolls_back(app, tmp_path):
    source = tmp_path / "legacy.db"
    with sqlite3.connect(source) as db:
        db.executescript(
            "CREATE TABLE lotes (id INTEGER, codigo_lote TEXT, quantidade_animais INTEGER, especie TEXT, data_formacao TEXT); CREATE TABLE animais (id INTEGER, identificacao TEXT, especie TEXT); CREATE TABLE vacinacao (id INTEGER, animal TEXT, vacina TEXT, data_aplicacao TEXT); INSERT INTO lotes VALUES (1,'L',1,'Bovino','2020-01-01'); INSERT INTO vacinacao VALUES (1,'A','V',NULL);"
        )
    result = app.test_cli_runner().invoke(args=["import-legacy", str(source)])
    assert result.exit_code != 0
    with app.app_context():
        for table in ("lotes", "animais", "vacinacao", "audit_log"):
            assert get_db().execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"] == 0


def test_sql_and_html_are_treated_as_data(client):
    login(client)
    label = "<script>alert(1)</script>' OR 1=1 --"
    response = api(client, "POST", "/api/animais", {"identificacao": label, "especie": "Bovino"})
    assert response.status_code == 201
    page = client.get("/listagem")
    assert b"<script>alert(1)</script>" not in page.data
    assert b"&lt;script&gt;" in page.data
    assert len(client.get("/api/animais").json) == 1


def test_production_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()
    monkeypatch.setenv("SECRET_KEY", "a" * 64)
    production = create_app(
        {"TESTING": True, "DATABASE": str(tmp_path / "prod.db"), "DATABASE_URL": ""}
    )
    assert production.config["SESSION_COOKIE_SECURE"]
    assert production.config["SESSION_COOKIE_HTTPONLY"]


def test_public_registration_and_login(client, app):
    assert client.get("/register").status_code == 200
    csrf = token(client, "/register")
    payload = {
        "username": "visitor",
        "password": "VisitorTest2026!",
        "confirm_password": "VisitorTest2026!",
        "perfil": "admin",
        "csrf_token": csrf,
    }
    assert client.post("/register", data=payload).status_code == 302
    with app.app_context():
        row = get_db().execute("SELECT * FROM usuarios WHERE username = ?", ("visitor",)).fetchone()
        assert row["perfil"] == "app_user"
        assert row["senha"] != payload["password"]
    assert client.post("/register", data=payload).status_code == 400
    assert (
        client.post(
            "/login",
            data={
                "username": "visitor",
                "password": payload["password"],
                "csrf_token": token(client),
            },
        ).status_code
        == 302
    )


def test_registration_confirmation_and_csrf(client):
    assert client.post("/register", data={"username": "x"}).status_code == 400
    csrf = token(client, "/register")
    assert (
        client.post(
            "/register",
            data={
                "username": "x",
                "password": "VisitorTest2026!",
                "confirm_password": "different",
                "csrf_token": csrf,
            },
        ).status_code
        == 400
    )


def test_first_registration_bootstrap(client, app):
    with app.app_context():
        get_db().execute("DELETE FROM usuarios")
        get_db().commit()
    payload = {
        "username": "owner",
        "password": "OwnerTest2026!",
        "confirm_password": "OwnerTest2026!",
        "csrf_token": token(client, "/register"),
    }
    assert client.post("/register", data=payload).status_code == 302
    with app.app_context():
        assert get_db().execute("SELECT perfil FROM usuarios").fetchone()["perfil"] == "admin"
    payload.update(username="second")
    assert client.post("/register", data=payload).status_code == 302
    with app.app_context():
        assert (
            get_db()
            .execute("SELECT perfil FROM usuarios WHERE username = ?", ("second",))
            .fetchone()["perfil"]
            == "app_user"
        )
