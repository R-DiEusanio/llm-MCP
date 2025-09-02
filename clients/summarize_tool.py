# clients/summarize_tool.py
from __future__ import annotations
import os, tempfile, pathlib
from typing import Optional, List, Dict
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_community.document_loaders import (
    PyPDFLoader,
    UnstructuredWordDocumentLoader,
    TextLoader,
)
from langchain.text_splitter import RecursiveCharacterTextSplitter

class SummaryPayload(BaseModel):
    topic: str
    length: str
    summary_md: str  # markdown pronto da mostrare

# ---------- parsing file ----------
def _extract_text(file_path: str) -> str:
    ext = pathlib.Path(file_path).suffix.lower()
    if ext == ".pdf":
        docs = PyPDFLoader(file_path).load()
        return "\n\n".join(d.page_content for d in docs)
    elif ext in (".docx", ".doc"):
        docs = UnstructuredWordDocumentLoader(file_path).load()
        return "\n\n".join(d.page_content for d in docs)
    elif ext == ".txt":
        return TextLoader(file_path).load()[0].page_content
    else:
        raise ValueError(f"Estensione non supportata: {ext}")

def _shrink(text: str, target_chars: int = 15000) -> List[str]:
    """Spezzetta il testo in chunk per riassunti lunghi."""
    splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
    chunks = [d.page_content for d in splitter.create_documents([text])]
    # limitiamo i chunk complessivi per evitare prompt enormi
    out, total = [], 0
    for c in chunks:
        if total + len(c) > target_chars:
            break
        out.append(c); total += len(c)
    return out

# ---------- LLM ----------
def _summarize_chunks(topic: str, chunks: List[str], length: str) -> str:
    """
    map → reduce semplice: prima riassunti per chunk, poi fusione finale.
    """
    llm = ChatOpenAI(model="gpt-4o", temperature=0.2)
    # 1) map
    partials: List[str] = []
    for c in chunks:
        prompt = f"""Sei un docente delle scuole superiori.
Riassumi il seguente testo sull'argomento "{topic}" in italiano, in modo fedele e didattico.
Usa punti elenco compatti e conserva termini tecnici rilevanti.

TESTO:
\"\"\"{c}\"\"\""""
        partials.append(llm.invoke(prompt).content.strip())

    # 2) reduce
    bullets_target = {"short": 6, "medium": 10, "long": 16}.get(length, 10)
    prompt_reduce = f"""Unifica e ripulisci i riassunti parziali sull'argomento "{topic}".
Produci **solo** markdown con questa struttura:

# Riassunto: {topic}
- (max {bullets_target} punti) punti chiave sintetici

## Concetti chiave
- 5–8 bullet con definizioni chiare

## Glossario
- 5–10 termini con spiegazione breve

## Domande di ripasso
1. ...
2. ...
3. ...

Riassunti parziali:
\"\"\"{chr(10).join(partials)}\"\"\""""
    return llm.invoke(prompt_reduce).content.strip()

def summarize_topic_and_optional_file(
    topic: str,
    length: str = "medium",
    file_storage=None,  # Werkzeug FileStorage (opzionale)
    plain_text: Optional[str] = None,
) -> SummaryPayload:
    """
    Se c'è un file: estrai testo e riassumi; altrimenti riassumi il plain_text (o il solo topic).
    """
    source_text = ""
    if file_storage:
        suffix = pathlib.Path(file_storage.filename or "upload").suffix or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            file_storage.save(tmp.name)
            source_text = _extract_text(tmp.name)
        os.unlink(tmp.name)
    elif plain_text:
        source_text = plain_text

    if not source_text:
        # Riassunto “solo topic”
        llm = ChatOpenAI(model="gpt-4o", temperature=0.2)
        bullets_target = {"short": 6, "medium": 10, "long": 16}.get(length, 10)
        prompt = f"""Fornisci un riassunto didattico in italiano su "{topic}".
Usa **markdown** con:
- un elenco di max {bullets_target} punti chiave
- sezione "Concetti chiave" (5–8 bullet)
- sezione "Glossario" (5–10 voci)
- sezione "Domande di ripasso" (3 domande)"""
        md = llm.invoke(prompt).content.strip()
        return SummaryPayload(topic=topic, length=length, summary_md=md)

    chunks = _shrink(source_text, target_chars={"short": 8000, "medium": 15000, "long": 22000}.get(length, 15000))
    md = _summarize_chunks(topic, chunks, length)
    return SummaryPayload(topic=topic, length=length, summary_md=md)
