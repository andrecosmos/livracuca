import os
from urllib.parse import quote

import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# IMPORTANTE: Removemos a substituição grosseira de socket.getaddrinfo que corrompia as strings das URLs.
# Agora deixamos o requests gerenciar as URLs de forma nativa e segura.

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "templates"))
if not os.path.exists(os.path.join(TEMPLATES_DIR, "catalogo.html")):
    TEMPLATES_DIR = os.path.normpath(os.path.join(BASE_DIR, "templates"))

templates = Jinja2Templates(directory=TEMPLATES_DIR)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}
OPENLIBRARY_URL = "https://openlibrary.org"
COVERS_URL = "https://covers.openlibrary.org/b/id"

# ROTA 1: CATÁLOGO PRINCIPAL
@app.get("/", response_class=HTMLResponse)
def ler_catalogo(request: Request, busca: str = "programming"):
    livros_formatados = []
    busca_limpa = busca.strip()

    # Criamos sessões limpas para garantir o isolamento da requisição HTTP
    session = requests.Session()

    try:
        # Separação cirúrgica de rotas baseada na documentação da Open Library
        if busca_limpa.startswith("subject:"):
            categoria = busca_limpa.replace("subject:", "").strip()
            url = f"{OPENLIBRARY_URL}/subjects/{quote(categoria, safe='')}.json"
            params = {"limit": 12}
        else:
            url = f"{OPENLIBRARY_URL}/search.json"
            params = {"q": busca_limpa, "limit": 12}
        
        response = session.get(url, params=params, headers=HEADERS, timeout=10.0)
        response.raise_for_status()

        if response.status_code == 200:
            dados = response.json()
            
            # Mapeamento dinâmico: rota subjects usa 'works', rota search usa 'docs'
            colecao_livros = dados.get("works", []) if "subjects" in url else dados.get("docs", [])
            
            for doc in colecao_livros:
                chave_completa = doc.get("key", "")
                id_obra = chave_completa.split("/")[-1] if chave_completa else ""
                
                if id_obra:
                    capa_id = doc.get("cover_i") or doc.get("cover_id")
                    
                    # Captura robusta de autores variando pelas duas respostas de API
                    autores_lista = doc.get("author_name", [])
                    if not autores_lista and doc.get("authors"):
                        autores_lista = [a.get("name") for a in doc.get("authors", []) if a.get("name")]
                    
                    autores_texto = ", ".join(autores_lista) if autores_lista else "Autor Desconhecido"

                    livros_formatados.append({
                        "id": id_obra,
                        "titulo": doc.get("title", "Título desconhecido"),
                        "autores": autores_texto,
                        "ano": doc.get("first_publish_year") or "Não informado",
                        "capa_url": f"{COVERS_URL}/{capa_id}-M.jpg" if capa_id else f"{COVERS_URL}/0-M.jpg"
                    })
    except (requests.RequestException, ValueError) as e:
        print(f"❌ Erro de conexão na listagem: {e}")

    # Fallback caso ocorra falhas ou timeouts de DNS no ambiente local do WSL
    if not livros_formatados:
        livros_formatados = [
            {
                "id": "OL26310232W",
                "titulo": "Python Cookbook (Modo de Segurança)",
                "autores": "David Beazley, Brian K. Jones",
                "ano": 2013,
                "capa_url": f"{COVERS_URL}/10531742-M.jpg"
            }
        ]

    return templates.TemplateResponse(
        name="catalogo.html",
        request=request,
        context={"livros": livros_formatados, "busca": busca_limpa},
    )

# ROTA 2: PÁGINA DE DETALHES
@app.get("/livro/{id_livro}", response_class=HTMLResponse)
def detalhe_livro(request: Request, id_livro: str):
    detalhes = {}
    session = requests.Session()
    
    url = f"{OPENLIBRARY_URL}/works/{quote(id_livro, safe='')}.json"

    try:
        response = session.get(url, headers=HEADERS, timeout=10.0)
        response.raise_for_status()
        if response.status_code == 200:
            dados = response.json()

            desc_bruta = dados.get("description", "Sem descrição disponível.")
            descricao = desc_bruta.get("value", "Sem descrição disponível.") if isinstance(desc_bruta, dict) else desc_bruta

            lista_capas = dados.get("covers", [])
            capa_url = f"{COVERS_URL}/0-L.jpg"
            
            if lista_capas and isinstance(lista_capas, list) and len(lista_capas) > 0:
                try:
                    id_capa = int(lista_capas[0])
                except (TypeError, ValueError):
                    id_capa = 0
                if id_capa > 0:
                    capa_url = f"{COVERS_URL}/{id_capa}-L.jpg"

            assuntos = dados.get("subjects", [])
            
            detalhes = {
                "titulo": dados.get("title", "Título desconhecido"),
                "descricao": descricao,
                "capa_url": capa_url,
                "assuntos": ", ".join(assuntos)[:300] + "..." if assuntos else "Nenhum assunto informado."
            }
    except (requests.RequestException, ValueError) as e:
        print(f"❌ Erro ao buscar detalhes da obra {id_livro}: {e}")

    if not detalhes:
        detalhes = {
            "titulo": "Dados da Obra (Modo Local)",
            "descricao": "Não foi possível resgatar os detalhes originais através do link externo.",
            "capa_url": f"{COVERS_URL}/0-L.jpg",
            "assuntos": "Desenvolvimento, Tecnologia"
        }

    return templates.TemplateResponse(
        name="detalhes.html",
        request=request,
        context={"livro": detalhes},
    )
