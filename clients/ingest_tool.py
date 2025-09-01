"""
ingest_tool.py
--------------
Universal ingest per PDF, TXT, DOCX, HTML → PostgreSQL + pgvector

USO DA TERMINALE (esempi):
    # Ingesta un singolo file
    python -m clients.ingest_tool --file data/manuale.pdf --source "manuale"

    # Ingesta tutti i file in ./data/ (non ricorsivo)
    python -m clients.ingest_tool --dir data

    # Ingest ricorsivo di sottocartelle
    python -m clients.ingest_tool --dir data --recursive
"""

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    UnstructuredWordDocumentLoader,
    UnstructuredHTMLLoader,
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain.tools import StructuredTool

load_dotenv()

# ---------- Loader detection ---------- #
def detect_loader(file_path: str):
    """Sceglie il loader corretto in base all'estensione."""
    ext = file_path.lower().split(".")[-1]
    if ext == "pdf":
        return PyPDFLoader(file_path)
    elif ext == "txt":
        return TextLoader(file_path)
    elif ext in {"docx", "doc"}:
        return UnstructuredWordDocumentLoader(file_path)
    elif ext == "html":
        return UnstructuredHTMLLoader(file_path)
    else:
        raise ValueError(f"Tipo di file '{ext}' non supportato")

# ---------- Core ingest for a single file ---------- #
def _ingest_single_file(file_path: str, source: str, splitter, embeddings, cursor):
    loader = detect_loader(file_path)
    docs = loader.load()

    chunks = splitter.split_documents(docs)
    count = 0
    for i, chunk in enumerate(chunks):
        text = chunk.page_content.strip()
        if not text:
            continue
        vector = embeddings.embed_query(text)
        cursor.execute(
            "INSERT INTO documents (source, page, chunk_text, embedding) "
            "VALUES (%s, %s, %s, %s)",
            (source, i + 1, text, vector),
        )
        count += 1
    return count

# ---------- Public API: ingest_file ---------- #
def ingest_file_to_pgvector(file_path: str, source: str = "manual") -> str:
    """Ingesta UN singolo file (PDF, TXT, DOCX, HTML) nel database."""
    try:
        # Se il percorso non esiste, prova a cercarlo in ./data/
        if not os.path.exists(file_path):
            file_path = Path("data") / file_path
            if not file_path.exists():
                return f"File {file_path} non trovato."

        splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        embeddings = OpenAIEmbeddings()

        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
        )
        cursor = conn.cursor()
        count = _ingest_single_file(
            str(file_path), source, splitter, embeddings, cursor
        )
        conn.commit()
        cursor.close()
        conn.close()
        return f"{count} chunk inseriti da {file_path}"
    except Exception as e:
        return f"Errore ingest del file {file_path}: {e}"

# ---------- Public API: ingest_directory ---------- #
def ingest_directory_to_pgvector(
    dir_path: str = "data", recursive: bool = True, source: str = "batch"
) -> str:
    """
    Ingesta TUTTI i file supportati all'interno di una directory
    (default ./data/). Con recursive=True scansiona le sottocartelle.
    """
    dir_path = Path(dir_path)
    if not dir_path.is_dir():
        return f"La directory {dir_path} non esiste."

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    embeddings = OpenAIEmbeddings()

    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    cursor = conn.cursor()

    pattern = "**/*" if recursive else "*"
    files = [p for p in dir_path.glob(pattern) if p.is_file()]
    total_chunks, total_files = 0, 0

    for f in files:
        try:
            chunks = _ingest_single_file(str(f), source, splitter, embeddings, cursor)
            total_chunks += chunks
            total_files += 1
        except ValueError:
            # file non supportato → lo saltiamo senza bloccare il batch
            continue

    conn.commit()
    cursor.close()
    conn.close()

    return (
        f"Ingest terminato: {total_chunks} chunk da {total_files} file "
        f"nella directory {dir_path}"
    )

# ---------- LangChain tool wrappers ---------- #
ingest_file_tool = StructuredTool.from_function(
    func=ingest_file_to_pgvector,
    name="Ingest_File_pgvector",
    description="Carica un singolo file (PDF, TXT, DOCX, HTML) nel vector store",
)

ingest_directory_tool = StructuredTool.from_function(
    func=ingest_directory_to_pgvector,
    name="Ingest_Directory_pgvector",
    description=(
        "Esegue l'ingestion di TUTTI i file supportati presenti in una directory (default ./data/). "
        "Parametri: dir_path (str, opzionale), recursive (bool, opzionale)."
    ),
)

# ---------- CLI entry‑point ---------- #
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Ingesta file o directory nel vector store pgvector"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", "-f", help="Percorso di un singolo file da ingestare")
    group.add_argument(
        "--dir", "-d", help="Percorso di una directory da ingestare (default ./data)"
    )
    parser.add_argument(
        "--recursive",
        "-r",
        action="store_true",
        help="Scansiona ricorsivamente le sottocartelle (solo con --dir)",
    )
    parser.add_argument(
        "--source",
        "-s",
        default="manual",
        help="Etichetta 'source' da salvare nel DB (default 'manual')",
    )
    args = parser.parse_args()

    if args.file:
        print(ingest_file_to_pgvector(args.file, source=args.source))
    else:
        dir_path = args.dir or "data"
        print(
            ingest_directory_to_pgvector(
                dir_path, recursive=args.recursive, source=args.source
            )
        )
