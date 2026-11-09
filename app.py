import os
import re
import json
import base64
import time
import socket
import requests
from datetime import datetime
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from db import (
    init_db, get_connection, get_config, set_config,
    get_todas_categorias, adicionar_categoria, get_dashboard,
    get_todas_midias, salvar_midia_db, excluir_midia_db,
    get_habitos_dados, salvar_habito_db, alternar_registro_habito_db,
    excluir_habito_db, salvar_meta_leitura_db, get_grafo_conhecimento
)
from importer import importar_arquivo_xlsx, importar_arquivo_json, exportar_todos_dados
from gdrive_sync import enviar_backup_para_drive, restaurar_backup_do_drive, status_drive
from media_fetcher import buscar_metadados_midia
from gcalendar_sync import sincronizar_tarefas_google_calendar, obter_eventos_google_calendar

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
STATIC_DIR = os.path.join(BASE_DIR, "static")

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

# Inicializa banco de dados
init_db()

app = FastAPI(title="Study Hub & Life OS Local")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Monta arquivos de uploads e estáticos
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

def salvar_arquivo_base64(file_obj):
    if not file_obj or not file_obj.get("data"):
        return {"url": "", "name": "", "directUrl": ""}
    
    raw_data = file_obj["data"]
    if "," in raw_data:
        raw_data = raw_data.split(",", 1)[1]
    
    file_bytes = base64.b64decode(raw_data)
    original_name = file_obj.get("fileName") or f"FILE_{int(time.time() * 1000)}.dat"
    # Sanitiza o nome do arquivo
    clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', original_name)
    unique_name = f"{int(time.time() * 1000)}_{clean_name}"
    
    filepath = os.path.join(UPLOADS_DIR, unique_name)
    with open(filepath, "wb") as f:
        f.write(file_bytes)
        
    url = f"/uploads/{unique_name}"
    return {
        "url": url,
        "name": original_name,
        "directUrl": url
    }

# ================= HANDLERS DOS ENDPOINTS =================

def api_getDashboardData():
    return get_dashboard()

def api_getCategorias():
    return get_todas_categorias()

def api_salvarCategoria(nome):
    sucesso, msg = adicionar_categoria(nome)
    return {"success": sucesso, "message": msg}

def api_getAnotacoes():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM anotacoes ORDER BY rowid DESC")
    rows = cursor.fetchall()
    conn.close()
    
    resultado = []
    for r in rows:
        resultado.append({
            "id": r["id"],
            "data": r["data"],
            "materia": r["materia"],
            "topico": r["topico"],
            "conteudo": r["conteudo"],
            "tags": r["tags"],
            "link": r["link"],
            "anexoNome": r["anexo_nome"] or "",
            "anexoUrl": r["anexo_url"] or ""
        })
    return resultado

def api_salvarAnotacao(dados):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        anexo_nome = dados.get("anexoNome", "")
        anexo_url = dados.get("anexoUrl", "")
        
        if dados.get("arquivoData"):
            anexo = salvar_arquivo_base64(dados["arquivoData"])
            anexo_nome = anexo["name"]
            anexo_url = anexo["url"]
            
        aid = dados.get("id")
        if aid:
            cursor.execute("""
            UPDATE anotacoes 
            SET materia = ?, topico = ?, conteudo = ?, tags = ?, link = ?, anexo_nome = ?, anexo_url = ?
            WHERE id = ?
            """, (
                dados.get("materia", ""),
                dados.get("topico", ""),
                dados.get("conteudo", ""),
                dados.get("tags", ""),
                dados.get("link", ""),
                anexo_nome,
                anexo_url,
                aid
            ))
            conn.commit()
            conn.close()
            return {"success": True, "message": "Anotação atualizada!"}
        else:
            novo_id = f"NOTE-{str(int(time.time() * 1000))[-6:]}"
            data_atual = datetime.now().strftime("%d/%m/%Y %H:%M")
            cursor.execute("""
            INSERT INTO anotacoes (id, data, materia, topico, conteudo, tags, link, anexo_nome, anexo_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                novo_id,
                data_atual,
                dados.get("materia", ""),
                dados.get("topico", ""),
                dados.get("conteudo", ""),
                dados.get("tags", ""),
                dados.get("link", ""),
                anexo_nome,
                anexo_url
            ))
            conn.commit()
            conn.close()
            return {"success": True, "message": "Anotação salva com sucesso!"}
    except Exception as e:
        return {"success": False, "message": str(e)}

def api_excluirAnotacao(aid):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM anotacoes WHERE id = ?", (aid,))
        conn.commit()
        conn.close()
        return {"success": True, "message": "Anotação excluída!"}
    except Exception as e:
        return {"success": False, "message": str(e)}

def api_getTarefas():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tarefas ORDER BY rowid DESC")
    rows = cursor.fetchall()
    conn.close()
    
    resultado = []
    for r in rows:
        resultado.append({
            "id": r["id"],
            "dataCriacao": r["data_criacao"],
            "titulo": r["titulo"],
            "categoria": r["categoria"],
            "status": r["status"],
            "prazo": r["prazo"],
            "prioridade": r["prioridade"],
            "descricao": r["descricao"] or "",
            "anexoNome": r["anexo_nome"] or "",
            "anexoUrl": r["anexo_url"] or ""
        })
    return resultado

def api_salvarTarefa(dados):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        anexo_nome = dados.get("anexoNome", "")
        anexo_url = dados.get("anexoUrl", "")
        
        if dados.get("arquivoData"):
            anexo = salvar_arquivo_base64(dados["arquivoData"])
            anexo_nome = anexo["name"]
            anexo_url = anexo["url"]
            
        tid = dados.get("id")
        if tid:
            cursor.execute("""
            UPDATE tarefas
            SET titulo = ?, categoria = ?, status = ?, prazo = ?, prioridade = ?, descricao = ?, anexo_nome = ?, anexo_url = ?
            WHERE id = ?
            """, (
                dados.get("titulo", ""),
                dados.get("categoria", ""),
                dados.get("status", "Pendente"),
                dados.get("prazo", ""),
                dados.get("prioridade", "Média"),
                dados.get("descricao", ""),
                anexo_nome,
                anexo_url,
                tid
            ))
            conn.commit()
            conn.close()
            return {"success": True, "message": "Tarefa atualizada!"}
        else:
            novo_id = f"TASK-{str(int(time.time() * 1000))[-6:]}"
            data_atual = datetime.now().strftime("%d/%m/%Y")
            cursor.execute("""
            INSERT INTO tarefas (id, data_criacao, titulo, categoria, status, prazo, prioridade, descricao, anexo_nome, anexo_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                novo_id,
                data_atual,
                dados.get("titulo", ""),
                dados.get("categoria", ""),
                dados.get("status", "Pendente"),
                dados.get("prazo", ""),
                dados.get("prioridade", "Média"),
                dados.get("descricao", ""),
                anexo_nome,
                anexo_url
            ))
            conn.commit()
            conn.close()
            return {"success": True, "message": "Tarefa salva com sucesso!"}
    except Exception as e:
        return {"success": False, "message": str(e)}

def api_atualizarStatusTarefa(tid, novo_status):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE tarefas SET status = ? WHERE id = ?", (novo_status, tid))
        conn.commit()
        conn.close()
        return {"success": True, "message": "Status atualizado!"}
    except Exception as e:
        return {"success": False, "message": str(e)}

def api_excluirTarefa(tid):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tarefas WHERE id = ?", (tid,))
        conn.commit()
        conn.close()
        return {"success": True, "message": "Tarefa excluída!"}
    except Exception as e:
        return {"success": False, "message": str(e)}

def api_getCursos():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cursos ORDER BY rowid DESC")
    rows = cursor.fetchall()
    conn.close()
    
    resultado = []
    for r in rows:
        resultado.append({
            "id": r["id"],
            "nome": r["nome"],
            "instituicao": r["instituicao"],
            "categoria": r["categoria"],
            "cargaHoraria": r["carga_horaria"],
            "status": r["status"],
            "link": r["link"]
        })
    return resultado

def api_salvarCurso(dados):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cid = f"CRS-{str(int(time.time() * 1000))[-6:]}"
        cursor.execute("""
        INSERT INTO cursos (id, nome, instituicao, categoria, carga_horaria, status, link)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            cid,
            dados.get("nome", ""),
            dados.get("instituicao", ""),
            dados.get("categoria", ""),
            dados.get("cargaHoraria", ""),
            dados.get("status", "Em Andamento"),
            dados.get("link", "")
        ))
        conn.commit()
        conn.close()
        return {"success": True, "message": "Curso salvo!"}
    except Exception as e:
        return {"success": False, "message": str(e)}

def api_excluirCurso(cid):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cursos WHERE id = ?", (cid,))
        conn.commit()
        conn.close()
        return {"success": True, "message": "Curso excluído!"}
    except Exception as e:
        return {"success": False, "message": str(e)}

def api_getFlashcards():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM flashcards ORDER BY rowid DESC")
    rows = cursor.fetchall()
    conn.close()
    
    resultado = []
    for r in rows:
        resultado.append({
            "id": r["id"],
            "categoria": r["categoria"],
            "frente": r["frente"],
            "verso": r["verso"],
            "nivel": r["nivel"] or "Novo",
            "ultimaRevisao": r["ultima_revisao"] or "Nunca"
        })
    return resultado

def api_salvarFlashcard(dados):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        fid = f"FC-{str(int(time.time() * 1000))[-6:]}{int(time.time() % 100)}"
        cursor.execute("""
        INSERT INTO flashcards (id, categoria, frente, verso, nivel, ultima_revisao)
        VALUES (?, ?, ?, ?, 'Novo', '')
        """, (
            fid,
            dados.get("categoria", ""),
            dados.get("frente", ""),
            dados.get("verso", "")
        ))
        conn.commit()
        conn.close()
        return {"success": True, "message": "Flashcard criado!"}
    except Exception as e:
        return {"success": False, "message": str(e)}

def api_atualizarNivelFlashcard(fid, nivel):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        hoje = datetime.now().strftime("%d/%m/%Y")
        cursor.execute("UPDATE flashcards SET nivel = ?, ultima_revisao = ? WHERE id = ?", (nivel, hoje, fid))
        conn.commit()
        conn.close()
        return {"success": True}
    except Exception as e:
        return {"success": False, "message": str(e)}

def api_excluirFlashcard(fid):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM flashcards WHERE id = ?", (fid,))
        conn.commit()
        conn.close()
        return {"success": True, "message": "Flashcard excluído!"}
    except Exception as e:
        return {"success": False, "message": str(e)}

def api_registrarSessaoPomodoro(categoria, minutos):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        pid = f"POMO-{str(int(time.time() * 1000))[-6:]}"
        data_atual = datetime.now().strftime("%d/%m/%Y %H:%M")
        cursor.execute("""
        INSERT INTO pomodoro (id, data, categoria, minutos)
        VALUES (?, ?, ?, ?)
        """, (pid, data_atual, categoria or "Geral", int(minutos) if minutos else 25))
        conn.commit()
        conn.close()
        return {"success": True, "message": f"Sessão de {minutos} min registrada com sucesso!"}
    except Exception as e:
        return {"success": False, "message": str(e)}

def api_uploadImagemEditor(file_obj):
    res = salvar_arquivo_base64(file_obj)
    return {"directUrl": res["directUrl"]}

def api_uploadArquivoDrive(file_obj):
    return salvar_arquivo_base64(file_obj)

def api_salvarChaveGemini(api_key):
    set_config("GEMINI_API_KEY", api_key.strip())
    return {"success": True, "message": "Chave da API Gemini guardada com segurança no banco local!"}

def api_chamarAssistenteIA(acao, texto_conteudo, categoria_atual):
    try:
        api_key = os.getenv("GEMINI_API_KEY") or get_config("GEMINI_API_KEY")
        if not api_key:
            return {
                "success": False,
                "needKey": True,
                "message": "Configure a sua chave da API do Google Gemini no arquivo .env (GEMINI_API_KEY=...) ou clique no ícone de engrenagem."
            }

        prompt = ""
        if acao == 'resumir':
            prompt = "Crie um resumo executivo estruturado em HTML (use apenas tags <h3>, <p>, <ul>, <li>, <strong>, sem blocos markdown ```html) destacando os pontos principais do seguinte texto:\n\n" + texto_conteudo
        elif acao == 'topicos':
            prompt = "Extraia os conceitos-chave, termos técnicos e ideias centrais em formato de lista de revisão em HTML (use <h3>, <ul>, <li>, <strong>, sem markdown ```html) a partir do seguinte texto:\n\n" + texto_conteudo
        elif acao == 'flashcards':
            prompt = "A partir do texto abaixo, gere exatamente 4 flashcards de estudo com perguntas diretas e respostas claras. Retorne APENAS um JSON válido no formato [{\"frente\": \"Pergunta?\", \"verso\": \"Resposta\"}] sem nenhum texto adicional ou formatação markdown:\n\n" + texto_conteudo

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }

        resp = requests.post(url, json=payload, timeout=30)
        data = resp.json()

        if "error" in data:
            return {"success": False, "message": f"Erro na API Gemini: {data['error'].get('message', '')}"}

        resposta_texto = data["candidates"][0]["content"]["parts"][0]["text"]
        resposta_texto = re.sub(r'```(html|json)?', '', resposta_texto).replace('```', '').strip()

        if acao == 'flashcards':
            cards = json.loads(resposta_texto)
            for c in cards:
                api_salvarFlashcard({
                    "categoria": categoria_atual or "Geral",
                    "frente": c.get("frente", ""),
                    "verso": c.get("verso", "")
                })
            return {
                "success": True,
                "isFlashcards": True,
                "message": f"{len(cards)} Flashcards foram gerados e adicionados automaticamente à sua aba de Flashcards!"
            }

        return {"success": True, "html": resposta_texto}
    except Exception as e:
        return {"success": False, "message": f"Erro ao processar com IA: {str(e)}"}

def api_getMidias(tipo=None, status=None):
    return get_todas_midias(tipo, status)

def api_salvarMidia(dados):
    return salvar_midia_db(dados)

def api_excluirMidia(mid):
    return excluir_midia_db(mid)

def api_buscarMetadadosMidia(tipo, termo):
    return buscar_metadados_midia(tipo, termo)

def api_sincronizarGoogleCalendar():
    return sincronizar_tarefas_google_calendar()

def api_getEventosGoogleCalendar():
    return obter_eventos_google_calendar()

def api_getHabitosDados():
    return get_habitos_dados()

def api_salvarHabito(dados):
    return salvar_habito_db(dados)

def api_alternarRegistroHabito(habito_id, data_str):
    return alternar_registro_habito_db(habito_id, data_str)

def api_excluirHabito(habito_id):
    return excluir_habito_db(habito_id)

def api_salvarMetaLeitura(meta):
    return salvar_meta_leitura_db(meta)

def api_getGrafoConhecimento():
    return get_grafo_conhecimento()

def obter_ip_rede_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def api_getInfoRede():
    ip = obter_ip_rede_local()
    return {
        "ip": ip,
        "porta": 8000,
        "urlRede": f"http://{ip}:8000",
        "urlLocal": "http://127.0.0.1:8000"
    }

HANDLERS = {
    "getDashboardData": api_getDashboardData,
    "getCategorias": api_getCategorias,
    "salvarCategoria": api_salvarCategoria,
    "getAnotacoes": api_getAnotacoes,
    "salvarAnotacao": api_salvarAnotacao,
    "excluirAnotacao": api_excluirAnotacao,
    "getTarefas": api_getTarefas,
    "salvarTarefa": api_salvarTarefa,
    "atualizarStatusTarefa": api_atualizarStatusTarefa,
    "excluirTarefa": api_excluirTarefa,
    "getCursos": api_getCursos,
    "salvarCurso": api_salvarCurso,
    "excluirCurso": api_excluirCurso,
    "getFlashcards": api_getFlashcards,
    "salvarFlashcard": api_salvarFlashcard,
    "atualizarNivelFlashcard": api_atualizarNivelFlashcard,
    "excluirFlashcard": api_excluirFlashcard,
    "registrarSessaoPomodoro": api_registrarSessaoPomodoro,
    "uploadImagemEditor": api_uploadImagemEditor,
    "uploadArquivoDrive": api_uploadArquivoDrive,
    "salvarChaveGemini": api_salvarChaveGemini,
    "chamarAssistenteIA": api_chamarAssistenteIA,
    "getMidias": api_getMidias,
    "salvarMidia": api_salvarMidia,
    "excluirMidia": api_excluirMidia,
    "buscarMetadadosMidia": api_buscarMetadadosMidia,
    "sincronizarGoogleCalendar": api_sincronizarGoogleCalendar,
    "getEventosGoogleCalendar": api_getEventosGoogleCalendar,
    "getHabitosDados": api_getHabitosDados,
    "salvarHabito": api_salvarHabito,
    "alternarRegistroHabito": api_alternarRegistroHabito,
    "excluirHabito": api_excluirHabito,
    "salvarMetaLeitura": api_salvarMetaLeitura,
    "getGrafoConhecimento": api_getGrafoConhecimento,
    "getInfoRede": api_getInfoRede,
}

# ================= ROTAS DE IMPORTAÇÃO E EXPORTAÇÃO =================

@app.post("/api/importarPlanilha")
async def importar_planilha(arquivo: UploadFile = File(...)):
    try:
        nome = arquivo.filename.lower()
        temp_path = os.path.join(BASE_DIR, f"temp_upload_{arquivo.filename}")
        with open(temp_path, "wb") as f:
            content = await arquivo.read()
            f.write(content)

        if nome.endswith(".xlsx"):
            resumo = importar_arquivo_xlsx(temp_path)
        elif nome.endswith(".json"):
            resumo = importar_arquivo_json(temp_path)
        else:
            if os.path.exists(temp_path): os.remove(temp_path)
            return {"success": False, "message": "Formato inválido. Envie um arquivo .xlsx ou .json."}

        if os.path.exists(temp_path):
            os.remove(temp_path)

        total = sum(resumo.values())
        msg = f"Importação concluída com sucesso! Total de {total} registos importados (Anotações: {resumo['anotacoes']}, Tarefas: {resumo['tarefas']}, Cursos: {resumo['cursos']}, Flashcards: {resumo['flashcards']}, Pomodoros: {resumo['pomodoro']}, Categorias: {resumo['categorias']})."
        return {"success": True, "message": msg, "resumo": resumo}
    except Exception as e:
        return {"success": False, "message": f"Erro ao importar: {str(e)}"}

@app.get("/api/exportarBackup")
async def exportar_backup():
    dados = exportar_todos_dados()
    return JSONResponse(
        content=dados,
        headers={"Content-Disposition": f"attachment; filename=study_hub_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"}
    )

# Rotas de Sincronização com o Google Drive
@app.get("/api/statusDrive")
async def rota_status_drive():
    return JSONResponse(content=status_drive())

@app.post("/api/sincronizarDrive")
async def rota_sincronizar_drive():
    res = enviar_backup_para_drive()
    return JSONResponse(content=res)

@app.post("/api/restaurarDrive")
async def rota_restaurar_drive():
    res = restaurar_backup_do_drive()
    return JSONResponse(content=res)

@app.get("/api/infoRede")
async def rota_info_rede():
    return JSONResponse(content=api_getInfoRede())

@app.post("/api/{func_name}")
async def generic_api_endpoint(func_name: str, request: Request):
    if func_name not in HANDLERS:
        return JSONResponse(status_code=404, content={"error": f"Função '{func_name}' não encontrada."})
    
    try:
        body = await request.json()
        args = body if isinstance(body, list) else [body]
    except Exception:
        args = []
        
    func = HANDLERS[func_name]
    try:
        res = func(*args)
        return JSONResponse(content=res)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e), "success": False, "message": str(e)})

# Rota principal para a aplicação
@app.get("/", response_class=HTMLResponse)
async def home():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(index_path):
        # Fallback para o Index.html da raiz
        index_path = os.path.join(BASE_DIR, "Index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())
