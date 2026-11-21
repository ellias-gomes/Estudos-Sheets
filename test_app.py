import os
import openpyxl
import db

# Usa um banco isolado durante os testes automatizados para nunca alterar o study_hub.db real
TEST_DB = os.path.join(os.path.dirname(__file__), "study_hub_test.db")
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)
db.DB_PATH = TEST_DB

from fastapi.testclient import TestClient
from app import app
from db import init_db, get_connection

init_db()
client = TestClient(app)

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

    # Adicionar categoria
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
        "link": "https://univesp.br"
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
        "status": "Em Andamento"
    }
    res = client.post("/api/salvarTarefa", json=[dados])
    assert res.status_code == 200
    assert res.json()["success"] is True

    res_list = client.post("/api/getTarefas", json=[])
    tarefas = res_list.json()
    assert len(tarefas) > 0
    tid = tarefas[0]["id"]

    # Atualizar status
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
    # Cria uma planilha temporária com todas as abas
    wb = openpyxl.Workbook()
    wb.remove(wb.active) # Remove aba padrão

    # Aba Anotações
    ws_anot = wb.create_sheet("Anotações")
    ws_anot.append(['ID', 'Data', 'Matéria/Categoria', 'Tópico', 'Conteúdo', 'Tags', 'Link', 'AnexoNome', 'AnexoUrl'])
    ws_anot.append(['NOTE-999', '27/10/2026 20:00', 'DevOps / Cloud (Alura)', 'Docker e K8s', '<p>Containerização avançada</p>', 'docker', '', '', ''])

    # Aba Tarefas
    ws_tar = wb.create_sheet("Tarefas")
    ws_tar.append(['ID', 'Data Criação', 'Título', 'Categoria', 'Status', 'Prazo', 'Prioridade', 'Descrição', 'AnexoNome', 'AnexoUrl'])
    ws_tar.append(['TASK-999', '27/10/2026', 'Estudar Docker', 'DevOps / Cloud (Alura)', 'Pendente', '2026-11-01', 'Alta', 'Módulo 3', '', ''])

    # Aba Cursos
    ws_cur = wb.create_sheet("Cursos")
    ws_cur.append(['ID', 'Nome', 'Instituição', 'Categoria', 'Carga Horária', 'Status', 'Link'])
    ws_cur.append(['CRS-999', 'Kubernetes Avançado', 'Alura', 'DevOps / Cloud (Alura)', '40', 'Em Andamento', 'https://alura.com.br'])

    # Aba Flashcards
    ws_fc = wb.create_sheet("Flashcards")
    ws_fc.append(['ID', 'Categoria', 'Frente', 'Verso', 'Nivel', 'UltimaRevisao'])
    ws_fc.append(['FC-999', 'DevOps / Cloud (Alura)', 'O que é um Pod no K8s?', 'Menor unidade de implantação', 'Novo', 'Nunca'])

    # Aba Pomodoro
    ws_pomo = wb.create_sheet("Pomodoro")
    ws_pomo.append(['ID', 'Data', 'Categoria', 'Minutos'])
    ws_pomo.append(['POMO-999', '27/10/2026 19:30', 'DevOps / Cloud (Alura)', 50])

    teste_xlsx = "teste_importacao.xlsx"
    wb.save(teste_xlsx)

    with open(teste_xlsx, "rb") as f:
        res = client.post("/api/importarPlanilha", files={"arquivo": ("teste_importacao.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})

    if os.path.exists(teste_xlsx):
        os.remove(teste_xlsx)

    assert res.status_code == 200
    res_json = res.json()
    assert res_json["success"] is True
    print(f"✅ Teste 9: Importação da Planilha Google Sheets testada e aprovada: {res_json['message']}")

def test_midias():
    # Salvar mídia
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
        "citacoes": "Qualquer tolo pode escrever código que um computador entenda. Bons programadores escrevem código que humanos podem entender."
    }
    res_salvar = client.post("/api/salvarMidia", json=[dados])
    assert res_salvar.status_code == 200
    assert res_salvar.json()["success"] is True

    # Listar mídias
    res_list = client.post("/api/getMidias", json=[])
    assert res_list.status_code == 200
    midias = res_list.json()
    assert len(midias) > 0
    assert midias[0]["titulo"] == "Clean Code"
    assert midias[0]["nota"] == 5
    print(f"✅ Teste 10: Módulo de Leituras/Reviews salvo e listado com sucesso ({len(midias)} obras)!")

    # Teste de busca de metadados
    res_meta = client.post("/api/buscarMetadadosMidia", json=["Livro", "Clean Code"])
    assert res_meta.status_code == 200
    print(f"✅ Teste 11: Busca automática de metadados testada com sucesso: {res_meta.json().get('titulo')}")

def test_google_calendar():
    # Teste de obtenção de eventos e sincronização do Calendar
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

    # Marcar hábito hoje
    res_toggle = client.post("/api/alternarRegistroHabito", json=[hab_id, hoje_str])
    assert res_toggle.status_code == 200
    assert res_toggle.json()["marcado"] is True

    # Verificar streak e progresso
    res_check = client.post("/api/getHabitosDados", json=[])
    dados_atualizados = res_check.json()
    assert dados_atualizados["concluidosHoje"] >= 1
    assert dados_atualizados["streakGlobal"] >= 1
    print(f"✅ Teste 13: Rastreador de Hábitos & Heatmap funcionando! Streak Global: {dados_atualizados['streakGlobal']}d")

def test_grafo_e_backlinks():
    # Cria uma anotação que cita [[Clean Code]] e [[Estruturas de Dados]]
    nota_conectada = {
        "materia": "Desenvolvimento de Software / Projetos",
        "topico": "Arquitetura Limpa na Prática",
        "conteudo": "<p>Aplicando os princípios de [[Clean Code]] junto com [[Estruturas de Dados]].</p>",
        "tags": "arquitetura, estrutura",
        "link": ""
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
    # 1. Criar subcategoria via API
    res_sub = client.post("/api/salvarSubcategoria", json=[cat, "Cálculo I"])
    assert res_sub.status_code == 200
    assert res_sub.json()["success"] is True

    # 2. Rejeitar duplicata na mesma categoria
    res_dup = client.post("/api/salvarSubcategoria", json=[cat, "Cálculo I"])
    assert res_dup.status_code == 200
    assert res_dup.json()["success"] is False

    # 3. Listar todas e filtradas por categoria
    res_all = client.post("/api/getSubcategorias", json=[])
    assert res_all.status_code == 200
    assert any(s["categoria"] == cat and s["nome"] == "Cálculo I" for s in res_all.json())

    res_filt = client.post("/api/getSubcategorias", json=[cat])
    assert res_filt.status_code == 200
    assert all(s["categoria"] == cat for s in res_filt.json())

    # 4. Criar anotação com nova subcategoria (deve auto-registrar em subcategorias)
    nota = {
        "materia": cat,
        "subcategoria": "Física Geral",
        "topico": "Leis de Newton",
        "conteudo": "<p>Resumo sobre cinemática e dinâmica.</p>",
        "tags": "fisica, mecanica",
        "link": ""
    }
    res_nota = client.post("/api/salvarAnotacao", json=[nota])
    assert res_nota.status_code == 200
    assert res_nota.json()["success"] is True

    res_notas = client.post("/api/getAnotacoes", json=[])
    notas = res_notas.json()
    nota_fisica = next(n for n in notas if n["topico"] == "Leis de Newton")
    assert nota_fisica["subcategoria"] == "Física Geral"

    # Confirma auto-registro em subcategorias
    subs_cat = client.post("/api/getSubcategorias", json=[cat]).json()
    sub_fisica = next((s for s in subs_cat if s["nome"] == "Física Geral"), None)
    assert sub_fisica is not None

    # 5. Editar subcategoria da anotação
    nota_edit = dict(nota_fisica)
    nota_edit["subcategoria"] = "Cálculo I"
    res_edit = client.post("/api/salvarAnotacao", json=[nota_edit])
    assert res_edit.status_code == 200
    assert res_edit.json()["success"] is True

    notas_pos_edit = client.post("/api/getAnotacoes", json=[]).json()
    nota_atualizada = next(n for n in notas_pos_edit if n["id"] == nota_fisica["id"])
    assert nota_atualizada["subcategoria"] == "Cálculo I"

    # 6. Verificar nó e aresta de subcategoria no Grafo de Conhecimento
    grafo = client.post("/api/getGrafoConhecimento", json=[]).json()
    assert any(n.get("group") == "subcategoria" and n.get("label") == "Cálculo I" for n in grafo["nodes"])
    assert any(e.get("type") == "subcategoria" for e in grafo["edges"])

    # 7. Excluir subcategoria e validar limpeza na anotação (preservando a anotação)
    sub_calc = next(s for s in subs_cat if s["nome"] == "Cálculo I")
    res_del = client.post("/api/excluirSubcategoria", json=[sub_calc["id"]])
    assert res_del.status_code == 200
    assert res_del.json()["success"] is True

    subs_depois = client.post("/api/getSubcategorias", json=[cat]).json()
    assert not any(s["id"] == sub_calc["id"] for s in subs_depois)

    notas_depois = client.post("/api/getAnotacoes", json=[]).json()
    nota_preservada = next(n for n in notas_depois if n["id"] == nota_fisica["id"])
    assert nota_preservada["subcategoria"] == ""
    print("✅ Teste 16: Subcategorias nas Anotações (CRUD, auto-registro, grafo e exclusão segura) aprovadas!")

def test_eisenhower_tarefas():
    # 1. Criar tarefa já com quadrante e outra sem quadrante
    res_q1 = client.post("/api/salvarTarefa", json=[{
        "titulo": "Entregar lista de exercícios",
        "descricao": "Prazo hoje",
        "categoria": "Engenharia de Computação (UNIVESP)",
        "prazo": "2026-11-21",
        "prioridade": "Alta",
        "status": "Pendente",
        "eisenhower": "fazer"
    }])
    assert res_q1.status_code == 200 and res_q1.json()["success"] is True

    res_inbox = client.post("/api/salvarTarefa", json=[{
        "titulo": "Organizar bookmarks",
        "descricao": "",
        "categoria": "Outros",
        "prazo": "",
        "prioridade": "Baixa",
        "status": "Pendente"
    }])
    assert res_inbox.status_code == 200 and res_inbox.json()["success"] is True

    tarefas = client.post("/api/getTarefas", json=[]).json()
    t_q1 = next(t for t in tarefas if t["titulo"] == "Entregar lista de exercícios")
    t_inbox = next(t for t in tarefas if t["titulo"] == "Organizar bookmarks")
    assert t_q1["eisenhower"] == "fazer"
    assert t_inbox["eisenhower"] == ""

    # 2. Mover entre quadrantes
    for q in ["agendar", "delegar", "eliminar", ""]:
        res_mv = client.post("/api/atualizarEisenhowerTarefa", json=[t_inbox["id"], q])
        assert res_mv.status_code == 200 and res_mv.json()["success"] is True
        lista = client.post("/api/getTarefas", json=[]).json()
        atual = next(t for t in lista if t["id"] == t_inbox["id"])
        assert atual["eisenhower"] == q

    # 3. Rejeitar quadrante inválido
    res_inv = client.post("/api/atualizarEisenhowerTarefa", json=[t_inbox["id"], "invalido"])
    assert res_inv.status_code == 200
    assert res_inv.json()["success"] is False
    print("✅ Teste 17: Matriz de Eisenhower nas Tarefas (criação, transição entre quadrantes e validação) aprovada!")

def test_backup_json_novos_campos():
    import json
    from importer import importar_arquivo_json

    # Garante uma anotação com subcategoria e uma tarefa com quadrante antes de exportar
    client.post("/api/salvarAnotacao", json=[{
        "materia": "DevOps / Cloud (Alura)",
        "subcategoria": "Kubernetes",
        "topico": "Ingress Controllers",
        "conteudo": "<p>Roteamento L7</p>",
        "tags": "k8s",
        "link": ""
    }])

    res_exp = client.get("/api/exportarBackup")
    assert res_exp.status_code == 200
    backup = res_exp.json()
    assert "subcategorias" in backup
    assert any(s["nome"] == "Kubernetes" for s in backup["subcategorias"])
    assert any(a.get("subcategoria") == "Kubernetes" for a in backup["anotacoes"])
    assert any(t.get("eisenhower") == "fazer" for t in backup["tarefas"])

    # Testa reimportação em JSON temporário com novos registros
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
        "anexoUrl": ""
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
        "eisenhower": "agendar"
    })
    with open(temp_json, "w", encoding="utf-8") as f:
        json.dump(backup, f, ensure_ascii=False)

    try:
        importar_arquivo_json(temp_json)
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
    import sqlite3
    legacy_db = os.path.join(os.path.dirname(__file__), "study_hub_legacy_test.db")
    if os.path.exists(legacy_db):
        os.remove(legacy_db)

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
        assert "eisenhower" in tar_cols
        assert "subcategorias" in tables

        anot_row = cur2.execute("SELECT topico, subcategoria FROM anotacoes WHERE id='NOTE-OLD'").fetchone()
        tar_row = cur2.execute("SELECT titulo, eisenhower FROM tarefas WHERE id='TASK-OLD'").fetchone()
        assert anot_row[0] == "Nota Antiga" and (anot_row[1] or "") == ""
        assert tar_row[0] == "Tarefa Antiga" and (tar_row[1] or "") == ""
        conn2.close()
    finally:
        db.DB_PATH = old_path
        if os.path.exists(legacy_db):
            os.remove(legacy_db)
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
    ]:
        assert elem_id in html, f"Elemento esperado ausente no HTML: {elem_id}"
    print("✅ Teste 20: Todos os elementos de interface novos presentes no frontend!")

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
    print("\n🎉 TODOS OS 20 TESTES PASSARAM COM 100% DE SUCESSO!")
