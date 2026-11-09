#!/usr/bin/env python3
import os
import sys
import webbrowser
import threading
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Se houver um ambiente virtual .venv e não estiver ativado, reexecuta dentro dele
venv_python = os.path.join(BASE_DIR, ".venv", "bin", "python3")
if os.path.exists(venv_python) and sys.executable != venv_python:
    os.execv(venv_python, [venv_python] + sys.argv)

import uvicorn
import socket
from gdrive_sync import status_drive, restaurar_backup_do_drive, enviar_backup_para_drive

def obter_ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def abrir_navegador():
    time.sleep(1.2)
    url = "http://127.0.0.1:8000"
    print(f"\n🚀 Abrindo {url} no seu navegador...")
    webbrowser.open(url)

if __name__ == "__main__":
    os.chdir(BASE_DIR)
    ip_rede = obter_ip_local()
    print("=" * 65)
    print("🌟 Study Hub & Life OS - Servidor Local Iniciado")
    print("🖥️  No Computador:       http://127.0.0.1:8000")
    print(f"📱 No Celular / Tablet: http://{ip_rede}:8000  (Mesma rede Wi-Fi)")
    print("⚡ Pressione Ctrl+C para encerrar com backup automático.")
    print("=" * 65)

    # 1. SINCRONIZAÇÃO AO INICIAR
    print("\n🔄 [Inicialização] Verificando conexão com o Google Drive e Google Calendar...")
    try:
        st = status_drive()
        if st["status"] == "conectado":
            print("☁️ Conta Google conectada. Verificando se há novos dados...")
            res = restaurar_backup_do_drive()
            print(f"📥 {res.get('message', 'Sincronizado.')}")
        elif st["status"] == "pendente_autorizacao":
            print("🔑 credentials.json detectado. Abrindo navegador para autorizar Google Drive e Google Calendar...")
            try:
                from google_auth import get_google_credentials
                creds, err = get_google_credentials(interactive=True)
                if creds:
                    print("✅ Autorizado com sucesso! Google Drive e Google Calendar conectados.")
                else:
                    print(f"⚠️ Não foi possível autorizar agora: {err}")
            except Exception as e:
                print(f"ℹ️ Autorização pendente: {e}")
        else:
            print(f"ℹ️ Google Drive / Agenda: {st['mensagem']}")
    except Exception as e:
        print(f"⚠️ Aviso na verificação do Google: {e}")

    # Inicia o navegador em background
    threading.Thread(target=abrir_navegador, daemon=True).start()

    # Roda o servidor FastAPI em 0.0.0.0 (acessível no PC e na rede Wi-Fi local)
    try:
        uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False, log_level="info")
    finally:
        print("\n" + "=" * 65)
        print("💾 [Encerramento] Gravando backup de segurança dos seus dados...")
        try:
            st = status_drive()
            if st["status"] == "conectado":
                print("☁️ Enviando banco de dados e imagens para o Google Drive...")
                res = enviar_backup_para_drive()
                if res.get("success"):
                    print(f"✅ {res.get('message')}")
                else:
                    print(f"⚠️ {res.get('message')}")
            else:
                from gdrive_sync import criar_pacote_backup_local
                zip_path = criar_pacote_backup_local()
                print(f"📁 Backup local salvo com segurança em: {os.path.basename(zip_path)}")
                print("ℹ️ Para ativar o envio automático ao Google Drive, configure o credentials.json.")
        except Exception as e:
            print(f"⚠️ Erro ao gerar backup no encerramento: {e}")

        print("👋 Servidor encerrado. Bons estudos!")
        print("=" * 65)
