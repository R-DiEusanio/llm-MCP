import os
import psycopg2
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain.tools import StructuredTool

load_dotenv()

def query_rag(question: str, top_k: int = 3) -> str:
    """
    Recupera i chunk di testo più rilevanti per una domanda, dal database PostgreSQL con pgvector.
    """
    try:
        embeddings = OpenAIEmbeddings()
        query_vector = embeddings.embed_query(question)

        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD")
        )
        cursor = conn.cursor()

        cursor.execute("""
            SELECT source, page, chunk_text
            FROM documents
            ORDER BY embedding <=> %s
            LIMIT %s
        """, (query_vector, top_k))

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        if not results:
            return "Nessun risultato rilevante trovato nei documenti."

        formatted = "\n---\n".join(
            f"[{source} - pagina {page}]\n{chunk}"
            for source, page, chunk in results
        )

        return f"Contesto recuperato:\n{formatted}"

    except Exception as e:
        return f"Errore nel retrieval dal database: {str(e)}"

query_rag_tool = StructuredTool.from_function(
    func=query_rag,
    name="RAG_Query",
    description="Recupera contenuto rilevante dal database (pgvector) in base a una domanda semantica. Usa top_k=3 di default."
)
