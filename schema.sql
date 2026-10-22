-- Fonte única do modelo físico SQLite. PostgreSQL é gerado a partir deste DDL.
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS usuarios (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 username TEXT NOT NULL UNIQUE,
 senha TEXT NOT NULL,
 perfil TEXT NOT NULL CHECK (perfil IN ('admin', 'app_user'))
);
CREATE TABLE IF NOT EXISTS lotes (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 codigo_lote TEXT NOT NULL UNIQUE,
 quantidade_animais INTEGER NOT NULL CHECK (quantidade_animais >= 0),
 especie TEXT NOT NULL,
 data_formacao TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS animais (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 identificacao TEXT NOT NULL UNIQUE,
 especie TEXT NOT NULL,
 raca TEXT,
 sexo TEXT,
 data_nascimento TEXT,
 lote_id INTEGER REFERENCES lotes(id) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS vacinacao (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 animal_id INTEGER NOT NULL REFERENCES animais(id) ON DELETE RESTRICT,
 vacina TEXT NOT NULL,
 fabricante TEXT,
 lote_vacina TEXT,
 dose TEXT NOT NULL,
 data_aplicacao TEXT NOT NULL,
 proxima_dose TEXT,
 responsavel TEXT NOT NULL,
 observacoes TEXT,
 carencia_dias INTEGER NOT NULL DEFAULT 0 CHECK (carencia_dias >= 0),
 CHECK (proxima_dose IS NULL OR proxima_dose >= data_aplicacao)
);
CREATE TABLE IF NOT EXISTS manejo_sanitario (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 animal_id INTEGER NOT NULL REFERENCES animais(id) ON DELETE RESTRICT,
 tipo_manejo TEXT NOT NULL,
 data_manejo TEXT NOT NULL,
 produto TEXT,
 dose TEXT,
 responsavel TEXT NOT NULL,
 observacoes TEXT,
 carencia_dias INTEGER NOT NULL DEFAULT 0 CHECK (carencia_dias >= 0)
);
CREATE TABLE IF NOT EXISTS audit_log (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 acao TEXT NOT NULL,
 detalhes TEXT NOT NULL,
 usuario TEXT NOT NULL DEFAULT 'banco',
 data_hora TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- O contador é persistente e compartilhado pelos processos do servidor.
CREATE TABLE IF NOT EXISTS login_attempts (
 username TEXT PRIMARY KEY,
 tentativas INTEGER NOT NULL DEFAULT 0,
 bloqueado_ate DOUBLE PRECISION NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_animais_lote ON animais(lote_id);
CREATE INDEX IF NOT EXISTS idx_vacinacao_animal ON vacinacao(animal_id);
CREATE INDEX IF NOT EXISTS idx_vacinacao_prazo ON vacinacao(proxima_dose);
CREATE INDEX IF NOT EXISTS idx_manejo_animal ON manejo_sanitario(animal_id);
