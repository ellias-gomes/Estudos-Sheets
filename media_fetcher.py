import re
import requests

def buscar_metadados_livro(query: str):
    """Busca dados de livros via Open Library API (sem necessidade de chaves, gratuito e confiável)."""
    try:
        url = "https://openlibrary.org/search.json"
        params = {"q": query, "limit": 1}
        headers = {"User-Agent": "StudyHubApp/1.0"}
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            docs = data.get("docs", [])
            if docs:
                doc = docs[0]
                titulo = doc.get("title", "")
                autores_list = doc.get("author_name", [])
                autores = ", ".join(autores_list) if autores_list else ""
                ano = str(doc.get("first_publish_year", ""))
                
                # Capa da Open Library
                cover_id = doc.get("cover_i")
                capa = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else ""
                
                # Assunto / Categoria
                subjects = doc.get("subject", [])
                categoria = subjects[0] if subjects else "Livros"
                
                link = f"https://openlibrary.org{doc.get('key')}" if doc.get("key") else ""

                return {
                    "success": True,
                    "titulo": titulo,
                    "autorDiretor": autores,
                    "ano": ano,
                    "categoria": categoria,
                    "capaUrl": capa,
                    "link": link,
                    "tipo": "Livro"
                }

        # Fallback para Google Books API se configurada
        return {"success": False, "message": "Nenhum livro encontrado com este termo."}
    except Exception as e:
        return {"success": False, "message": f"Erro ao buscar livro: {str(e)}"}

def buscar_metadados_youtube(url: str):
    """Extrai informações e thumbnail de um vídeo do YouTube."""
    try:
        padrao = r'(?:v=|\/)([0-9A-Za-z_-]{11}).*'
        match = re.search(padrao, url)
        video_id = match.group(1) if match else None

        titulo = ""
        autor = ""
        oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
        try:
            resp = requests.get(oembed_url, timeout=5)
            if resp.status_code == 200:
                o_data = resp.json()
                titulo = o_data.get("title", "")
                autor = o_data.get("author_name", "")
        except Exception:
            pass

        capa = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg" if video_id else ""

        return {
            "success": True,
            "titulo": titulo or "Vídeo do YouTube",
            "autorDiretor": autor or "Canal YouTube",
            "capaUrl": capa,
            "link": url,
            "tipo": "Vídeo"
        }
    except Exception as e:
        return {"success": False, "message": f"Erro ao buscar vídeo: {str(e)}"}

def buscar_metadados_midia(tipo: str, termo: str):
    termo = termo.strip()
    if not termo:
        return {"success": False, "message": "Termo de busca vazio."}

    if "youtube.com" in termo or "youtu.be" in termo:
        return buscar_metadados_youtube(termo)
    elif tipo in ["Livro", "Artigo"] or not ("http://" in termo or "https://" in termo):
        return buscar_metadados_livro(termo)
    else:
        return {
            "success": True,
            "titulo": termo,
            "link": termo,
            "autorDiretor": "",
            "capaUrl": "",
            "tipo": tipo or "Geral"
        }
