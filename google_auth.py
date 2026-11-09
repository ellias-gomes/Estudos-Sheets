import os
import json
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Escopos unificados para Google Drive (backup) e Google Calendar (agenda)
SCOPES = [
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/calendar'
]

def get_credentials_path():
    cred_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    if not os.path.isabs(cred_file):
        cred_file = os.path.join(BASE_DIR, cred_file)
    return cred_file

def get_token_path():
    token_file = os.getenv("GOOGLE_TOKEN_FILE", "token.json")
    if not os.path.isabs(token_file):
        token_file = os.path.join(BASE_DIR, token_file)
    return token_file

def get_google_credentials(force_reauth=False, interactive=False):
    """
    Retorna credenciais OAuth2 válidas para Google Drive e Google Calendar.
    Garante que o token.json possua os escopos completos.
    """
    cred_path = get_credentials_path()
    token_path = get_token_path()

    if not os.path.exists(cred_path) and not os.path.exists(token_path):
        return None, "Arquivo credentials.json não encontrado. Veja o guia INSTRUCOES_DRIVE.md."

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        creds = None

        if os.path.exists(token_path) and not force_reauth:
            try:
                # Inspeciona os escopos gravados no próprio arquivo JSON
                with open(token_path, 'r', encoding='utf-8') as f:
                    token_data = json.load(f)
                
                saved_scopes = token_data.get('scopes', [])
                
                # Se o token antigo não tiver permissão para o Calendar, descarta e força reautorização
                tem_calendar = any('calendar' in s for s in saved_scopes)
                if not tem_calendar:
                    print("⚠️ O token.json atual possui apenas permissões do Drive. Atualizando para incluir Google Calendar...")
                    try: os.remove(token_path)
                    except Exception: pass
                    creds = None
                else:
                    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            except Exception as e:
                print(f"⚠️ Erro ao ler token.json: {e}")
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    creds = None

            if not creds:
                if not os.path.exists(cred_path):
                    return None, f"Arquivo {os.path.basename(cred_path)} necessário para gerar nova autorização."

                if not interactive:
                    return None, "Autorização pendente. Inicie o programa via './iniciar.sh' no terminal para autorizar o Google Drive e o Google Calendar no seu navegador."

                print("\n🌐 Abrindo navegador para autorizar acesso ao Google Drive e Google Calendar...")
                flow = InstalledAppFlow.from_client_secrets_file(cred_path, SCOPES)
                creds = flow.run_local_server(port=0)

            # Salva o novo token.json com os escopos completos
            with open(token_path, 'w', encoding='utf-8') as token:
                token.write(creds.to_json())
            print("✅ Novo token.json gerado com sucesso com permissões completas!")

        return creds, None
    except Exception as e:
        return None, f"Erro na autenticação do Google: {str(e)}"
