import os
import re
import json
import base64
import time
import socket
import requests
from datetime import datetime, timezone
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

from db import (
    init_db, get_connection, get_config, set_config, gerar_id_unico, seed_usuario_padrao,
    get_todas_categorias, adicionar_categoria,
    get_todas_subcategorias, adicionar_subcategoria, excluir_subcategoria,
    get_dashboard,
    get_todas_midias, salvar_midia_db, excluir_midia_db,
    get_habitos_dados, salvar_habito_db, alternar_registro_habito_db,
    excluir_habito_db, salvar_meta_leitura_db, get_grafo_conhecimento,
    obter_permissoes_recurso, pode_criar_no_espaco, obter_itens_acessiveis,
    remover_compartilhamentos_do_item,
    buscar_usuarios_compartilhamento_db, salvar_compartilhamento_db,
    listar_compartilhamentos_db, atualizar_compartilhamento_db,
    revogar_compartilhamento_db, obter_categorias_dono_db,
)
from auth import (
    DEFAULT_OWNER_EMAIL,
    normalizar_email, validar_email, hash_senha, verificar_senha,
    usuario_publico, criar_sessao, revogar_sessao,
    extrair_token_request, obter_usuario_request,
    definir_cookie_sessao, limpar_cookie_sessao, tem_migracao_pendente,
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

# Inicializa banco de dados (com migração automática idempotente)
init_db()

app = FastAPI(title="Study Hub & Life OS Local")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def salvar_arquivo_base64(file_obj):
    if not file_obj or not file_obj.get("data"):
        return {"url": "", "name": "", "directUrl": ""}

    raw_data = file_obj["data"]
    if "," in raw_data:
        raw_data = raw_data.split(",", 1)[1]

    file_bytes = base64.b64decode(raw_data)
    original_name = file_obj.get("fileName") or f"FILE_{int(time.time() * 1000)}.dat"
    clean_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", original_name)
    unique_name = f"{int(time.time() * 1000)}_{clean_name}"

    filepath = os.path.join(UPLOADS_DIR, unique_name)
    with open(filepath, "wb") as f:
        f.write(file_bytes)

    url = f"/uploads/{unique_name}"
    return {
        "url": url,
        "name": original_name,
        "directUrl": url,
    }


def _nao_autenticado_response():
    return JSONResponse(
        status_code=401,
        content={
            "error": "Não autenticado.",
            "message": "Faça login para continuar.",
            "requireAuth": True,
        },
    )


# ================= ROTAS DE AUTENTICAÇÃO E CONTA =================

@app.get("/api/auth/me")
async def auth_me(request: Request):
    user = obter_usuario_request(request)
    if user:
        return JSONResponse(content={"authenticated": True, "user": user})
    return JSONResponse(content={
        "authenticated": False,
        "hasPendingMigration": tem_migracao_pendente(),
    })


@app.post("/api/auth/registrar")
async def auth_registrar(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    nome = (body.get("nome") or "").strip()
    email = normalizar_email(body.get("email") or "")
    senha = body.get("senha") or ""

    if not validar_email(email):
        return JSONResponse(status_code=400, content={"success": False, "message": "Informe um e-mail válido."})
    if len(senha) < 6:
        return JSONResponse(status_code=400, content={"success": False, "message": "A senha deve ter pelo menos 6 caracteres."})

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email,))
    existente = cursor.fetchone()

    if existente:
        if int(existente["precisa_definir_senha"] or 0) == 1:
            nome_final = nome or existente["nome"]
            cursor.execute(
                "UPDATE usuarios SET nome = ?, senha_hash = ?, precisa_definir_senha = 0 WHERE id = ?",
                (nome_final, hash_senha(senha), existente["id"]),
            )
            conn.commit()
            cursor.execute("SELECT * FROM usuarios WHERE id = ?", (existente["id"],))
            row_user = cursor.fetchone()
            conn.close()

            user = usuario_publico(row_user)
            token = criar_sessao(user["id"], request.headers.get("User-Agent", ""))
            resp = JSONResponse(content={
                "success": True,
                "migrated": True,
                "user": user,
                "message": "Conta ativada com sucesso! Todos os seus dados foram carregados.",
            })
            definir_cookie_sessao(resp, token)
            return resp

        conn.close()
        return JSONResponse(status_code=400, content={"success": False, "message": "Este e-mail já está cadastrado."})

    if not nome:
        conn.close()
        return JSONResponse(status_code=400, content={"success": False, "message": "Informe seu nome completo."})

    is_admin = 1 if email == DEFAULT_OWNER_EMAIL else 0
    agora_iso = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        """
        INSERT INTO usuarios (email, nome, senha_hash, precisa_definir_senha, is_admin, criado_em)
        VALUES (?, ?, ?, 0, ?, ?)
        """,
        (email, nome, hash_senha(senha), is_admin, agora_iso),
    )
    new_user_id = int(cursor.lastrowid)
    seed_usuario_padrao(conn, new_user_id)
    conn.commit()

    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (new_user_id,))
    row_user = cursor.fetchone()
    conn.close()

    user = usuario_publico(row_user)
    token = criar_sessao(user["id"], request.headers.get("User-Agent", ""))
    resp = JSONResponse(content={
        "success": True,
        "user": user,
        "message": "Conta criada com sucesso!",
    })
    definir_cookie_sessao(resp, token)
    return resp


@app.post("/api/auth/login")
async def auth_login(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    email = normalizar_email(body.get("email") or "")
    senha = body.get("senha") or ""

    if not email:
        return JSONResponse(status_code=400, content={"success": False, "message": "Informe seu e-mail."})

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()

    if row and int(row["precisa_definir_senha"] or 0) == 1:
        return JSONResponse(content={
            "success": False,
            "requirePasswordSetup": True,
            "email": row["email"],
            "nome": row["nome"],
            "message": "Conta migrada encontrada! Defina sua senha de primeiro acesso para liberar seus dados.",
        })

    if not row or not verificar_senha(senha, row["senha_hash"]):
        return JSONResponse(status_code=401, content={"success": False, "message": "E-mail ou senha incorretos."})

    user = usuario_publico(row)
    token = criar_sessao(user["id"], request.headers.get("User-Agent", ""))
    resp = JSONResponse(content={"success": True, "user": user})
    definir_cookie_sessao(resp, token)
    return resp


@app.post("/api/auth/definirSenhaInicial")
async def auth_definir_senha_inicial(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    email = normalizar_email(body.get("email") or "")
    senha = body.get("senha") or ""
    nome = (body.get("nome") or "").strip()

    if not validar_email(email):
        return JSONResponse(status_code=400, content={"success": False, "message": "Informe um e-mail válido."})
    if len(senha) < 6:
        return JSONResponse(status_code=400, content={"success": False, "message": "A senha deve ter pelo menos 6 caracteres."})

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email,))
    row = cursor.fetchone()
    if not row or int(row["precisa_definir_senha"] or 0) != 1:
        conn.close()
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Esta conta não está pendente de definição inicial de senha."},
        )

    nome_final = nome or row["nome"]
    cursor.execute(
        "UPDATE usuarios SET nome = ?, senha_hash = ?, precisa_definir_senha = 0 WHERE id = ?",
        (nome_final, hash_senha(senha), row["id"]),
    )
    conn.commit()
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (row["id"],))
    atual = cursor.fetchone()
    conn.close()

    user = usuario_publico(atual)
    token = criar_sessao(user["id"], request.headers.get("User-Agent", ""))
    resp = JSONResponse(content={
        "success": True,
        "user": user,
        "message": "Senha definida com sucesso! Seus dados estão prontos.",
    })
    definir_cookie_sessao(resp, token)
    return resp


@app.post("/api/auth/logout")
async def auth_logout(request: Request):
    token = extrair_token_request(request)
    if token:
        revogar_sessao(token)
    resp = JSONResponse(content={"success": True})
    limpar_cookie_sessao(resp)
    return resp


@app.post("/api/auth/alterarSenha")
async def auth_alterar_senha(request: Request):
    user = obter_usuario_request(request)
    if not user:
        return _nao_autenticado_response()

    try:
        body = await request.json()
    except Exception:
        body = {}

    senha_atual = body.get("senhaAtual") or ""
    nova_senha = body.get("novaSenha") or ""

    if len(nova_senha) < 6:
        return JSONResponse(status_code=400, content={"success": False, "message": "A nova senha deve ter pelo menos 6 caracteres."})

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT senha_hash FROM usuarios WHERE id = ?", (user["id"],))
    row = cursor.fetchone()
    if not row or not verificar_senha(senha_atual, row["senha_hash"]):
        conn.close()
        return JSONResponse(status_code=400, content={"success": False, "message": "Senha atual incorreta."})

    cursor.execute("UPDATE usuarios SET senha_hash = ? WHERE id = ?", (hash_senha(nova_senha), user["id"]))
    conn.commit()
    conn.close()
    return JSONResponse(content={"success": True, "message": "Senha alterada com sucesso!"})


@app.post("/api/auth/atualizarPerfil")
async def auth_atualizar_perfil(request: Request):
    user = obter_usuario_request(request)
    if not user:
        return _nao_autenticado_response()

    try:
        body = await request.json()
    except Exception:
        body = {}

    nome = (body.get("nome") or "").strip()
    if not nome:
        return JSONResponse(status_code=400, content={"success": False, "message": "Informe um nome válido."})

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET nome = ? WHERE id = ?", (nome, user["id"]))
    conn.commit()
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user["id"],))
    atual = cursor.fetchone()
    conn.close()
    return JSONResponse(content={
        "success": True,
        "user": usuario_publico(atual),
        "message": "Perfil atualizado com sucesso!",
    })


# ================= HANDLERS DOS ENDPOINTS =================

QUADRANTES_EISENHOWER = {"", "fazer", "agendar", "delegar", "eliminar"}


def api_getDashboardData(user):
    return get_dashboard(user["id"])


def api_getCategorias(user):
    return get_todas_categorias(user["id"])


def api_salvarCategoria(user, nome):
    sucesso, msg = adicionar_categoria(user["id"], nome)
    return {"success": sucesso, "message": msg}


def api_getSubcategorias(user, categoria=None):
    return get_todas_subcategorias(user["id"], categoria)


def api_salvarSubcategoria(user, categoria, nome):
    sucesso, msg = adicionar_subcategoria(user["id"], categoria, nome)
    return {"success": sucesso, "message": msg}


def api_excluirSubcategoria(user, sub_id):
    try:
        sucesso, msg = excluir_subcategoria(user["id"], int(sub_id))
        return {"success": sucesso, "message": msg}
    except (ValueError, TypeError):
        return {"success": False, "message": "ID de subcategoria inválido."}


def api_getAnotacoes(user):
    conn = get_connection()
    itens = obter_itens_acessiveis(conn, user["id"], "anotacao")
    conn.close()

    resultado = []
    for r, perms, owner_info, shared_count in itens:
        resultado.append({
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
            "ownerId": owner_info["id"],
            "ownerNome": owner_info["nome"],
            "ownerEmail": owner_info["email"],
            "compartilhado": not perms["isOwner"],
            "compartilhadoComCount": shared_count,
            "permissoes": perms,
        })
    return resultado


def api_salvarAnotacao(user, dados):
    try:
        uid = user["id"]
        conn = get_connection()
        cursor = conn.cursor()

        anexo_nome = dados.get("anexoNome", "")
        anexo_url = dados.get("anexoUrl", "")

        materia = (dados.get("materia") or "").strip()
        subcategoria = (dados.get("subcategoria") or "").strip()
        aid = dados.get("id")

        if aid:
            cursor.execute("SELECT user_id, materia FROM anotacoes WHERE id = ?", (aid,))
            atual = cursor.fetchone()
            if not atual:
                conn.close()
                return {"success": False, "message": "Anotação não encontrada."}

            owner_id = int(atual["user_id"])
            perms = obter_permissoes_recurso(conn, uid, owner_id, "anotacao", aid, atual["materia"] or "")
            if not perms or not perms["podeEditar"]:
                conn.close()
                return {
                    "success": False,
                    "forbidden": True,
                    "message": "Você não tem permissão para editar esta anotação.",
                }

            if not perms["isOwner"] and materia != (atual["materia"] or ""):
                perms_dest = obter_permissoes_recurso(conn, uid, owner_id, "anotacao", aid, materia)
                if not perms_dest or not perms_dest["podeEditar"]:
                    conn.close()
                    return {
                        "success": False,
                        "forbidden": True,
                        "message": "Você não tem permissão para mover esta anotação para esta categoria.",
                    }

            if dados.get("arquivoData"):
                anexo = salvar_arquivo_base64(dados["arquivoData"])
                anexo_nome = anexo["name"]
                anexo_url = anexo["url"]

            if materia and subcategoria:
                cursor.execute(
                    "INSERT OR IGNORE INTO subcategorias (user_id, categoria, nome) VALUES (?, ?, ?)",
                    (owner_id, materia, subcategoria),
                )

            cursor.execute(
                """
                UPDATE anotacoes
                SET materia = ?, subcategoria = ?, topico = ?, conteudo = ?, tags = ?, link = ?, anexo_nome = ?, anexo_url = ?
                WHERE id = ?
                """,
                (
                    materia,
                    subcategoria,
                    dados.get("topico", ""),
                    dados.get("conteudo", ""),
                    dados.get("tags", ""),
                    dados.get("link", ""),
                    anexo_nome,
                    anexo_url,
                    aid,
                ),
            )
            conn.commit()
            conn.close()
            return {"success": True, "message": "Anotação atualizada!", "id": aid}

        target_owner_id = int(dados.get("ownerUserId") or uid)
        if not pode_criar_no_espaco(conn, uid, target_owner_id, "anotacao", materia):
            conn.close()
            return {
                "success": False,
                "forbidden": True,
                "message": "Sem permissão de escrita para criar anotação neste espaço.",
            }

        if dados.get("arquivoData"):
            anexo = salvar_arquivo_base64(dados["arquivoData"])
            anexo_nome = anexo["name"]
            anexo_url = anexo["url"]

        if materia and subcategoria:
            cursor.execute(
                "INSERT OR IGNORE INTO subcategorias (user_id, categoria, nome) VALUES (?, ?, ?)",
                (target_owner_id, materia, subcategoria),
            )

        novo_id = gerar_id_unico("NOTE")
        data_atual = datetime.now().strftime("%d/%m/%Y %H:%M")
        cursor.execute(
            """
            INSERT INTO anotacoes (id, user_id, data, materia, subcategoria, topico, conteudo, tags, link, anexo_nome, anexo_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                novo_id,
                target_owner_id,
                data_atual,
                materia,
                subcategoria,
                dados.get("topico", ""),
                dados.get("conteudo", ""),
                dados.get("tags", ""),
                dados.get("link", ""),
                anexo_nome,
                anexo_url,
            ),
        )
        conn.commit()
        conn.close()
        return {"success": True, "message": "Anotação salva com sucesso!", "id": novo_id}
    except Exception as e:
        return {"success": False, "message": str(e)}


def api_excluirAnotacao(user, aid):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, materia FROM anotacoes WHERE id = ?", (aid,))
        atual = cursor.fetchone()
        if not atual:
            conn.close()
            return {"success": False, "message": "Anotação não encontrada."}

        perms = obter_permissoes_recurso(conn, user["id"], atual["user_id"], "anotacao", aid, atual["materia"] or "")
        if not perms or not perms["podeExcluir"]:
            conn.close()
            return {"success": False, "forbidden": True, "message": "Sem permissão para excluir esta anotação."}

        cursor.execute("DELETE FROM anotacoes WHERE id = ?", (aid,))
        remover_compartilhamentos_do_item(conn, int(atual["user_id"]), "anotacao", aid)
        conn.commit()
        conn.close()
        return {"success": True, "message": "Anotação excluída!"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def api_getTarefas(user):
    conn = get_connection()
    itens = obter_itens_acessiveis(conn, user["id"], "tarefa")
    conn.close()

    resultado = []
    for r, perms, owner_info, shared_count in itens:
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
            "anexoUrl": r["anexo_url"] or "",
            "eisenhower": r["eisenhower"] or "",
            "ownerId": owner_info["id"],
            "ownerNome": owner_info["nome"],
            "ownerEmail": owner_info["email"],
            "compartilhado": not perms["isOwner"],
            "compartilhadoComCount": shared_count,
            "permissoes": perms,
        })
    return resultado


def api_salvarTarefa(user, dados):
    try:
        uid = user["id"]
        conn = get_connection()
        cursor = conn.cursor()

        anexo_nome = dados.get("anexoNome", "")
        anexo_url = dados.get("anexoUrl", "")
        categoria = (dados.get("categoria") or "").strip()

        eisenhower = (dados.get("eisenhower") or "").strip().lower()
        if eisenhower not in QUADRANTES_EISENHOWER:
            eisenhower = ""

        tid = dados.get("id")
        if tid:
            cursor.execute("SELECT user_id, categoria FROM tarefas WHERE id = ?", (tid,))
            atual = cursor.fetchone()
            if not atual:
                conn.close()
                return {"success": False, "message": "Tarefa não encontrada."}

            owner_id = int(atual["user_id"])
            perms = obter_permissoes_recurso(conn, uid, owner_id, "tarefa", tid, atual["categoria"] or "")
            if not perms or not perms["podeEditar"]:
                conn.close()
                return {"success": False, "forbidden": True, "message": "Sem permissão para editar esta tarefa."}

            if not perms["isOwner"] and categoria != (atual["categoria"] or ""):
                perms_dest = obter_permissoes_recurso(conn, uid, owner_id, "tarefa", tid, categoria)
                if not perms_dest or not perms_dest["podeEditar"]:
                    conn.close()
                    return {
                        "success": False,
                        "forbidden": True,
                        "message": "Você não tem permissão para mover esta tarefa para esta categoria.",
                    }

            if dados.get("arquivoData"):
                anexo = salvar_arquivo_base64(dados["arquivoData"])
                anexo_nome = anexo["name"]
                anexo_url = anexo["url"]

            cursor.execute(
                """
                UPDATE tarefas
                SET titulo = ?, categoria = ?, status = ?, prazo = ?, prioridade = ?, descricao = ?, anexo_nome = ?, anexo_url = ?, eisenhower = ?
                WHERE id = ?
                """,
                (
                    dados.get("titulo", ""),
                    categoria,
                    dados.get("status", "Pendente"),
                    dados.get("prazo", ""),
                    dados.get("prioridade", "Média"),
                    dados.get("descricao", ""),
                    anexo_nome,
                    anexo_url,
                    eisenhower,
                    tid,
                ),
            )
            conn.commit()
            conn.close()
            return {"success": True, "message": "Tarefa atualizada!", "id": tid}

        target_owner_id = int(dados.get("ownerUserId") or uid)
        if not pode_criar_no_espaco(conn, uid, target_owner_id, "tarefa", categoria):
            conn.close()
            return {
                "success": False,
                "forbidden": True,
                "message": "Sem permissão de escrita para criar tarefa neste espaço.",
            }

        if dados.get("arquivoData"):
            anexo = salvar_arquivo_base64(dados["arquivoData"])
            anexo_nome = anexo["name"]
            anexo_url = anexo["url"]

        novo_id = gerar_id_unico("TASK")
        data_atual = datetime.now().strftime("%d/%m/%Y")
        cursor.execute(
            """
            INSERT INTO tarefas (id, user_id, data_criacao, titulo, categoria, status, prazo, prioridade, descricao, anexo_nome, anexo_url, eisenhower)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                novo_id,
                target_owner_id,
                data_atual,
                dados.get("titulo", ""),
                categoria,
                dados.get("status", "Pendente"),
                dados.get("prazo", ""),
                dados.get("prioridade", "Média"),
                dados.get("descricao", ""),
                anexo_nome,
                anexo_url,
                eisenhower,
            ),
        )
        conn.commit()
        conn.close()
        return {"success": True, "message": "Tarefa salva com sucesso!", "id": novo_id}
    except Exception as e:
        return {"success": False, "message": str(e)}


def api_atualizarStatusTarefa(user, tid, novo_status):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, categoria FROM tarefas WHERE id = ?", (tid,))
        atual = cursor.fetchone()
        if not atual:
            conn.close()
            return {"success": False, "message": "Tarefa não encontrada."}

        perms = obter_permissoes_recurso(conn, user["id"], atual["user_id"], "tarefa", tid, atual["categoria"] or "")
        if not perms or not perms["podeEditar"]:
            conn.close()
            return {"success": False, "forbidden": True, "message": "Sem permissão para atualizar esta tarefa."}

        cursor.execute("UPDATE tarefas SET status = ? WHERE id = ?", (novo_status, tid))
        conn.commit()
        conn.close()
        return {"success": True, "message": "Status atualizado!"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def api_atualizarEisenhowerTarefa(user, tid, quadrante):
    try:
        q = (quadrante or "").strip().lower()
        if q not in QUADRANTES_EISENHOWER:
            return {"success": False, "message": "Quadrante inválido."}
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, categoria FROM tarefas WHERE id = ?", (tid,))
        atual = cursor.fetchone()
        if not atual:
            conn.close()
            return {"success": False, "message": "Tarefa não encontrada."}

        perms = obter_permissoes_recurso(conn, user["id"], atual["user_id"], "tarefa", tid, atual["categoria"] or "")
        if not perms or not perms["podeEditar"]:
            conn.close()
            return {"success": False, "forbidden": True, "message": "Sem permissão para atualizar esta tarefa."}

        cursor.execute("UPDATE tarefas SET eisenhower = ? WHERE id = ?", (q, tid))
        conn.commit()
        conn.close()
        return {"success": True, "message": "Quadrante atualizado!"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def api_excluirTarefa(user, tid):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, categoria FROM tarefas WHERE id = ?", (tid,))
        atual = cursor.fetchone()
        if not atual:
            conn.close()
            return {"success": False, "message": "Tarefa não encontrada."}

        perms = obter_permissoes_recurso(conn, user["id"], atual["user_id"], "tarefa", tid, atual["categoria"] or "")
        if not perms or not perms["podeExcluir"]:
            conn.close()
            return {"success": False, "forbidden": True, "message": "Sem permissão para excluir esta tarefa."}

        cursor.execute("DELETE FROM tarefas WHERE id = ?", (tid,))
        remover_compartilhamentos_do_item(conn, int(atual["user_id"]), "tarefa", tid)
        conn.commit()
        conn.close()
        return {"success": True, "message": "Tarefa excluída!"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def api_getCursos(user):
    conn = get_connection()
    itens = obter_itens_acessiveis(conn, user["id"], "curso")
    conn.close()

    resultado = []
    for r, perms, owner_info, shared_count in itens:
        resultado.append({
            "id": r["id"],
            "nome": r["nome"],
            "instituicao": r["instituicao"],
            "categoria": r["categoria"],
            "cargaHoraria": r["carga_horaria"],
            "status": r["status"],
            "link": r["link"],
            "ownerId": owner_info["id"],
            "ownerNome": owner_info["nome"],
            "ownerEmail": owner_info["email"],
            "compartilhado": not perms["isOwner"],
            "compartilhadoComCount": shared_count,
            "permissoes": perms,
        })
    return resultado


def api_salvarCurso(user, dados):
    try:
        uid = user["id"]
        conn = get_connection()
        cursor = conn.cursor()
        categoria = (dados.get("categoria") or "").strip()
        cid = dados.get("id")

        if cid:
            cursor.execute("SELECT user_id, categoria FROM cursos WHERE id = ?", (cid,))
            atual = cursor.fetchone()
            if not atual:
                conn.close()
                return {"success": False, "message": "Curso não encontrado."}
            owner_id = int(atual["user_id"])
            perms = obter_permissoes_recurso(conn, uid, owner_id, "curso", cid, atual["categoria"] or "")
            if not perms or not perms["podeEditar"]:
                conn.close()
                return {"success": False, "forbidden": True, "message": "Sem permissão para editar este curso."}

            if not perms["isOwner"] and categoria != (atual["categoria"] or ""):
                perms_dest = obter_permissoes_recurso(conn, uid, owner_id, "curso", cid, categoria)
                if not perms_dest or not perms_dest["podeEditar"]:
                    conn.close()
                    return {
                        "success": False,
                        "forbidden": True,
                        "message": "Você não tem permissão para mover este curso para esta categoria.",
                    }

            cursor.execute(
                """
                UPDATE cursos
                SET nome = ?, instituicao = ?, categoria = ?, carga_horaria = ?, status = ?, link = ?
                WHERE id = ?
                """,
                (
                    dados.get("nome", ""),
                    dados.get("instituicao", ""),
                    categoria,
                    dados.get("cargaHoraria", ""),
                    dados.get("status", "Em Andamento"),
                    dados.get("link", ""),
                    cid,
                ),
            )
            conn.commit()
            conn.close()
            return {"success": True, "message": "Curso atualizado!", "id": cid}

        target_owner_id = int(dados.get("ownerUserId") or uid)
        if not pode_criar_no_espaco(conn, uid, target_owner_id, "curso", categoria):
            conn.close()
            return {"success": False, "forbidden": True, "message": "Sem permissão para criar curso neste espaço."}

        novo_cid = gerar_id_unico("CRS")
        cursor.execute(
            """
            INSERT INTO cursos (id, user_id, nome, instituicao, categoria, carga_horaria, status, link)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                novo_cid,
                target_owner_id,
                dados.get("nome", ""),
                dados.get("instituicao", ""),
                categoria,
                dados.get("cargaHoraria", ""),
                dados.get("status", "Em Andamento"),
                dados.get("link", ""),
            ),
        )
        conn.commit()
        conn.close()
        return {"success": True, "message": "Curso salvo!", "id": novo_cid}
    except Exception as e:
        return {"success": False, "message": str(e)}


def api_excluirCurso(user, cid):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, categoria FROM cursos WHERE id = ?", (cid,))
        atual = cursor.fetchone()
        if not atual:
            conn.close()
            return {"success": False, "message": "Curso não encontrado."}

        perms = obter_permissoes_recurso(conn, user["id"], atual["user_id"], "curso", cid, atual["categoria"] or "")
        if not perms or not perms["podeExcluir"]:
            conn.close()
            return {"success": False, "forbidden": True, "message": "Sem permissão para excluir este curso."}

        cursor.execute("DELETE FROM cursos WHERE id = ?", (cid,))
        remover_compartilhamentos_do_item(conn, int(atual["user_id"]), "curso", cid)
        conn.commit()
        conn.close()
        return {"success": True, "message": "Curso excluído!"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def api_getFlashcards(user):
    conn = get_connection()
    itens = obter_itens_acessiveis(conn, user["id"], "flashcard")
    conn.close()

    resultado = []
    for r, perms, owner_info, shared_count in itens:
        resultado.append({
            "id": r["id"],
            "categoria": r["categoria"],
            "frente": r["frente"],
            "verso": r["verso"],
            "nivel": r["nivel"] or "Novo",
            "ultimaRevisao": r["ultima_revisao"] or "Nunca",
            "ownerId": owner_info["id"],
            "ownerNome": owner_info["nome"],
            "ownerEmail": owner_info["email"],
            "compartilhado": not perms["isOwner"],
            "compartilhadoComCount": shared_count,
            "permissoes": perms,
        })
    return resultado


def api_salvarFlashcard(user, dados):
    try:
        uid = user["id"]
        conn = get_connection()
        cursor = conn.cursor()
        categoria = (dados.get("categoria") or "").strip()
        fid = dados.get("id")

        if fid:
            cursor.execute("SELECT user_id, categoria FROM flashcards WHERE id = ?", (fid,))
            atual = cursor.fetchone()
            if not atual:
                conn.close()
                return {"success": False, "message": "Flashcard não encontrado."}
            owner_id = int(atual["user_id"])
            perms = obter_permissoes_recurso(conn, uid, owner_id, "flashcard", fid, atual["categoria"] or "")
            if not perms or not perms["podeEditar"]:
                conn.close()
                return {"success": False, "forbidden": True, "message": "Sem permissão para editar este flashcard."}

            if not perms["isOwner"] and categoria != (atual["categoria"] or ""):
                perms_dest = obter_permissoes_recurso(conn, uid, owner_id, "flashcard", fid, categoria)
                if not perms_dest or not perms_dest["podeEditar"]:
                    conn.close()
                    return {
                        "success": False,
                        "forbidden": True,
                        "message": "Você não tem permissão para mover este flashcard para esta categoria.",
                    }

            cursor.execute(
                """
                UPDATE flashcards SET categoria = ?, frente = ?, verso = ? WHERE id = ?
                """,
                (categoria, dados.get("frente", ""), dados.get("verso", ""), fid),
            )
            conn.commit()
            conn.close()
            return {"success": True, "message": "Flashcard atualizado!", "id": fid}

        target_owner_id = int(dados.get("ownerUserId") or uid)
        if not pode_criar_no_espaco(conn, uid, target_owner_id, "flashcard", categoria):
            conn.close()
            return {"success": False, "forbidden": True, "message": "Sem permissão para criar flashcard neste espaço."}

        novo_fid = gerar_id_unico("FC")
        cursor.execute(
            """
            INSERT INTO flashcards (id, user_id, categoria, frente, verso, nivel, ultima_revisao)
            VALUES (?, ?, ?, ?, ?, 'Novo', '')
            """,
            (
                novo_fid,
                target_owner_id,
                categoria,
                dados.get("frente", ""),
                dados.get("verso", ""),
            ),
        )
        conn.commit()
        conn.close()
        return {"success": True, "message": "Flashcard criado!", "id": novo_fid}
    except Exception as e:
        return {"success": False, "message": str(e)}


def api_atualizarNivelFlashcard(user, fid, nivel):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, categoria FROM flashcards WHERE id = ?", (fid,))
        atual = cursor.fetchone()
        if not atual:
            conn.close()
            return {"success": False, "message": "Flashcard não encontrado."}

        perms = obter_permissoes_recurso(conn, user["id"], atual["user_id"], "flashcard", fid, atual["categoria"] or "")
        if not perms or not perms["podeEditar"]:
            conn.close()
            return {"success": False, "forbidden": True, "message": "Sem permissão para alterar este flashcard."}

        hoje = datetime.now().strftime("%d/%m/%Y")
        cursor.execute("UPDATE flashcards SET nivel = ?, ultima_revisao = ? WHERE id = ?", (nivel, hoje, fid))
        conn.commit()
        conn.close()
        return {"success": True}
    except Exception as e:
        return {"success": False, "message": str(e)}


def api_excluirFlashcard(user, fid):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, categoria FROM flashcards WHERE id = ?", (fid,))
        atual = cursor.fetchone()
        if not atual:
            conn.close()
            return {"success": False, "message": "Flashcard não encontrado."}

        perms = obter_permissoes_recurso(conn, user["id"], atual["user_id"], "flashcard", fid, atual["categoria"] or "")
        if not perms or not perms["podeExcluir"]:
            conn.close()
            return {"success": False, "forbidden": True, "message": "Sem permissão para excluir este flashcard."}

        cursor.execute("DELETE FROM flashcards WHERE id = ?", (fid,))
        remover_compartilhamentos_do_item(conn, int(atual["user_id"]), "flashcard", fid)
        conn.commit()
        conn.close()
        return {"success": True, "message": "Flashcard excluído!"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def api_registrarSessaoPomodoro(user, categoria, minutos):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        pid = gerar_id_unico("POMO")
        data_atual = datetime.now().strftime("%d/%m/%Y %H:%M")
        cursor.execute(
            """
            INSERT INTO pomodoro (id, user_id, data, categoria, minutos)
            VALUES (?, ?, ?, ?, ?)
            """,
            (pid, user["id"], data_atual, categoria or "Geral", int(minutos) if minutos else 25),
        )
        conn.commit()
        conn.close()
        return {"success": True, "message": f"Sessão de {minutos} min registrada com sucesso!"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def api_uploadImagemEditor(user, file_obj):
    res = salvar_arquivo_base64(file_obj)
    return {"directUrl": res["directUrl"]}


def api_uploadArquivoDrive(user, file_obj):
    return salvar_arquivo_base64(file_obj)


def api_salvarChaveGemini(user, api_key):
    set_config(user["id"], "GEMINI_API_KEY", api_key.strip())
    return {"success": True, "message": "Chave da API Gemini guardada com segurança no banco local!"}


def api_chamarAssistenteIA(user, acao, texto_conteudo, categoria_atual):
    try:
        api_key = get_config(user["id"], "GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            return {
                "success": False,
                "needKey": True,
                "message": "Configure a sua chave da API do Google Gemini no arquivo .env (GEMINI_API_KEY=...) ou clique no ícone de engrenagem.",
            }

        prompt = ""
        if acao == "resumir":
            prompt = (
                "Crie um resumo executivo estruturado em HTML (use apenas tags <h3>, <p>, <ul>, <li>, <strong>, sem blocos markdown ```html) destacando os pontos principais do seguinte texto:\n\n"
                + texto_conteudo
            )
        elif acao == "topicos":
            prompt = (
                "Extraia os conceitos-chave, termos técnicos e ideias centrais em formato de lista de revisão em HTML (use <h3>, <ul>, <li>, <strong>, sem markdown ```html) a partir do seguinte texto:\n\n"
                + texto_conteudo
            )
        elif acao == "flashcards":
            prompt = (
                "A partir do texto abaixo, gere exatamente 4 flashcards de estudo com perguntas diretas e respostas claras. Retorne APENAS um JSON válido no formato [{\"frente\": \"Pergunta?\", \"verso\": \"Resposta\"}] sem nenhum texto adicional ou formatação markdown:\n\n"
                + texto_conteudo
            )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}

        resp = requests.post(url, json=payload, timeout=30)
        data = resp.json()

        if "error" in data:
            return {"success": False, "message": f"Erro na API Gemini: {data['error'].get('message', '')}"}

        resposta_texto = data["candidates"][0]["content"]["parts"][0]["text"]
        resposta_texto = re.sub(r"```(html|json)?", "", resposta_texto).replace("```", "").strip()

        if acao == "flashcards":
            cards = json.loads(resposta_texto)
            for c in cards:
                api_salvarFlashcard(
                    user,
                    {
                        "categoria": categoria_atual or "Geral",
                        "frente": c.get("frente", ""),
                        "verso": c.get("verso", ""),
                    },
                )
            return {
                "success": True,
                "isFlashcards": True,
                "message": f"{len(cards)} Flashcards foram gerados e adicionados automaticamente à sua aba de Flashcards!",
            }

        return {"success": True, "html": resposta_texto}
    except Exception as e:
        return {"success": False, "message": f"Erro ao processar com IA: {str(e)}"}


def api_getMidias(user, tipo=None, status=None):
    return get_todas_midias(user["id"], tipo, status)


def api_salvarMidia(user, dados):
    return salvar_midia_db(user["id"], dados)


def api_excluirMidia(user, mid):
    return excluir_midia_db(user["id"], mid)


def api_buscarMetadadosMidia(user, tipo, termo):
    return buscar_metadados_midia(tipo, termo)


def api_sincronizarGoogleCalendar(user):
    if not user["isAdmin"]:
        return {
            "success": False,
            "forbidden": True,
            "message": "Apenas o administrador pode sincronizar a Google Agenda do servidor.",
        }
    return sincronizar_tarefas_google_calendar(user["id"])


def api_getEventosGoogleCalendar(user):
    if not user["isAdmin"]:
        return []
    return obter_eventos_google_calendar()


def api_getHabitosDados(user):
    return get_habitos_dados(user["id"])


def api_salvarHabito(user, dados):
    return salvar_habito_db(user["id"], dados)


def api_alternarRegistroHabito(user, habito_id, data_str):
    return alternar_registro_habito_db(user["id"], habito_id, data_str)


def api_excluirHabito(user, habito_id):
    return excluir_habito_db(user["id"], habito_id)


def api_salvarMetaLeitura(user, meta):
    return salvar_meta_leitura_db(user["id"], meta)


def api_getGrafoConhecimento(user):
    return get_grafo_conhecimento(user["id"])


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


def api_getInfoRede(user=None):
    ip = obter_ip_rede_local()
    return {
        "ip": ip,
        "porta": 8000,
        "urlRede": f"http://{ip}:8000",
        "urlLocal": "http://127.0.0.1:8000",
    }


# ================= HANDLERS DE COMPARTILHAMENTO =================

def api_buscarUsuariosCompartilhamento(user, termo=""):
    return buscar_usuarios_compartilhamento_db(user["id"], termo)


def api_criarOuAtualizarCompartilhamento(user, dados):
    return salvar_compartilhamento_db(user["id"], dados)


def api_getCompartilhamentos(user, filtro=None):
    return listar_compartilhamentos_db(user["id"], filtro)


def api_atualizarPermissaoCompartilhamento(user, share_id, dados):
    return atualizar_compartilhamento_db(user["id"], share_id, dados)


def api_revogarCompartilhamento(user, share_id):
    return revogar_compartilhamento_db(user["id"], share_id)


def api_getCategoriasDono(user, owner_id):
    try:
        return obter_categorias_dono_db(user["id"], int(owner_id))
    except (ValueError, TypeError):
        return {"success": False, "categorias": [], "subcategorias": []}


HANDLERS = {
    "getDashboardData": api_getDashboardData,
    "getCategorias": api_getCategorias,
    "salvarCategoria": api_salvarCategoria,
    "getSubcategorias": api_getSubcategorias,
    "salvarSubcategoria": api_salvarSubcategoria,
    "excluirSubcategoria": api_excluirSubcategoria,
    "getAnotacoes": api_getAnotacoes,
    "salvarAnotacao": api_salvarAnotacao,
    "excluirAnotacao": api_excluirAnotacao,
    "getTarefas": api_getTarefas,
    "salvarTarefa": api_salvarTarefa,
    "atualizarStatusTarefa": api_atualizarStatusTarefa,
    "atualizarEisenhowerTarefa": api_atualizarEisenhowerTarefa,
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
    "buscarUsuariosCompartilhamento": api_buscarUsuariosCompartilhamento,
    "criarOuAtualizarCompartilhamento": api_criarOuAtualizarCompartilhamento,
    "getCompartilhamentos": api_getCompartilhamentos,
    "atualizarPermissaoCompartilhamento": api_atualizarPermissaoCompartilhamento,
    "revogarCompartilhamento": api_revogarCompartilhamento,
    "getCategoriasDono": api_getCategoriasDono,
}


# ================= ROTAS PROTEGIDAS DE ARQUIVOS, IMPORTAÇÃO E BACKUP =================

@app.get("/uploads/{filename:path}")
async def servir_upload(filename: str, request: Request):
    user = obter_usuario_request(request)
    if not user:
        return _nao_autenticado_response()

    uploads_real = os.path.realpath(UPLOADS_DIR)
    target_real = os.path.realpath(os.path.join(uploads_real, filename))
    if not target_real.startswith(uploads_real + os.sep):
        return JSONResponse(status_code=403, content={"error": "Acesso negado."})
    if not os.path.isfile(target_real):
        return JSONResponse(status_code=404, content={"error": "Arquivo não encontrado."})
    return FileResponse(target_real)


@app.post("/api/importarPlanilha")
async def importar_planilha(request: Request, arquivo: UploadFile = File(...)):
    user = obter_usuario_request(request)
    if not user:
        return _nao_autenticado_response()

    try:
        nome_base = os.path.basename(arquivo.filename or "import.dat")
        nome = nome_base.lower()
        temp_path = os.path.join(BASE_DIR, f"temp_upload_{user['id']}_{nome_base}")
        with open(temp_path, "wb") as f:
            content = await arquivo.read()
            f.write(content)

        if nome.endswith(".xlsx"):
            resumo = importar_arquivo_xlsx(temp_path, user["id"])
        elif nome.endswith(".json"):
            resumo = importar_arquivo_json(temp_path, user["id"])
        else:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return {"success": False, "message": "Formato inválido. Envie um arquivo .xlsx ou .json."}

        if os.path.exists(temp_path):
            os.remove(temp_path)

        total = sum(resumo.values())
        msg = f"Importação concluída com sucesso! Total de {total} registos importados (Anotações: {resumo['anotacoes']}, Tarefas: {resumo['tarefas']}, Cursos: {resumo['cursos']}, Flashcards: {resumo['flashcards']}, Pomodoros: {resumo['pomodoro']}, Categorias: {resumo['categorias']})."
        return {"success": True, "message": msg, "resumo": resumo}
    except Exception as e:
        return {"success": False, "message": f"Erro ao importar: {str(e)}"}


@app.get("/api/exportarBackup")
async def exportar_backup(request: Request):
    user = obter_usuario_request(request)
    if not user:
        return _nao_autenticado_response()

    dados = exportar_todos_dados(user["id"])
    return JSONResponse(
        content=dados,
        headers={"Content-Disposition": f"attachment; filename=study_hub_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"},
    )


@app.get("/api/statusDrive")
async def rota_status_drive(request: Request):
    user = obter_usuario_request(request)
    if not user:
        return _nao_autenticado_response()
    res = status_drive()
    res["isAdmin"] = user["isAdmin"]
    return JSONResponse(content=res)


@app.post("/api/sincronizarDrive")
async def rota_sincronizar_drive(request: Request):
    user = obter_usuario_request(request)
    if not user:
        return _nao_autenticado_response()
    if not user["isAdmin"]:
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Apenas o administrador pode executar backup do servidor no Google Drive."},
        )
    res = enviar_backup_para_drive()
    return JSONResponse(content=res)


@app.post("/api/restaurarDrive")
async def rota_restaurar_drive(request: Request):
    user = obter_usuario_request(request)
    if not user:
        return _nao_autenticado_response()
    if not user["isAdmin"]:
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Apenas o administrador pode restaurar backup do servidor do Google Drive."},
        )
    res = restaurar_backup_do_drive()
    return JSONResponse(content=res)


@app.get("/api/infoRede")
async def rota_info_rede(request: Request):
    user = obter_usuario_request(request)
    if not user:
        return _nao_autenticado_response()
    return JSONResponse(content=api_getInfoRede(user))


@app.post("/api/{func_name}")
async def generic_api_endpoint(func_name: str, request: Request):
    user = obter_usuario_request(request)
    if not user:
        return _nao_autenticado_response()

    if func_name not in HANDLERS:
        return JSONResponse(status_code=404, content={"error": f"Função '{func_name}' não encontrada."})

    try:
        body = await request.json()
        args = body if isinstance(body, list) else [body]
    except Exception:
        args = []

    func = HANDLERS[func_name]
    try:
        res = func(user, *args)
        if isinstance(res, dict) and res.get("forbidden"):
            return JSONResponse(status_code=403, content=res)
        return JSONResponse(content=res)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e), "success": False, "message": str(e)})


# Rota principal para a aplicação
@app.get("/", response_class=HTMLResponse)
async def home():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(index_path):
        index_path = os.path.join(BASE_DIR, "Index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())
