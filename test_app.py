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
    print("\n🎉 TODOS OS 15 TESTES PASSARAM COM 100% DE SUCESSO!")
