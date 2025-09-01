import os
import psycopg2
from langchain.tools import StructuredTool
from dotenv import load_dotenv

load_dotenv()

def execute_sql_query(query: str) -> str:
    """
    Esegue una query SQL sul database PostgreSQL locale.
    Supporta SELECT, INSERT, UPDATE, DELETE.
    """
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD")
        )
        cursor = conn.cursor()
        cursor.execute(query)

        if query.strip().lower().startswith("select"):
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            result = [dict(zip(columns, row)) for row in rows]
        else:
            conn.commit()
            result = f"Query eseguita con successo."

        cursor.close()
        conn.close()
        return str(result)
    
    except Exception as e:
        return f"Errore nella query: {str(e)}"

db_tool = StructuredTool.from_function(
    func=execute_sql_query,
    name="PostgreSQL_Query",
    description="Usa questo strumento per eseguire query SQL su un database PostgreSQL locale. Accetta solo query SQL valide."
)
