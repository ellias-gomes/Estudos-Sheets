import os
import json
import sqlite3
import openpyxl
import db

# Usa um banco isolado durante os testes automatizados para nunca alterar o study_hub.db real
TEST_DB = os.path.join(os.path.dirname(__file__), "study_hub_test.db")
for p in [TEST_DB, f"{TEST_DB}.pre_multiuser.bak"]:
    if os.path.exists(p):
        os.remove(p)
db.DB_PATH = TEST_DB

from fastapi.testclient import TestClient
from app import app
from db import init_db, get_connection

init_db()
anon_client = TestClient(app)
client = TestClient(app)

# Autentica a conta principal migrada (eu.elliasaugusto@gmail.com) definindo senha de 1º acesso
_res_login_inicial = client.post(
    "/api/auth/login",
    json={"email": "eu.elliasaugusto@gmail.com", "senha": "qualquer"},
)
assert _res_login_inicial.status_code == 200
assert _res_login_inicial.json().get("requirePasswordSetup") is True

_res_setup = client.post(
    "/api/auth/definirSenhaInicial",
    json={
        "email": "eu.elliasaugusto@gmail.com",
        "senha": "SenhaOwner123",
        "nome": "Ellias Augusto",
    },
)
assert _res_setup.status_code == 200
assert _res_setup.json()["success"] is True
OWNER_USER = _res_setup.json()["user"]
OWNER_ID = OWNER_USER["id"]
assert OWNER_USER["isAdmin"] is True


def test_home():
    res = client.get("/")
    assert res.status_code == 200
    assert "Study Hub" in res.text
    print("✅ Teste 1: Página inicial carregada com sucesso!")


def test_categorias():
    res = client.post("/api/getCategorias", json=[])
    assert res.status_code == 200
    cats = res.json()
    assert len(cats) >= 7
    print(f"✅ Teste 2: Categorias obtidas com sucesso ({len(cats)} categorias)!")

    import uuid
    nova_cat = "Categoria " + str(uuid.uuid4())[:8]
    res_add = client.post("/api/salvarCategoria", json=[nova_cat])
    assert res_add.status_code == 200
    assert res_add.json()["success"] is True
    print("✅ Teste 3: Nova categoria salva com sucesso!")


def test_anotacoes():
    dados = {
        "materia": "Engenharia de Computação (UNIVESP)",
        "topico": "Estruturas de Dados",
        "conteudo": "<p>Anotação de teste sobre árvores binárias.</p>",
        "tags": "estrutura, algoritmos",
        "link": "https://univesp.br",
    }
    res = client.post("/api/salvarAnotacao", json=[dados])
    assert res.status_code == 200
    assert res.json()["success"] is True

    res_list = client.post("/api/getAnotacoes", json=[])
    anotacoes = res_list.json()
    assert len(anotacoes) > 0
    assert anotacoes[0]["topico"] == "Estruturas de Dados"
    print(f"✅ Teste 4: Anotação criada e listada ({len(anotacoes)} anotações)!")


def test_tarefas():
    dados = {
        "titulo": "Implementar migração local",
        "descricao": "Migrar do GAS para FastAPI e SQLite",
        "categoria": "DevOps / Cloud (Alura)",
        "prazo": "2026-10-28",
        "prioridade": "Alta",
        "status": "Em Andamento",
    }
    res = client.post("/api/salvarTarefa", json=[dados])
    assert res.status_code == 200
    assert res.json()["success"] is True

    res_list = client.post("/api/getTarefas", json=[])
    tarefas = res_list.json()
    assert len(tarefas) > 0
    tid = tarefas[0]["id"]

    res_status = client.post("/api/atualizarStatusTarefa", json=[tid, "Concluído"])
    assert res_status.status_code == 200
    assert res_status.json()["success"] is True
    print("✅ Teste 5: Tarefa criada, listada e status atualizado com sucesso!")


def test_pomodoro():
    res = client.post("/api/registrarSessaoPomodoro", json=["Desenvolvimento de Software / Projetos", 25])
    assert res.status_code == 200
    assert res.json()["success"] is True
    print("✅ Teste 6: Sessão Pomodoro registrada com sucesso!")


def test_dashboard():
    res = client.post("/api/getDashboardData", json=[])
    assert res.status_code == 200
    data = res.json()
    assert data["anotacoes"] >= 1
    assert data["concluidas"] >= 1
    assert data["minutosEstudo"] >= 25
    print(f"✅ Teste 7: Dashboard calculado perfeitamente: {data}")


def test_exportar_backup():
    res = client.get("/api/exportarBackup")
    assert res.status_code == 200
    backup = res.json()
    assert "anotacoes" in backup
    assert "tarefas" in backup
    print("✅ Teste 8: Exportação de Backup JSON funcionando 100%!")


def test_importar_xlsx():
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    ws_anot = wb.create_sheet("Anotações")
    ws_anot.append(["ID", "Data", "Matéria/Categoria", "Tópico", "Conteúdo", "Tags", "Link", "AnexoNome", "AnexoUrl"])
    ws_anot.append(["NOTE-999", "27/10/2026 20:00", "DevOps / Cloud (Alura)", "Docker e K8s", "<p>Containerização avançada</p>", "docker", "", "", ""])

    ws_tar = wb.create_sheet("Tarefas")
    ws_tar.append(["ID", "Data Criação", "Título", "Categoria", "Status", "Prazo", "Prioridade", "Descrição", "AnexoNome", "AnexoUrl"])
    ws_tar.append(["TASK-999", "27/10/2026", "Estudar Docker", "DevOps / Cloud (Alura)", "Pendente", "2026-11-01", "Alta", "Módulo 3", "", ""])

    ws_cur = wb.create_sheet("Cursos")
    ws_cur.append(["ID", "Nome", "Instituição", "Categoria", "Carga Horária", "Status", "Link"])
    ws_cur.append(["CRS-999", "Kubernetes Avançado", "Alura", "DevOps / Cloud (Alura)", "40", "Em Andamento", "https://alura.com.br"])

    ws_fc = wb.create_sheet("Flashcards")
    ws_fc.append(["ID", "Categoria", "Frente", "Verso", "Nivel", "UltimaRevisao"])
    ws_fc.append(["FC-999", "DevOps / Cloud (Alura)", "O que é um Pod no K8s?", "Menor unidade de implantação", "Novo", "Nunca"])

    ws_pomo = wb.create_sheet("Pomodoro")
    ws_pomo.append(["ID", "Data", "Categoria", "Minutos"])
    ws_pomo.append(["POMO-999", "27/10/2026 19:30", "DevOps / Cloud (Alura)", 50])

    teste_xlsx = "teste_importacao.xlsx"
    wb.save(teste_xlsx)

    with open(teste_xlsx, "rb") as f:
        res = client.post(
            "/api/importarPlanilha",
            files={"arquivo": ("teste_importacao.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )

    if os.path.exists(teste_xlsx):
        os.remove(teste_xlsx)

    assert res.status_code == 200
    res_json = res.json()
    assert res_json["success"] is True
    print(f"✅ Teste 9: Importação da Planilha Google Sheets testada e aprovada: {res_json['message']}")


def test_midias():
    dados = {
        "tipo": "Livro",
        "titulo": "Clean Code",
        "autorDiretor": "Robert C. Martin",
        "ano": "2008",
        "categoria": "Desenvolvimento de Software / Projetos",
        "status": "Concluído",
        "nota": 5,
        "capaUrl": "https://covers.openlibrary.org/b/id/8065615-L.jpg",
        "link": "https://openlibrary.org",
        "resenha": "Livro fundamental para quem deseja programar com clareza e manutenibilidade.",
        "citacoes": "Qualquer tolo pode escrever código que um computador entenda. Bons programadores escrevem código que humanos podem entender.",
    }
    res_salvar = client.post("/api/salvarMidia", json=[dados])
    assert res_salvar.status_code == 200
    assert res_salvar.json()["success"] is True

    res_list = client.post("/api/getMidias", json=[])
    assert res_list.status_code == 200
    midias = res_list.json()
    assert len(midias) > 0
    assert midias[0]["titulo"] == "Clean Code"
    assert midias[0]["nota"] == 5
    print(f"✅ Teste 10: Módulo de Leituras/Reviews salvo e listado com sucesso ({len(midias)} obras)!")

    res_meta = client.post("/api/buscarMetadadosMidia", json=["Livro", "Clean Code"])
    assert res_meta.status_code == 200
    print(f"✅ Teste 11: Busca automática de metadados testada com sucesso: {res_meta.json().get('titulo')}")


def test_google_calendar():
    res_eventos = client.post("/api/getEventosGoogleCalendar", json=[])
    assert res_eventos.status_code == 200
    assert isinstance(res_eventos.json(), list)

    res_sync = client.post("/api/sincronizarGoogleCalendar", json=[])
    assert res_sync.status_code == 200
    print(f"✅ Teste 12: Integração Google Calendar testada com resposta elegante: {res_sync.json().get('message')}")


def test_habitos_e_gamificacao():
    res = client.post("/api/getHabitosDados", json=[])
    assert res.status_code == 200
    dados = res.json()
    assert len(dados["habitos"]) >= 5
    hoje_str = dados["diasSemana"][-1]["data"]
    hab_id = dados["habitos"][0]["id"]

    res_toggle = client.post("/api/alternarRegistroHabito", json=[hab_id, hoje_str])
    assert res_toggle.status_code == 200
    assert res_toggle.json()["marcado"] is True

    res_check = client.post("/api/getHabitosDados", json=[])
    dados_atualizados = res_check.json()
    assert dados_atualizados["concluidosHoje"] >= 1
    assert dados_atualizados["streakGlobal"] >= 1
    print(f"✅ Teste 13: Rastreador de Hábitos & Heatmap funcionando! Streak Global: {dados_atualizados['streakGlobal']}d")


def test_grafo_e_backlinks():
    nota_conectada = {
        "materia": "Desenvolvimento de Software / Projetos",
        "topico": "Arquitetura Limpa na Prática",
        "conteudo": "<p>Aplicando os princípios de [[Clean Code]] junto com [[Estruturas de Dados]].</p>",
        "tags": "arquitetura, estrutura",
        "link": "",
    }
    client.post("/api/salvarAnotacao", json=[nota_conectada])

    res_grafo = client.post("/api/getGrafoConhecimento", json=[])
    assert res_grafo.status_code == 200
    grafo = res_grafo.json()
    assert len(grafo["nodes"]) >= 5
    backlink_edges = [e for e in grafo["edges"] if e.get("type") == "backlink"]
    assert len(backlink_edges) >= 2
    print(f"✅ Teste 14: Grafo de Conhecimento & [[Backlinks]] validados ({len(grafo['nodes'])} nós, {len(backlink_edges)} backlinks explícitos)!")


def test_info_rede_mobile():
    res = client.get("/api/infoRede")
    assert res.status_code == 200
    info = res.json()
    assert "urlRede" in info
    print(f"✅ Teste 15: Acesso Mobile Wi-Fi configurado em: {info['urlRede']}")


def test_subcategorias_e_anotacoes_subcategoria():
    cat = "Engenharia de Computação (UNIVESP)"
    res_sub = client.post("/api/salvarSubcategoria", json=[cat, "Cálculo I"])
    assert res_sub.status_code == 200
    assert res_sub.json()["success"] is True

    res_dup = client.post("/api/salvarSubcategoria", json=[cat, "Cálculo I"])
    assert res_dup.status_code == 200
    assert res_dup.json()["success"] is False

    res_all = client.post("/api/getSubcategorias", json=[])
    assert res_all.status_code == 200
    assert any(s["categoria"] == cat and s["nome"] == "Cálculo I" for s in res_all.json())

    res_filt = client.post("/api/getSubcategorias", json=[cat])
    assert res_filt.status_code == 200
    assert all(s["categoria"] == cat for s in res_filt.json())

    nota = {
        "materia": cat,
        "subcategoria": "Física Geral",
        "topico": "Leis de Newton",
        "conteudo": "<p>Resumo sobre cinemática e dinâmica.</p>",
        "tags": "fisica, mecanica",
        "link": "",
    }
    res_nota = client.post("/api/salvarAnotacao", json=[nota])
    assert res_nota.status_code == 200
    assert res_nota.json()["success"] is True

    notas = client.post("/api/getAnotacoes", json=[]).json()
    nota_fisica = next(n for n in notas if n["topico"] == "Leis de Newton")
    assert nota_fisica["subcategoria"] == "Física Geral"

    subs_cat = client.post("/api/getSubcategorias", json=[cat]).json()
    sub_fisica = next((s for s in subs_cat if s["nome"] == "Física Geral"), None)
    assert sub_fisica is not None

    nota_edit = dict(nota_fisica)
    nota_edit["subcategoria"] = "Cálculo I"
    res_edit = client.post("/api/salvarAnotacao", json=[nota_edit])
    assert res_edit.status_code == 200 and res_edit.json()["success"] is True

    notas_pos_edit = client.post("/api/getAnotacoes", json=[]).json()
    nota_atualizada = next(n for n in notas_pos_edit if n["id"] == nota_fisica["id"])
    assert nota_atualizada["subcategoria"] == "Cálculo I"

    grafo = client.post("/api/getGrafoConhecimento", json=[]).json()
    assert any(n.get("group") == "subcategoria" and n.get("label") == "Cálculo I" for n in grafo["nodes"])
    assert any(e.get("type") == "subcategoria" for e in grafo["edges"])

    sub_calc = next(s for s in subs_cat if s["nome"] == "Cálculo I")
    res_del = client.post("/api/excluirSubcategoria", json=[sub_calc["id"]])
    assert res_del.status_code == 200 and res_del.json()["success"] is True

    subs_depois = client.post("/api/getSubcategorias", json=[cat]).json()
    assert not any(s["id"] == sub_calc["id"] for s in subs_depois)

    notas_depois = client.post("/api/getAnotacoes", json=[]).json()
    nota_preservada = next(n for n in notas_depois if n["id"] == nota_fisica["id"])
    assert nota_preservada["subcategoria"] == ""
    print("✅ Teste 16: Subcategorias nas Anotações (CRUD, auto-registro, grafo e exclusão segura) aprovadas!")


def test_eisenhower_tarefas():
    res_q1 = client.post("/api/salvarTarefa", json=[{
        "titulo": "Entregar lista de exercícios",
        "descricao": "Prazo hoje",
        "categoria": "Engenharia de Computação (UNIVESP)",
        "prazo": "2026-11-21",
        "prioridade": "Alta",
        "status": "Pendente",
        "eisenhower": "fazer",
    }])
    assert res_q1.status_code == 200 and res_q1.json()["success"] is True

    res_inbox = client.post("/api/salvarTarefa", json=[{
        "titulo": "Organizar bookmarks",
        "descricao": "",
        "categoria": "Outros",
        "prazo": "",
        "prioridade": "Baixa",
        "status": "Pendente",
    }])
    assert res_inbox.status_code == 200 and res_inbox.json()["success"] is True

    tarefas = client.post("/api/getTarefas", json=[]).json()
    t_q1 = next(t for t in tarefas if t["titulo"] == "Entregar lista de exercícios")
    t_inbox = next(t for t in tarefas if t["titulo"] == "Organizar bookmarks")
    assert t_q1["eisenhower"] == "fazer"
    assert t_inbox["eisenhower"] == ""

    for q in ["agendar", "delegar", "eliminar", ""]:
        res_mv = client.post("/api/atualizarEisenhowerTarefa", json=[t_inbox["id"], q])
        assert res_mv.status_code == 200 and res_mv.json()["success"] is True
        lista = client.post("/api/getTarefas", json=[]).json()
        atual = next(t for t in lista if t["id"] == t_inbox["id"])
        assert atual["eisenhower"] == q

    res_inv = client.post("/api/atualizarEisenhowerTarefa", json=[t_inbox["id"], "invalido"])
    assert res_inv.status_code == 200
    assert res_inv.json()["success"] is False
    print("✅ Teste 17: Matriz de Eisenhower nas Tarefas (criação, transição entre quadrantes e validação) aprovada!")


def test_backup_json_novos_campos():
    from importer import importar_arquivo_json

    client.post("/api/salvarAnotacao", json=[{
        "materia": "DevOps / Cloud (Alura)",
        "subcategoria": "Kubernetes",
        "topico": "Ingress Controllers",
        "conteudo": "<p>Roteamento L7</p>",
        "tags": "k8s",
        "link": "",
    }])

    res_exp = client.get("/api/exportarBackup")
    assert res_exp.status_code == 200
    backup = res_exp.json()
    assert "subcategorias" in backup
    assert any(s["nome"] == "Kubernetes" for s in backup["subcategorias"])
    assert any(a.get("subcategoria") == "Kubernetes" for a in backup["anotacoes"])
    assert any(t.get("eisenhower") == "fazer" for t in backup["tarefas"])

    temp_json = os.path.join(os.path.dirname(__file__), "teste_backup_v31.json")
    backup["subcategorias"].append({"categoria": "Outros", "nome": "Sub Importada"})
    backup["anotacoes"].append({
        "id": "NOTE-IMP-31",
        "data": "21/11/2026 20:00",
        "materia": "Outros",
        "subcategoria": "Sub Importada",
        "topico": "Nota Importada v3.1",
        "conteudo": "<p>Conteúdo</p>",
        "tags": "",
        "link": "",
        "anexoNome": "",
        "anexoUrl": "",
    })
    backup["tarefas"].append({
        "id": "TASK-IMP-31",
        "dataCriacao": "21/11/2026",
        "titulo": "Tarefa Importada v3.1",
        "categoria": "Outros",
        "status": "Pendente",
        "prazo": "",
        "prioridade": "Média",
        "descricao": "",
        "anexoNome": "",
        "anexoUrl": "",
        "eisenhower": "agendar",
    })
    with open(temp_json, "w", encoding="utf-8") as f:
        json.dump(backup, f, ensure_ascii=False)

    try:
        importar_arquivo_json(temp_json, OWNER_ID)
        notas = client.post("/api/getAnotacoes", json=[]).json()
        tarefas = client.post("/api/getTarefas", json=[]).json()
        subs = client.post("/api/getSubcategorias", json=["Outros"]).json()
        assert any(n["id"] == "NOTE-IMP-31" and n["subcategoria"] == "Sub Importada" for n in notas)
        assert any(t["id"] == "TASK-IMP-31" and t["eisenhower"] == "agendar" for t in tarefas)
        assert any(s["nome"] == "Sub Importada" for s in subs)
    finally:
        if os.path.exists(temp_json):
            os.remove(temp_json)
    print("✅ Teste 18: Exportação e Importação JSON com subcategorias e quadrantes Eisenhower aprovadas!")


def test_migracao_banco_legado():
    legacy_db = os.path.join(os.path.dirname(__file__), "study_hub_legacy_test.db")
    legacy_bak = f"{legacy_db}.pre_multiuser.bak"
    for p in [legacy_db, legacy_bak]:
        if os.path.exists(p):
            os.remove(p)

    conn = sqlite3.connect(legacy_db)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE anotacoes (
        id TEXT PRIMARY KEY, data TEXT, materia TEXT, topico TEXT,
        conteudo TEXT, tags TEXT, link TEXT, anexo_nome TEXT, anexo_url TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE tarefas (
        id TEXT PRIMARY KEY, data_criacao TEXT, titulo TEXT, categoria TEXT,
        status TEXT, prazo TEXT, prioridade TEXT, descricao TEXT, anexo_nome TEXT, anexo_url TEXT
    )
    """)
    cur.execute("INSERT INTO anotacoes VALUES ('NOTE-OLD', '01/01/2026', 'Outros', 'Nota Antiga', '<p>Ok</p>', '', '', '', '')")
    cur.execute("INSERT INTO tarefas VALUES ('TASK-OLD', '01/01/2026', 'Tarefa Antiga', 'Outros', 'Pendente', '', 'Média', '', '', '')")
    conn.commit()
    conn.close()

    old_path = db.DB_PATH
    try:
        db.DB_PATH = legacy_db
        init_db()

        conn2 = sqlite3.connect(legacy_db)
        cur2 = conn2.cursor()
        anot_cols = {r[1] for r in cur2.execute("PRAGMA table_info(anotacoes)").fetchall()}
        tar_cols = {r[1] for r in cur2.execute("PRAGMA table_info(tarefas)").fetchall()}
        tables = {r[0] for r in cur2.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "subcategoria" in anot_cols
        assert "user_id" in anot_cols
        assert "eisenhower" in tar_cols
        assert "user_id" in tar_cols
        assert "subcategorias" in tables
        assert "usuarios" in tables

        owner_row = cur2.execute("SELECT id, is_admin, precisa_definir_senha FROM usuarios WHERE email='eu.elliasaugusto@gmail.com'").fetchone()
        assert owner_row is not None and owner_row[1] == 1 and owner_row[2] == 1
        anot_row = cur2.execute("SELECT topico, subcategoria, user_id FROM anotacoes WHERE id='NOTE-OLD'").fetchone()
        tar_row = cur2.execute("SELECT titulo, eisenhower, user_id FROM tarefas WHERE id='TASK-OLD'").fetchone()
        assert anot_row[0] == "Nota Antiga" and (anot_row[1] or "") == "" and anot_row[2] == owner_row[0]
        assert tar_row[0] == "Tarefa Antiga" and (tar_row[1] or "") == "" and tar_row[2] == owner_row[0]
        conn2.close()
    finally:
        db.DB_PATH = old_path
        for p in [legacy_db, legacy_bak]:
            if os.path.exists(p):
                os.remove(p)
    print("✅ Teste 19: Migração segura de banco legado validada (dados preservados + novas colunas/tabela criadas)!")


def test_frontend_elementos_novos():
    html = client.get("/").text
    for elem_id in [
        "view-eisenhower",
        "menu-eisenhower",
        "filtroSubcategoriaAnotacao",
        "filtroCategoriaTarefa",
        "containerCategoriasTarefas",
        "modalSubcategoria",
        "subcategoriaAnotacao",
        "eisenhowerTarefa",
        "btnAlternarTema",
        "alternarTema",
        "study_hub_tema",
        "html.dark",
        'name="viewport"',
        "mobileBottomNav",
        "modalAcaoRapidaMobile",
        "tabelaTarefasMobile",
        "alternarAbaEditorMobile",
    ]:
        assert elem_id in html, f"Elemento esperado ausente no HTML: {elem_id}"
    print("✅ Teste 20: Todos os elementos de interface novos presentes no frontend!")


# ================= NOVOS TESTES: AUTENTICAÇÃO, MIGRAÇÃO, ISOLAMENTO E COMPARTILHAMENTO =================

def test_protecao_nao_autenticado():
    me = anon_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["authenticated"] is False

    assert anon_client.post("/api/getAnotacoes", json=[]).status_code == 401
    assert anon_client.get("/api/exportarBackup").status_code == 401
    assert anon_client.get("/api/infoRede").status_code == 401
    assert anon_client.get("/api/statusDrive").status_code == 401
    assert anon_client.get("/uploads/teste.txt").status_code == 401
    print("✅ Teste 21: Proteção 401 validada para rotas privadas e /uploads!")


def test_migracao_completa_banco_legado_para_owner():
    legacy_full = os.path.join(os.path.dirname(__file__), "study_hub_full_legacy.db")
    legacy_bak = f"{legacy_full}.pre_multiuser.bak"
    for p in [legacy_full, legacy_bak]:
        if os.path.exists(p):
            os.remove(p)

    conn = sqlite3.connect(legacy_full)
    cur = conn.cursor()
    cur.execute("CREATE TABLE config (chave TEXT PRIMARY KEY, valor TEXT)")
    cur.execute("CREATE TABLE categorias (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE NOT NULL)")
    cur.execute("CREATE TABLE subcategorias (id INTEGER PRIMARY KEY AUTOINCREMENT, categoria TEXT NOT NULL, nome TEXT NOT NULL, UNIQUE(categoria, nome))")
    cur.execute("CREATE TABLE anotacoes (id TEXT PRIMARY KEY, data TEXT, materia TEXT, subcategoria TEXT DEFAULT '', topico TEXT, conteudo TEXT, tags TEXT, link TEXT, anexo_nome TEXT, anexo_url TEXT)")
    cur.execute("CREATE TABLE tarefas (id TEXT PRIMARY KEY, data_criacao TEXT, titulo TEXT, categoria TEXT, status TEXT, prazo TEXT, prioridade TEXT, descricao TEXT, anexo_nome TEXT, anexo_url TEXT, eisenhower TEXT DEFAULT '')")
    cur.execute("CREATE TABLE cursos (id TEXT PRIMARY KEY, nome TEXT, instituicao TEXT, categoria TEXT, carga_horaria TEXT, status TEXT, link TEXT)")
    cur.execute("CREATE TABLE flashcards (id TEXT PRIMARY KEY, categoria TEXT, frente TEXT, verso TEXT, nivel TEXT DEFAULT 'Novo', ultima_revisao TEXT DEFAULT 'Nunca')")
    cur.execute("CREATE TABLE pomodoro (id TEXT PRIMARY KEY, data TEXT, categoria TEXT, minutos INTEGER DEFAULT 25)")
    cur.execute("CREATE TABLE midias (id TEXT PRIMARY KEY, tipo TEXT, titulo TEXT, autor_diretor TEXT, ano TEXT, categoria TEXT, status TEXT, nota INTEGER, capa_url TEXT, link TEXT, resenha TEXT, citacoes TEXT, data_criacao TEXT, data_conclusao TEXT)")
    cur.execute("CREATE TABLE habitos (id TEXT PRIMARY KEY, nome TEXT NOT NULL, icone TEXT, cor TEXT, meta_semanal INTEGER)")
    cur.execute("CREATE TABLE habitos_registros (habito_id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (habito_id, data))")

    cur.execute("INSERT INTO config VALUES ('META_LIVROS_ANO', '24')")
    cur.execute("INSERT INTO categorias (nome) VALUES ('Categoria Real')")
    cur.execute("INSERT INTO subcategorias (categoria, nome) VALUES ('Categoria Real', 'Sub Real')")
    cur.execute("INSERT INTO anotacoes VALUES ('NOTE-R1', '01/11/2026', 'Categoria Real', 'Sub Real', 'Nota Real', '<p>Texto</p>', 'real', '', '', '')")
    cur.execute("INSERT INTO tarefas VALUES ('TASK-R1', '01/11/2026', 'Tarefa Real', 'Categoria Real', 'Pendente', '2026-12-01', 'Alta', '', '', '', 'fazer')")
    cur.execute("INSERT INTO cursos VALUES ('CRS-R1', 'Curso Real', 'USP', 'Categoria Real', '60', 'Em Andamento', '')")
    cur.execute("INSERT INTO flashcards VALUES ('FC-R1', 'Categoria Real', 'P?', 'R!', 'Novo', 'Nunca')")
    cur.execute("INSERT INTO pomodoro VALUES ('POMO-R1', '01/11/2026', 'Categoria Real', 45)")
    cur.execute("INSERT INTO midias VALUES ('MID-R1', 'Livro', 'Sapiens', 'Harari', '2011', 'Categoria Real', 'Concluído', 5, '', '', '', '', '01/11/2026', '05/11/2026')")
    cur.execute("INSERT INTO habitos VALUES ('HAB-01', 'Leitura Real', 'fa-solid fa-book', '#10b981', 7)")
    cur.execute("INSERT INTO habitos_registros VALUES ('HAB-01', '2026-11-01')")
    conn.commit()
    conn.close()

    old_path = db.DB_PATH
    try:
        db.DB_PATH = legacy_full
        init_db()
        init_db()  # Idempotente
        assert os.path.exists(legacy_bak)

        conn2 = sqlite3.connect(legacy_full)
        cur2 = conn2.cursor()
        owner_row = cur2.execute(
            "SELECT id, is_admin, precisa_definir_senha FROM usuarios WHERE email='eu.elliasaugusto@gmail.com'"
        ).fetchone()
        assert owner_row is not None
        oid = owner_row[0]
        assert owner_row[1] == 1 and owner_row[2] == 1

        for tabela in [
            "config", "categorias", "subcategorias", "anotacoes", "tarefas",
            "cursos", "flashcards", "pomodoro", "midias", "habitos", "habitos_registros",
        ]:
            total = cur2.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
            do_dono = cur2.execute(f"SELECT COUNT(*) FROM {tabela} WHERE user_id = ?", (oid,)).fetchone()[0]
            assert total == do_dono and total >= 1, f"Falha na migração da tabela {tabela}"
        conn2.close()

        leg_client = TestClient(app)
        assert leg_client.get("/api/auth/me").json()["hasPendingMigration"] is True
        res1 = leg_client.post(
            "/api/auth/definirSenhaInicial",
            json={"email": "eu.elliasaugusto@gmail.com", "senha": "NovaSenhaMigrada123"},
        )
        assert res1.status_code == 200 and res1.json()["success"] is True

        # 2ª tentativa de definir senha inicial deve ser bloqueada
        res2 = leg_client.post(
            "/api/auth/definirSenhaInicial",
            json={"email": "eu.elliasaugusto@gmail.com", "senha": "TentativaInvalida123"},
        )
        assert res2.status_code == 400
    finally:
        db.DB_PATH = old_path
        for p in [legacy_full, legacy_bak]:
            if os.path.exists(p):
                os.remove(p)
    print("✅ Teste 22: Migração completa de 11 tabelas legadas para eu.elliasaugusto@gmail.com e proteção do 1º acesso validada!")


client2 = TestClient(app)
USER2_ID = None


def test_isolamento_multi_usuario():
    global USER2_ID
    from importer import importar_arquivo_json

    res_reg = client2.post(
        "/api/auth/registrar",
        json={"nome": "Colega Teste", "email": "colega@teste.com", "senha": "SenhaColega123"},
    )
    assert res_reg.status_code == 200 and res_reg.json()["success"] is True
    user2 = res_reg.json()["user"]
    USER2_ID = user2["id"]
    assert user2["isAdmin"] is False
    assert USER2_ID != OWNER_ID

    # Isolamento completo inicial (vê 0 dados do Usuário A, possui seus próprios hábitos e categorias)
    assert len(client2.post("/api/getAnotacoes", json=[]).json()) == 0
    assert len(client2.post("/api/getTarefas", json=[]).json()) == 0
    assert len(client2.post("/api/getCursos", json=[]).json()) == 0
    assert len(client2.post("/api/getMidias", json=[]).json()) == 0
    assert len(client2.post("/api/getFlashcards", json=[]).json()) == 0
    assert len(client2.post("/api/getCategorias", json=[]).json()) >= 7
    assert len(client2.post("/api/getHabitosDados", json=[]).json()["habitos"]) == 5

    # Mesmo nome de categoria/subcategoria e colisão de ID na importação JSON não afetam Usuário A
    assert client2.post("/api/salvarSubcategoria", json=["Outros", "Sub Colega"]).json()["success"] is True
    backup_colisao = {
        "anotacoes": [{
            "id": "NOTE-IMP-31",
            "data": "25/11/2026 10:00",
            "materia": "Outros",
            "subcategoria": "Sub Colega",
            "topico": "Nota do Colega",
            "conteudo": "<p>Privado</p>",
            "tags": "",
            "link": "",
        }]
    }
    temp_b = os.path.join(os.path.dirname(__file__), "teste_colisao_b.json")
    with open(temp_b, "w", encoding="utf-8") as f:
        json.dump(backup_colisao, f)
    try:
        importar_arquivo_json(temp_b, USER2_ID)
    finally:
        if os.path.exists(temp_b):
            os.remove(temp_b)

    notas_a = client.post("/api/getAnotacoes", json=[]).json()
    nota_a_imp = next(n for n in notas_a if n["id"] == "NOTE-IMP-31")
    assert nota_a_imp["topico"] == "Nota Importada v3.1"

    notas_b = client2.post("/api/getAnotacoes", json=[]).json()
    assert len(notas_b) == 1
    assert notas_b[0]["topico"] == "Nota do Colega"
    assert notas_b[0]["id"] != "NOTE-IMP-31"

    # Admin-only Drive e Calendar para não-admin
    assert client2.post("/api/sincronizarDrive").status_code == 403
    assert client2.post("/api/restaurarDrive").status_code == 403
    assert client2.post("/api/sincronizarGoogleCalendar", json=[]).status_code == 403
    assert client2.post("/api/getEventosGoogleCalendar", json=[]).json() == []

    # Perfil, alterar senha, logout e re-login
    res_perf = client2.post("/api/auth/atualizarPerfil", json={"nome": "Colega Atualizado"})
    assert res_perf.status_code == 200 and res_perf.json()["user"]["nome"] == "Colega Atualizado"

    res_pwd = client2.post(
        "/api/auth/alterarSenha",
        json={"senhaAtual": "SenhaColega123", "novaSenha": "NovaSenhaColega456"},
    )
    assert res_pwd.status_code == 200 and res_pwd.json()["success"] is True

    assert client2.post("/api/auth/logout").status_code == 200
    assert client2.post("/api/getAnotacoes", json=[]).status_code == 401
    res_relogin = client2.post(
        "/api/auth/login",
        json={"email": "colega@teste.com", "senha": "NovaSenhaColega456"},
    )
    assert res_relogin.status_code == 200 and res_relogin.json()["success"] is True
    print("✅ Teste 23: Isolamento multi-usuário, proteção contra colisão de IDs, admin-only Drive/Calendar e fluxo de conta validados!")


def test_compartilhamento_hibrido_e_permissoes():
    # Usuário A cria itens dedicados para testar permissões
    r_nota = client.post("/api/salvarAnotacao", json=[{
        "materia": "Engenharia de Computação (UNIVESP)",
        "subcategoria": "Sistemas Operacionais",
        "topico": "Nota Compartilhada SO",
        "conteudo": "<p>Conteúdo inicial SO</p>",
        "tags": "so",
        "link": "",
    }]).json()
    nota_id = r_nota["id"]

    r_tar = client.post("/api/salvarTarefa", json=[{
        "titulo": "Tarefa Compartilhada Lab",
        "descricao": "Relatório",
        "categoria": "Engenharia de Computação (UNIVESP)",
        "prazo": "2026-12-10",
        "prioridade": "Alta",
        "status": "Pendente",
        "eisenhower": "fazer",
    }]).json()
    tar_id = r_tar["id"]

    r_cur = client.post("/api/salvarCurso", json=[{
        "nome": "Curso Compartilhado",
        "instituicao": "UNIVESP",
        "categoria": "Engenharia de Computação (UNIVESP)",
        "cargaHoraria": "80",
        "status": "Em Andamento",
        "link": "",
    }]).json()
    cur_id = r_cur["id"]

    r_mid = client.post("/api/salvarMidia", json=[{
        "tipo": "Livro",
        "titulo": "Sistemas Operacionais Modernos",
        "autorDiretor": "Tanenbaum",
        "ano": "2015",
        "categoria": "Engenharia de Computação (UNIVESP)",
        "status": "Em Andamento",
        "nota": 5,
    }]).json()
    mid_id = r_mid["id"]

    r_fc = client.post("/api/salvarFlashcard", json=[{
        "categoria": "Engenharia de Computação (UNIVESP)",
        "frente": "O que é paginação?",
        "verso": "Gerenciamento de memória virtual.",
    }]).json()
    fc_id = r_fc["id"]

    r_hab = client.post("/api/salvarHabito", json=[{
        "nome": "Hábito Compartilhado",
        "icone": "fa-solid fa-fire",
        "cor": "#6366f1",
        "metaSemanal": 5,
    }]).json()
    hab_id = r_hab["id"]

    # 1. Compartilhar cada item com nível VISUALIZAR para colega@teste.com
    share_ids = {}
    for tipo, rid in [
        ("anotacao", nota_id),
        ("tarefa", tar_id),
        ("curso", cur_id),
        ("midia", mid_id),
        ("flashcard", fc_id),
        ("habito", hab_id),
    ]:
        rs = client.post("/api/criarOuAtualizarCompartilhamento", json=[{
            "escopo": "item",
            "recursoTipo": tipo,
            "recursoId": rid,
            "emailDestinatario": "colega@teste.com",
            "nivel": "visualizar",
        }]).json()
        assert rs["success"] is True
        share_ids[tipo] = rs["id"]

    # B lê todos com flag compartilhado=True, nível visualizar, mas é bloqueado (403) em edição/exclusão
    nota_b = next(x for x in client2.post("/api/getAnotacoes", json=[]).json() if x["id"] == nota_id)
    assert nota_b["compartilhado"] is True and nota_b["permissoes"]["nivel"] == "visualizar"
    tar_b = next(x for x in client2.post("/api/getTarefas", json=[]).json() if x["id"] == tar_id)
    assert tar_b["compartilhado"] is True
    cur_b = next(x for x in client2.post("/api/getCursos", json=[]).json() if x["id"] == cur_id)
    assert cur_b["compartilhado"] is True
    mid_b = next(x for x in client2.post("/api/getMidias", json=[]).json() if x["id"] == mid_id)
    assert mid_b["compartilhado"] is True
    fc_b = next(x for x in client2.post("/api/getFlashcards", json=[]).json() if x["id"] == fc_id)
    assert fc_b["compartilhado"] is True
    hab_b = next(x for x in client2.post("/api/getHabitosDados", json=[]).json()["habitos"] if x["id"] == hab_id)
    assert hab_b["compartilhado"] is True

    assert client2.post("/api/salvarAnotacao", json=[{"id": nota_id, "materia": nota_b["materia"], "topico": "Hack"}]).status_code == 403
    assert client2.post("/api/excluirAnotacao", json=[nota_id]).status_code == 403
    assert client2.post("/api/atualizarStatusTarefa", json=[tar_id, "Concluído"]).status_code == 403
    assert client2.post("/api/atualizarEisenhowerTarefa", json=[tar_id, "agendar"]).status_code == 403
    assert client2.post("/api/excluirTarefa", json=[tar_id]).status_code == 403
    assert client2.post("/api/salvarCurso", json=[{"id": cur_id, "nome": "Hack", "categoria": "Outros"}]).status_code == 403
    assert client2.post("/api/salvarMidia", json=[{"id": mid_id, "titulo": "Hack", "categoria": "Outros"}]).status_code == 403
    assert client2.post("/api/atualizarNivelFlashcard", json=[fc_id, "Dominado"]).status_code == 403
    assert client2.post("/api/alternarRegistroHabito", json=[hab_id, "2026-11-25"]).status_code == 403
    assert client2.post("/api/excluirHabito", json=[hab_id]).status_code == 403

    # 2. Upgrade para EDITAR: B edita mas não exclui nem compartilha item de A
    for tipo in ["anotacao", "tarefa", "flashcard", "habito"]:
        ru = client.post("/api/atualizarPermissaoCompartilhamento", json=[share_ids[tipo], {"nivel": "editar"}])
        assert ru.status_code == 200 and ru.json()["success"] is True

    assert client2.post("/api/salvarAnotacao", json=[{
        "id": nota_id,
        "materia": "Engenharia de Computação (UNIVESP)",
        "subcategoria": "Sistemas Operacionais",
        "topico": "Nota SO Editada por B",
        "conteudo": "<p>Editado!</p>",
    }]).status_code == 200
    assert client2.post("/api/atualizarStatusTarefa", json=[tar_id, "Em Andamento"]).status_code == 200
    assert client2.post("/api/atualizarEisenhowerTarefa", json=[tar_id, "agendar"]).status_code == 200
    assert client2.post("/api/atualizarNivelFlashcard", json=[fc_id, "Bom"]).status_code == 200
    assert client2.post("/api/alternarRegistroHabito", json=[hab_id, "2026-11-25"]).json()["marcado"] is True

    # Não pode excluir nem compartilhar item que não lhe pertence
    assert client2.post("/api/excluirAnotacao", json=[nota_id]).status_code == 403
    assert client2.post("/api/criarOuAtualizarCompartilhamento", json=[{
        "escopo": "item",
        "recursoTipo": "anotacao",
        "recursoId": nota_id,
        "emailDestinatario": "eu.elliasaugusto@gmail.com",
        "nivel": "visualizar",
    }]).status_code == 403

    # 3. Compartilhamento por CATEGORIA e MÓDULO com ESCREVER (criar no espaço do dono)
    rs_cat = client.post("/api/criarOuAtualizarCompartilhamento", json=[{
        "escopo": "categoria",
        "recursoTipo": "anotacao",
        "recursoId": "Outros",
        "emailDestinatario": "colega@teste.com",
        "nivel": "escrever",
    }]).json()
    assert rs_cat["success"] is True

    rs_mod = client.post("/api/criarOuAtualizarCompartilhamento", json=[{
        "escopo": "modulo",
        "recursoTipo": "tarefa",
        "recursoId": "",
        "emailDestinatario": "colega@teste.com",
        "nivel": "escrever",
    }]).json()
    assert rs_mod["success"] is True

    # B cria anotação em "Outros" no espaço de A -> sucesso, mas falha em categoria não compartilhada ("Autoescola / DETRAN")
    res_cr_nota_b = client2.post("/api/salvarAnotacao", json=[{
        "ownerUserId": OWNER_ID,
        "materia": "Outros",
        "topico": "Nota Criada por B em A",
        "conteudo": "<p>Colaborativa</p>",
    }])
    assert res_cr_nota_b.status_code == 200 and res_cr_nota_b.json()["success"] is True
    nova_nota_ab_id = res_cr_nota_b.json()["id"]

    res_cr_nota_proib = client2.post("/api/salvarAnotacao", json=[{
        "ownerUserId": OWNER_ID,
        "materia": "Autoescola / DETRAN",
        "topico": "Sem permissão",
        "conteudo": "<p>Proibido</p>",
    }])
    assert res_cr_nota_proib.status_code == 403

    # Se tentar mover uma nota da categoria compartilhada para fora dela -> 403
    res_move_proib = client2.post("/api/salvarAnotacao", json=[{
        "id": nova_nota_ab_id,
        "materia": "Autoescola / DETRAN",
        "topico": "Tentativa de fuga",
        "conteudo": "<p>Proibido</p>",
    }])
    assert res_move_proib.status_code == 403

    # B cria tarefa no módulo tarefas de A -> sucesso, visível imediatamente para A
    res_cr_tar_b = client2.post("/api/salvarTarefa", json=[{
        "ownerUserId": OWNER_ID,
        "titulo": "Tarefa Criada por B em A",
        "categoria": "Outros",
        "status": "Pendente",
    }])
    assert res_cr_tar_b.status_code == 200 and res_cr_tar_b.json()["success"] is True
    nova_tar_ab_id = res_cr_tar_b.json()["id"]

    assert any(n["id"] == nova_nota_ab_id for n in client.post("/api/getAnotacoes", json=[]).json())
    assert any(t["id"] == nova_tar_ab_id for t in client.post("/api/getTarefas", json=[]).json())
    assert client2.post("/api/excluirAnotacao", json=[nova_nota_ab_id]).status_code == 403

    # 4. Permissão personalizada (podeExcluir=True sem editar) e admin
    res_pers = client.post("/api/atualizarPermissaoCompartilhamento", json=[
        share_ids["curso"],
        {"nivel": "personalizado", "podeEditar": False, "podeCriar": False, "podeExcluir": True},
    ])
    assert res_pers.status_code == 200 and res_pers.json()["success"] is True
    assert client2.post("/api/salvarCurso", json=[{"id": cur_id, "nome": "Nao edita", "categoria": "Engenharia de Computação (UNIVESP)"}]).status_code == 403
    assert client2.post("/api/excluirCurso", json=[cur_id]).status_code == 200

    res_adm = client.post("/api/atualizarPermissaoCompartilhamento", json=[share_ids["habito"], {"nivel": "admin"}])
    assert res_adm.status_code == 200 and res_adm.json()["success"] is True
    assert client2.post("/api/excluirHabito", json=[hab_id]).status_code == 200

    # 5. Revogação pelo dono e saída pelo destinatário removem acesso
    assert client.post("/api/revogarCompartilhamento", json=[share_ids["anotacao"]]).json()["success"] is True
    assert not any(n["id"] == nota_id for n in client2.post("/api/getAnotacoes", json=[]).json())
    assert client2.post("/api/salvarAnotacao", json=[{"id": nota_id, "materia": "Engenharia de Computação (UNIVESP)", "topico": "X"}]).status_code == 403

    # Destinatário sai do compartilhamento de módulo de tarefas
    assert client2.post("/api/revogarCompartilhamento", json=[rs_mod["id"]]).json()["success"] is True
    assert client2.post("/api/salvarTarefa", json=[{"ownerUserId": OWNER_ID, "titulo": "Sem acesso", "categoria": "Outros"}]).status_code == 403
    print("✅ Teste 24: Compartilhamento híbrido (item/categoria/módulo), 4 níveis + granular e revogação aprovados!")


def test_frontend_auth_e_compartilhamentos():
    html = client.get("/").text
    for elem_id in [
        "telaAuth",
        "formLogin",
        "formRegistro",
        "boxPrimeiroAcesso",
        "view-compartilhamentos",
        "modalCompartilharItem",
        "modalConta",
        "sidebarUsuarioCard",
        "filtroOrigemAnotacao",
        "filtroOrigemTarefa",
        "filtroOrigemFlashcard",
        "filtroOrigemCurso",
        "filtroOrigemMidia",
        "ownerAnotacaoSelect",
        "ownerTarefaSelect",
    ]:
        assert elem_id in html, f"Elemento esperado ausente no HTML: {elem_id}"
    print("✅ Teste 25: Todos os elementos de autenticação, perfil e compartilhamento presentes no frontend!")


if __name__ == "__main__":
    test_home()
    test_categorias()
    test_anotacoes()
    test_tarefas()
    test_pomodoro()
    test_dashboard()
    test_exportar_backup()
    test_importar_xlsx()
    test_midias()
    test_google_calendar()
    test_habitos_e_gamificacao()
    test_grafo_e_backlinks()
    test_info_rede_mobile()
    test_subcategorias_e_anotacoes_subcategoria()
    test_eisenhower_tarefas()
    test_backup_json_novos_campos()
    test_migracao_banco_legado()
    test_frontend_elementos_novos()
    test_protecao_nao_autenticado()
    test_migracao_completa_banco_legado_para_owner()
    test_isolamento_multi_usuario()
    test_compartilhamento_hibrido_e_permissoes()
    test_frontend_auth_e_compartilhamentos()
    print("\n🎉 TODOS OS 25 TESTES PASSARAM COM 100% DE SUCESSO!")
