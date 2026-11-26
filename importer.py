import json
import secrets
import unicodedata
from datetime import datetime, date
import openpyxl
import db
from db import get_connection, gerar_id_unico

QUADRANTES_EISENHOWER = {"", "fazer", "agendar", "delegar", "eliminar"}


def normalizar_nome(texto: str) -> str:
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", str(texto)).encode("ASCII", "ignore").decode("ASCII")
    return texto.strip().lower()


def formatar_data(val, formato="%d/%m/%Y"):
    if val is None or val == "":
        return ""
    if isinstance(val, (datetime, date)):
        return val.strftime(formato)
    return str(val).strip()


def _resolver_id_importacao(cursor, tabela: str, item_id, user_id: int, prefixo: str) -> str:
    """Resolve o ID durante importação garantindo que registros de outros usuários nunca sejam sobrescritos."""
    raw_id = str(item_id).strip() if item_id is not None else ""
    if not raw_id:
        return gerar_id_unico(prefixo)

    cursor.execute(f"SELECT user_id FROM {tabela} WHERE id = ?", (raw_id,))
    row = cursor.fetchone()
    if row is None or int(row["user_id"]) == int(user_id):
        return raw_id
    return f"{raw_id}-U{user_id}-{secrets.token_hex(2)}"


def importar_arquivo_xlsx(caminho_arquivo: str, user_id: int):
    wb = openpyxl.load_workbook(caminho_arquivo, data_only=True)
    resumo = {
        "anotacoes": 0,
        "tarefas": 0,
        "cursos": 0,
        "categorias": 0,
        "flashcards": 0,
        "pomodoro": 0,
    }

    conn = get_connection()
    cursor = conn.cursor()

    for sheet_name in wb.sheetnames:
        norm = normalizar_nome(sheet_name)
        sheet = wb[sheet_name]
        rows = list(sheet.iter_rows(values_only=True))
        if not rows or len(rows) < 2:
            continue

        dados_linhas = rows[1:]

        if "anotac" in norm:
            for r in dados_linhas:
                if not r or r[0] is None:
                    continue
                aid = _resolver_id_importacao(cursor, "anotacoes", r[0], user_id, "NOTE")
                adata = formatar_data(r[1] if len(r) > 1 else "", "%d/%m/%Y %H:%M")
                materia = str(r[2]).strip() if len(r) > 2 and r[2] is not None else ""
                topico = str(r[3]).strip() if len(r) > 3 and r[3] is not None else ""
                conteudo = str(r[4]) if len(r) > 4 and r[4] is not None else ""
                tags = str(r[5]).strip() if len(r) > 5 and r[5] is not None else ""
                link = str(r[6]).strip() if len(r) > 6 and r[6] is not None else ""
                anexo_nome = str(r[7]).strip() if len(r) > 7 and r[7] is not None else ""
                anexo_url = str(r[8]).strip() if len(r) > 8 and r[8] is not None else ""
                subcategoria = str(r[9]).strip() if len(r) > 9 and r[9] is not None else ""

                if materia and subcategoria:
                    cursor.execute(
                        "INSERT OR IGNORE INTO subcategorias (user_id, categoria, nome) VALUES (?, ?, ?)",
                        (user_id, materia, subcategoria),
                    )

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO anotacoes (
                        id, user_id, data, materia, subcategoria, topico, conteudo, tags, link, anexo_nome, anexo_url
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (aid, user_id, adata, materia, subcategoria, topico, conteudo, tags, link, anexo_nome, anexo_url),
                )
                resumo["anotacoes"] += 1

        elif "tarefa" in norm:
            for r in dados_linhas:
                if not r or r[0] is None:
                    continue
                tid = _resolver_id_importacao(cursor, "tarefas", r[0], user_id, "TASK")
                data_criacao = formatar_data(r[1] if len(r) > 1 else "", "%d/%m/%Y")
                titulo = str(r[2]).strip() if len(r) > 2 and r[2] is not None else ""
                categoria = str(r[3]).strip() if len(r) > 3 and r[3] is not None else ""
                status = str(r[4]).strip() if len(r) > 4 and r[4] is not None else "Pendente"
                prazo = formatar_data(r[5] if len(r) > 5 else "", "%Y-%m-%d")
                prioridade = str(r[6]).strip() if len(r) > 6 and r[6] is not None else "Média"
                descricao = str(r[7]) if len(r) > 7 and r[7] is not None else ""
                anexo_nome = str(r[8]).strip() if len(r) > 8 and r[8] is not None else ""
                anexo_url = str(r[9]).strip() if len(r) > 9 and r[9] is not None else ""
                eisenhower = str(r[10]).strip().lower() if len(r) > 10 and r[10] is not None else ""
                if eisenhower not in QUADRANTES_EISENHOWER:
                    eisenhower = ""

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO tarefas (
                        id, user_id, data_criacao, titulo, categoria, status, prazo, prioridade, descricao, anexo_nome, anexo_url, eisenhower
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (tid, user_id, data_criacao, titulo, categoria, status, prazo, prioridade, descricao, anexo_nome, anexo_url, eisenhower),
                )
                resumo["tarefas"] += 1

        elif "curso" in norm:
            for r in dados_linhas:
                if not r or r[0] is None:
                    continue
                cid = _resolver_id_importacao(cursor, "cursos", r[0], user_id, "CRS")
                nome = str(r[1]).strip() if len(r) > 1 and r[1] is not None else ""
                instituicao = str(r[2]).strip() if len(r) > 2 and r[2] is not None else ""
                categoria = str(r[3]).strip() if len(r) > 3 and r[3] is not None else ""
                carga_horaria = str(r[4]).strip() if len(r) > 4 and r[4] is not None else ""
                status = str(r[5]).strip() if len(r) > 5 and r[5] is not None else "Em Andamento"
                link = str(r[6]).strip() if len(r) > 6 and r[6] is not None else ""

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO cursos (id, user_id, nome, instituicao, categoria, carga_horaria, status, link)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (cid, user_id, nome, instituicao, categoria, carga_horaria, status, link),
                )
                resumo["cursos"] += 1

        elif "subcategoria" in norm:
            for r in dados_linhas:
                if not r or r[0] is None:
                    continue
                cat = str(r[0]).strip()
                sub = str(r[1]).strip() if len(r) > 1 and r[1] is not None else ""
                if cat and sub:
                    cursor.execute(
                        "INSERT OR IGNORE INTO subcategorias (user_id, categoria, nome) VALUES (?, ?, ?)",
                        (user_id, cat, sub),
                    )

        elif "categoria" in norm:
            for r in dados_linhas:
                if not r or r[0] is None:
                    continue
                nome = str(r[0]).strip()
                if nome:
                    cursor.execute(
                        "INSERT OR IGNORE INTO categorias (user_id, nome) VALUES (?, ?)",
                        (user_id, nome),
                    )
                    resumo["categorias"] += 1

        elif "flashcard" in norm:
            for r in dados_linhas:
                if not r or r[0] is None:
                    continue
                fid = _resolver_id_importacao(cursor, "flashcards", r[0], user_id, "FC")
                categoria = str(r[1]).strip() if len(r) > 1 and r[1] is not None else ""
                frente = str(r[2]).strip() if len(r) > 2 and r[2] is not None else ""
                verso = str(r[3]).strip() if len(r) > 3 and r[3] is not None else ""
                nivel = str(r[4]).strip() if len(r) > 4 and r[4] is not None else "Novo"
                ultima = formatar_data(r[5] if len(r) > 5 else "", "%d/%m/%Y")
                if not ultima:
                    ultima = "Nunca"

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO flashcards (id, user_id, categoria, frente, verso, nivel, ultima_revisao)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (fid, user_id, categoria, frente, verso, nivel, ultima),
                )
                resumo["flashcards"] += 1

        elif "pomo" in norm:
            for r in dados_linhas:
                if not r or r[0] is None:
                    continue
                pid = _resolver_id_importacao(cursor, "pomodoro", r[0], user_id, "POMO")
                pdata = formatar_data(r[1] if len(r) > 1 else "", "%d/%m/%Y %H:%M")
                categoria = str(r[2]).strip() if len(r) > 2 and r[2] is not None else "Geral"
                try:
                    minutos = int(r[3]) if len(r) > 3 and r[3] is not None else 25
                except (ValueError, TypeError):
                    minutos = 25

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO pomodoro (id, user_id, data, categoria, minutos)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (pid, user_id, pdata, categoria, minutos),
                )
                resumo["pomodoro"] += 1

    conn.commit()
    conn.close()
    return resumo


def importar_arquivo_json(caminho_arquivo: str, user_id: int):
    with open(caminho_arquivo, "r", encoding="utf-8") as f:
        dados = json.load(f)

    resumo = {
        "anotacoes": 0,
        "tarefas": 0,
        "cursos": 0,
        "categorias": 0,
        "flashcards": 0,
        "pomodoro": 0,
    }

    conn = get_connection()
    cursor = conn.cursor()

    if "categorias" in dados:
        for c in dados["categorias"]:
            nome = c if isinstance(c, str) else c.get("nome")
            if nome:
                cursor.execute(
                    "INSERT OR IGNORE INTO categorias (user_id, nome) VALUES (?, ?)",
                    (user_id, nome.strip()),
                )
                resumo["categorias"] += 1

    if "subcategorias" in dados:
        for s in dados["subcategorias"]:
            if isinstance(s, dict):
                cat = (s.get("categoria") or "").strip()
                nome = (s.get("nome") or "").strip()
                if cat and nome:
                    cursor.execute(
                        "INSERT OR IGNORE INTO subcategorias (user_id, categoria, nome) VALUES (?, ?, ?)",
                        (user_id, cat, nome),
                    )

    if "anotacoes" in dados:
        for a in dados["anotacoes"]:
            aid = _resolver_id_importacao(cursor, "anotacoes", a.get("id"), user_id, "NOTE")
            materia = (a.get("materia") or "").strip()
            subcategoria = (a.get("subcategoria") or "").strip()
            if materia and subcategoria:
                cursor.execute(
                    "INSERT OR IGNORE INTO subcategorias (user_id, categoria, nome) VALUES (?, ?, ?)",
                    (user_id, materia, subcategoria),
                )
            cursor.execute(
                """
                INSERT OR REPLACE INTO anotacoes (
                    id, user_id, data, materia, subcategoria, topico, conteudo, tags, link, anexo_nome, anexo_url
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    aid,
                    user_id,
                    a.get("data", ""),
                    materia,
                    subcategoria,
                    a.get("topico", ""),
                    a.get("conteudo", ""),
                    a.get("tags", ""),
                    a.get("link", ""),
                    a.get("anexoNome", a.get("anexo_nome", "")),
                    a.get("anexoUrl", a.get("anexo_url", "")),
                ),
            )
            resumo["anotacoes"] += 1

    if "tarefas" in dados:
        for t in dados["tarefas"]:
            tid = _resolver_id_importacao(cursor, "tarefas", t.get("id"), user_id, "TASK")
            eisenhower = (t.get("eisenhower") or "").strip().lower()
            if eisenhower not in QUADRANTES_EISENHOWER:
                eisenhower = ""
            cursor.execute(
                """
                INSERT OR REPLACE INTO tarefas (
                    id, user_id, data_criacao, titulo, categoria, status, prazo, prioridade, descricao, anexo_nome, anexo_url, eisenhower
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tid,
                    user_id,
                    t.get("dataCriacao", t.get("data_criacao", "")),
                    t.get("titulo", ""),
                    t.get("categoria", ""),
                    t.get("status", "Pendente"),
                    t.get("prazo", ""),
                    t.get("prioridade", "Média"),
                    t.get("descricao", ""),
                    t.get("anexoNome", t.get("anexo_nome", "")),
                    t.get("anexoUrl", t.get("anexo_url", "")),
                    eisenhower,
                ),
            )
            resumo["tarefas"] += 1

    if "cursos" in dados:
        for c in dados["cursos"]:
            cid = _resolver_id_importacao(cursor, "cursos", c.get("id"), user_id, "CRS")
            cursor.execute(
                """
                INSERT OR REPLACE INTO cursos (id, user_id, nome, instituicao, categoria, carga_horaria, status, link)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cid,
                    user_id,
                    c.get("nome", ""),
                    c.get("instituicao", ""),
                    c.get("categoria", ""),
                    c.get("cargaHoraria", c.get("carga_horaria", "")),
                    c.get("status", "Em Andamento"),
                    c.get("link", ""),
                ),
            )
            resumo["cursos"] += 1

    if "flashcards" in dados:
        for fc in dados["flashcards"]:
            fid = _resolver_id_importacao(cursor, "flashcards", fc.get("id"), user_id, "FC")
            cursor.execute(
                """
                INSERT OR REPLACE INTO flashcards (id, user_id, categoria, frente, verso, nivel, ultima_revisao)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fid,
                    user_id,
                    fc.get("categoria", ""),
                    fc.get("frente", ""),
                    fc.get("verso", ""),
                    fc.get("nivel", "Novo"),
                    fc.get("ultimaRevisao", fc.get("ultima_revisao", "Nunca")),
                ),
            )
            resumo["flashcards"] += 1

    if "pomodoro" in dados:
        for p in dados["pomodoro"]:
            pid = _resolver_id_importacao(cursor, "pomodoro", p.get("id"), user_id, "POMO")
            cursor.execute(
                """
                INSERT OR REPLACE INTO pomodoro (id, user_id, data, categoria, minutos)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    pid,
                    user_id,
                    p.get("data", ""),
                    p.get("categoria", "Geral"),
                    int(p.get("minutos", 25)),
                ),
            )
            resumo["pomodoro"] += 1

    if "midias" in dados:
        for m in dados["midias"]:
            mid = _resolver_id_importacao(cursor, "midias", m.get("id"), user_id, "MID")
            cursor.execute(
                """
                INSERT OR REPLACE INTO midias (
                    id, user_id, tipo, titulo, autor_diretor, ano, categoria, status,
                    nota, capa_url, link, resenha, citacoes, data_criacao, data_conclusao
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mid,
                    user_id,
                    m.get("tipo", "Livro"),
                    m.get("titulo", ""),
                    m.get("autorDiretor", m.get("autor_diretor", "")),
                    m.get("ano", ""),
                    m.get("categoria", ""),
                    m.get("status", "Quero Ler/Ver"),
                    int(m.get("nota", 0) or 0),
                    m.get("capaUrl", m.get("capa_url", "")),
                    m.get("link", ""),
                    m.get("resenha", ""),
                    m.get("citacoes", ""),
                    m.get("dataCriacao", m.get("data_criacao", "")),
                    m.get("dataConclusao", m.get("data_conclusao", "")),
                ),
            )

    habito_id_map = {}
    if "habitos" in dados:
        for h in dados["habitos"]:
            old_hid = str(h.get("id") or "")
            hid = _resolver_id_importacao(cursor, "habitos", old_hid, user_id, "HAB")
            if old_hid:
                habito_id_map[old_hid] = hid
            cursor.execute(
                """
                INSERT OR REPLACE INTO habitos (id, user_id, nome, icone, cor, meta_semanal)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    hid,
                    user_id,
                    h.get("nome", ""),
                    h.get("icone", "fa-solid fa-fire"),
                    h.get("cor", "#10b981"),
                    int(h.get("metaSemanal", h.get("meta_semanal", 7)) or 7),
                ),
            )

    if "habitosRegistros" in dados:
        for hr in dados["habitosRegistros"]:
            raw_hid = str(hr.get("habitoId", hr.get("habito_id", "")) or "").strip()
            dt = str(hr.get("data", "") or "").strip()
            if not raw_hid or not dt:
                continue
            target_hid = habito_id_map.get(raw_hid, raw_hid)
            cursor.execute("SELECT user_id FROM habitos WHERE id = ?", (target_hid,))
            hrow = cursor.fetchone()
            if hrow and int(hrow["user_id"]) == int(user_id):
                cursor.execute(
                    "INSERT OR IGNORE INTO habitos_registros (habito_id, data, user_id) VALUES (?, ?, ?)",
                    (target_hid, dt, user_id),
                )

    conn.commit()
    conn.close()
    return resumo


def exportar_todos_dados(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT nome FROM categorias WHERE user_id = ? ORDER BY id ASC", (user_id,))
    categorias = [r[0] for r in cursor.fetchall()]

    cursor.execute(
        "SELECT id, categoria, nome FROM subcategorias WHERE user_id = ? ORDER BY categoria ASC, nome ASC",
        (user_id,),
    )
    subcategorias = [
        {"id": r["id"], "categoria": r["categoria"], "nome": r["nome"]}
        for r in cursor.fetchall()
    ]

    cursor.execute("SELECT * FROM anotacoes WHERE user_id = ? ORDER BY rowid DESC", (user_id,))
    anotacoes = [
        {
            "id": r["id"],
            "data": r["data"],
            "materia": r["materia"],
            "subcategoria": r["subcategoria"] or "",
            "topico": r["topico"],
            "conteudo": r["conteudo"],
            "tags": r["tags"],
            "link": r["link"],
            "anexoNome": r["anexo_nome"] or "",
            "anexoUrl": r["anexo_url"] or "",
        }
        for r in cursor.fetchall()
    ]

    cursor.execute("SELECT * FROM tarefas WHERE user_id = ? ORDER BY rowid DESC", (user_id,))
    tarefas = [
        {
            "id": r["id"],
            "dataCriacao": r["data_criacao"],
            "titulo": r["titulo"],
            "categoria": r["categoria"],
            "status": r["status"],
            "prazo": r["prazo"],
            "prioridade": r["prioridade"],
            "descricao": r["descricao"] or "",
            "anexoNome": r["anexo_nome"] or "",
            "anexoUrl": r["anexo_url"] or "",
            "eisenhower": r["eisenhower"] or "",
        }
        for r in cursor.fetchall()
    ]

    cursor.execute("SELECT * FROM cursos WHERE user_id = ? ORDER BY rowid DESC", (user_id,))
    cursos = [
        {
            "id": r["id"],
            "nome": r["nome"],
            "instituicao": r["instituicao"],
            "categoria": r["categoria"],
            "cargaHoraria": r["carga_horaria"],
            "status": r["status"],
            "link": r["link"],
        }
        for r in cursor.fetchall()
    ]

    cursor.execute("SELECT * FROM flashcards WHERE user_id = ? ORDER BY rowid DESC", (user_id,))
    flashcards = [
        {
            "id": r["id"],
            "categoria": r["categoria"],
            "frente": r["frente"],
            "verso": r["verso"],
            "nivel": r["nivel"],
            "ultimaRevisao": r["ultima_revisao"],
        }
        for r in cursor.fetchall()
    ]

    cursor.execute("SELECT * FROM pomodoro WHERE user_id = ? ORDER BY rowid DESC", (user_id,))
    pomodoro = [
        {
            "id": r["id"],
            "data": r["data"],
            "categoria": r["categoria"],
            "minutos": r["minutos"],
        }
        for r in cursor.fetchall()
    ]

    cursor.execute("SELECT * FROM midias WHERE user_id = ? ORDER BY rowid DESC", (user_id,))
    midias = [
        {
            "id": r["id"],
            "tipo": r["tipo"],
            "titulo": r["titulo"],
            "autorDiretor": r["autor_diretor"] or "",
            "ano": r["ano"] or "",
            "categoria": r["categoria"] or "",
            "status": r["status"] or "",
            "nota": r["nota"] or 0,
            "capaUrl": r["capa_url"] or "",
            "link": r["link"] or "",
            "resenha": r["resenha"] or "",
            "citacoes": r["citacoes"] or "",
            "dataCriacao": r["data_criacao"] or "",
            "dataConclusao": r["data_conclusao"] or "",
        }
        for r in cursor.fetchall()
    ]

    cursor.execute("SELECT * FROM habitos WHERE user_id = ? ORDER BY rowid ASC", (user_id,))
    habitos = [
        {
            "id": r["id"],
            "nome": r["nome"],
            "icone": r["icone"],
            "cor": r["cor"],
            "metaSemanal": r["meta_semanal"],
        }
        for r in cursor.fetchall()
    ]

    cursor.execute("SELECT * FROM habitos_registros WHERE user_id = ?", (user_id,))
    habitos_registros = [
        {"habitoId": r["habito_id"], "data": r["data"]}
        for r in cursor.fetchall()
    ]

    conn.close()

    return {
        "versao": "4.0",
        "geradoEm": datetime.now().isoformat(),
        "categorias": categorias,
        "subcategorias": subcategorias,
        "anotacoes": anotacoes,
        "tarefas": tarefas,
        "cursos": cursos,
        "flashcards": flashcards,
        "pomodoro": pomodoro,
        "midias": midias,
        "habitos": habitos,
        "habitosRegistros": habitos_registros,
    }
