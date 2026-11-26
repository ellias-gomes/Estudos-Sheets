import os
import re
import time
import shutil
import sqlite3
import secrets
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.path.join(os.path.dirname(__file__), "study_hub.db")

DEFAULT_OWNER_EMAIL = os.getenv("DEFAULT_OWNER_EMAIL", "eu.elliasaugusto@gmail.com").strip().lower()
DEFAULT_OWNER_NAME = "Ellias Augusto"

ESCOPOS_VALIDOS = {"item", "modulo", "categoria"}
TIPOS_RECURSO_ITEM = {"anotacao", "tarefa", "curso", "midia", "flashcard", "habito"}
TIPOS_RECURSO_VALIDOS = TIPOS_RECURSO_ITEM | {"todos"}

TABELA_POR_TIPO = {
    "anotacao": ("anotacoes", "topico", "materia"),
    "tarefa": ("tarefas", "titulo", "categoria"),
    "curso": ("cursos", "nome", "categoria"),
    "midia": ("midias", "titulo", "categoria"),
    "flashcard": ("flashcards", "frente", "categoria"),
    "habito": ("habitos", "nome", None),
}

PRESETS_PERMISSAO = {
    "visualizar": (1, 0, 0, 0),
    "editar": (1, 1, 0, 0),
    "escrever": (1, 1, 1, 0),
    "admin": (1, 1, 1, 1),
}


def get_connection():
    """Retorna conexão SQLite configurada com Row factory e timeout seguro."""
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    return conn


def gerar_id_unico(prefixo: str) -> str:
    """Gera identificador único livre de colisões entre usuários."""
    return f"{prefixo}-{int(time.time() * 1000)}-{secrets.token_hex(3)}"


def seed_usuario_padrao(conn, user_id: int):
    """Popula categorias e hábitos iniciais para um usuário caso ainda não possua."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM categorias WHERE user_id = ?", (user_id,))
    if cursor.fetchone()[0] == 0:
        padrao = [
            "Engenharia de Computação (UNIVESP)",
            "DevOps / Cloud (Alura)",
            "Desenvolvimento de Software / Projetos",
            "Conhecimentos Gerais / Leituras",
            "Autoescola / DETRAN",
            "Atividade Física / Jiu-Jitsu",
            "Outros",
        ]
        for cat in padrao:
            cursor.execute(
                "INSERT OR IGNORE INTO categorias (user_id, nome) VALUES (?, ?)",
                (user_id, cat),
            )

    cursor.execute("SELECT COUNT(*) FROM habitos WHERE user_id = ?", (user_id,))
    if cursor.fetchone()[0] == 0:
        habitos_padrao = [
            (f"HAB-{user_id}-01", "Leitura Diária (20 pág.)", "fa-solid fa-book-open", "#f43f5e", 7),
            (f"HAB-{user_id}-02", "Sessão de Foco (Pomodoro)", "fa-solid fa-stopwatch", "#6366f1", 5),
            (f"HAB-{user_id}-03", "Revisar Flashcards", "fa-solid fa-layer-group", "#f59e0b", 5),
            (f"HAB-{user_id}-04", "Estudo / Programação", "fa-solid fa-laptop-code", "#10b981", 5),
            (f"HAB-{user_id}-05", "Atividade Física / Jiu-Jitsu", "fa-solid fa-dumbbell", "#0ea5e9", 4),
        ]
        for hid, hnome, hicone, hcor, hmeta in habitos_padrao:
            cursor.execute(
                """
                INSERT OR IGNORE INTO habitos (id, user_id, nome, icone, cor, meta_semanal)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (hid, user_id, hnome, hicone, hcor, hmeta),
            )


def _garantir_owner_migracao(cursor, has_legacy_data_tables: bool) -> int:
    """Garante a existência da conta administradora padrão e retorna seu ID."""
    cursor.execute("SELECT id FROM usuarios WHERE email = ?", (DEFAULT_OWNER_EMAIL,))
    row = cursor.fetchone()
    if row:
        return int(row[0])

    cursor.execute("SELECT COUNT(*) FROM usuarios")
    total_usuarios = cursor.fetchone()[0]
    if has_legacy_data_tables or total_usuarios == 0:
        agora_iso = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """
            INSERT INTO usuarios (email, nome, senha_hash, precisa_definir_senha, is_admin, criado_em)
            VALUES (?, ?, '', 1, 1, ?)
            """,
            (DEFAULT_OWNER_EMAIL, DEFAULT_OWNER_NAME, agora_iso),
        )
        return int(cursor.lastrowid)

    cursor.execute("SELECT id FROM usuarios ORDER BY is_admin DESC, id ASC LIMIT 1")
    fallback = cursor.fetchone()
    return int(fallback[0]) if fallback else 1


def _colunas_tabela(cursor, tabela: str) -> set:
    cursor.execute(f"PRAGMA table_info({tabela})")
    return {r[1] for r in cursor.fetchall()}


def init_db():
    """Inicializa o banco SQLite e executa migração idempotente com backup para multi-usuário."""
    has_legacy_data_tables = False
    if os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 0:
        tmp_conn = get_connection()
        tmp_cur = tmp_conn.cursor()
        tmp_cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {r[0] for r in tmp_cur.fetchall()}
        tmp_conn.close()

        legacy_data_tables = {
            "anotacoes", "tarefas", "cursos", "flashcards",
            "pomodoro", "midias", "habitos", "categorias", "config",
        }
        has_legacy_data_tables = bool(existing_tables & legacy_data_tables)
        if has_legacy_data_tables and "usuarios" not in existing_tables:
            bak_path = f"{DB_PATH}.pre_multiuser.bak"
            if not os.path.exists(bak_path):
                shutil.copy2(DB_PATH, bak_path)

    conn = get_connection()
    cursor = conn.cursor()

    # Tabelas de Autenticação, Sessões e Compartilhamento
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        nome TEXT NOT NULL,
        senha_hash TEXT DEFAULT '',
        precisa_definir_senha INTEGER DEFAULT 0,
        is_admin INTEGER DEFAULT 0,
        criado_em TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessoes (
        token_hash TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        criado_em TEXT NOT NULL,
        expira_em TEXT NOT NULL,
        user_agent TEXT DEFAULT ''
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS compartilhamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_user_id INTEGER NOT NULL,
        target_user_id INTEGER NOT NULL,
        escopo TEXT NOT NULL,
        recurso_tipo TEXT NOT NULL,
        recurso_id TEXT NOT NULL DEFAULT '',
        nivel TEXT NOT NULL,
        pode_visualizar INTEGER NOT NULL DEFAULT 1,
        pode_editar INTEGER NOT NULL DEFAULT 0,
        pode_criar INTEGER NOT NULL DEFAULT 0,
        pode_excluir INTEGER NOT NULL DEFAULT 0,
        criado_em TEXT NOT NULL,
        UNIQUE(owner_user_id, target_user_id, escopo, recurso_tipo, recurso_id)
    )
    """)

    # Tabelas de Domínio (para bancos novos já nascem com user_id)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS config (
        user_id INTEGER NOT NULL,
        chave TEXT NOT NULL,
        valor TEXT,
        PRIMARY KEY (user_id, chave)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS categorias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        nome TEXT NOT NULL,
        UNIQUE(user_id, nome)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS subcategorias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        categoria TEXT NOT NULL,
        nome TEXT NOT NULL,
        UNIQUE(user_id, categoria, nome)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS anotacoes (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL DEFAULT 1,
        data TEXT,
        materia TEXT,
        subcategoria TEXT DEFAULT '',
        topico TEXT,
        conteudo TEXT,
        tags TEXT,
        link TEXT,
        anexo_nome TEXT,
        anexo_url TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tarefas (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL DEFAULT 1,
        data_criacao TEXT,
        titulo TEXT,
        categoria TEXT,
        status TEXT,
        prazo TEXT,
        prioridade TEXT,
        descricao TEXT,
        anexo_nome TEXT,
        anexo_url TEXT,
        eisenhower TEXT DEFAULT ''
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cursos (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL DEFAULT 1,
        nome TEXT,
        instituicao TEXT,
        categoria TEXT,
        carga_horaria TEXT,
        status TEXT,
        link TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS flashcards (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL DEFAULT 1,
        categoria TEXT,
        frente TEXT,
        verso TEXT,
        nivel TEXT DEFAULT 'Novo',
        ultima_revisao TEXT DEFAULT 'Nunca'
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pomodoro (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL DEFAULT 1,
        data TEXT,
        categoria TEXT,
        minutos INTEGER DEFAULT 25
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS midias (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL DEFAULT 1,
        tipo TEXT,
        titulo TEXT,
        autor_diretor TEXT,
        ano TEXT,
        categoria TEXT,
        status TEXT DEFAULT 'Quero Ler/Ver',
        nota INTEGER DEFAULT 0,
        capa_url TEXT,
        link TEXT,
        resenha TEXT,
        citacoes TEXT,
        data_criacao TEXT,
        data_conclusao TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS habitos (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL DEFAULT 1,
        nome TEXT NOT NULL,
        icone TEXT DEFAULT 'fa-solid fa-fire',
        cor TEXT DEFAULT '#10b981',
        meta_semanal INTEGER DEFAULT 7
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS habitos_registros (
        habito_id TEXT NOT NULL,
        data TEXT NOT NULL,
        user_id INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY (habito_id, data)
    )
    """)

    # Garante o usuário dono padrão antes de migrar os registros legados
    owner_id = _garantir_owner_migracao(cursor, has_legacy_data_tables)

    # Migrações de colunas opcionais antigas
    anot_cols = _colunas_tabela(cursor, "anotacoes")
    if "subcategoria" not in anot_cols:
        cursor.execute("ALTER TABLE anotacoes ADD COLUMN subcategoria TEXT DEFAULT ''")

    tar_cols = _colunas_tabela(cursor, "tarefas")
    if "eisenhower" not in tar_cols:
        cursor.execute("ALTER TABLE tarefas ADD COLUMN eisenhower TEXT DEFAULT ''")

    # Reconstrução de tabelas com restrições UNIQUE/PRIMARY KEY globais para escopo por user_id
    if "user_id" not in _colunas_tabela(cursor, "config"):
        cursor.execute("""
        CREATE TABLE config_new (
            user_id INTEGER NOT NULL,
            chave TEXT NOT NULL,
            valor TEXT,
            PRIMARY KEY (user_id, chave)
        )
        """)
        cursor.execute(
            "INSERT OR IGNORE INTO config_new (user_id, chave, valor) SELECT ?, chave, valor FROM config",
            (owner_id,),
        )
        cursor.execute("DROP TABLE config")
        cursor.execute("ALTER TABLE config_new RENAME TO config")

    if "user_id" not in _colunas_tabela(cursor, "categorias"):
        cursor.execute("""
        CREATE TABLE categorias_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            UNIQUE(user_id, nome)
        )
        """)
        cursor.execute(
            "INSERT OR IGNORE INTO categorias_new (id, user_id, nome) SELECT id, ?, nome FROM categorias",
            (owner_id,),
        )
        cursor.execute("DROP TABLE categorias")
        cursor.execute("ALTER TABLE categorias_new RENAME TO categorias")

    if "user_id" not in _colunas_tabela(cursor, "subcategorias"):
        cursor.execute("""
        CREATE TABLE subcategorias_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            categoria TEXT NOT NULL,
            nome TEXT NOT NULL,
            UNIQUE(user_id, categoria, nome)
        )
        """)
        cursor.execute(
            "INSERT OR IGNORE INTO subcategorias_new (id, user_id, categoria, nome) SELECT id, ?, categoria, nome FROM subcategorias",
            (owner_id,),
        )
        cursor.execute("DROP TABLE subcategorias")
        cursor.execute("ALTER TABLE subcategorias_new RENAME TO subcategorias")

    # Adição de user_id às demais tabelas de dados legadas e vinculação ao owner_id
    for tabela in ["anotacoes", "tarefas", "cursos", "flashcards", "pomodoro", "midias", "habitos"]:
        if "user_id" not in _colunas_tabela(cursor, tabela):
            cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN user_id INTEGER")
        cursor.execute(f"UPDATE {tabela} SET user_id = ? WHERE user_id IS NULL", (owner_id,))

    if "user_id" not in _colunas_tabela(cursor, "habitos_registros"):
        cursor.execute("ALTER TABLE habitos_registros ADD COLUMN user_id INTEGER")
    cursor.execute(
        """
        UPDATE habitos_registros
        SET user_id = COALESCE(
            (SELECT h.user_id FROM habitos h WHERE h.id = habitos_registros.habito_id),
            ?
        )
        WHERE user_id IS NULL
        """,
        (owner_id,),
    )

    # Índices para performance das consultas multi-usuário
    for tabela in [
        "config", "categorias", "subcategorias", "anotacoes", "tarefas",
        "cursos", "flashcards", "pomodoro", "midias", "habitos", "habitos_registros",
    ]:
        cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{tabela}_user_id ON {tabela}(user_id)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_compart_target ON compartilhamentos(target_user_id, escopo, recurso_tipo)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_compart_owner ON compartilhamentos(owner_user_id)"
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessoes_user ON sessoes(user_id)")

    # Popula dados iniciais do dono caso seja banco novo vazio
    seed_usuario_padrao(conn, owner_id)

    conn.commit()
    conn.close()


# ================= MOTOR DE PERMISSÕES E COMPARTILHAMENTO =================

def _classificar_nivel(pode_editar: int, pode_criar: int, pode_excluir: int) -> str:
    tup = (1, int(bool(pode_editar)), int(bool(pode_criar)), int(bool(pode_excluir)))
    for nome, preset in PRESETS_PERMISSAO.items():
        if tup == preset:
            return nome
    return "personalizado"


def resolver_flags_permissao(
    nivel: str = "visualizar",
    pode_editar=None,
    pode_criar=None,
    pode_excluir=None,
):
    """Resolve o nível e as 4 flags de permissão garantindo sempre pode_visualizar=1."""
    nivel_norm = (nivel or "visualizar").strip().lower()
    base = PRESETS_PERMISSAO.get(nivel_norm, (1, 0, 0, 0))

    if nivel_norm in PRESETS_PERMISSAO and pode_editar is None and pode_criar is None and pode_excluir is None:
        return nivel_norm, base[0], base[1], base[2], base[3]

    ed = int(bool(pode_editar)) if pode_editar is not None else base[1]
    cr = int(bool(pode_criar)) if pode_criar is not None else base[2]
    ex = int(bool(pode_excluir)) if pode_excluir is not None else base[3]
    nivel_final = _classificar_nivel(ed, cr, ex)
    return nivel_final, 1, ed, cr, ex


def _avaliar_permissoes_shares(shares_do_owner: list, user_id: int, owner_id: int, tipo: str, recurso_id: str, categoria: str = ""):
    if int(user_id) == int(owner_id):
        return {
            "isOwner": True,
            "nivel": "dono",
            "podeVisualizar": True,
            "podeEditar": True,
            "podeCriar": True,
            "podeExcluir": True,
        }

    cat_limpa = (categoria or "").strip()
    aplicaveis = []
    for s in shares_do_owner:
        escopo = s["escopo"]
        rtipo = s["recurso_tipo"]
        rid = s["recurso_id"] or ""
        if escopo == "item" and rtipo == tipo and rid == recurso_id:
            aplicaveis.append(s)
        elif escopo == "modulo" and rtipo in (tipo, "todos"):
            aplicaveis.append(s)
        elif escopo == "categoria" and rtipo in (tipo, "todos") and cat_limpa and rid == cat_limpa:
            aplicaveis.append(s)

    if not aplicaveis:
        return None

    vis = any(bool(r["pode_visualizar"]) for r in aplicaveis)
    if not vis:
        return None

    ed = any(bool(r["pode_editar"]) for r in aplicaveis)
    cr = any(bool(r["pode_criar"]) for r in aplicaveis)
    ex = any(bool(r["pode_excluir"]) for r in aplicaveis)
    return {
        "isOwner": False,
        "nivel": _classificar_nivel(ed, cr, ex),
        "podeVisualizar": True,
        "podeEditar": ed,
        "podeCriar": cr,
        "podeExcluir": ex,
    }


def obter_permissoes_recurso(conn, user_id: int, owner_id: int, tipo: str, recurso_id: str, categoria: str = ""):
    """Retorna o mapa efetivo de permissões do usuário sobre um recurso de owner_id, ou None."""
    if int(user_id) == int(owner_id):
        return {
            "isOwner": True,
            "nivel": "dono",
            "podeVisualizar": True,
            "podeEditar": True,
            "podeCriar": True,
            "podeExcluir": True,
        }

    cursor = conn.cursor()
    cat_limpa = (categoria or "").strip()
    if cat_limpa:
        cursor.execute(
            """
            SELECT * FROM compartilhamentos
            WHERE owner_user_id = ? AND target_user_id = ?
              AND (
                (escopo = 'item' AND recurso_tipo = ? AND recurso_id = ?)
                OR (escopo = 'modulo' AND recurso_tipo IN (?, 'todos'))
                OR (escopo = 'categoria' AND recurso_tipo IN (?, 'todos') AND recurso_id = ?)
              )
            """,
            (owner_id, user_id, tipo, recurso_id, tipo, tipo, cat_limpa),
        )
    else:
        cursor.execute(
            """
            SELECT * FROM compartilhamentos
            WHERE owner_user_id = ? AND target_user_id = ?
              AND (
                (escopo = 'item' AND recurso_tipo = ? AND recurso_id = ?)
                OR (escopo = 'modulo' AND recurso_tipo IN (?, 'todos'))
              )
            """,
            (owner_id, user_id, tipo, recurso_id, tipo),
        )
    rows = cursor.fetchall()
    return _avaliar_permissoes_shares(rows, user_id, owner_id, tipo, recurso_id, cat_limpa)


def pode_criar_no_espaco(conn, user_id: int, owner_id: int, tipo: str, categoria: str = "") -> bool:
    """Verifica se user_id possui permissão de escrita (criar itens) no espaço de owner_id."""
    if int(user_id) == int(owner_id):
        return True
    cursor = conn.cursor()
    cat_limpa = (categoria or "").strip()
    if cat_limpa:
        cursor.execute(
            """
            SELECT 1 FROM compartilhamentos
            WHERE owner_user_id = ? AND target_user_id = ? AND pode_visualizar = 1 AND pode_criar = 1
              AND (
                (escopo = 'modulo' AND recurso_tipo IN (?, 'todos'))
                OR (escopo = 'categoria' AND recurso_tipo IN (?, 'todos') AND recurso_id = ?)
              )
            LIMIT 1
            """,
            (owner_id, user_id, tipo, tipo, cat_limpa),
        )
    else:
        cursor.execute(
            """
            SELECT 1 FROM compartilhamentos
            WHERE owner_user_id = ? AND target_user_id = ? AND pode_visualizar = 1 AND pode_criar = 1
              AND escopo = 'modulo' AND recurso_tipo IN (?, 'todos')
            LIMIT 1
            """,
            (owner_id, user_id, tipo),
        )
    return cursor.fetchone() is not None


def carregar_usuarios_mapa(conn, user_ids) -> dict:
    """Retorna dicionário {user_id: {'id', 'nome', 'email'}} para os IDs informados."""
    ids = sorted({int(uid) for uid in user_ids if uid is not None})
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT id, nome, email FROM usuarios WHERE id IN ({placeholders})",
        ids,
    )
    return {
        int(r["id"]): {"id": int(r["id"]), "nome": r["nome"], "email": r["email"]}
        for r in cursor.fetchall()
    }


def contar_compartilhamentos_enviados(conn, owner_user_id: int, tipo: str) -> dict:
    """Conta com quantos destinatários distintos cada item do dono foi compartilhado."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT recurso_id, COUNT(DISTINCT target_user_id) AS total
        FROM compartilhamentos
        WHERE owner_user_id = ? AND escopo = 'item' AND recurso_tipo = ?
        GROUP BY recurso_id
        """,
        (owner_user_id, tipo),
    )
    return {r["recurso_id"]: int(r["total"]) for r in cursor.fetchall()}


def obter_itens_acessiveis(conn, user_id: int, tipo: str, extra_where: str = "", extra_params: tuple = ()):
    """Retorna todos os registros próprios e compartilhados acessíveis a user_id para um tipo."""
    tabela, _, cat_col = TABELA_POR_TIPO[tipo]
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM compartilhamentos
        WHERE target_user_id = ? AND pode_visualizar = 1
          AND (recurso_tipo = ? OR recurso_tipo = 'todos')
        """,
        (user_id, tipo),
    )
    shares_recebidos = cursor.fetchall()

    shares_por_owner = {}
    for s in shares_recebidos:
        oid = int(s["owner_user_id"])
        shares_por_owner.setdefault(oid, []).append(s)

    owners_consulta = [int(user_id)] + [oid for oid in shares_por_owner.keys() if oid != int(user_id)]
    placeholders = ",".join("?" for _ in owners_consulta)
    where_sql = f"user_id IN ({placeholders})"
    params = list(owners_consulta)
    if extra_where:
        where_sql += f" AND ({extra_where})"
        params.extend(extra_params)

    order_sql = "rowid ASC" if tipo == "habito" else "rowid DESC"
    cursor.execute(f"SELECT * FROM {tabela} WHERE {where_sql} ORDER BY {order_sql}", params)
    candidatos = cursor.fetchall()

    usuarios_map = carregar_usuarios_mapa(conn, {int(r["user_id"]) for r in candidatos} | {int(user_id)})
    shared_counts = contar_compartilhamentos_enviados(conn, user_id, tipo)

    itens = []
    for row in candidatos:
        oid = int(row["user_id"])
        cat_val = (row[cat_col] or "") if cat_col else ""
        perms = _avaliar_permissoes_shares(
            shares_por_owner.get(oid, []),
            user_id,
            oid,
            tipo,
            row["id"],
            cat_val,
        )
        if not perms:
            continue
        owner_info = usuarios_map.get(oid, {"id": oid, "nome": "Usuário", "email": ""})
        count_item = shared_counts.get(row["id"], 0) if oid == int(user_id) else 0
        itens.append((row, perms, owner_info, count_item))

    return itens


def remover_compartilhamentos_do_item(conn, owner_user_id: int, recurso_tipo: str, recurso_id: str):
    """Remove vínculos de compartilhamento de item quando o registro original é excluído."""
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM compartilhamentos
        WHERE owner_user_id = ? AND escopo = 'item' AND recurso_tipo = ? AND recurso_id = ?
        """,
        (owner_user_id, recurso_tipo, recurso_id),
    )


def buscar_usuarios_compartilhamento_db(current_user_id: int, termo: str = "") -> list:
    """Lista outros usuários cadastrados (por nome/e-mail) para autocompletar no compartilhamento."""
    conn = get_connection()
    cursor = conn.cursor()
    q = f"%{(termo or '').strip().lower()}%"
    cursor.execute(
        """
        SELECT id, nome, email
        FROM usuarios
        WHERE id != ? AND (LOWER(email) LIKE ? OR LOWER(nome) LIKE ?)
        ORDER BY nome ASC
        LIMIT 20
        """,
        (current_user_id, q, q),
    )
    rows = [{"id": int(r["id"]), "nome": r["nome"], "email": r["email"]} for r in cursor.fetchall()]
    conn.close()
    return rows


def salvar_compartilhamento_db(owner_user_id: int, dados: dict) -> dict:
    """Cria ou atualiza um compartilhamento de item, categoria ou módulo."""
    escopo = (dados.get("escopo") or "").strip().lower()
    recurso_tipo = (dados.get("recursoTipo") or "").strip().lower()
    recurso_id = (dados.get("recursoId") or "").strip()

    if escopo not in ESCOPOS_VALIDOS:
        return {"success": False, "message": "Escopo de compartilhamento inválido."}
    if recurso_tipo not in TIPOS_RECURSO_VALIDOS:
        return {"success": False, "message": "Tipo de recurso inválido."}
    if escopo == "item" and recurso_tipo not in TIPOS_RECURSO_ITEM:
        return {"success": False, "message": "Compartilhamento de item exige um tipo de item específico."}
    if escopo == "item" and not recurso_id:
        return {"success": False, "message": "ID do item não informado."}
    if escopo == "categoria":
        if recurso_tipo == "habito":
            return {"success": False, "message": "Hábitos não possuem categoria; compartilhe o módulo ou o hábito específico."}
        if not recurso_id:
            return {"success": False, "message": "Selecione uma categoria para compartilhar."}
    if escopo == "modulo":
        recurso_id = ""

    conn = get_connection()
    cursor = conn.cursor()

    if escopo == "item":
        tabela, _, _ = TABELA_POR_TIPO[recurso_tipo]
        cursor.execute(f"SELECT user_id FROM {tabela} WHERE id = ?", (recurso_id,))
        item_row = cursor.fetchone()
        if not item_row:
            conn.close()
            return {"success": False, "message": "Item não encontrado para compartilhamento."}
        if int(item_row["user_id"]) != int(owner_user_id):
            conn.close()
            return {
                "success": False,
                "forbidden": True,
                "message": "Você só pode compartilhar itens que pertencem à sua conta.",
            }

    target_id = dados.get("targetUserId")
    email_dest = (dados.get("emailDestinatario") or dados.get("targetEmail") or "").strip().lower()
    if target_id:
        cursor.execute("SELECT id, email, nome FROM usuarios WHERE id = ?", (int(target_id),))
    else:
        if not email_dest:
            conn.close()
            return {"success": False, "message": "Informe o e-mail do usuário destinatário."}
        cursor.execute("SELECT id, email, nome FROM usuarios WHERE email = ?", (email_dest,))
    dest_row = cursor.fetchone()
    if not dest_row:
        conn.close()
        return {"success": False, "message": f"Nenhum usuário encontrado com o e-mail '{email_dest}'."}

    dest_user_id = int(dest_row["id"])
    if dest_user_id == int(owner_user_id):
        conn.close()
        return {"success": False, "message": "Você não pode compartilhar recursos consigo mesmo."}

    nivel, vis, ed, cr, ex = resolver_flags_permissao(
        dados.get("nivel", "visualizar"),
        dados.get("podeEditar"),
        dados.get("podeCriar"),
        dados.get("podeExcluir"),
    )
    agora_iso = datetime.now(timezone.utc).isoformat()

    cursor.execute(
        """
        INSERT INTO compartilhamentos (
            owner_user_id, target_user_id, escopo, recurso_tipo, recurso_id,
            nivel, pode_visualizar, pode_editar, pode_criar, pode_excluir, criado_em
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(owner_user_id, target_user_id, escopo, recurso_tipo, recurso_id)
        DO UPDATE SET
            nivel = excluded.nivel,
            pode_visualizar = excluded.pode_visualizar,
            pode_editar = excluded.pode_editar,
            pode_criar = excluded.pode_criar,
            pode_excluir = excluded.pode_excluir
        """,
        (owner_user_id, dest_user_id, escopo, recurso_tipo, recurso_id, nivel, vis, ed, cr, ex, agora_iso),
    )
    cursor.execute(
        """
        SELECT id FROM compartilhamentos
        WHERE owner_user_id = ? AND target_user_id = ? AND escopo = ? AND recurso_tipo = ? AND recurso_id = ?
        """,
        (owner_user_id, dest_user_id, escopo, recurso_tipo, recurso_id),
    )
    share_id = int(cursor.fetchone()["id"])
    conn.commit()
    conn.close()
    return {
        "success": True,
        "id": share_id,
        "message": f"Compartilhado com {dest_row['nome']} ({dest_row['email']})!",
    }


def _resolver_titulos_itens(conn, share_rows: list) -> dict:
    titulos = {}
    agrupado = {}
    for s in share_rows:
        if s["escopo"] == "item" and s["recurso_tipo"] in TABELA_POR_TIPO and s["recurso_id"]:
            agrupado.setdefault(s["recurso_tipo"], set()).add(s["recurso_id"])

    cursor = conn.cursor()
    for rtipo, rids in agrupado.items():
        tabela, title_col, _ = TABELA_POR_TIPO[rtipo]
        ids_list = list(rids)
        placeholders = ",".join("?" for _ in ids_list)
        cursor.execute(
            f"SELECT id, {title_col} AS titulo FROM {tabela} WHERE id IN ({placeholders})",
            ids_list,
        )
        for r in cursor.fetchall():
            titulos[(rtipo, r["id"])] = r["titulo"] or r["id"]
    return titulos


def _formatar_compartilhamento_row(row, usuarios_map: dict, titulos_map: dict) -> dict:
    oid = int(row["owner_user_id"])
    tid = int(row["target_user_id"])
    owner = usuarios_map.get(oid, {"nome": "Usuário", "email": ""})
    target = usuarios_map.get(tid, {"nome": "Usuário", "email": ""})

    if row["escopo"] == "item":
        recurso_titulo = titulos_map.get((row["recurso_tipo"], row["recurso_id"]), row["recurso_id"])
    elif row["escopo"] == "categoria":
        recurso_titulo = row["recurso_id"]
    else:
        recurso_titulo = "Módulo Completo"

    return {
        "id": int(row["id"]),
        "ownerId": oid,
        "ownerNome": owner["nome"],
        "ownerEmail": owner["email"],
        "targetUserId": tid,
        "targetNome": target["nome"],
        "targetEmail": target["email"],
        "escopo": row["escopo"],
        "recursoTipo": row["recurso_tipo"],
        "recursoId": row["recurso_id"] or "",
        "recursoTitulo": recurso_titulo,
        "nivel": row["nivel"],
        "podeVisualizar": bool(row["pode_visualizar"]),
        "podeEditar": bool(row["pode_editar"]),
        "podeCriar": bool(row["pode_criar"]),
        "podeExcluir": bool(row["pode_excluir"]),
        "criadoEm": row["criado_em"],
    }


def obter_espacos_escrita_db(user_id: int, conn=None) -> list:
    """Lista espaços compartilhados de outros usuários nos quais user_id pode criar novos itens."""
    fechar_conn = conn is None
    if conn is None:
        conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT c.*, u.nome AS owner_nome, u.email AS owner_email
        FROM compartilhamentos c
        JOIN usuarios u ON u.id = c.owner_user_id
        WHERE c.target_user_id = ?
          AND c.pode_visualizar = 1
          AND c.pode_criar = 1
          AND c.escopo IN ('modulo', 'categoria')
        ORDER BY u.nome ASC, c.escopo ASC, c.recurso_id ASC
        """,
        (user_id,),
    )
    resultado = [
        {
            "id": int(r["id"]),
            "ownerId": int(r["owner_user_id"]),
            "ownerNome": r["owner_nome"],
            "ownerEmail": r["owner_email"],
            "escopo": r["escopo"],
            "recursoTipo": r["recurso_tipo"],
            "recursoId": r["recurso_id"] or "",
            "nivel": r["nivel"],
        }
        for r in cursor.fetchall()
    ]
    if fechar_conn:
        conn.close()
    return resultado


def listar_compartilhamentos_db(user_id: int, filtro: dict = None):
    """Lista compartilhamentos enviados/recebidos pelo usuário ou acessos de um item específico."""
    conn = get_connection()
    cursor = conn.cursor()

    if filtro and isinstance(filtro, dict) and filtro.get("recursoId") and filtro.get("recursoTipo"):
        escopo = (filtro.get("escopo") or "item").strip().lower()
        rtipo = (filtro.get("recursoTipo") or "").strip().lower()
        rid = (filtro.get("recursoId") or "").strip()
        cursor.execute(
            """
            SELECT * FROM compartilhamentos
            WHERE owner_user_id = ? AND escopo = ? AND recurso_tipo = ? AND recurso_id = ?
            ORDER BY id DESC
            """,
            (user_id, escopo, rtipo, rid),
        )
        rows = cursor.fetchall()
        user_ids = {int(r["owner_user_id"]) for r in rows} | {int(r["target_user_id"]) for r in rows}
        usuarios_map = carregar_usuarios_mapa(conn, user_ids)
        titulos_map = _resolver_titulos_itens(conn, rows)
        lista = [_formatar_compartilhamento_row(r, usuarios_map, titulos_map) for r in rows]
        conn.close()
        return lista

    cursor.execute(
        """
        SELECT * FROM compartilhamentos
        WHERE owner_user_id = ? OR target_user_id = ?
        ORDER BY id DESC
        """,
        (user_id, user_id),
    )
    todos = cursor.fetchall()
    user_ids = {int(r["owner_user_id"]) for r in todos} | {int(r["target_user_id"]) for r in todos}
    usuarios_map = carregar_usuarios_mapa(conn, user_ids)
    titulos_map = _resolver_titulos_itens(conn, todos)

    enviados = []
    recebidos = []
    for r in todos:
        item_fmt = _formatar_compartilhamento_row(r, usuarios_map, titulos_map)
        if int(r["owner_user_id"]) == int(user_id):
            enviados.append(item_fmt)
        if int(r["target_user_id"]) == int(user_id):
            recebidos.append(item_fmt)

    espacos_escrita = obter_espacos_escrita_db(user_id, conn=conn)
    conn.close()
    return {
        "enviados": enviados,
        "recebidos": recebidos,
        "espacosEscrita": espacos_escrita,
    }


def atualizar_compartilhamento_db(owner_user_id: int, share_id: int, dados: dict) -> dict:
    """Atualiza o nível ou as permissões granulares de um compartilhamento existente."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM compartilhamentos WHERE id = ?", (int(share_id),))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"success": False, "message": "Compartilhamento não encontrado."}
    if int(row["owner_user_id"]) != int(owner_user_id):
        conn.close()
        return {
            "success": False,
            "forbidden": True,
            "message": "Apenas o dono pode alterar as permissões deste compartilhamento.",
        }

    nivel, vis, ed, cr, ex = resolver_flags_permissao(
        dados.get("nivel", row["nivel"]),
        dados.get("podeEditar"),
        dados.get("podeCriar"),
        dados.get("podeExcluir"),
    )
    cursor.execute(
        """
        UPDATE compartilhamentos
        SET nivel = ?, pode_visualizar = ?, pode_editar = ?, pode_criar = ?, pode_excluir = ?
        WHERE id = ?
        """,
        (nivel, vis, ed, cr, ex, int(share_id)),
    )
    conn.commit()
    conn.close()
    return {"success": True, "message": "Permissões atualizadas com sucesso!"}


def revogar_compartilhamento_db(user_id: int, share_id: int) -> dict:
    """Remove um compartilhamento (permitido tanto para o dono quanto para o destinatário sair)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM compartilhamentos WHERE id = ?", (int(share_id),))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"success": False, "message": "Compartilhamento não encontrado."}
    if int(row["owner_user_id"]) != int(user_id) and int(row["target_user_id"]) != int(user_id):
        conn.close()
        return {"success": False, "forbidden": True, "message": "Sem permissão para revogar este compartilhamento."}

    cursor.execute("DELETE FROM compartilhamentos WHERE id = ?", (int(share_id),))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Compartilhamento removido com sucesso!"}


def obter_categorias_dono_db(current_user_id: int, owner_id: int) -> dict:
    """Retorna categorias e subcategorias de um dono quando houver acesso ou compartilhamento."""
    conn = get_connection()
    cursor = conn.cursor()
    if int(current_user_id) != int(owner_id):
        cursor.execute(
            """
            SELECT 1 FROM compartilhamentos
            WHERE owner_user_id = ? AND target_user_id = ? AND pode_visualizar = 1
            LIMIT 1
            """,
            (int(owner_id), int(current_user_id)),
        )
        if not cursor.fetchone():
            conn.close()
            return {"success": False, "forbidden": True, "categorias": [], "subcategorias": []}

    cursor.execute("SELECT nome FROM categorias WHERE user_id = ? ORDER BY id ASC", (int(owner_id),))
    categorias = [r[0] for r in cursor.fetchall()]

    cursor.execute(
        "SELECT id, categoria, nome FROM subcategorias WHERE user_id = ? ORDER BY categoria ASC, nome ASC",
        (int(owner_id),),
    )
    subcategorias = [
        {"id": r["id"], "categoria": r["categoria"], "nome": r["nome"]}
        for r in cursor.fetchall()
    ]
    conn.close()
    return {"success": True, "categorias": categorias, "subcategorias": subcategorias}


# ================= HELPERS POR USUÁRIO =================

def get_config(user_id: int, chave: str, default=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT valor FROM config WHERE user_id = ? AND chave = ?", (user_id, chave))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default


def set_config(user_id: int, chave: str, valor: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO config (user_id, chave, valor) VALUES (?, ?, ?)",
        (user_id, chave, valor),
    )
    conn.commit()
    conn.close()


def get_todas_categorias(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT nome FROM categorias WHERE user_id = ? ORDER BY id ASC", (user_id,))
    rows = [r[0] for r in cursor.fetchall()]
    conn.close()
    return rows


def adicionar_categoria(user_id: int, nome: str):
    if not nome or not nome.strip():
        return False, "Nome inválido."
    nome = nome.strip()
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO categorias (user_id, nome) VALUES (?, ?)", (user_id, nome))
        conn.commit()
        return True, "Categoria criada com sucesso!"
    except sqlite3.IntegrityError:
        return False, "Esta categoria já existe!"
    finally:
        conn.close()


def get_todas_subcategorias(user_id: int, categoria: str = None):
    """Retorna subcategorias cadastradas do usuário, filtradas por categoria se informada."""
    conn = get_connection()
    cursor = conn.cursor()
    if categoria and str(categoria).strip():
        cursor.execute(
            "SELECT id, categoria, nome FROM subcategorias WHERE user_id = ? AND categoria = ? ORDER BY nome ASC",
            (user_id, str(categoria).strip()),
        )
    else:
        cursor.execute(
            "SELECT id, categoria, nome FROM subcategorias WHERE user_id = ? ORDER BY categoria ASC, nome ASC",
            (user_id,),
        )
    rows = [{"id": r["id"], "categoria": r["categoria"], "nome": r["nome"]} for r in cursor.fetchall()]
    conn.close()
    return rows


def adicionar_subcategoria(user_id: int, categoria: str, nome: str):
    """Cria uma nova subcategoria vinculada a uma categoria do usuário."""
    cat = (categoria or "").strip()
    sub = (nome or "").strip()
    if not cat:
        return False, "Categoria inválida."
    if not sub:
        return False, "Nome de subcategoria inválido."
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO subcategorias (user_id, categoria, nome) VALUES (?, ?, ?)",
            (user_id, cat, sub),
        )
        conn.commit()
        return True, "Subcategoria criada com sucesso!"
    except sqlite3.IntegrityError:
        return False, "Esta subcategoria já existe nesta categoria!"
    finally:
        conn.close()


def excluir_subcategoria(user_id: int, sub_id: int):
    """Remove uma subcategoria do usuário e limpa seu vínculo nas anotações existentes."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT categoria, nome FROM subcategorias WHERE id = ? AND user_id = ?",
        (sub_id, user_id),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, "Subcategoria não encontrada."
    cat, nome = row["categoria"], row["nome"]
    cursor.execute(
        "UPDATE anotacoes SET subcategoria = '' WHERE user_id = ? AND materia = ? AND subcategoria = ?",
        (user_id, cat, nome),
    )
    cursor.execute("DELETE FROM subcategorias WHERE id = ? AND user_id = ?", (sub_id, user_id))
    conn.commit()
    conn.close()
    return True, "Subcategoria removida com sucesso!"


def get_dashboard(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM anotacoes WHERE user_id = ?", (user_id,))
    total_anotacoes = cursor.fetchone()[0]

    cursor.execute(
        "SELECT status, categoria, COUNT(*) FROM tarefas WHERE user_id = ? GROUP BY status, categoria",
        (user_id,),
    )
    tarefas_rows = cursor.fetchall()
    pendentes = 0
    concluidas = 0
    categorias_map = {}

    for row in tarefas_rows:
        status, cat, count = row[0], row[1], row[2]
        if status in ["Pendente", "Em Andamento"]:
            pendentes += count
        elif status == "Concluído":
            concluidas += count
        if cat:
            categorias_map[cat] = categorias_map.get(cat, 0) + count

    cursor.execute("SELECT COUNT(*) FROM cursos WHERE user_id = ? AND status = 'Em Andamento'", (user_id,))
    cursos_andamento = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(minutos) FROM pomodoro WHERE user_id = ?", (user_id,))
    minutos_res = cursor.fetchone()[0]
    minutos_estudo = minutos_res if minutos_res else 0

    cursor.execute("SELECT COUNT(*) FROM midias WHERE user_id = ?", (user_id,))
    total_midias = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM midias WHERE user_id = ? AND status = 'Concluído'", (user_id,))
    midias_concluidas = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM compartilhamentos WHERE target_user_id = ? AND pode_visualizar = 1",
        (user_id,),
    )
    compartilhados_comigo = cursor.fetchone()[0]

    conn.close()

    grafico = [{"nome": k, "valor": v} for k, v in categorias_map.items()]

    return {
        "anotacoes": total_anotacoes,
        "pendentes": pendentes,
        "concluidas": concluidas,
        "cursosAndamento": cursos_andamento,
        "minutosEstudo": minutos_estudo,
        "totalMidias": total_midias,
        "midiasConcluidas": midias_concluidas,
        "compartilhadosComigo": compartilhados_comigo,
        "graficoCategorias": grafico,
    }


def get_todas_midias(user_id: int, tipo_filtro=None, status_filtro=None):
    conn = get_connection()
    extra_clauses = []
    extra_params = []
    if tipo_filtro:
        extra_clauses.append("tipo = ?")
        extra_params.append(tipo_filtro)
    if status_filtro:
        extra_clauses.append("status = ?")
        extra_params.append(status_filtro)
    extra_where = " AND ".join(extra_clauses)

    itens = obter_itens_acessiveis(conn, user_id, "midia", extra_where, tuple(extra_params))
    conn.close()

    resultado = []
    for r, perms, owner_info, shared_count in itens:
        resultado.append({
            "id": r["id"],
            "tipo": r["tipo"],
            "titulo": r["titulo"],
            "autorDiretor": r["autor_diretor"] or "",
            "ano": r["ano"] or "",
            "categoria": r["categoria"] or "",
            "status": r["status"] or "Quero Ler/Ver",
            "nota": r["nota"] or 0,
            "capaUrl": r["capa_url"] or "",
            "link": r["link"] or "",
            "resenha": r["resenha"] or "",
            "citacoes": r["citacoes"] or "",
            "dataCriacao": r["data_criacao"] or "",
            "dataConclusao": r["data_conclusao"] or "",
            "ownerId": owner_info["id"],
            "ownerNome": owner_info["nome"],
            "ownerEmail": owner_info["email"],
            "compartilhado": not perms["isOwner"],
            "compartilhadoComCount": shared_count,
            "permissoes": perms,
        })
    return resultado


def salvar_midia_db(user_id: int, dados: dict):
    conn = get_connection()
    cursor = conn.cursor()
    mid = dados.get("id")
    hoje = datetime.now().strftime("%d/%m/%Y")

    if mid:
        cat = (dados.get("categoria") or "").strip()
        cursor.execute("SELECT user_id, categoria FROM midias WHERE id = ?", (mid,))
        atual = cursor.fetchone()
        if not atual:
            conn.close()
            return {"success": False, "message": "Obra não encontrada."}
        owner_id = int(atual["user_id"])
        perms = obter_permissoes_recurso(conn, user_id, owner_id, "midia", mid, atual["categoria"] or "")
        if not perms or not perms["podeEditar"]:
            conn.close()
            return {"success": False, "forbidden": True, "message": "Sem permissão para editar esta obra."}

        if not perms["isOwner"] and cat != (atual["categoria"] or ""):
            perms_dest = obter_permissoes_recurso(conn, user_id, owner_id, "midia", mid, cat)
            if not perms_dest or not perms_dest["podeEditar"]:
                conn.close()
                return {
                    "success": False,
                    "forbidden": True,
                    "message": "Você não tem permissão para mover esta obra para esta categoria.",
                }

        cursor.execute(
            """
            UPDATE midias
            SET tipo = ?, titulo = ?, autor_diretor = ?, ano = ?, categoria = ?,
                status = ?, nota = ?, capa_url = ?, link = ?, resenha = ?, citacoes = ?,
                data_conclusao = ?
            WHERE id = ?
            """,
            (
                dados.get("tipo", "Livro"),
                dados.get("titulo", ""),
                dados.get("autorDiretor", ""),
                dados.get("ano", ""),
                cat,
                dados.get("status", "Quero Ler/Ver"),
                int(dados.get("nota", 0)),
                dados.get("capaUrl", ""),
                dados.get("link", ""),
                dados.get("resenha", ""),
                dados.get("citacoes", ""),
                dados.get("dataConclusao", hoje if dados.get("status") == "Concluído" else ""),
                mid,
            ),
        )
        conn.commit()
        conn.close()
        return {"success": True, "message": "Item atualizado com sucesso!", "id": mid}

    target_owner_id = int(dados.get("ownerUserId") or user_id)
    cat = (dados.get("categoria") or "").strip()
    if not pode_criar_no_espaco(conn, user_id, target_owner_id, "midia", cat):
        conn.close()
        return {"success": False, "forbidden": True, "message": "Sem permissão para criar obra neste espaço."}

    novo_id = gerar_id_unico("MID")
    data_criacao = hoje
    data_conclusao = hoje if dados.get("status") == "Concluído" else ""
    cursor.execute(
        """
        INSERT INTO midias (
            id, user_id, tipo, titulo, autor_diretor, ano, categoria, status,
            nota, capa_url, link, resenha, citacoes, data_criacao, data_conclusao
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            novo_id,
            target_owner_id,
            dados.get("tipo", "Livro"),
            dados.get("titulo", ""),
            dados.get("autorDiretor", ""),
            dados.get("ano", ""),
            cat,
            dados.get("status", "Quero Ler/Ver"),
            int(dados.get("nota", 0)),
            dados.get("capaUrl", ""),
            dados.get("link", ""),
            dados.get("resenha", ""),
            dados.get("citacoes", ""),
            data_criacao,
            data_conclusao,
        ),
    )
    conn.commit()
    conn.close()
    return {"success": True, "message": "Item adicionado ao seu acervo!", "id": novo_id}


def excluir_midia_db(user_id: int, mid: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, categoria FROM midias WHERE id = ?", (mid,))
    atual = cursor.fetchone()
    if not atual:
        conn.close()
        return {"success": False, "message": "Obra não encontrada."}
    perms = obter_permissoes_recurso(conn, user_id, atual["user_id"], "midia", mid, atual["categoria"] or "")
    if not perms or not perms["podeExcluir"]:
        conn.close()
        return {"success": False, "forbidden": True, "message": "Sem permissão para excluir esta obra."}

    cursor.execute("DELETE FROM midias WHERE id = ?", (mid,))
    remover_compartilhamentos_do_item(conn, int(atual["user_id"]), "midia", mid)
    conn.commit()
    conn.close()
    return {"success": True, "message": "Item removido com sucesso!"}


# ================= RASTREADOR DE HÁBITOS & GAMIFICAÇÃO =================

def get_habitos_dados(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    habitos_acessiveis = obter_itens_acessiveis(conn, user_id, "habito")
    visiveis_ids = [r["id"] for r, _, _, _ in habitos_acessiveis]

    registros_por_habito = {}
    if visiveis_ids:
        placeholders = ",".join("?" for _ in visiveis_ids)
        cursor.execute(
            f"SELECT habito_id, data FROM habitos_registros WHERE habito_id IN ({placeholders})",
            visiveis_ids,
        )
        for r in cursor.fetchall():
            hid, dt = r["habito_id"], r["data"]
            registros_por_habito.setdefault(hid, set()).add(dt)

    # Heatmap e streak global refletem a atividade individual do usuário logado
    contagem_por_data = {}
    cursor.execute("SELECT data FROM habitos_registros WHERE user_id = ?", (user_id,))
    for r in cursor.fetchall():
        dt = r["data"]
        contagem_por_data[dt] = contagem_por_data.get(dt, 0) + 1

    cursor.execute("SELECT data FROM pomodoro WHERE user_id = ?", (user_id,))
    for r in cursor.fetchall():
        dt_str = (r["data"] or "").split(" ")[0]
        if len(dt_str) == 10 and "/" in dt_str:
            partes = dt_str.split("/")
            dt_iso = f"{partes[2]}-{partes[1]}-{partes[0]}"
            contagem_por_data[dt_iso] = contagem_por_data.get(dt_iso, 0) + 1

    cursor.execute("SELECT data FROM anotacoes WHERE user_id = ?", (user_id,))
    for r in cursor.fetchall():
        dt_str = (r["data"] or "").split(" ")[0]
        if len(dt_str) == 10 and "/" in dt_str:
            partes = dt_str.split("/")
            dt_iso = f"{partes[2]}-{partes[1]}-{partes[0]}"
            contagem_por_data[dt_iso] = contagem_por_data.get(dt_iso, 0) + 1

    hoje = datetime.now().date()
    hoje_str = hoje.strftime("%Y-%m-%d")

    ultimos_7_dias = []
    nomes_dias = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    for i in range(6, -1, -1):
        d = hoje - timedelta(days=i)
        d_str = d.strftime("%Y-%m-%d")
        ultimos_7_dias.append({
            "data": d_str,
            "diaMes": d.strftime("%d/%m"),
            "diaSemana": "Hoje" if i == 0 else nomes_dias[d.weekday()],
        })

    habitos_lista = []
    concluidos_hoje = 0
    total_proprios = 0
    for h, perms, owner_info, shared_count in habitos_acessiveis:
        hid = h["id"]
        datas_feitas = registros_por_habito.get(hid, set())
        if int(h["user_id"]) == int(user_id):
            total_proprios += 1
            if hoje_str in datas_feitas:
                concluidos_hoje += 1

        streak = 0
        dia_check = hoje
        if dia_check.strftime("%Y-%m-%d") not in datas_feitas:
            dia_check = hoje - timedelta(days=1)
        while dia_check.strftime("%Y-%m-%d") in datas_feitas:
            streak += 1
            dia_check -= timedelta(days=1)

        historico_7d = {d["data"]: (d["data"] in datas_feitas) for d in ultimos_7_dias}
        habitos_lista.append({
            "id": hid,
            "nome": h["nome"],
            "icone": h["icone"] or "fa-solid fa-fire",
            "cor": h["cor"] or "#10b981",
            "metaSemanal": h["meta_semanal"] or 7,
            "streak": streak,
            "historico7d": historico_7d,
            "ownerId": owner_info["id"],
            "ownerNome": owner_info["nome"],
            "ownerEmail": owner_info["email"],
            "compartilhado": not perms["isOwner"],
            "compartilhadoComCount": shared_count,
            "permissoes": perms,
        })

    streak_global = 0
    dia_g = hoje
    if contagem_por_data.get(dia_g.strftime("%Y-%m-%d"), 0) == 0:
        dia_g = hoje - timedelta(days=1)
    while contagem_por_data.get(dia_g.strftime("%Y-%m-%d"), 0) > 0:
        streak_global += 1
        dia_g -= timedelta(days=1)

    heatmap = []
    for i in range(139, -1, -1):
        d = hoje - timedelta(days=i)
        d_str = d.strftime("%Y-%m-%d")
        heatmap.append({
            "data": d_str,
            "dataFmt": d.strftime("%d/%m/%Y"),
            "count": contagem_por_data.get(d_str, 0),
        })

    cursor.execute(
        "SELECT COUNT(*) FROM midias WHERE user_id = ? AND tipo = 'Livro' AND status = 'Concluído'",
        (user_id,),
    )
    livros_concluidos = cursor.fetchone()[0]
    cursor.execute(
        "SELECT COUNT(*) FROM midias WHERE user_id = ? AND status = 'Concluído'",
        (user_id,),
    )
    midias_concluidas = cursor.fetchone()[0]

    conn.close()

    meta_livros = int(get_config(user_id, "META_LIVROS_ANO", "12") or 12)

    return {
        "habitos": habitos_lista,
        "diasSemana": ultimos_7_dias,
        "concluidosHoje": concluidos_hoje,
        "totalHabitos": total_proprios,
        "streakGlobal": streak_global,
        "heatmap": heatmap,
        "livrosConcluidos": livros_concluidos,
        "midiasConcluidas": midias_concluidas,
        "metaLivrosAno": meta_livros,
    }


def salvar_habito_db(user_id: int, dados: dict):
    nome = (dados.get("nome") or "").strip()
    if not nome:
        return {"success": False, "message": "Informe o nome do hábito."}

    icone = dados.get("icone") or "fa-solid fa-fire"
    cor = dados.get("cor") or "#10b981"
    meta = int(dados.get("metaSemanal") or 7)
    hid = dados.get("id")

    conn = get_connection()
    cursor = conn.cursor()

    if hid:
        cursor.execute("SELECT user_id FROM habitos WHERE id = ?", (hid,))
        atual = cursor.fetchone()
        if not atual:
            conn.close()
            return {"success": False, "message": "Hábito não encontrado."}
        perms = obter_permissoes_recurso(conn, user_id, atual["user_id"], "habito", hid, "")
        if not perms or not perms["podeEditar"]:
            conn.close()
            return {"success": False, "forbidden": True, "message": "Sem permissão para editar este hábito."}

        cursor.execute(
            """
            UPDATE habitos
            SET nome = ?, icone = ?, cor = ?, meta_semanal = ?
            WHERE id = ?
            """,
            (nome, icone, cor, meta, hid),
        )
        conn.commit()
        conn.close()
        return {"success": True, "message": "Hábito atualizado com sucesso!", "id": hid}

    target_owner_id = int(dados.get("ownerUserId") or user_id)
    if not pode_criar_no_espaco(conn, user_id, target_owner_id, "habito", ""):
        conn.close()
        return {"success": False, "forbidden": True, "message": "Sem permissão para criar hábito neste espaço."}

    novo_id = gerar_id_unico("HAB")
    cursor.execute(
        """
        INSERT INTO habitos (id, user_id, nome, icone, cor, meta_semanal)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (novo_id, target_owner_id, nome, icone, cor, meta),
    )
    conn.commit()
    conn.close()
    return {"success": True, "message": "Hábito salvo com sucesso!", "id": novo_id}


def alternar_registro_habito_db(user_id: int, habito_id: str, data_str: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM habitos WHERE id = ?", (habito_id,))
    atual = cursor.fetchone()
    if not atual:
        conn.close()
        return {"success": False, "message": "Hábito não encontrado."}

    perms = obter_permissoes_recurso(conn, user_id, atual["user_id"], "habito", habito_id, "")
    if not perms or not perms["podeEditar"]:
        conn.close()
        return {"success": False, "forbidden": True, "message": "Sem permissão para alterar este hábito."}

    cursor.execute(
        "SELECT 1 FROM habitos_registros WHERE habito_id = ? AND data = ?",
        (habito_id, data_str),
    )
    existe = cursor.fetchone()
    if existe:
        cursor.execute(
            "DELETE FROM habitos_registros WHERE habito_id = ? AND data = ?",
            (habito_id, data_str),
        )
        marcado = False
    else:
        cursor.execute(
            "INSERT INTO habitos_registros (habito_id, data, user_id) VALUES (?, ?, ?)",
            (habito_id, data_str, int(atual["user_id"])),
        )
        marcado = True
    conn.commit()
    conn.close()
    return {"success": True, "marcado": marcado}


def excluir_habito_db(user_id: int, habito_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM habitos WHERE id = ?", (habito_id,))
    atual = cursor.fetchone()
    if not atual:
        conn.close()
        return {"success": False, "message": "Hábito não encontrado."}

    perms = obter_permissoes_recurso(conn, user_id, atual["user_id"], "habito", habito_id, "")
    if not perms or not perms["podeExcluir"]:
        conn.close()
        return {"success": False, "forbidden": True, "message": "Sem permissão para excluir este hábito."}

    cursor.execute("DELETE FROM habitos WHERE id = ?", (habito_id,))
    cursor.execute("DELETE FROM habitos_registros WHERE habito_id = ?", (habito_id,))
    remover_compartilhamentos_do_item(conn, int(atual["user_id"]), "habito", habito_id)
    conn.commit()
    conn.close()
    return {"success": True, "message": "Hábito removido!"}


def salvar_meta_leitura_db(user_id: int, meta: int):
    set_config(user_id, "META_LIVROS_ANO", str(max(1, int(meta))))
    return {"success": True, "message": "Meta anual de leitura atualizada!"}


# ================= GRAFO DE CONHECIMENTO & BACKLINKS =================

def get_grafo_conhecimento(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    nodes = []
    edges = []
    node_ids = set()

    def garantir_no_categoria(cat_nome: str) -> str:
        cat_limpa = (cat_nome or "").strip() or "Outros"
        nid = f"CAT:{cat_limpa}"
        if nid not in node_ids:
            node_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": cat_limpa,
                "group": "categoria",
                "val": 18,
            })
        return nid

    # 1. Categorias do próprio usuário
    cursor.execute("SELECT nome FROM categorias WHERE user_id = ?", (user_id,))
    for r in cursor.fetchall():
        garantir_no_categoria(r["nome"])

    titulo_para_id = {}

    # 2. Anotações acessíveis (próprias + compartilhadas)
    anotacoes_acessiveis = obter_itens_acessiveis(conn, user_id, "anotacao")
    anotacoes_rows = [r for r, _, _, _ in anotacoes_acessiveis]
    for a, perms, _, _ in anotacoes_acessiveis:
        aid = a["id"]
        topico = a["topico"] or "Sem título"
        materia = a["materia"] or "Outros"
        subcat = (a["subcategoria"] or "").strip()
        node_ids.add(aid)
        titulo_para_id[topico.strip().lower()] = aid
        nodes.append({
            "id": aid,
            "label": topico,
            "group": "anotacao",
            "categoria": materia,
            "subcategoria": subcat,
            "rawId": aid,
            "compartilhado": not perms["isOwner"],
            "val": 11,
        })
        cat_id = garantir_no_categoria(materia)
        if subcat:
            sub_id = f"SUB:{materia}::{subcat}"
            if sub_id not in node_ids:
                node_ids.add(sub_id)
                nodes.append({
                    "id": sub_id,
                    "label": subcat,
                    "group": "subcategoria",
                    "categoria": materia,
                    "val": 14,
                })
                edges.append({"from": sub_id, "to": cat_id, "type": "subcategoria"})
            edges.append({"from": aid, "to": sub_id, "type": "categoria"})
        else:
            edges.append({"from": aid, "to": cat_id, "type": "categoria"})

    # 3. Leituras & Mídias acessíveis
    midias_acessiveis = obter_itens_acessiveis(conn, user_id, "midia")
    midias_rows = [r for r, _, _, _ in midias_acessiveis]
    for m, perms, _, _ in midias_acessiveis:
        mid = m["id"]
        titulo = m["titulo"] or "Obra"
        cat = m["categoria"] or "Outros"
        node_ids.add(mid)
        titulo_para_id[titulo.strip().lower()] = mid
        nodes.append({
            "id": mid,
            "label": f"📚 {titulo}" if m["tipo"] == "Livro" else f"🎬 {titulo}",
            "group": "midia",
            "categoria": cat,
            "rawId": mid,
            "compartilhado": not perms["isOwner"],
            "val": 12,
        })
        cat_id = garantir_no_categoria(cat)
        edges.append({"from": mid, "to": cat_id, "type": "categoria"})

    # 4. Cursos acessíveis
    cursos_acessiveis = obter_itens_acessiveis(conn, user_id, "curso")
    for c, perms, _, _ in cursos_acessiveis:
        cid = c["id"]
        nome = c["nome"] or "Curso"
        cat = c["categoria"] or "Outros"
        node_ids.add(cid)
        titulo_para_id[nome.strip().lower()] = cid
        nodes.append({
            "id": cid,
            "label": f"🎓 {nome}",
            "group": "curso",
            "categoria": cat,
            "rawId": cid,
            "compartilhado": not perms["isOwner"],
            "val": 11,
        })
        cat_id = garantir_no_categoria(cat)
        edges.append({"from": cid, "to": cat_id, "type": "categoria"})

    # 5. Backlinks [[...]] e Tags compartilhadas entre nós visíveis
    padrao_backlink = re.compile(r"\[\[([^\]]+)\]\]")
    tags_map = {}

    for a in anotacoes_rows:
        aid = a["id"]
        conteudo = a["conteudo"] or ""
        for m_texto in padrao_backlink.findall(conteudo):
            alvo_id = titulo_para_id.get(m_texto.strip().lower())
            if alvo_id and alvo_id != aid:
                edges.append({
                    "from": aid,
                    "to": alvo_id,
                    "type": "backlink",
                    "label": "cita",
                })

        for t in (a["tags"] or "").split(","):
            t_clean = t.strip().lower()
            if t_clean:
                tags_map.setdefault(t_clean, []).append(aid)

    for m in midias_rows:
        mid = m["id"]
        resenha = m["resenha"] or ""
        for m_texto in padrao_backlink.findall(resenha):
            alvo_id = titulo_para_id.get(m_texto.strip().lower())
            if alvo_id and alvo_id != mid:
                edges.append({
                    "from": mid,
                    "to": alvo_id,
                    "type": "backlink",
                    "label": "cita",
                })

    for tag, ids in tags_map.items():
        if len(ids) > 1:
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    edges.append({
                        "from": ids[i],
                        "to": ids[j],
                        "type": "tag",
                        "label": f"#{tag}",
                    })

    conn.close()
    return {"nodes": nodes, "edges": edges}
