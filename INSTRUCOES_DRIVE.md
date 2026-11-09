# ☁️ Guia de Configuração: Google Drive & Google Gemini (.env)

Este guia ensina o passo a passo para configurar o **backup automático no Google Drive** e a **chave de Inteligência Artificial do Google Gemini** no arquivo `.env`.

---

## 📋 Resumo das Variáveis do Arquivo `.env`

O seu arquivo `.env` fica na raiz do projeto e possui o seguinte formato:

```env
# 1. Chave da IA (Google Gemini Studio)
GEMINI_API_KEY=sua_chave_gemini_aqui

# 2. Configurações do Google Drive (Opção 2 - API Oficial)
GOOGLE_DRIVE_SYNC_ENABLED=true
GOOGLE_DRIVE_FOLDER_NAME=Study Hub - Backup
GOOGLE_CREDENTIALS_FILE=credentials.json
GOOGLE_TOKEN_FILE=token.json
```

---

## 🤖 Parte 1: Como Obter e Configurar a Chave do Gemini (IA)

O assistente de IA resume seus documentos, extrai tópicos de estudo e cria flashcards automaticamente.

1. Acesse o **[Google AI Studio](https://aistudio.google.com/app/apikey)** com sua conta Google.
2. Clique no botão azul **"Create API Key"** (Criar chave de API).
3. Copie a chave alfanumérica gerada (exemplo: `AIzaSyD...`).
4. Abra o arquivo `.env` no seu editor e cole na linha:
   ```env
   GEMINI_API_KEY=AIzaSyD...cole_sua_chave_aqui...
   ```
5. Salve o arquivo. Pronto! A IA já está ativa.

---

## ☁️ Parte 2: Como Configurar o Google Drive (Backup Automático)

Com essa configuração, todo o seu banco de dados (`study_hub.db`) e todas as imagens/anexos (`uploads/`) serão salvos na nuvem sempre que você **iniciar** ou **desligar** o sistema.

### Passo 1: Criar o Projeto no Google Cloud

1. Acesse o **[Google Cloud Console](https://console.cloud.google.com/)**.
2. No topo da tela, clique no seletor de projetos e clique em **Novo Projeto** (*New Project*).
3. Dê o nome de **Study Hub** e clique em **Criar**.

---

### Passo 2: Ativar a Google Drive API e a Google Calendar API

1. No menu lateral esquerdo (☰), vá em **APIs e Serviços > Biblioteca** (*APIs & Services > Library*).
2. Na barra de pesquisa, digite: `Google Drive API`. Clique nela e depois no botão azul **Ativar** (*Enable*).
3. Volte na Biblioteca, pesquise por: `Google Calendar API`. Clique nela e também no botão **Ativar** (*Enable*).
*(Isso permite que o sistema faça backup automático no Drive e envie seus prazos para a sua Google Agenda).*

---

### Passo 3: Configurar a Tela de Consentimento (OAuth)

1. No menu lateral, clique em **Tela de permissão OAuth** (*OAuth consent screen*).
2. Selecione o tipo de usuário: **Externo** (*External*) e clique em **Criar**.
3. Preencha as informações básicas:
   - **Nome do app**: `Study Hub`
   - **E-mail para suporte**: Seu endereço do Gmail
   - **E-mail do desenvolvedor**: Seu endereço do Gmail
4. Clique em **Salvar e Continuar** até chegar na etapa **Usuários de teste** (*Test Users*).
5. ⚠️ **Muito Importante**: Na etapa de *Test Users*, clique em **+ Add Users** e adicione o seu próprio e-mail do Gmail.
6. Clique em **Salvar e Continuar** e conclua.

---

### Passo 4: Gerar o arquivo `credentials.json`

1. No menu lateral, clique em **Credenciais** (*Credentials*).
2. No topo da tela, clique em **+ Criar Credenciais > ID do cliente OAuth** (*+ Create Credentials > OAuth client ID*).
3. No campo **Tipo de aplicativo** (*Application type*), selecione:
   👉 **Aplicativo para Computador** (*Desktop App*).
4. No campo **Nome**, digite: `Study Hub Local`.
5. Clique em **Criar**.
6. Uma janela abrirá com a confirmação. Clique no botão **Fazer o download do JSON** (*Download JSON*).
7. Renomeie o arquivo baixado para **`credentials.json`**.
8. Mova esse arquivo para a pasta do Study Hub:
   ```text
   /media/elliasgomes/HD_1TB/apps/estudos_sheets/credentials.json
   ```

---

## 🚀 Parte 3: Primeira Inicialização e Autorização

1. Abra o terminal na pasta e execute:
   ```bash
   ./iniciar.sh
   ```
2. Na primeira vez, uma aba do navegador será aberta pelo Google solicitando que você faça login na sua conta Google para autorizar o Study Hub a gerenciar os backups.
3. Se o Google exibir a tela *"O Google não verificou este app"*, não se preocupe (pois o app foi criado por você mesmo):
   - Clique em **Avançado** (*Advanced*).
   - Clique em **Acessar Study Hub (não seguro)**.
   - Clique em **Continuar**.
4. Um arquivo `token.json` será criado automaticamente na pasta.
5. Pronto! Agora o sistema está 100% integrado.

---

## 🔄 Como Funciona no Dia a Dia

- **Ao Iniciar (`./iniciar.sh`)**: O programa verifica se há novos dados no Google Drive e sincroniza automaticamente.
- **Durante o Uso**: Velocidade instantânea (< 15ms) no seu computador.
- **Ao Desligar (`Ctrl+C`)**: O programa gera um pacote comprimido com seu banco de dados e imagens e envia para a pasta **`Study Hub - Backup`** no seu Google Drive.
- **Backup Manual**: Você também pode clicar no botão **"Importar / Backup"** no topo da tela e clicar em **"Fazer Backup no Drive Agora"** a qualquer momento.
