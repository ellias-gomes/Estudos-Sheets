import os
import re
import hmac
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

import db

load_dotenv()

DEFAULT_OWNER_EMAIL = os.getenv("DEFAULT_OWNER_EMAIL", "eu.elliasaugusto@gmail.com").strip().lower()
DEFAULT_OWNER_NAME = "Ellias Augusto"
SESSION_COOKIE_NAME = "study_hub_session"
SESSION_DURATION_DAYS = 30

_EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalizar_email(email: str) -> str:
    """Normaliza um endereço de e-mail removendo espaços e convertendo para minúsculas."""
    return (email or "").strip().lower()


def validar_email(email: str) -> bool:
    """Valida o formato básico de um endereço de e-mail."""
    return bool(_EMAIL_REGEX.match(normalizar_email(email)))


def hash_senha(senha: str) -> str:
    """Gera hash seguro da senha usando scrypt (com fallback PBKDF2-HMAC-SHA256)."""
    if not senha:
        raise ValueError("A senha não pode ser vazia.")
    salt = secrets.token_bytes(16)
    senha_bytes = senha.encode("utf-8")
    if hasattr(hashlib, "scrypt"):
        try:
            dk = hashlib.scrypt(
                senha_bytes,
                salt=salt,
                n=16384,
                r=8,
                p=1,
                maxmem=32 * 1024 * 1024,
                dklen=32,
            )
            return f"scrypt${salt.hex()}${dk.hex()}"
        except (ValueError, OSError):
            pass
    dk = hashlib.pbkdf2_hmac("sha256", senha_bytes, salt, 200_000, dklen=32)
    return f"pbkdf2${salt.hex()}${dk.hex()}"


def verificar_senha(senha: str, senha_hash: str) -> bool:
    """Verifica senha em texto plano contra o hash armazenado usando comparação constante."""
    if not senha or not senha_hash or "$" not in senha_hash:
        return False
    partes = senha_hash.split("$")
    if len(partes) != 3:
        return False
    algo, salt_hex, hash_hex = partes
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False

    senha_bytes = senha.encode("utf-8")
    if algo == "scrypt" and hasattr(hashlib, "scrypt"):
        try:
            dk = hashlib.scrypt(
                senha_bytes,
                salt=salt,
                n=16384,
                r=8,
                p=1,
                maxmem=32 * 1024 * 1024,
                dklen=len(expected),
            )
            return hmac.compare_digest(dk, expected)
        except (ValueError, OSError):
            return False
    if algo == "pbkdf2":
        dk = hashlib.pbkdf2_hmac("sha256", senha_bytes, salt, 200_000, dklen=len(expected))
        return hmac.compare_digest(dk, expected)
    return False


def hash_token(token: str) -> str:
    """Retorna o hash SHA-256 do token de sessão para persistência segura."""
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def usuario_publico(row) -> dict:
    """Converte uma linha da tabela usuarios para dicionário público seguro."""
    return {
        "id": row["id"],
        "email": row["email"],
        "nome": row["nome"],
        "isAdmin": bool(row["is_admin"]),
        "criadoEm": row["criado_em"],
    }


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _esta_expirada(expira_em_str: str, agora: datetime) -> bool:
    if not expira_em_str:
        return True
    try:
        expira_dt = datetime.fromisoformat(expira_em_str)
        if expira_dt.tzinfo is None:
            expira_dt = expira_dt.replace(tzinfo=timezone.utc)
        return expira_dt <= agora
    except ValueError:
        return True


def criar_sessao(user_id: int, user_agent: str = "") -> str:
    """Cria uma nova sessão persistida no SQLite e retorna o token bruto."""
    token = secrets.token_urlsafe(32)
    token_h = hash_token(token)
    agora = _agora_utc()
    expira = agora + timedelta(days=SESSION_DURATION_DAYS)
    agora_iso = agora.isoformat()

    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM sessoes WHERE user_id = ? AND expira_em <= ?",
        (user_id, agora_iso),
    )
    cursor.execute(
        """
        INSERT INTO sessoes (token_hash, user_id, criado_em, expira_em, user_agent)
        VALUES (?, ?, ?, ?, ?)
        """,
        (token_h, user_id, agora_iso, expira.isoformat(), (user_agent or "")[:255]),
    )
    conn.commit()
    conn.close()
    return token


def obter_usuario_por_token(token: str):
    """Obtém o usuário autenticado a partir do token de sessão, validando expiração."""
    if not token:
        return None
    token_h = hash_token(token)
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT s.token_hash, s.expira_em, u.id, u.email, u.nome, u.is_admin, u.criado_em, u.precisa_definir_senha
        FROM sessoes s
        JOIN usuarios u ON u.id = s.user_id
        WHERE s.token_hash = ?
        """,
        (token_h,),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    if _esta_expirada(row["expira_em"], _agora_utc()) or int(row["precisa_definir_senha"] or 0) == 1:
        cursor.execute("DELETE FROM sessoes WHERE token_hash = ?", (token_h,))
        conn.commit()
        conn.close()
        return None

    user = usuario_publico(row)
    conn.close()
    return user


def revogar_sessao(token: str) -> None:
    """Remove a sessão correspondente ao token fornecido."""
    if not token:
        return
    token_h = hash_token(token)
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessoes WHERE token_hash = ?", (token_h,))
    conn.commit()
    conn.close()


def extrair_token_request(request):
    """Extrai o token de sessão do cookie HttpOnly ou do cabeçalho Authorization Bearer."""
    if request is None:
        return None
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        return token
    auth_header = request.headers.get("Authorization") or ""
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip() or None
    return None


def obter_usuario_request(request):
    """Retorna o usuário autenticado da requisição HTTP atual, ou None."""
    token = extrair_token_request(request)
    if not token:
        return None
    return obter_usuario_por_token(token)


def definir_cookie_sessao(response, token: str) -> None:
    """Anexa o cookie HttpOnly da sessão à resposta HTTP (compatível com LAN HTTP)."""
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=SESSION_DURATION_DAYS * 86400,
        path="/",
    )


def limpar_cookie_sessao(response) -> None:
    """Remove o cookie de sessão da resposta HTTP."""
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")


def tem_migracao_pendente() -> bool:
    """Indica se existe conta migrada aguardando definição da senha de primeiro acesso."""
    conn = db.get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM usuarios WHERE precisa_definir_senha = 1 LIMIT 1")
        existe = cursor.fetchone() is not None
    except Exception:
        existe = False
    finally:
        conn.close()
    return existe
