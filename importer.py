import openpyxl
import json
import unicodedata
from datetime import datetime, date
from db import get_connection

def normalizar_nome(texto: str) -> str:
    if not texto:
        return ""
    texto = unicodedata.normalize('NFKD', str(texto)).encode('ASCII', 'ignore').decode('ASCII')
    return texto.strip().lower()

def formatar_data(val, formato="%d/%m/%Y"):
    if val is None or val == "":
        return ""
    if isinstance(val, (datetime, date)):
        return val.strftime(formato)
    return str(val).strip()

def importar_arquivo_xlsx(caminho_arquivo: str):
    wb = openpyxl.load_workbook(caminho_arquivo, data_only=True)
    resumo = {
        "anotacoes": 0,
        "tarefas": 0,
        "cursos": 0,
        "categorias": 0,
        "flashcards": 0,
        "pomodoro": 0
    }

    conn = get_connection()
    cursor = conn.cursor()

    for sheet_name in wb.sheetnames:
        norm = normalizar_nome(sheet_name)
        sheet = wb[sheet_name]
        rows = list(sheet.iter_rows(values_only=True))
        if not rows or len(rows) < 2:
            continue

        # Linha 1 = cabeçalhos, Linha 2+ = dados
        dados_linhas = rows[1:]

        if "anotac" in norm:  # Anotações
            for r in dados_linhas:
                if not r or r[0] is None:
                    continue
                aid = str(r[0]).strip()
                adata = formatar_data(r[1] if len(r) > 1 else "", "%d/%m/%Y %H:%M")
                materia = str(r[2]).strip() if len(r) > 2 and r[2] is not None else ""
                topico = str(r[3]).strip() if len(r) > 3 and r[3] is not None else ""
                conteudo = str(r[4]) if len(r) > 4 and r[4] is not None else ""
                tags = str(r[5]).strip() if len(r) > 5 and r[5] is not None else ""
                link = str(r[6]).strip() if len(r) > 6 and r[6] is not None else ""
                anexo_nome = str(r[7]).strip() if len(r) > 7 and r[7] is not None else ""
                anexo_url = str(r[8]).strip() if len(r) > 8 and r[8] is not None else ""

                cursor.execute("""
                INSERT OR REPLACE INTO anotacoes (id, data, materia, topico, conteudo, tags, link, anexo_nome, anexo_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (aid, adata, materia, topico, conteudo, tags, link, anexo_nome, anexo_url))
                resumo["anotacoes"] += 1

        elif "tarefa" in norm:  # Tarefas
            for r in dados_linhas:
                if not r or r[0] is None:
                    continue
                tid = str(r[0]).strip()
                data_criacao = formatar_data(r[1] if len(r) > 1 else "", "%d/%m/%Y")
                titulo = str(r[2]).strip() if len(r) > 2 and r[2] is not None else ""
                categoria = str(r[3]).strip() if len(r) > 3 and r[3] is not None else ""
                status = str(r[4]).strip() if len(r) > 4 and r[4] is not None else "Pendente"
                prazo = formatar_data(r[5] if len(r) > 5 else "", "%Y-%m-%d")
                prioridade = str(r[6]).strip() if len(r) > 6 and r[6] is not None else "Média"
                descricao = str(r[7]) if len(r) > 7 and r[7] is not None else ""
                anexo_nome = str(r[8]).strip() if len(r) > 8 and r[8] is not None else ""
                anexo_url = str(r[9]).strip() if len(r) > 9 and r[9] is not None else ""

                cursor.execute("""
                INSERT OR REPLACE INTO tarefas (id, data_criacao, titulo, categoria, status, prazo, prioridade, descricao, anexo_nome, anexo_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (tid, data_criacao, titulo, categoria, status, prazo, prioridade, descricao, anexo_nome, anexo_url))
                resumo["tarefas"] += 1

        elif "curso" in norm:  # Cursos
            for r in dados_linhas:
                if not r or r[0] is None:
                    continue
                cid = str(r[0]).strip()
                nome = str(r[1]).strip() if len(r) > 1 and r[1] is not None else ""
                instituicao = str(r[2]).strip() if len(r) > 2 and r[2] is not None else ""
                categoria = str(r[3]).strip() if len(r) > 3 and r[3] is not None else ""
                carga_horaria = str(r[4]).strip() if len(r) > 4 and r[4] is not None else ""
                status = str(r[5]).strip() if len(r) > 5 and r[5] is not None else "Em Andamento"
                link = str(r[6]).strip() if len(r) > 6 and r[6] is not None else ""

                cursor.execute("""
                INSERT OR REPLACE INTO cursos (id, nome, instituicao, categoria, carga_horaria, status, link)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (cid, nome, instituicao, categoria, carga_horaria, status, link))
                resumo["cursos"] += 1

        elif "categoria" in norm:  # Categorias
            for r in dados_linhas:
                if not r or r[0] is None:
                    continue
                nome = str(r[0]).strip()
                if nome:
                    cursor.execute("INSERT OR IGNORE INTO categorias (nome) VALUES (?)", (nome,))
                    resumo["categorias"] += 1

        elif "flashcard" in norm:  # Flashcards
            for r in dados_linhas:
                if not r or r[0] is None:
                    continue
                fid = str(r[0]).strip()
                categoria = str(r[1]).strip() if len(r) > 1 and r[1] is not None else ""
                frente = str(r[2]).strip() if len(r) > 2 and r[2] is not None else ""
                verso = str(r[3]).strip() if len(r) > 3 and r[3] is not None else ""
                nivel = str(r[4]).strip() if len(r) > 4 and r[4] is not None else "Novo"
                ultima = formatar_data(r[5] if len(r) > 5 else "", "%d/%m/%Y")
                if not ultima:
                    ultima = "Nunca"

                cursor.execute("""
                INSERT OR REPLACE INTO flashcards (id, categoria, frente, verso, nivel, ultima_revisao)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (fid, categoria, frente, verso, nivel, ultima))
                resumo["flashcards"] += 1

        elif "pomo" in norm:  # Pomodoro
            for r in dados_linhas:
                if not r or r[0] is None:
                    continue
                pid = str(r[0]).strip()
                pdata = formatar_data(r[1] if len(r) > 1 else "", "%d/%m/%Y %H:%M")
                categoria = str(r[2]).strip() if len(r) > 2 and r[2] is not None else "Geral"
                try:
                    minutos = int(r[3]) if len(r) > 3 and r[3] is not None else 25
                except (ValueError, TypeError):
                    minutos = 25

                cursor.execute("""
                INSERT OR REPLACE INTO pomodoro (id, data, categoria, minutos)
                VALUES (?, ?, ?, ?)
                """, (pid, pdata, categoria, minutos))
                resumo["pomodoro"] += 1

    conn.commit()
    conn.close()
    return resumo

def importar_arquivo_json(caminho_arquivo: str):
    with open(caminho_arquivo, "r", encoding="utf-8") as f:
        dados = json.load(f)

    resumo = {
        "anotacoes": 0,
        "tarefas": 0,
        "cursos": 0,
        "categorias": 0,
        "flashcards": 0,
        "pomodoro": 0
    }

    conn = get_connection()
    cursor = conn.cursor()

    if "categorias" in dados:
        for c in dados["categorias"]:
            nome = c if isinstance(c, str) else c.get("nome")
            if nome:
                cursor.execute("INSERT OR IGNORE INTO categorias (nome) VALUES (?)", (nome.strip(),))
                resumo["categorias"] += 1

    if "anotacoes" in dados:
        for a in dados["anotacoes"]:
            cursor.execute("""
            INSERT OR REPLACE INTO anotacoes (id, data, materia, topico, conteudo, tags, link, anexo_nome, anexo_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                a.get("id"),
                a.get("data", ""),
                a.get("materia", ""),
                a.get("topico", ""),
                a.get("conteudo", ""),
                a.get("tags", ""),
                a.get("link", ""),
                a.get("anexoNome", a.get("anexo_nome", "")),
                a.get("anexoUrl", a.get("anexo_url", ""))
            ))
            resumo["anotacoes"] += 1

    if "tarefas" in dados:
        for t in dados["tarefas"]:
            cursor.execute("""
            INSERT OR REPLACE INTO tarefas (id, data_criacao, titulo, categoria, status, prazo, prioridade, descricao, anexo_nome, anexo_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                t.get("id"),
                t.get("dataCriacao", t.get("data_criacao", "")),
                t.get("titulo", ""),
                t.get("categoria", ""),
                t.get("status", "Pendente"),
                t.get("prazo", ""),
                t.get("prioridade", "Média"),
                t.get("descricao", ""),
                t.get("anexoNome", t.get("anexo_nome", "")),
                t.get("anexoUrl", t.get("anexo_url", ""))
            ))
            resumo["tarefas"] += 1

    if "cursos" in dados:
        for c in dados["cursos"]:
            cursor.execute("""
            INSERT OR REPLACE INTO cursos (id, nome, instituicao, categoria, carga_horaria, status, link)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                c.get("id"),
                c.get("nome", ""),
                c.get("instituicao", ""),
                c.get("categoria", ""),
                c.get("cargaHoraria", c.get("carga_horaria", "")),
                c.get("status", "Em Andamento"),
                c.get("link", "")
            ))
            resumo["cursos"] += 1

    if "flashcards" in dados:
        for f in dados["flashcards"]:
            cursor.execute("""
            INSERT OR REPLACE INTO flashcards (id, categoria, frente, verso, nivel, ultima_revisao)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (
                f.get("id"),
                f.get("categoria", ""),
                f.get("frente", ""),
                f.get("verso", ""),
                f.get("nivel", "Novo"),
                f.get("ultimaRevisao", f.get("ultima_revisao", "Nunca"))
            ))
            resumo["flashcards"] += 1

    if "pomodoro" in dados:
        for p in dados["pomodoro"]:
            cursor.execute("""
            INSERT OR REPLACE INTO pomodoro (id, data, categoria, minutos)
            VALUES (?, ?, ?, ?)
            """, (
                p.get("id"),
                p.get("data", ""),
                p.get("categoria", "Geral"),
                int(p.get("minutos", 25))
            ))
            resumo["pomodoro"] += 1

    conn.commit()
    conn.close()
    return resumo

def exportar_todos_dados():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT nome FROM categorias ORDER BY id ASC")
    categorias = [r[0] for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM anotacoes ORDER BY rowid DESC")
    anotacoes = [
        {
            "id": r["id"], "data": r["data"], "materia": r["materia"], "topico": r["topico"],
            "conteudo": r["conteudo"], "tags": r["tags"], "link": r["link"],
            "anexoNome": r["anexo_nome"] or "", "anexoUrl": r["anexo_url"] or ""
        } for r in cursor.fetchall()
    ]

    cursor.execute("SELECT * FROM tarefas ORDER BY rowid DESC")
    tarefas = [
        {
            "id": r["id"], "dataCriacao": r["data_criacao"], "titulo": r["titulo"],
            "categoria": r["categoria"], "status": r["status"], "prazo": r["prazo"],
            "prioridade": r["prioridade"], "descricao": r["descricao"] or "",
            "anexoNome": r["anexo_nome"] or "", "anexoUrl": r["anexo_url"] or ""
        } for r in cursor.fetchall()
    ]

    cursor.execute("SELECT * FROM cursos ORDER BY rowid DESC")
    cursos = [
        {
            "id": r["id"], "nome": r["nome"], "instituicao": r["instituicao"],
            "categoria": r["categoria"], "cargaHoraria": r["carga_horaria"],
            "status": r["status"], "link": r["link"]
        } for r in cursor.fetchall()
    ]

    cursor.execute("SELECT * FROM flashcards ORDER BY rowid DESC")
    flashcards = [
        {
            "id": r["id"], "categoria": r["categoria"], "frente": r["frente"],
            "verso": r["verso"], "nivel": r["nivel"], "ultimaRevisao": r["ultima_revisao"]
        } for r in cursor.fetchall()
    ]

    cursor.execute("SELECT * FROM pomodoro ORDER BY rowid DESC")
    pomodoro = [
        {
            "id": r["id"], "data": r["data"], "categoria": r["categoria"], "minutos": r["minutos"]
        } for r in cursor.fetchall()
    ]

    cursor.execute("SELECT * FROM midias ORDER BY rowid DESC")
    midias = [
        {
            "id": r["id"], "tipo": r["tipo"], "titulo": r["titulo"],
            "autorDiretor": r["autor_diretor"] or "", "ano": r["ano"] or "",
            "categoria": r["categoria"] or "", "status": r["status"] or "",
            "nota": r["nota"] or 0, "capaUrl": r["capa_url"] or "",
            "link": r["link"] or "", "resenha": r["resenha"] or "",
            "citacoes": r["citacoes"] or "", "dataCriacao": r["data_criacao"] or "",
            "dataConclusao": r["data_conclusao"] or ""
        } for r in cursor.fetchall()
    ]

    cursor.execute("SELECT * FROM habitos ORDER BY rowid ASC")
    habitos = [
        {
            "id": r["id"], "nome": r["nome"], "icone": r["icone"],
            "cor": r["cor"], "metaSemanal": r["meta_semanal"]
        } for r in cursor.fetchall()
    ]

    cursor.execute("SELECT * FROM habitos_registros")
    habitos_registros = [
        {"habitoId": r["habito_id"], "data": r["data"]} for r in cursor.fetchall()
    ]

    conn.close()

    return {
        "versao": "3.0",
        "geradoEm": datetime.now().isoformat(),
        "categorias": categorias,
        "anotacoes": anotacoes,
        "tarefas": tarefas,
        "cursos": cursos,
        "flashcards": flashcards,
        "pomodoro": pomodoro,
        "midias": midias,
        "habitos": habitos,
        "habitosRegistros": habitos_registros
    }
