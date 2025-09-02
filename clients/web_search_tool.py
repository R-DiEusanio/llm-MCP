import os, requests, logging
from typing import Optional, List, Dict
from langchain_core.tools import Tool

# --- utility: leggi la key al momento della chiamata (lazy) ---
def _get_brave_key() -> Optional[str]:
    return os.getenv("BRAVE_API_KEY")

# --- Web search (testo) ---
def brave_search(query: str, count: Optional[int] = 3) -> str:
    key = _get_brave_key()
    if not key:
        return "Brave API Key non trovata (BRAVE_API_KEY assente)."

    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {"accept": "application/json", "X-Subscription-Token": key}
    params = {"q": query, "count": count or 3, "search_lang": "it-IT", "country": "it", "safesearch": "strict"}

    try:
        r = requests.get(url, headers=headers, params=params, timeout=12)
        r.raise_for_status()
        data = r.json()
        results = data.get("web", {}).get("results", [])
        if not results:
            return "Nessun risultato trovato"
        formatted = "\n".join(f"{i+1}. {r['title']}: {r['url']}" for i, r in enumerate(results[:count]))
        return f"Risultati da Brave Search:\n{formatted}"
    except requests.HTTPError as e:
        return f"Errore HTTP Brave: {e} — {getattr(e.response, 'text', '')[:200]}"
    except Exception as e:
        return f"Errore durante la ricerca web: {e}"

# --- Image search (immagini) ---
def brave_image_search(query: str, count: Optional[int] = 6) -> List[Dict]:
    """
    Ritorna una lista di dict immagine (url, source/page_url, width/height se disponibili).
    """
    key = _get_brave_key()
    if not key:
        logging.info("[brave] BRAVE_API_KEY assente")
        return []

    url = "https://api.search.brave.com/res/v1/images/search"
    headers = {"accept": "application/json", "X-Subscription-Token": key}
    params = {"q": query, "count": count or 6, "search_lang": "it-IT", "country": "it", "safesearch": "strict"}

    try:
        r = requests.get(url, headers=headers, params=params, timeout=12)
        r.raise_for_status()
        data = r.json()
        results = data.get("results") or data.get("images", {}).get("results") or []
        # normalizza i campi principali
        out = []
        for it in results:
            out.append({
                "url": it.get("url") or it.get("image") or it.get("img", {}).get("url"),
                "thumbnail": (it.get("thumbnail") if isinstance(it.get("thumbnail"), str)
                              else (it.get("thumbnail") or {}).get("url")),
                "page_url": it.get("source") or it.get("page_url"),
                "width": it.get("width") or (it.get("properties") or {}).get("width"),
                "height": it.get("height") or (it.get("properties") or {}).get("height"),
            })
        return [x for x in out if x["url"]]
    except requests.HTTPError as e:
        logging.info(f"[brave] HTTP {e} — {getattr(e.response, 'text', '')[:200]}")
        return []
    except Exception as e:
        logging.info(f"[brave] Errore images: {e}")
        return []

def get_brave_tool():
    # Nome senza spazi (pattern ^[a-zA-Z0-9_-]+$)
    return Tool.from_function(
        func=brave_search,
        name="Brave_Web_Search",
        description="Cerca sul web (testo) con Brave."
    )

def get_brave_images_tool():
    # Ritorna JSON con elenco immagini normalizzato
    return Tool.from_function(
        func=lambda q: brave_image_search(q, count=6),
        name="Brave_Image_Search",
        description="Cerca immagini (licenze varie) con Brave; ritorna una lista di oggetti {url, thumbnail, page_url, width, height}."
    )
