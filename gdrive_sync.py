import os
import io
import json
import zipfile
import shutil
from datetime import datetime
from dotenv import load_dotenv

# Carrega variáveis de ambiente do .env
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "study_hub.db")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
BACKUPS_DIR = os.path.join(BASE_DIR, "backups")
os.makedirs(BACKUPS_DIR, exist_ok=True)

from google_auth import get_google_credentials, get_credentials_path, get_token_path, SCOPES

def is_sync_enabled():
    val = os.getenv("GOOGLE_DRIVE_SYNC_ENABLED", "true").lower()
    return val in ["true", "1", "yes", "sim"]

def get_folder_name():
    return os.getenv("GOOGLE_DRIVE_FOLDER_NAME", "Study Hub - Backup")

def get_drive_service():
    """Autentica e retorna a instância da API do Google Drive."""
    creds, err = get_google_credentials()
    if err:
        return None, err
    try:
        from googleapiclient.discovery import build
        service = build('drive', 'v3', credentials=creds)
        return service, None
    except Exception as e:
        return None, f"Erro na autenticação do Google Drive: {str(e)}"

def get_or_create_drive_folder(service):
    """Encontra ou cria a pasta no Google Drive."""
    folder_name = get_folder_name()
    query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    files = results.get('files', [])

    if files:
        return files[0]['id']

    # Cria a pasta
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    folder = service.files().create(body=file_metadata, fields='id').execute()
    return folder.get('id')

def criar_pacote_backup_local():
    """Cria um arquivo ZIP contendo study_hub.db e a pasta uploads/."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"study_hub_backup_{timestamp}.zip"
    zip_filepath = os.path.join(BACKUPS_DIR, zip_filename)
    latest_filepath = os.path.join(BACKUPS_DIR, "study_hub_latest_backup.zip")

    with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Adiciona o banco SQLite se existir
        if os.path.exists(DB_PATH):
            zipf.write(DB_PATH, arcname="study_hub.db")

        # Adiciona pasta de uploads
        if os.path.exists(UPLOADS_DIR):
            for root, _, files in os.walk(UPLOADS_DIR):
                for f in files:
                    file_path = os.path.join(root, f)
                    arcname = os.path.relpath(file_path, BASE_DIR)
                    zipf.write(file_path, arcname=arcname)

        # Adiciona metadados
        metadata = {
            "geradoEm": datetime.now().isoformat(),
            "timestamp": timestamp,
            "versao": "2.0"
        }
        zipf.writestr("metadata.json", json.dumps(metadata, indent=2))

    # Atualiza cópia "latest"
    shutil.copy2(zip_filepath, latest_filepath)
    return zip_filepath

def enviar_backup_para_drive():
    """Gera o pacote de backup e envia para o Google Drive."""
    if not is_sync_enabled():
        return {"success": False, "message": "Sincronização com Google Drive desativada no .env."}

    service, err = get_drive_service()
    if err:
        return {"success": False, "message": err}

    try:
        from googleapiclient.http import MediaFileUpload

        zip_path = criar_pacote_backup_local()
        folder_id = get_or_create_drive_folder(service)
        filename = "study_hub_latest_backup.zip"

        # Verifica se já existe um backup com esse nome na pasta
        query = f"'{folder_id}' in parents and name='{filename}' and trashed=false"
        results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        files = results.get('files', [])

        media = MediaFileUpload(zip_path, mimetype='application/zip', resumable=True)

        if files:
            # Atualiza o arquivo existente
            file_id = files[0]['id']
            updated_file = service.files().update(
                fileId=file_id,
                media_body=media,
                fields='id, name, modifiedTime'
            ).execute()
            msg = f"Backup atualizado no Google Drive com sucesso! ({updated_file.get('name')})"
        else:
            # Cria novo arquivo
            file_metadata = {
                'name': filename,
                'parents': [folder_id]
            }
            new_file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, modifiedTime'
            ).execute()
            msg = f"Backup criado no Google Drive com sucesso! ({new_file.get('name')})"

        return {
            "success": True,
            "message": msg,
            "arquivo": os.path.basename(zip_path),
            "data": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        }
    except Exception as e:
        return {"success": False, "message": f"Erro no upload para o Google Drive: {str(e)}"}

def restaurar_backup_do_drive():
    """Baixa o backup mais recente do Google Drive e restaura se for mais recente."""
    if not is_sync_enabled():
        return {"success": False, "message": "Sincronização desativada no .env."}

    service, err = get_drive_service()
    if err:
        return {"success": False, "message": err}

    try:
        from googleapiclient.http import MediaIoBaseDownload

        folder_id = get_or_create_drive_folder(service)
        filename = "study_hub_latest_backup.zip"

        query = f"'{folder_id}' in parents and name='{filename}' and trashed=false"
        results = service.files().list(q=query, spaces='drive', fields='files(id, name, modifiedTime)').execute()
        files = results.get('files', [])

        if not files:
            return {"success": True, "message": "Nenhum backup encontrado no Google Drive ainda."}

        file_id = files[0]['id']
        drive_mod_time_str = files[0].get('modifiedTime')

        # Se temos banco local, verifica timestamp
        if os.path.exists(DB_PATH) and drive_mod_time_str:
            local_mod_time = datetime.fromtimestamp(os.path.getmtime(DB_PATH))
            drive_mod_time = datetime.fromisoformat(drive_mod_time_str.replace("Z", "+00:00")).replace(tzinfo=None)
            # Se o local for mais recente ou igual, não precisa sobrescrever
            if local_mod_time >= drive_mod_time:
                return {"success": True, "message": "O banco local já é a versão mais recente."}

        # Baixa o arquivo ZIP
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()

        fh.seek(0)
        with zipfile.ZipFile(fh, 'r') as zipf:
            zipf.extractall(BASE_DIR)

        return {"success": True, "message": "Dados e imagens sincronizados do Google Drive com sucesso!"}
    except Exception as e:
        return {"success": False, "message": f"Erro ao restaurar do Google Drive: {str(e)}"}

def status_drive():
    """Retorna o estado da configuração do Google Drive."""
    cred_path = get_credentials_path()
    token_path = get_token_path()
    tem_cred = os.path.exists(cred_path)
    tem_token = os.path.exists(token_path)
    ativo = is_sync_enabled()

    if not ativo:
        return {"status": "desativado", "mensagem": "Sincronização desativada nas configurações (.env)."}
    if tem_token:
        return {"status": "conectado", "mensagem": "Google Drive conectado e pronto para sincronizar!"}
    if tem_cred:
        return {"status": "pendente_autorizacao", "mensagem": "credentials.json detectado. Inicie o programa para autorizar o acesso."}
    return {"status": "nao_configurado", "mensagem": "credentials.json não encontrado. Veja o arquivo INSTRUCOES_DRIVE.md."}
