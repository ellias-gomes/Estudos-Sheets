import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from db import get_connection

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
from google_auth import get_google_credentials, get_credentials_path, get_token_path, SCOPES

def get_calendar_service(force_reauth=False):
    """Autentica e retorna o serviço da API do Google Calendar."""
    creds, err = get_google_credentials(force_reauth=force_reauth)
    if err:
        return None, err

    try:
        from googleapiclient.discovery import build
        service = build('calendar', 'v3', credentials=creds)
        return service, None
    except Exception as e:
        return None, f"Erro ao conectar com Google Calendar: {str(e)}"

def get_or_create_study_calendar(service):
    """Encontra ou cria uma agenda dedicada 'Study Hub - Prazos & Estudos'."""
    try:
        calendars = service.calendarList().list().execute().get('items', [])
        nome_agenda = "Study Hub - Prazos & Estudos"
        for cal in calendars:
            if cal.get('summary') == nome_agenda:
                return cal['id']

        # Cria a agenda secundária
        calendar = {
            'summary': nome_agenda,
            'timeZone': 'America/Sao_Paulo',
            'description': 'Agenda sincronizada automaticamente pelo Study Hub PRO'
        }
        created_cal = service.calendars().insert(body=calendar).execute()
        return created_cal['id']
    except Exception:
        # Fallback para a agenda principal se falhar
        return 'primary'

def sincronizar_tarefas_google_calendar():
    """Envia tarefas pendentes com prazo para o Google Calendar."""
    service, err = get_calendar_service()
    if err:
        return {"success": False, "message": err}

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tarefas WHERE prazo IS NOT NULL AND prazo != '' AND status != 'Concluído'")
        tarefas = cursor.fetchall()
        conn.close()

        if not tarefas:
            return {"success": True, "message": "Nenhuma tarefa pendente com prazo para sincronizar.", "total": 0}

        cal_id = get_or_create_study_calendar(service)

        # Busca eventos existentes para não duplicar
        agora = datetime.utcnow().isoformat() + 'Z'
        events_result = service.events().list(calendarId=cal_id, timeMin=agora, maxResults=250, singleEvents=True).execute()
        existing_events = events_result.get('items', [])
        existing_descriptions = {ev.get('description', ''): ev['id'] for ev in existing_events}

        sincronizados = 0
        for t in tarefas:
            tid = t["id"]
            marcador_id = f"[ID:{tid}]"
            
            # Verifica se já existe um evento com o ID desta tarefa
            evento_ja_existe = any(marcador_id in desc for desc in existing_descriptions)
            if evento_ja_existe:
                continue

            prazo_str = t["prazo"] # Formato YYYY-MM-DD
            event_body = {
                'summary': f"📌 [{t['prioridade']}] {t['titulo']}",
                'description': f"{marcador_id}\nCategoria: {t['categoria']}\nStatus: {t['status']}\n\n{t['descricao'] or ''}",
                'start': {'date': prazo_str},
                'end': {'date': prazo_str},
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'popup', 'minutes': 24 * 60}, # 1 dia antes
                        {'method': 'popup', 'minutes': 60}       # 1 hora antes
                    ]
                }
            }
            service.events().insert(calendarId=cal_id, body=event_body).execute()
            sincronizados += 1

        return {
            "success": True,
            "message": f"Sincronização concluída! {sincronizados} nova(s) tarefa(s) enviada(s) para sua Google Agenda.",
            "total": sincronizados
        }
    except Exception as e:
        msg = str(e)
        if "insufficient" in msg.lower() or "403" in msg:
            token_p = get_token_path()
            if os.path.exists(token_p):
                try: os.remove(token_p)
                except Exception: pass
            return {
                "success": False,
                "message": "Permissão do Google Calendar ausente no token antigo. O token desatualizado foi removido automaticamente! Execute './iniciar.sh' ou clique em sincronizar novamente para conceder acesso à sua Google Agenda no navegador."
            }
        return {"success": False, "message": f"Erro na sincronização da agenda: {msg}"}

def obter_eventos_google_calendar():
    """Puxa eventos dos próximos 60 dias da Google Agenda para exibição local."""
    service, err = get_calendar_service()
    if err:
        return []

    try:
        cal_id = get_or_create_study_calendar(service)
        inicio = (datetime.utcnow() - timedelta(days=30)).isoformat() + 'Z'
        fim = (datetime.utcnow() + timedelta(days=90)).isoformat() + 'Z'

        events_result = service.events().list(
            calendarId=cal_id,
            timeMin=inicio,
            timeMax=fim,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        eventos = []
        for ev in events_result.get('items', []):
            start = ev['start'].get('date') or ev['start'].get('dateTime')
            if start and 'T' in start:
                start = start.split('T')[0]

            eventos.append({
                "id": ev['id'],
                "title": f"🗓️ {ev.get('summary', 'Compromisso')}",
                "start": start,
                "backgroundColor": "#0284c7",
                "borderColor": "#0284c7",
                "origem": "google"
            })
        return eventos
    except Exception:
        return []
