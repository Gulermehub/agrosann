"""Telas e API compartilham a mesma validação e as mesmas permissões."""

import re
import time
from datetime import date, timedelta
from functools import wraps

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from . import User
from .db import audit, get_db, integrity_errors

web = Blueprint("web", __name__)
# Cada campo: nome, rótulo, tipo, obrigatório. Também define a lista permitida para SQL.
ENTITIES = {
    "lotes": (
        "Lotes",
        [
            ("codigo_lote", "Código do lote", "text", True),
            ("quantidade_animais", "Quantidade informada de animais", "number", True),
            ("especie", "Espécie", "text", True),
            ("data_formacao", "Data de formação", "date", True),
        ],
    ),
    "animais": (
        "Animais",
        [
            ("identificacao", "Identificação", "text", True),
            ("especie", "Espécie", "text", True),
            ("raca", "Raça", "text", False),
            ("sexo", "Sexo", "text", False),
            ("data_nascimento", "Data de nascimento", "date", False),
            ("lote_id", "Lote", "lote", False),
        ],
    ),
    "vacinacao": (
        "Vacinações",
        [
            ("animal_id", "Animal", "animal", True),
            ("vacina", "Vacina", "text", True),
            ("fabricante", "Fabricante", "text", False),
            ("lote_vacina", "Lote da vacina", "text", False),
            ("dose", "Dose aplicada", "text", True),
            ("data_aplicacao", "Data da aplicação", "date", True),
            ("proxima_dose", "Próxima dose", "date", False),
            ("responsavel", "Responsável", "text", True),
            ("observacoes", "Observações", "textarea", False),
            ("carencia_dias", "Carência em dias (conforme produto)", "number", True),
        ],
    ),
    "manejo_sanitario": (
        "Manejos sanitários",
        [
            ("animal_id", "Animal", "animal", True),
            ("tipo_manejo", "Tipo de manejo", "text", True),
            ("data_manejo", "Data do manejo", "date", True),
            ("produto", "Produto", "text", False),
            ("dose", "Dose", "text", False),
            ("responsavel", "Responsável", "text", True),
            ("observacoes", "Observações", "textarea", False),
            ("carencia_dias", "Carência em dias (conforme produto)", "number", True),
        ],
    ),
}


def admin_required(func):
    @wraps(func)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.perfil != "admin":
            abort(403)
        return func(*args, **kwargs)

    return wrapped


def password_error(value):
    if (
        not isinstance(value, str)
        or not (12 <= len(value) <= 128)
        or not re.search("[a-z]", value)
        or not re.search("[A-Z]", value)
        or not re.search("[0-9]", value)
        or not re.search(r"[^a-zA-Z0-9]", value)
    ):
        return "Use uma senha de 12 a 128 caracteres com maiúscula, minúscula, número e símbolo."
    return None


def status_vacina(value):
    if not value:
        return "Sem agendamento"
    remaining = (date.fromisoformat(value) - date.today()).days
    return "Atrasada" if remaining < 0 else "Hoje" if remaining == 0 else "Em dia"


@web.context_processor
def context():
    return dict(entities=ENTITIES)


@web.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("web.inicio"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()[:80]
        password = request.form.get("password", "")
        db = get_db()
        attempt = db.execute(
            "SELECT * FROM login_attempts WHERE username = ?", (username,)
        ).fetchone()
        now = time.time()
        if attempt and attempt["bloqueado_ate"] > now:
            flash("Muitas tentativas. Aguarde 15 minutos para tentar novamente.", "error")
            return render_template("login.html"), 429
        row = db.execute("SELECT * FROM usuarios WHERE username = ?", (username,)).fetchone()
        # Um hash fictício evita responder imediatamente para usuários inexistentes.
        from flask import current_app

        dummy = current_app.config.get("DUMMY_HASH")
        if dummy is None:
            dummy = current_app.config["DUMMY_HASH"] = generate_password_hash(
                "credencial fictícia não utilizável"
            )
        valid = check_password_hash(row["senha"] if row else dummy, password[:128])
        if row and len(password) <= 128 and valid:
            session.clear()
            login_user(User(row))
            session.permanent = True
            db.execute("DELETE FROM login_attempts WHERE username = ?", (username,))
            audit("LOGIN", "Autenticação bem-sucedida")
            db.commit()
            return redirect(url_for("web.inicio"))
        db.execute(
            """INSERT INTO login_attempts (username, tentativas, bloqueado_ate) VALUES (?, 1, 0)
            ON CONFLICT(username) DO UPDATE SET
            tentativas = CASE WHEN login_attempts.bloqueado_ate > 0 AND login_attempts.bloqueado_ate <= ? THEN 1 ELSE login_attempts.tentativas + 1 END,
            bloqueado_ate = CASE WHEN login_attempts.bloqueado_ate > 0 AND login_attempts.bloqueado_ate <= ? THEN 0 WHEN login_attempts.tentativas >= 4 THEN ? ELSE 0 END""",
            (username, now, now, now + 900),
        )
        audit("LOGIN_FALHOU", "Tentativa de autenticação recusada")
        db.commit()
        flash("Usuário ou senha incorretos.", "error")
        return render_template("login.html"), 401
    return render_template("login.html")


@web.post("/logout")
@login_required
def logout():
    audit("LOGOUT", "Sessão encerrada")
    get_db().commit()
    logout_user()
    session.clear()
    return redirect(url_for("web.login"))


@web.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("web.inicio"))
    return registration(public=True)


@web.route("/usuarios/novo", methods=["GET", "POST"])
@admin_required
def create_user():
    return registration(public=False)


def registration(public):
    username = request.form.get("username", "").strip()
    if request.method == "POST":
        password = request.form.get("password", "")
        perfil = "app_user" if public else request.form.get("perfil", "app_user")
        error = password_error(password)
        if not username or len(username) > 80 or perfil not in ("admin", "app_user"):
            error = "Informe um usuário válido e um perfil permitido."
        if public and password != request.form.get("confirm_password", ""):
            error = "As senhas não conferem."
        if not error:
            db = get_db()
            hashed = generate_password_hash(password)
            try:
                if public:
                    # Serializa o primeiro cadastro: apenas uma conta recebe administração.
                    if db.postgres:
                        db.execute("SELECT pg_advisory_xact_lock(71642026)")
                    else:
                        db.execute("BEGIN IMMEDIATE")
                    if db.execute("SELECT COUNT(*) AS n FROM usuarios").fetchone()["n"] == 0:
                        perfil = "admin"
                db.execute(
                    "INSERT INTO usuarios (username, senha, perfil) VALUES (?, ?, ?)",
                    (username, hashed, perfil),
                )
                audit("CRIAR_USUARIO", f"Conta criada: {username} ({perfil})")
                db.commit()
                if public:
                    flash("Conta criada! Entre com seu usuário e senha.", "success")
                    return redirect(url_for("web.login"))
                flash("Usuário criado com sucesso.", "success")
                return redirect(url_for("web.create_user"))
            except integrity_errors():
                db.rollback()
                error = "Este nome de usuário já existe."
        flash(error, "error")
        return render_template("registrar.html", public=public, username=username), 400
    return render_template("registrar.html", public=public, username="")


@web.get("/")
@login_required
def inicio():
    db = get_db()
    totals = {
        entity: db.execute(f"SELECT COUNT(*) AS total FROM {entity}").fetchone()["total"]
        for entity in ENTITIES
    }
    today = date.today().isoformat()
    alerts = db.execute(
        """SELECT v.*, a.identificacao FROM vacinacao v JOIN animais a ON a.id=v.animal_id
        WHERE v.proxima_dose <= ? ORDER BY v.proxima_dose, v.id""",
        (today,),
    ).fetchall()
    return render_template("index.html", totals=totals, alerts=alerts, status_vacina=status_vacina)


def entity_info(entity):
    if entity not in ENTITIES:
        abort(404)
    return ENTITIES[entity]


def record(entity, rid):
    row = get_db().execute(f"SELECT * FROM {entity} WHERE id = ?", (rid,)).fetchone()
    if not row:
        abort(404)
    return dict(row)


def validate(entity, source):
    values = {}
    for name, label, kind, required in ENTITIES[entity][1]:
        raw = source.get(name, "")
        if raw is None:
            raw = ""
        if isinstance(raw, (dict, list, bool)):
            raise ValueError(f"{label}: valor inválido.")
        value = str(raw).strip()
        if not value:
            if required:
                raise ValueError(f"Preencha {label.lower()}.")
            values[name] = None
            continue
        if len(value) > (2000 if kind == "textarea" else 200):
            raise ValueError(f"{label}: texto muito longo.")
        if kind == "date":
            try:
                value = date.fromisoformat(value).isoformat()
            except ValueError:
                raise ValueError(f"{label}: data inválida.")
        if kind in ("number", "animal", "lote"):
            try:
                value = int(value)
            except ValueError:
                raise ValueError(f"{label}: informe um número inteiro.")
            if value < 0 or value > 1000000 or (kind != "number" and value == 0):
                raise ValueError(f"{label}: número fora do intervalo permitido.")
            if kind in ("animal", "lote"):
                target = "animais" if kind == "animal" else "lotes"
                if (
                    not get_db()
                    .execute(f"SELECT id FROM {target} WHERE id = ?", (value,))
                    .fetchone()
                ):
                    raise ValueError(f"{label}: registro não encontrado.")
        values[name] = value
    today = date.today().isoformat()
    for name in ("data_nascimento", "data_formacao", "data_aplicacao", "data_manejo"):
        if values.get(name) and values[name] > today:
            raise ValueError("A data do registro não pode estar no futuro.")
    if values.get("proxima_dose") and values["proxima_dose"] < values["data_aplicacao"]:
        raise ValueError("A próxima dose não pode anteceder a aplicação.")
    if values.get("animal_id"):
        animal = record("animais", values["animal_id"])
        occurred = values.get("data_aplicacao") or values.get("data_manejo")
        if animal["data_nascimento"] and occurred < animal["data_nascimento"]:
            raise ValueError("A aplicação ou manejo não pode anteceder o nascimento do animal.")
    return values


def save(entity, source, rid=None):
    values = validate(entity, source)
    db = get_db()
    if rid is not None and entity == "animais" and values.get("data_nascimento"):
        for table, field in (("vacinacao", "data_aplicacao"), ("manejo_sanitario", "data_manejo")):
            if db.execute(
                f"SELECT id FROM {table} WHERE animal_id = ? AND {field} < ? LIMIT 1",
                (rid, values["data_nascimento"]),
            ).fetchone():
                raise ValueError(
                    "O nascimento não pode ser posterior ao histórico sanitário do animal."
                )
    if rid is None:
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        rid = db.execute(
            f"INSERT INTO {entity} ({columns}) VALUES ({placeholders}) RETURNING id",
            tuple(values.values()),
        ).fetchone()["id"]
    else:
        record(entity, rid)
        assignments = ", ".join(f"{name} = ?" for name in values)
        db.execute(f"UPDATE {entity} SET {assignments} WHERE id = ?", (*values.values(), rid))
    audit("SALVAR", f"{entity} ID {rid}")
    db.commit()
    return rid


def form(entity, rid=None):
    title, fields = entity_info(entity)
    values = record(entity, rid) if rid else {"carencia_dias": 0}
    error = None
    if request.method == "POST":
        values = request.form
        try:
            save(entity, values, rid)
            flash("Registro salvo com sucesso.", "success")
            return redirect(url_for("web.listagem"))
        except ValueError as exc:
            get_db().rollback()
            error = str(exc)
        except integrity_errors():
            get_db().rollback()
            error = "Já existe um registro com essa identificação ou há um vínculo inválido."
        flash(error, "error")
    db = get_db()
    return render_template(
        "form.html",
        entity=entity,
        title=title,
        fields=fields,
        values=values,
        rid=rid,
        animals=db.execute(
            "SELECT id, identificacao FROM animais ORDER BY identificacao"
        ).fetchall(),
        lots=db.execute("SELECT id, codigo_lote FROM lotes ORDER BY codigo_lote").fetchall(),
    ), 400 if error else 200


@web.route("/cadastro", methods=["GET", "POST"])
@login_required
def cadastro():
    return form("animais")


@web.route("/lotes", methods=["GET", "POST"])
@login_required
def lotes():
    return form("lotes")


@web.route("/vacinacao", methods=["GET", "POST"])
@login_required
def vacinacao():
    return form("vacinacao")


@web.route("/manejo", methods=["GET", "POST"])
@login_required
def manejo():
    return form("manejo_sanitario")


@web.route("/registros/<entity>/<int:rid>/editar", methods=["GET", "POST"])
@login_required
def edit(entity, rid):
    return form(entity, rid)


@web.get("/listagem")
@login_required
def listagem():
    db = get_db()
    groups = {}
    for entity in ENTITIES:
        rows = [dict(r) for r in db.execute(f"SELECT * FROM {entity} ORDER BY id DESC").fetchall()]
        for row in rows:
            if entity == "vacinacao":
                row["situacao"] = (
                    db.execute(
                        "SELECT status_vacinacao(?) AS status", (row["proxima_dose"],)
                    ).fetchone()["status"]
                    if db.postgres
                    else status_vacina(row["proxima_dose"])
                )
            if entity in ("vacinacao", "manejo_sanitario"):
                day = row.get("data_aplicacao") or row["data_manejo"]
                until = date.fromisoformat(day) + timedelta(days=row["carencia_dias"])
                row["carencia"] = (
                    f"Até {until.isoformat()}"
                    if row["carencia_dias"] and until >= date.today()
                    else "Sem carência ativa"
                )
        groups[entity] = rows
    labels = {r["id"]: r["identificacao"] for r in groups["animais"]}
    lots = {r["id"]: r["codigo_lote"] for r in groups["lotes"]}
    selected_lot = request.args.get("lote_id", "")
    selected_animal = request.args.get("animal_id", "")
    try:
        selected_lot = int(selected_lot) if selected_lot else None
        selected_animal = int(selected_animal) if selected_animal else None
    except ValueError:
        abort(400)
    if selected_lot is not None and selected_lot not in lots:
        abort(404)
    if selected_animal is not None and selected_animal not in labels:
        abort(404)
    if selected_lot is not None or selected_animal is not None:
        groups["animais"] = [
            r
            for r in groups["animais"]
            if (selected_lot is None or r["lote_id"] == selected_lot)
            and (selected_animal is None or r["id"] == selected_animal)
        ]
        animal_ids = {r["id"] for r in groups["animais"]}
        for entity in ("vacinacao", "manejo_sanitario"):
            groups[entity] = [r for r in groups[entity] if r["animal_id"] in animal_ids]
        if selected_lot is not None:
            groups["lotes"] = [r for r in groups["lotes"] if r["id"] == selected_lot]
    return render_template(
        "listagem.html",
        groups=groups,
        labels=labels,
        lots=lots,
        selected_lot=selected_lot,
        selected_animal=selected_animal,
    )


@web.route("/api/<entity>", methods=["GET", "POST"])
@login_required
def collection(entity):
    entity_info(entity)
    if request.method == "GET":
        return jsonify(
            [dict(r) for r in get_db().execute(f"SELECT * FROM {entity} ORDER BY id").fetchall()]
        )
    source = request.get_json(silent=True) if request.is_json else request.form
    if not isinstance(source, dict) and not hasattr(source, "get"):
        return jsonify(error="Envie um objeto com os campos do registro."), 400
    try:
        rid = save(entity, source)
        return jsonify(record(entity, rid)), 201
    except ValueError as exc:
        get_db().rollback()
        return jsonify(error=str(exc)), 400
    except integrity_errors():
        get_db().rollback()
        return jsonify(error="Identificação duplicada ou vínculo inválido."), 409


@web.route("/api/<entity>/<int:rid>", methods=["GET", "PUT", "DELETE"])
@login_required
def item(entity, rid):
    entity_info(entity)
    row = record(entity, rid)
    if request.method == "GET":
        return jsonify(row)
    if request.method == "DELETE" and current_user.perfil != "admin":
        abort(403)
    try:
        if request.method == "PUT":
            source = request.get_json(silent=True) if request.is_json else request.form
            if not hasattr(source, "get"):
                return jsonify(error="Envie um objeto com os campos do registro."), 400
            save(entity, source, rid)
        else:
            get_db().execute(f"DELETE FROM {entity} WHERE id = ?", (rid,))
            audit("EXCLUIR", f"{entity} ID {rid}")
            get_db().commit()
            return "", 204
    except ValueError as exc:
        get_db().rollback()
        return jsonify(error=str(exc)), 400
    except integrity_errors():
        get_db().rollback()
        return jsonify(
            error="Registro duplicado ou vinculado a outros registros. Remova ou altere os vínculos primeiro."
        ), 409
    return jsonify(record(entity, rid))


@web.get("/auditoria")
@admin_required
def logs():
    rows = get_db().execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 500").fetchall()
    return render_template("logs.html", rows=rows)
