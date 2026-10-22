"""Importação explícita e transacional; o arquivo recebido é aberto somente para leitura."""

import sqlite3
from datetime import date
from pathlib import Path

import click
from flask.cli import with_appcontext

from .db import get_db


@click.command("import-legacy")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@with_appcontext
def import_legacy(source):
    db = get_db()
    if (
        not db.postgres
        and source.resolve()
        == Path(db.conn.execute("PRAGMA database_list").fetchone()[2]).resolve()
    ):
        raise click.ClickException("Origem e destino devem ser bancos diferentes.")
    tables = ("lotes", "animais", "vacinacao", "manejo_sanitario")
    if any(db.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"] for t in tables):
        raise click.ClickException("O destino deve estar vazio de registros de negócio.")
    old = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
    old.row_factory = sqlite3.Row
    try:
        counts = {}
        for table in ("lotes", "animais", "vacinacao"):
            rows = [dict(r) for r in old.execute(f"SELECT * FROM {table} ORDER BY id")]
            counts[table] = len(rows)
            for r in rows:
                if table == "lotes":
                    if not r.get("data_formacao"):
                        raise ValueError(
                            f"Lote {r['id']} sem data de formação. Revise uma cópia da origem."
                        )
                    date.fromisoformat(r["data_formacao"])
                    data = dict(
                        id=r["id"],
                        codigo_lote=r.get("codigo_lote") or r.get("nome") or f"LEGADO-{r['id']}",
                        quantidade_animais=int(r.get("quantidade_animais") or 0),
                        especie=r.get("especie") or "Não informada (legado)",
                        data_formacao=r["data_formacao"],
                    )
                elif table == "animais":
                    if r.get("data_nascimento"):
                        date.fromisoformat(r["data_nascimento"])
                    data = dict(
                        id=r["id"],
                        identificacao=r.get("identificacao") or f"LEGADO-{r['id']}",
                        especie=r.get("especie") or "Não informada (legado)",
                        raca=r.get("raca"),
                        data_nascimento=r.get("data_nascimento") or None,
                    )
                else:
                    label = r.get("animal") or f"LEGADO-VAC-{r['id']}"
                    animal = db.execute(
                        "SELECT id FROM animais WHERE identificacao = ?", (label,)
                    ).fetchone()
                    if not animal:
                        animal = db.execute(
                            "INSERT INTO animais (identificacao, especie) VALUES (?, ?) RETURNING id",
                            (label, "Não informada (legado)"),
                        ).fetchone()
                    day = r.get("data_aplicacao") or r.get("data_vacinacao")
                    if not day:
                        raise ValueError(
                            f"Vacinação {r['id']} sem data; corrija a origem em uma cópia antes de importar."
                        )
                    date.fromisoformat(day)
                    if r.get("proxima_dose"):
                        date.fromisoformat(r["proxima_dose"])
                    data = dict(
                        id=r["id"],
                        animal_id=animal["id"],
                        vacina=r.get("vacina") or "Não informada (legado)",
                        data_aplicacao=day,
                        proxima_dose=r.get("proxima_dose") or None,
                        responsavel=r.get("responsavel") or "Não informado (legado)",
                        dose="Não informada (legado)",
                        observacoes=f"Importado do registro {r['id']}. Campos ausentes não foram recuperados.",
                    )
                columns = ", ".join(data)
                marks = ", ".join("?" for _ in data)
                db.execute(
                    f"INSERT INTO {table} ({columns}) VALUES ({marks})",
                    tuple(data.values()),
                )
            # Ajustar a sequência antes de criar animais referidos somente na vacinação.
            if db.postgres:
                db.execute(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {table}"
                )
        db.execute(
            "INSERT INTO audit_log (acao, detalhes, usuario) VALUES (?, ?, ?)",
            ("IMPORTACAO_LEGADO", str(counts), "CLI"),
        )
        db.commit()
        click.echo(
            f"Importação concluída: {counts}. Contas antigas não foram importadas; crie novas credenciais."
        )
    except Exception as exc:
        db.rollback()
        raise click.ClickException(f"Importação cancelada sem gravar alterações: {exc}") from exc
    finally:
        old.close()
