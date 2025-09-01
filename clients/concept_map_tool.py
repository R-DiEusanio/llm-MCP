from __future__ import annotations

import json
import re
from typing import List, Optional, Set

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field, ValidationError

from clients.query_rag_tool import query_rag


# ───────────── Pydantic schemas ─────────────

class Node(BaseModel):
    key: str
    text: str

class Link(BaseModel):
    from_: str = Field(..., alias="from")
    to: str

class ConceptMap(BaseModel):
    nodeDataArray: List[Node]
    linkDataArray: List[Link]


# ───────────── LLM ─────────────

llm = ChatOpenAI(model="gpt-4o", temperature=0.2)

SYSTEM_PROMPT = (
    "Sei un generatore di mappe concettuali GERARCHICHE.\n"
    "Devi restituire SOLO un JSON con due array: nodeDataArray e linkDataArray.\n\n"
    "REQUISITI:\n"
    "• Un nodo ROOT con key='root' e text=Titolo (es. l'argomento).\n"
    "• 6–10 categorie principali (primo livello) collegate da ROOT → Cx.\n"
    "• Per OGNI categoria inserisci 3–6 sotto-nodi (secondo livello) con collegamento Cx → Sx_y.\n"
    "• Etichette brevi e pulite (massimo 5 parole per nodo).\n"
    "• Non inserire altro testo oltre al JSON.\n\n"
    "Formato esatto del JSON da produrre:\n"
    "{\n"
    '  "nodeDataArray": [ {"key":"root","text":"<TITOLO>"} , {"key":"c1","text":"Categoria"}, {"key":"c1_1","text":"Sotto nodo"}, ... ],\n'
    '  "linkDataArray": [ {"from":"root","to":"c1"}, {"from":"c1","to":"c1_1"}, ... ]\n'
    "}\n"
)

_JSON_RE = re.compile(r"\{[\s\S]+\}")


# ───────────── Helper ─────────────

def _extract_json(text: str) -> dict:
    m = _JSON_RE.search(text or "")
    if not m:
        raise ValueError("Nessun JSON trovato nella risposta del modello.")
    return json.loads(m.group(0))

def _apply_max_nodes(cm: ConceptMap, max_nodes: int) -> ConceptMap:
    """
    Limita il numero totale di nodi (incluso root) a max_nodes,
    rimuovendo link a nodi eliminati.
    """
    if max_nodes is None or max_nodes <= 0:
        return cm

    # Ordina: root, poi categorie (chiavi che iniziano con 'c'), poi il resto
    nodes = list(cm.nodeDataArray)
    nodes_sorted: List[Node] = []

    # 1) root
    root = next((n for n in nodes if n.key == "root"), None)
    if root:
        nodes_sorted.append(root)

    # 2) categorie (c*, C*)
    cats = [n for n in nodes if n.key != "root" and n.key.lower().startswith("c")]
    # 3) altri (sottocategorie o altro)
    others = [n for n in nodes if n.key != "root" and n not in cats]

    nodes_sorted.extend(cats)
    nodes_sorted.extend(others)

    # taglio
    limited_nodes = nodes_sorted[:max_nodes]
    keep_keys: Set[str] = {n.key for n in limited_nodes}

    # filtra link
    limited_links = [l for l in cm.linkDataArray if l.from_ in keep_keys and l.to in keep_keys]

    return ConceptMap(nodeDataArray=limited_nodes, linkDataArray=limited_links)


# ───────────── Core function ─────────────

def generate_concept_map(topic: str, max_nodes: int = 20, top_k: int = 8) -> ConceptMap:
    """
    Genera una concept map GERARCHICA (root → categorie → sotto-nodi).
    max_nodes limita il totale dei nodi restituiti (incluso root).
    """
    rag = query_rag(topic, top_k=top_k)
    context = "" if rag.startswith("Nessun risultato") else rag

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=(
            f"ARGOMENTO: {topic}\n\n"
            f"CONTESTO DI SUPPORTO (opzionale, usa solo se utile):\n{context}\n\n"
            "Produci ORA il JSON richiesto. Nessun commento aggiuntivo."
        ))
    ]

    raw = llm.invoke(messages).content
    parsed = _extract_json(raw)

    try:
        cm = ConceptMap(**parsed)
    except ValidationError as e:
        # Proviamo una normalizzazione soft per errori comuni
        if isinstance(parsed, dict):
            nda = parsed.get("nodeDataArray") or []
            lda = parsed.get("linkDataArray") or []
            cm = ConceptMap(
                nodeDataArray=[Node(**n) for n in nda],
                linkDataArray=[Link(**l) for l in lda],
            )
        else:
            raise

    cm = _apply_max_nodes(cm, max_nodes)
    return cm


# ───────────── LangChain Tool wrapper (se serve nell'agente) ─────────────

concept_map_tool = StructuredTool.from_function(
    func=generate_concept_map,
    name="Concept_Map_with_RAG",
    description=(
        "Genera una mappa concettuale gerarchica (root → categorie → sotto-nodi) "
        "nel formato nodeDataArray/linkDataArray. Parametro max_nodes per limitare i nodi."
    ),
    return_direct=True,
    output_schema=ConceptMap,
)
