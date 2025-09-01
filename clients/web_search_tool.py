import os
import requests
from langchain_core.tools import Tool
from typing import Optional # Importa 'Optional' per indicare che un valore può essere del tipo specificato oppure None

BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")

def brave_search(query: str, count: Optional[int] = 3) -> str:
    if not BRAVE_API_KEY:
        return "Brave API Key non trovata."
    
    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "accept": "application/json",
        "X-Subscription-Token": BRAVE_API_KEY
    }
    
    params = {
        "q": query,
        "count": count
    }
    
    try:
        response = requests.get(url, headers=headers,params=params)
        response.raise_for_status()
        data = response.json()
        
        results = data.get("web",{}).get("results", [])
        if not results:
            return "Nessun risultato trovato"
        
        formatted = "\n".join( # Crea una stringa con i primi 'count' dei risultati di ricerca, numerati e formattati con titolo e URL
            [f"{i+1}. {r['title']}: {r['url']}" for i, r in enumerate(results[:count])]
        )
        return f"Risultati da Brave Search:\n{formatted}"
    
    except Exception as e:
        return f"Errore durante la ricerca web: {str(e)}"
    
def get_brave_tool():
    return Tool.from_function(
        func=brave_search,
        name="Brave_Search",
        description="Usalo solo se chiedono di cercare informazioni aggiornate sul web."
    )
    
