import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "study_hub.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Tabela de Configurações
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS config (
        chave TEXT PRIMARY KEY,
        valor TEXT
    )
    """)

    # Tabela de Categorias
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS categorias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT UNIQUE NOT NULL
    )
    """)

    # Tabela de Anotações
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS anotacoes (
        id TEXT PRIMARY KEY,
        data TEXT,
        materia TEXT,
        topico TEXT,
        conteudo TEXT,
        tags TEXT,
        link TEXT,
        anexo_nome TEXT,
        anexo_url TEXT
    )
    """)

    # Tabela de Tarefas
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tarefas (
        id TEXT PRIMARY KEY,
        data_criacao TEXT,
        titulo TEXT,
        categoria TEXT,
        status TEXT,
        prazo TEXT,
        prioridade TEXT,
        descricao TEXT,
        anexo_nome TEXT,
        anexo_url TEXT
    )
    """)

    # Tabela de Cursos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cursos (
        id TEXT PRIMARY KEY,
        nome TEXT,
        instituicao TEXT,
        categoria TEXT,
        carga_horaria TEXT,
        status TEXT,
        link TEXT
    )
    """)

    # Tabela de Flashcards
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS flashcards (
        id TEXT PRIMARY KEY,
        categoria TEXT,
        frente TEXT,
        verso TEXT,
        nivel TEXT DEFAULT 'Novo',
        ultima_revisao TEXT DEFAULT 'Nunca'
    )
    """)

    # Tabela de Pomodoro
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pomodoro (
        id TEXT PRIMARY KEY,
        data TEXT,
        categoria TEXT,
        minutos INTEGER DEFAULT 25
    )
    """)

    # Tabela de Leituras, Reviews e Acervo de Mídias
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS midias (
        id TEXT PRIMARY KEY,
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

    # Tabela de Hábitos (Habit Tracker)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS habitos (
        id TEXT PRIMARY KEY,
        nome TEXT NOT NULL,
        icone TEXT DEFAULT 'fa-solid fa-fire',
        cor TEXT DEFAULT '#10b981',
        meta_semanal INTEGER DEFAULT 7
    )
    """)

    # Tabela de Registros Diários de Hábitos (data no formato YYYY-MM-DD)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS habitos_registros (
        habito_id TEXT NOT NULL,
        data TEXT NOT NULL,
        PRIMARY KEY (habito_id, data)
    )
    """)

    conn.commit()

    # Categorias padrão caso a tabela esteja vazia
    cursor.execute("SELECT COUNT(*) FROM categorias")
    if cursor.fetchone()[0] == 0:
        padrao = [
            "Engenharia de Computação (UNIVESP)",
            "DevOps / Cloud (Alura)",
            "Desenvolvimento de Software / Projetos",
            "Conhecimentos Gerais / Leituras",
            "Autoescola / DETRAN",
            "Atividade Física / Jiu-Jitsu",
            "Outros"
        ]
        for cat in padrao:
            cursor.execute("INSERT OR IGNORE INTO categorias (nome) VALUES (?)", (cat,))
        conn.commit()

    # Hábitos padrão caso a tabela esteja vazia
    cursor.execute("SELECT COUNT(*) FROM habitos")
    if cursor.fetchone()[0] == 0:
        habitos_padrao = [
            ("HAB-01", "Leitura Diária (20 pág.)", "fa-solid fa-book-open", "#f43f5e", 7),
            ("HAB-02", "Sessão de Foco (Pomodoro)", "fa-solid fa-stopwatch", "#6366f1", 5),
            ("HAB-03", "Revisar Flashcards", "fa-solid fa-layer-group", "#f59e0b", 5),
            ("HAB-04", "Estudo / Programação", "fa-solid fa-laptop-code", "#10b981", 5),
            ("HAB-05", "Atividade Física / Jiu-Jitsu", "fa-solid fa-dumbbell", "#0ea5e9", 4)
        ]
        for hid, hnome, hicone, hcor, hmeta in habitos_padrao:
            cursor.execute(
                "INSERT OR IGNORE INTO habitos (id, nome, icone, cor, meta_semanal) VALUES (?, ?, ?, ?, ?)",
                (hid, hnome, hicone, hcor, hmeta)
            )
        conn.commit()

    conn.close()

# Helpers para operações

def get_config(chave: str, default=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT valor FROM config WHERE chave = ?", (chave,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default

def set_config(chave: str, valor: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", (chave, valor))
    conn.commit()
    conn.close()

def get_todas_categorias():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT nome FROM categorias ORDER BY id ASC")
    rows = [r[0] for r in cursor.fetchall()]
    conn.close()
    return rows

def adicionar_categoria(nome: str):
    if not nome or not nome.strip():
        return False, "Nome inválido."
    nome = nome.strip()
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO categorias (nome) VALUES (?)", (nome,))
        conn.commit()
        return True, "Categoria criada com sucesso!"
    except sqlite3.IntegrityError:
        return False, "Esta categoria já existe!"
    finally:
        conn.close()

def get_dashboard():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM anotacoes")
    total_anotacoes = cursor.fetchone()[0]

    cursor.execute("SELECT status, categoria, COUNT(*) FROM tarefas GROUP BY status, categoria")
    tarefas_rows = cursor.fetchall()
    pendentes = 0
    concluidas = 0
    categorias_map = {}

    for row in tarefas_rows:
        status, cat, count = row[0], row[1], row[2]
        if status in ['Pendente', 'Em Andamento']:
            pendentes += count
        elif status == 'Concluído':
            concluidas += count
        if cat:
            categorias_map[cat] = categorias_map.get(cat, 0) + count

    cursor.execute("SELECT COUNT(*) FROM cursos WHERE status = 'Em Andamento'")
    cursos_andamento = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(minutos) FROM pomodoro")
    minutos_res = cursor.fetchone()[0]
    minutos_estudo = minutos_res if minutos_res else 0

    cursor.execute("SELECT COUNT(*) FROM midias")
    total_midias = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM midias WHERE status = 'Concluído'")
    midias_concluidas = cursor.fetchone()[0]

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
        "graficoCategorias": grafico
    }

def get_todas_midias(tipo_filtro=None, status_filtro=None):
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM midias WHERE 1=1"
    params = []
    if tipo_filtro:
        query += " AND tipo = ?"
        params.append(tipo_filtro)
    if status_filtro:
        query += " AND status = ?"
        params.append(status_filtro)
    query += " ORDER BY rowid DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    resultado = []
    for r in rows:
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
            "dataConclusao": r["data_conclusao"] or ""
        })
    return resultado

def salvar_midia_db(dados):
    import time
    conn = get_connection()
    cursor = conn.cursor()
    mid = dados.get("id")
    hoje = datetime.now().strftime("%d/%m/%Y")

    if mid:
        cursor.execute("""
        UPDATE midias
        SET tipo = ?, titulo = ?, autor_diretor = ?, ano = ?, categoria = ?,
            status = ?, nota = ?, capa_url = ?, link = ?, resenha = ?, citacoes = ?,
            data_conclusao = ?
        WHERE id = ?
        """, (
            dados.get("tipo", "Livro"),
            dados.get("titulo", ""),
            dados.get("autorDiretor", ""),
            dados.get("ano", ""),
            dados.get("categoria", ""),
            dados.get("status", "Quero Ler/Ver"),
            int(dados.get("nota", 0)),
            dados.get("capaUrl", ""),
            dados.get("link", ""),
            dados.get("resenha", ""),
            dados.get("citacoes", ""),
            dados.get("dataConclusao", hoje if dados.get("status") == "Concluído" else ""),
            mid
        ))
        conn.commit()
        conn.close()
        return {"success": True, "message": "Item atualizado com sucesso!", "id": mid}
    else:
        novo_id = f"MID-{str(int(time.time() * 1000))[-6:]}"
        data_criacao = hoje
        data_conclusao = hoje if dados.get("status") == "Concluído" else ""
        cursor.execute("""
        INSERT INTO midias (id, tipo, titulo, autor_diretor, ano, categoria, status, nota, capa_url, link, resenha, citacoes, data_criacao, data_conclusao)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            novo_id,
            dados.get("tipo", "Livro"),
            dados.get("titulo", ""),
            dados.get("autorDiretor", ""),
            dados.get("ano", ""),
            dados.get("categoria", ""),
            dados.get("status", "Quero Ler/Ver"),
            int(dados.get("nota", 0)),
            dados.get("capaUrl", ""),
            dados.get("link", ""),
            dados.get("resenha", ""),
            dados.get("citacoes", ""),
            data_criacao,
            data_conclusao
        ))
        conn.commit()
        conn.close()
        return {"success": True, "message": "Item adicionado ao seu acervo!", "id": novo_id}

def excluir_midia_db(mid):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM midias WHERE id = ?", (mid,))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Item removido com sucesso!"}

# ================= RASTREADOR DE HÁBITOS & GAMIFICAÇÃO =================

def get_habitos_dados():
    from datetime import timedelta
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM habitos ORDER BY rowid ASC")
    habitos_rows = cursor.fetchall()

    cursor.execute("SELECT habito_id, data FROM habitos_registros")
    reg_rows = cursor.fetchall()

    registros_por_habito = {}
    contagem_por_data = {}
    for r in reg_rows:
        hid, dt = r["habito_id"], r["data"]
        if hid not in registros_por_habito:
            registros_por_habito[hid] = set()
        registros_por_habito[hid].add(dt)
        contagem_por_data[dt] = contagem_por_data.get(dt, 0) + 1

    # Também soma pomodoros e anotações no heatmap para refletir toda atividade de estudo
    cursor.execute("SELECT data FROM pomodoro")
    for r in cursor.fetchall():
        dt_str = (r["data"] or "").split(" ")[0]
        if len(dt_str) == 10 and "/" in dt_str:
            partes = dt_str.split("/")
            dt_iso = f"{partes[2]}-{partes[1]}-{partes[0]}"
            contagem_por_data[dt_iso] = contagem_por_data.get(dt_iso, 0) + 1

    cursor.execute("SELECT data FROM anotacoes")
    for r in cursor.fetchall():
        dt_str = (r["data"] or "").split(" ")[0]
        if len(dt_str) == 10 and "/" in dt_str:
            partes = dt_str.split("/")
            dt_iso = f"{partes[2]}-{partes[1]}-{partes[0]}"
            contagem_por_data[dt_iso] = contagem_por_data.get(dt_iso, 0) + 1

    hoje = datetime.now().date()
    hoje_str = hoje.strftime("%Y-%m-%d")

    # Últimos 7 dias (do mais antigo para hoje)
    ultimos_7_dias = []
    nomes_dias = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    for i in range(6, -1, -1):
        d = hoje - timedelta(days=i)
        d_str = d.strftime("%Y-%m-%d")
        ultimos_7_dias.append({
            "data": d_str,
            "diaMes": d.strftime("%d/%m"),
            "diaSemana": "Hoje" if i == 0 else nomes_dias[d.weekday()]
        })

    habitos_lista = []
    concluidos_hoje = 0
    for h in habitos_rows:
        hid = h["id"]
        datas_feitas = registros_por_habito.get(hid, set())
        if hoje_str in datas_feitas:
            concluidos_hoje += 1

        # Calcula streak do hábito
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
            "historico7d": historico_7d
        })

    # Streak global de estudos (dias consecutivos com pelo menos 1 atividade)
    streak_global = 0
    dia_g = hoje
    if contagem_por_data.get(dia_g.strftime("%Y-%m-%d"), 0) == 0:
        dia_g = hoje - timedelta(days=1)
    while contagem_por_data.get(dia_g.strftime("%Y-%m-%d"), 0) > 0:
        streak_global += 1
        dia_g -= timedelta(days=1)

    # Heatmap dos últimos 140 dias (20 semanas)
    heatmap = []
    for i in range(139, -1, -1):
        d = hoje - timedelta(days=i)
        d_str = d.strftime("%Y-%m-%d")
        heatmap.append({
            "data": d_str,
            "dataFmt": d.strftime("%d/%m/%Y"),
            "count": contagem_por_data.get(d_str, 0)
        })

    # Desafio de leitura anual
    cursor.execute("SELECT COUNT(*) FROM midias WHERE tipo = 'Livro' AND status = 'Concluído'")
    livros_concluidos = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM midias WHERE status = 'Concluído'")
    midias_concluidas = cursor.fetchone()[0]

    conn.close()

    meta_livros = int(get_config("META_LIVROS_ANO", "12") or 12)

    return {
        "habitos": habitos_lista,
        "diasSemana": ultimos_7_dias,
        "concluidosHoje": concluidos_hoje,
        "totalHabitos": len(habitos_lista),
        "streakGlobal": streak_global,
        "heatmap": heatmap,
        "livrosConcluidos": livros_concluidos,
        "midiasConcluidas": midias_concluidas,
        "metaLivrosAno": meta_livros
    }

def salvar_habito_db(dados):
    import time
    conn = get_connection()
    cursor = conn.cursor()
    hid = dados.get("id") or f"HAB-{str(int(time.time() * 1000))[-5:]}"
    nome = (dados.get("nome") or "").strip()
    if not nome:
        conn.close()
        return {"success": False, "message": "Informe o nome do hábito."}

    icone = dados.get("icone") or "fa-solid fa-fire"
    cor = dados.get("cor") or "#10b981"
    meta = int(dados.get("metaSemanal") or 7)

    cursor.execute("""
    INSERT OR REPLACE INTO habitos (id, nome, icone, cor, meta_semanal)
    VALUES (?, ?, ?, ?, ?)
    """, (hid, nome, icone, cor, meta))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Hábito salvo com sucesso!", "id": hid}

def alternar_registro_habito_db(habito_id: str, data_str: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM habitos_registros WHERE habito_id = ? AND data = ?", (habito_id, data_str))
    existe = cursor.fetchone()
    if existe:
        cursor.execute("DELETE FROM habitos_registros WHERE habito_id = ? AND data = ?", (habito_id, data_str))
        marcado = False
    else:
        cursor.execute("INSERT INTO habitos_registros (habito_id, data) VALUES (?, ?)", (habito_id, data_str))
        marcado = True
    conn.commit()
    conn.close()
    return {"success": True, "marcado": marcado}

def excluir_habito_db(habito_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM habitos WHERE id = ?", (habito_id,))
    cursor.execute("DELETE FROM habitos_registros WHERE habito_id = ?", (habito_id,))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Hábito removido!"}

def salvar_meta_leitura_db(meta: int):
    set_config("META_LIVROS_ANO", str(max(1, int(meta))))
    return {"success": True, "message": "Meta anual de leitura atualizada!"}

# ================= GRAFO DE CONHECIMENTO & BACKLINKS =================

def get_grafo_conhecimento():
    import re
    conn = get_connection()
    cursor = conn.cursor()

    nodes = []
    edges = []
    node_ids = set()

    # 1. Categorias (Hubs centrais)
    cursor.execute("SELECT nome FROM categorias")
    for r in cursor.fetchall():
        cat = r["nome"]
        nid = f"CAT:{cat}"
        node_ids.add(nid)
        nodes.append({
            "id": nid,
            "label": cat,
            "group": "categoria",
            "val": 18
        })

    # Mapa de títulos para resolução de [[Backlinks]]
    titulo_para_id = {}

    # 2. Anotações
    cursor.execute("SELECT id, topico, materia, conteudo, tags FROM anotacoes")
    anotacoes = cursor.fetchall()
    for a in anotacoes:
        aid = a["id"]
        topico = a["topico"] or "Sem título"
        materia = a["materia"] or "Outros"
        node_ids.add(aid)
        titulo_para_id[topico.strip().lower()] = aid
        nodes.append({
            "id": aid,
            "label": topico,
            "group": "anotacao",
            "categoria": materia,
            "rawId": aid,
            "val": 11
        })
        cat_id = f"CAT:{materia}"
        if cat_id in node_ids:
            edges.append({"from": aid, "to": cat_id, "type": "categoria"})

    # 3. Leituras & Mídias
    cursor.execute("SELECT id, titulo, tipo, categoria, resenha FROM midias")
    midias = cursor.fetchall()
    for m in midias:
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
            "val": 12
        })
        cat_id = f"CAT:{cat}"
        if cat_id in node_ids:
            edges.append({"from": mid, "to": cat_id, "type": "categoria"})

    # 4. Cursos
    cursor.execute("SELECT id, nome, categoria FROM cursos")
    for c in cursor.fetchall():
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
            "val": 11
        })
        cat_id = f"CAT:{cat}"
        if cat_id in node_ids:
            edges.append({"from": cid, "to": cat_id, "type": "categoria"})

    # 5. Extrai [[Backlinks]] explícitos e conexões por Tags
    padrao_backlink = re.compile(r'\[\[([^\]]+)\]\]')
    tags_map = {}

    for a in anotacoes:
        aid = a["id"]
        conteudo = a["conteudo"] or ""
        # Backlinks [[...]]
        matches = padrao_backlink.findall(conteudo)
        for m_texto in matches:
            alvo_key = m_texto.strip().lower()
            alvo_id = titulo_para_id.get(alvo_key)
            if alvo_id and alvo_id != aid:
                edges.append({
                    "from": aid,
                    "to": alvo_id,
                    "type": "backlink",
                    "label": "cita"
                })

        # Tags compartilhadas
        raw_tags = a["tags"] or ""
        for t in raw_tags.split(","):
            t_clean = t.strip().lower()
            if t_clean:
                tags_map.setdefault(t_clean, []).append(aid)

    for m in midias:
        mid = m["id"]
        resenha = m["resenha"] or ""
        matches = padrao_backlink.findall(resenha)
        for m_texto in matches:
            alvo_key = m_texto.strip().lower()
            alvo_id = titulo_para_id.get(alvo_key)
            if alvo_id and alvo_id != mid:
                edges.append({
                    "from": mid,
                    "to": alvo_id,
                    "type": "backlink",
                    "label": "cita"
                })

    # Arestas entre notas que compartilham a mesma tag
    for tag, ids in tags_map.items():
        if len(ids) > 1:
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    edges.append({
                        "from": ids[i],
                        "to": ids[j],
                        "type": "tag",
                        "label": f"#{tag}"
                    })

    conn.close()
    return {"nodes": nodes, "edges": edges}


