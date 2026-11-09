# 🚀 Study Hub & Life OS (Versão Web Local)

Transformação do sistema do Google Apps Script / Google Sheets para uma aplicação Web local de altíssima performance construída com **Python (FastAPI)**, **SQLite** e o seu **Frontend completo (Quill, Kanban, Pomodoro, Flashcards, FullCalendar)**.

---

## ⚡ Vantagens da Versão Local

- **Velocidade Instantânea**: O tempo de resposta caiu de 1-3 segundos (Google Apps Script) para **menos de 15ms** com SQLite.
- **Armazenamento no Google Drive (Opção 2 - API Oficial)**: Sincronização automática do banco de dados e imagens com o Google Drive ao **iniciar** e **desligar** o sistema.
- **Anexos e Imagens Locais**: Imagens coladas no editor ou anexadas em tarefas são salvas diretamente na pasta `uploads/` e sincronizadas com a nuvem.
- **Importador do Google Sheets**: Migração com 1 clique baixando a sua planilha `.xlsx` do Google Sheets.
- **Backup & Segurança**: Seus dados ficam salvos em um único arquivo `study_hub.db` e com cópias seguras no Google Drive.
- **Assistente IA (Gemini)**: Totalmente integrado para resumos, tópicos e geração automática de flashcards via `.env`.
- **📚 Central de Leituras & Reviews**: Acervo de livros, artigos, vídeos do YouTube, filmes e podcasts com busca automática de capas e metadados.
- **📅 Sincronização com Google Calendar**: Envia prazos de tarefas automaticamente para sua agenda do Google e exibe seus compromissos no calendário local.
- **🕸️ Segundo Cérebro (Backlinks & Grafo de Conhecimento)**: Conecte notas e livros usando `[[Título da Obra]]` e explore a rede interativa de conhecimento.
- **🔥 Rastreador de Hábitos & Gamificação**: Grade semanal de hábitos, ofensiva de dias seguidos (*streaks*), desafio anual de leitura e Mapa de Calor (*Heatmap* estilo GitHub).
- **📄 Exportador Acadêmico com 1 Clique (PDF/ABNT e Markdown)**: Gere documentos formatados nas normas ABNT prontos para impressão/PDF ou baixe em `.md` com frontmatter YAML.
- **📱 Acesso no Celular / Tablet (Wi-Fi)**: Interface responsiva com QR Code integrado para estudar ou revisar flashcards pelo celular na mesma rede Wi-Fi.

---

## ☁️ Configuração do Google Drive & Chaves de API (.env)

Consulte o passo a passo completo no arquivo:
👉 **[INSTRUCOES_DRIVE.md](file:///media/elliasgomes/HD_1TB/apps/estudos_sheets/INSTRUCOES_DRIVE.md)**

1. Edite o arquivo `.env` para inserir sua chave do Google Gemini:
   ```env
   GEMINI_API_KEY=sua_chave_aqui
   ```
2. Adicione o seu arquivo `credentials.json` gerado no Google Cloud Console para sincronizar com o Google Drive.

---

## 🏁 Como Iniciar o Programa

Abra o terminal nesta pasta e execute qualquer um dos comandos abaixo:

```bash
./iniciar.sh
```

Ou diretamente pelo Python:

```bash
python3 start.py
```

O navegador abrirá automaticamente em:  
👉 **http://127.0.0.1:8000**

---

## 📥 Como Importar seus Dados do Google Sheets

1. Abra a sua planilha no **Google Sheets**.
2. Clique no menu superior: **Arquivo > Fazer download > Microsoft Excel (.xlsx)**.
3. No Study Hub Local, clique no botão **"Importar / Backup"** no cabeçalho superior.
4. Selecione o arquivo `.xlsx` que você baixou e clique em **"Importar Agora"**.
5. Pronto! Todas as suas **Anotações**, **Tarefas**, **Cursos**, **Flashcards**, **Sessões Pomodoro** e **Categorias** serão importadas instantaneamente!

---

## 🤖 Como Usar a IA (Google Gemini)

1. No editor de anotações, clique no ícone de engrenagem ao lado dos botões de IA ou tente gerar uma ação (Resumo, Tópicos ou Flashcards).
2. Cole a sua chave gratuita do [Google AI Studio](https://aistudio.google.com/).
3. A chave fica guardada com segurança no banco local SQLite `study_hub.db`.

---

## 📁 Estrutura do Projeto

```text
.
├── app.py              # Servidor Web FastAPI e endpoints da API
├── db.py               # Gerenciador do Banco de Dados SQLite (study_hub.db)
├── importer.py         # Módulo de importação de planilhas (.xlsx e .json) e exportação
├── start.py            # Inicializador automático com abertura de navegador
├── iniciar.sh          # Script facilitador de inicialização no Linux
├── study_hub.db        # Banco de dados local SQLite
├── static/
│   └── index.html      # Interface web otimizada com a ponte transparente local
├── uploads/            # Pasta onde são salvas imagens e anexos
├── requirements.txt    # Dependências do projeto
└── README.md           # Guia de uso
```
