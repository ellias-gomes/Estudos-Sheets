function doGet() {
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('Study Hub PRO - Life OS')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

function testarPermissaoDrive() {
  const folderName = "Study Hub - Anexos";
  const folders = DriveApp.getFoldersByName(folderName);
  let folder = folders.hasNext() ? folders.next() : DriveApp.createFolder(folderName);
  Logger.log("Permissão completa do Drive OK!");
}

// Inicializa planilhas e garante todas as abas (incluindo Flashcards e Pomodoro)
function checkAndInitSheets() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  
  const estruturas = {
    'Anotações': ['ID', 'Data', 'Matéria/Categoria', 'Tópico', 'Conteúdo', 'Tags', 'Link', 'AnexoNome', 'AnexoUrl'],
    'Tarefas': ['ID', 'Data Criação', 'Título', 'Categoria', 'Status', 'Prazo', 'Prioridade', 'Descrição', 'AnexoNome', 'AnexoUrl'],
    'Cursos': ['ID', 'Nome', 'Instituição', 'Categoria', 'Carga Horária', 'Status', 'Link'],
    'Categorias': ['Nome'],
    'Flashcards': ['ID', 'Categoria', 'Frente', 'Verso', 'Nivel', 'UltimaRevisao'],
    'Pomodoro': ['ID', 'Data', 'Categoria', 'Minutos']
  };

  for (let nomeAba in estruturas) {
    let sheet = ss.getSheetByName(nomeAba);
    if (!sheet) {
      sheet = ss.insertSheet(nomeAba);
      sheet.appendRow(estruturas[nomeAba]);
      sheet.getRange(1, 1, 1, estruturas[nomeAba].length).setFontWeight("bold").setBackground("#f3f4f6");
    } else {
      const lastCol = Math.max(1, sheet.getLastColumn());
      const currentHeaders = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
      estruturas[nomeAba].forEach((header, index) => {
        if (!currentHeaders[index]) {
          sheet.getRange(1, index + 1).setValue(header).setFontWeight("bold").setBackground("#f3f4f6");
        }
      });
    }
  }
}

// Faz upload de imagens isoladas do editor para o Drive
function uploadImagemEditor(fileObj) {
  try {
    if (!fileObj || !fileObj.data) return { directUrl: '' };
    
    const folderName = "Study Hub - Anexos";
    const folders = DriveApp.getFoldersByName(folderName);
    let folder = folders.hasNext() ? folders.next() : DriveApp.createFolder(folderName);
    
    const bytes = Utilities.base64Decode(fileObj.data.split(',')[1]);
    const blob = Utilities.newBlob(bytes, fileObj.mimeType || 'image/png', fileObj.fileName || ('IMG_' + Date.now() + '.png'));
    const file = folder.createFile(blob);
    file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
    
    return {
      directUrl: "https://drive.google.com/thumbnail?id=" + file.getId() + "&sz=w1200"
    };
  } catch (e) {
    throw new Error("Erro no upload da imagem do editor: " + e.toString());
  }
}

// Upload de arquivo ou imagem embutida para o Google Drive
function uploadArquivoDrive(fileObj) {
  try {
    if (!fileObj) return { url: '', name: '', directUrl: '' };
    
    const folderName = "Study Hub - Anexos";
    const folders = DriveApp.getFoldersByName(folderName);
    let folder = folders.hasNext() ? folders.next() : DriveApp.createFolder(folderName);
    
    const bytes = Utilities.base64Decode(fileObj.data.split(',')[1]);
    const blob = Utilities.newBlob(bytes, fileObj.mimeType, fileObj.fileName);
    const file = folder.createFile(blob);
    file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
    
    const fileId = file.getId();
    return { 
      url: file.getUrl(), 
      name: file.getName(),
      directUrl: "https://drive.google.com/thumbnail?id=" + fileId + "&sz=w1200"
    };
  } catch (e) {
    throw new Error("Erro ao salvar anexo no Drive: " + e.toString());
  }
}

// ================= DASHBOARD =================
function getDashboardData() {
  checkAndInitSheets();
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  
  const wsTarefas = ss.getSheetByName('Tarefas');
  let tarefasPendentes = 0, tarefasConcluidas = 0;
  let categoriasAtividades = {};
  
  if (wsTarefas) {
    const dataTarefas = wsTarefas.getDataRange().getValues();
    for (let i = 1; i < dataTarefas.length; i++) {
      let status = dataTarefas[i][4];
      let cat = dataTarefas[i][3];
      if (status === 'Pendente' || status === 'Em Andamento') tarefasPendentes++;
      if (status === 'Concluído') tarefasConcluidas++;
      if (cat) categoriasAtividades[cat] = (categoriasAtividades[cat] || 0) + 1;
    }
  }

  const wsAnotacoes = ss.getSheetByName('Anotações');
  let totalAnotacoes = wsAnotacoes ? Math.max(0, wsAnotacoes.getLastRow() - 1) : 0;
  
  const wsCursos = ss.getSheetByName('Cursos');
  let cursosEmAndamento = 0;
  if (wsCursos) {
    const dataCursos = wsCursos.getDataRange().getValues();
    for (let i = 1; i < dataCursos.length; i++) {
      if (dataCursos[i][5] === 'Em Andamento') cursosEmAndamento++;
    }
  }

  const wsPomodoro = ss.getSheetByName('Pomodoro');
  let minutosEstudo = 0;
  if (wsPomodoro) {
    const dataPomo = wsPomodoro.getDataRange().getValues();
    for (let i = 1; i < dataPomo.length; i++) {
      minutosEstudo += Number(dataPomo[i][3]) || 0;
    }
  }

  return {
    anotacoes: totalAnotacoes,
    pendentes: tarefasPendentes,
    concluidas: tarefasConcluidas,
    cursosAndamento: cursosEmAndamento,
    minutosEstudo: minutosEstudo,
    graficoCategorias: Object.keys(categoriasAtividades).map(k => ({nome: k, valor: categoriasAtividades[k]}))
  };
}

// ================= ANOTAÇÕES =================
function getAnotacoes() {
  checkAndInitSheets();
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const ws = ss.getSheetByName('Anotações');
  const data = ws.getDataRange().getValues();
  const lista = [];
  
  for (let i = 1; i < data.length; i++) {
    if (data[i][0]) {
      let dataFmt = data[i][1] instanceof Date ? Utilities.formatDate(data[i][1], Session.getScriptTimeZone(), "dd/MM/yyyy HH:mm") : data[i][1];
      lista.push({
        id: data[i][0],
        data: dataFmt,
        materia: data[i][2],
        topico: data[i][3],
        conteudo: data[i][4],
        tags: data[i][5],
        link: data[i][6],
        anexoNome: data[i][7] || '',
        anexoUrl: data[i][8] || ''
      });
    }
  }
  return lista.reverse();
}

function salvarAnotacao(dados) {
  try {
    checkAndInitSheets();
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const ws = ss.getSheetByName('Anotações');
    const data = ws.getDataRange().getValues();
    
    let anexo = { url: dados.anexoUrl || '', name: dados.anexoNome || '' };
    if (dados.arquivoData) {
      anexo = uploadArquivoDrive(dados.arquivoData);
    }

    if (dados.id) {
      for (let i = 1; i < data.length; i++) {
        if (data[i][0] === dados.id) {
          ws.getRange(i + 1, 3, 1, 7).setValues([[
            dados.materia, dados.topico, dados.conteudo, dados.tags, dados.link, anexo.name, anexo.url
          ]]);
          return { success: true, message: "Anotação atualizada!" };
        }
      }
    } else {
      const id = "NOTE-" + new Date().getTime().toString().slice(-6);
      const dataAtual = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "dd/MM/yyyy HH:mm");
      ws.appendRow([id, dataAtual, dados.materia, dados.topico, dados.conteudo, dados.tags, dados.link, anexo.name, anexo.url]);
      return { success: true, message: "Anotação salva com sucesso!" };
    }
  } catch (error) {
    return { success: false, message: error.toString() };
  }
}

function excluirAnotacao(id) {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const ws = ss.getSheetByName('Anotações');
    const data = ws.getDataRange().getValues();
    for (let i = 1; i < data.length; i++) {
      if (data[i][0] === id) {
        ws.deleteRow(i + 1);
        return { success: true, message: "Anotação excluída!" };
      }
    }
  } catch (e) {
    return { success: false, message: e.toString() };
  }
}

// ================= TAREFAS & KANBAN =================
function getTarefas() {
  checkAndInitSheets();
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const ws = ss.getSheetByName('Tarefas');
  const data = ws.getDataRange().getValues();
  const lista = [];
  
  for (let i = 1; i < data.length; i++) {
    if (data[i][0]) {
      let dataCriacao = data[i][1] instanceof Date ? Utilities.formatDate(data[i][1], Session.getScriptTimeZone(), "dd/MM/yyyy") : data[i][1];
      let prazoFmt = data[i][5] instanceof Date ? Utilities.formatDate(data[i][5], Session.getScriptTimeZone(), "yyyy-MM-dd") : data[i][5];
      lista.push({
        id: data[i][0],
        dataCriacao: dataCriacao,
        titulo: data[i][2],
        categoria: data[i][3],
        status: data[i][4],
        prazo: prazoFmt,
        prioridade: data[i][6],
        descricao: data[i][7] || '',
        anexoNome: data[i][8] || '',
        anexoUrl: data[i][9] || ''
      });
    }
  }
  return lista.reverse();
}

function salvarTarefa(dados) {
  try {
    checkAndInitSheets();
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const ws = ss.getSheetByName('Tarefas');
    const data = ws.getDataRange().getValues();
    
    let anexo = { url: dados.anexoUrl || '', name: dados.anexoNome || '' };
    if (dados.arquivoData) {
      anexo = uploadArquivoDrive(dados.arquivoData);
    }

    if (dados.id) {
      for (let i = 1; i < data.length; i++) {
        if (data[i][0] === dados.id) {
          ws.getRange(i + 1, 3, 1, 8).setValues([[
            dados.titulo, dados.categoria, dados.status, dados.prazo, dados.prioridade, dados.descricao, anexo.name, anexo.url
          ]]);
          return { success: true, message: "Tarefa atualizada!" };
        }
      }
    } else {
      const id = "TASK-" + new Date().getTime().toString().slice(-6);
      const dataAtual = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "dd/MM/yyyy");
      ws.appendRow([id, dataAtual, dados.titulo, dados.categoria, dados.status || 'Pendente', dados.prazo, dados.prioridade || 'Média', dados.descricao, anexo.name, anexo.url]);
      return { success: true, message: "Tarefa salva com sucesso!" };
    }
  } catch (error) {
    return { success: false, message: error.toString() };
  }
}

function atualizarStatusTarefa(id, novoStatus) {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const ws = ss.getSheetByName('Tarefas');
    const data = ws.getDataRange().getValues();
    for (let i = 1; i < data.length; i++) {
      if (data[i][0] === id) {
        ws.getRange(i + 1, 5).setValue(novoStatus);
        return { success: true, message: "Status atualizado!" };
      }
    }
  } catch (e) {
    return { success: false, message: e.toString() };
  }
}

function excluirTarefa(id) {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const ws = ss.getSheetByName('Tarefas');
    const data = ws.getDataRange().getValues();
    for (let i = 1; i < data.length; i++) {
      if (data[i][0] === id) {
        ws.deleteRow(i + 1);
        return { success: true, message: "Tarefa excluída!" };
      }
    }
  } catch (e) {
    return { success: false, message: e.toString() };
  }
}

// ================= CURSOS =================
function getCursos() {
  checkAndInitSheets();
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const ws = ss.getSheetByName('Cursos');
  const data = ws.getDataRange().getValues();
  const lista = [];
  for (let i = 1; i < data.length; i++) {
    if (data[i][0]) {
      lista.push({
        id: data[i][0], nome: data[i][1], instituicao: data[i][2], categoria: data[i][3],
        cargaHoraria: data[i][4], status: data[i][5], link: data[i][6]
      });
    }
  }
  return lista.reverse();
}

function salvarCurso(dados) {
  try {
    checkAndInitSheets();
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const ws = ss.getSheetByName('Cursos');
    const id = "CRS-" + new Date().getTime().toString().slice(-6);
    ws.appendRow([id, dados.nome, dados.instituicao, dados.categoria, dados.cargaHoraria, dados.status, dados.link]);
    return { success: true, message: "Curso salvo!" };
  } catch (error) {
    return { success: false, message: error.toString() };
  }
}

function excluirCurso(id) {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const ws = ss.getSheetByName('Cursos');
    const data = ws.getDataRange().getValues();
    for (let i = 1; i < data.length; i++) {
      if (data[i][0] === id) {
        ws.deleteRow(i + 1);
        return { success: true, message: "Curso excluído!" };
      }
    }
  } catch (e) {
    return { success: false, message: e.toString() };
  }
}

// ================= CATEGORIAS =================
function getCategorias() {
  checkAndInitSheets();
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const ws = ss.getSheetByName('Categorias');
  const data = ws.getDataRange().getValues();
  const lista = [];
  
  for (let i = 1; i < data.length; i++) {
    if (data[i][0]) lista.push(data[i][0]);
  }
  
  if (lista.length === 0) {
    const padrao = [
      "Engenharia de Computação (UNIVESP)", "DevOps / Cloud (Alura)",
      "Desenvolvimento de Software / Projetos", "Conhecimentos Gerais / Leituras",
      "Autoescola / DETRAN", "Atividade Física / Jiu-Jitsu", "Outros"
    ];
    padrao.forEach(c => ws.appendRow([c]));
    return padrao;
  }
  return lista;
}

function salvarCategoria(nome) {
  try {
    if (!nome) return { success: false, message: "Nome inválido." };
    checkAndInitSheets();
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const ws = ss.getSheetByName('Categorias');
    const data = ws.getDataRange().getValues();
    for (let i = 1; i < data.length; i++) {
      if (data[i][0].toString().toLowerCase() === nome.toLowerCase()) {
        return { success: false, message: "Esta categoria já existe!" };
      }
    }
    ws.appendRow([nome]);
    return { success: true, message: "Categoria criada com sucesso!" };
  } catch (e) {
    return { success: false, message: e.toString() };
  }
}

// ================= FLASHCARDS =================
function getFlashcards() {
  checkAndInitSheets();
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const ws = ss.getSheetByName('Flashcards');
  const data = ws.getDataRange().getValues();
  const lista = [];
  for (let i = 1; i < data.length; i++) {
    if (data[i][0]) {
      lista.push({
        id: data[i][0],
        categoria: data[i][1],
        frente: data[i][2],
        verso: data[i][3],
        nivel: data[i][4] || 'Novo',
        ultimaRevisao: data[i][5] ? (data[i][5] instanceof Date ? Utilities.formatDate(data[i][5], Session.getScriptTimeZone(), "dd/MM/yyyy") : data[i][5]) : 'Nunca'
      });
    }
  }
  return lista.reverse();
}

function salvarFlashcard(dados) {
  try {
    checkAndInitSheets();
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const ws = ss.getSheetByName('Flashcards');
    const id = "FC-" + new Date().getTime().toString().slice(-6) + Math.floor(Math.random() * 100);
    ws.appendRow([id, dados.categoria, dados.frente, dados.verso, 'Novo', '']);
    return { success: true, message: "Flashcard criado!" };
  } catch (e) {
    return { success: false, message: e.toString() };
  }
}

function atualizarNivelFlashcard(id, nivel) {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const ws = ss.getSheetByName('Flashcards');
    const data = ws.getDataRange().getValues();
    const hoje = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "dd/MM/yyyy");
    for (let i = 1; i < data.length; i++) {
      if (data[i][0] === id) {
        ws.getRange(i + 1, 5, 1, 2).setValues([[nivel, hoje]]);
        return { success: true };
      }
    }
  } catch (e) {
    return { success: false, message: e.toString() };
  }
}

function excluirFlashcard(id) {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const ws = ss.getSheetByName('Flashcards');
    const data = ws.getDataRange().getValues();
    for (let i = 1; i < data.length; i++) {
      if (data[i][0] === id) {
        ws.deleteRow(i + 1);
        return { success: true, message: "Flashcard excluído!" };
      }
    }
  } catch (e) {
    return { success: false, message: e.toString() };
  }
}

// ================= POMODORO =================
function registrarSessaoPomodoro(categoria, minutos) {
  try {
    checkAndInitSheets();
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const ws = ss.getSheetByName('Pomodoro');
    const id = "POMO-" + new Date().getTime().toString().slice(-6);
    const dataAtual = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "dd/MM/yyyy HH:mm");
    ws.appendRow([id, dataAtual, categoria || 'Geral', Number(minutos) || 25]);
    return { success: true, message: `Sessão de ${minutos} min registrada com sucesso!` };
  } catch (e) {
    return { success: false, message: e.toString() };
  }
}

// ================= ASSISTENTE IA (GEMINI API) =================
function salvarChaveGemini(apiKey) {
  PropertiesService.getUserProperties().setProperty('GEMINI_API_KEY', apiKey.trim());
  return { success: true, message: "Chave da API Gemini guardada com segurança!" };
}

function chamarAssistenteIA(acao, textoConteudo, categoriaAtual) {
  try {
    const apiKey = PropertiesService.getUserProperties().getProperty('GEMINI_API_KEY');
    if (!apiKey) {
      return { 
        success: false, 
        needKey: true, 
        message: "Configure a sua chave gratuita da API do Google Gemini clicando no ícone de engrenagem ao lado dos botões de IA." 
      };
    }

    let prompt = "";
    if (acao === 'resumir') {
      prompt = "Crie um resumo executivo estruturado em HTML (use apenas tags <h3>, <p>, <ul>, <li>, <strong>, sem blocos markdown ```html) destacando os pontos principais do seguinte texto:\n\n" + textoConteudo;
    } else if (acao === 'topicos') {
      prompt = "Extraia os conceitos-chave, termos técnicos e ideias centrais em formato de lista de revisão em HTML (use <h3>, <ul>, <li>, <strong>, sem markdown ```html) a partir do seguinte texto:\n\n" + textoConteudo;
    } else if (acao === 'flashcards') {
      prompt = "A partir do texto abaixo, gere exatamente 4 flashcards de estudo com perguntas diretas e respostas claras. Retorne APENAS um JSON válido no formato [{\"frente\": \"Pergunta?\", \"verso\": \"Resposta\"}] sem nenhum texto adicional ou formatação markdown:\n\n" + textoConteudo;
    }

    const url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + apiKey;
    const payload = {
      contents: [{ parts: [{ text: prompt }] }]
    };

    const options = {
      method: "post",
      contentType: "application/json",
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    };

    const response = UrlFetchApp.fetch(url, options);
    const json = JSON.parse(response.getContentText());

    if (json.error) {
      return { success: false, message: "Erro na API Gemini: " + json.error.message };
    }

    let respostaTexto = json.candidates[0].content.parts[0].text;
    respostaTexto = respostaTexto.replace(/```html/g, '').replace(/```json/g, '').replace(/```/g, '').trim();

    if (acao === 'flashcards') {
      const cards = JSON.parse(respostaTexto);
      cards.forEach(c => {
        salvarFlashcard({ categoria: categoriaAtual || 'Geral', frente: c.frente, verso: c.verso });
      });
      return { success: true, isFlashcards: true, message: `${cards.length} Flashcards foram gerados e adicionados automaticamente à sua aba de Flashcards!` };
    }

    return { success: true, html: respostaTexto };
  } catch (e) {
    return { success: false, message: "Erro ao processar com IA: " + e.toString() };
  }
}