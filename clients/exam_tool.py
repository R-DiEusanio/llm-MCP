from __future__ import annotations
import json, re, uuid
from typing import List, Literal, Dict, Optional

from pydantic import BaseModel
from langchain.tools import StructuredTool
from langchain_openai import ChatOpenAI

# ─────────────────────────────────────────────────────────────
# Pydantic schema
# ─────────────────────────────────────────────────────────────
class Option(BaseModel):
    id: str
    text: str
    is_correct: bool

class Question(BaseModel):
    id: str
    qtype: Literal["mcq", "open"]
    text: str
    options: List[Option] | None = None
    ideal_answer: Optional[str] = None
    explanation: str

class Exam(BaseModel):
    title: str
    questions: List[Question]
    version_latin: Optional[str] = None
    solution_translation: Optional[str] = None

# ─────────────────────────────────────────────────────────────
# LLM settings
# ─────────────────────────────────────────────────────────────
llm = ChatOpenAI(model="gpt-4o", temperature=0.3)

_SYSTEM = """
Sei un autore di test. Restituisci SOLO un JSON Exam:
{
  "title": "...",
  "questions": [
    {
      "id": "uuid",
      "qtype": "mcq" | "open",
      "text": "...",
      "options": [                       # solo se qtype=="mcq"
        { "id": "A", "text": "...", "is_correct": true/false }
      ],
      "ideal_answer": "...",             # solo se qtype=="open"
      "explanation": "max 30 parole"
    }
  ]
}
Regole:
- Una sola opzione is_correct:true per MCQ.
- Non scrivere nulla prima o dopo il JSON.
"""

_SYSTEM_LATINO = """
Sei un autore di test di Latino. Restituisci SOLO un JSON con lo schema:
{
  "title": "...",
  "version_latin": "testo latino da tradurre (80-150 parole, livello coerente)",
  "solution_translation": "traduzione italiana chiara e fedele",
  "questions": [
    {
      "id": "uuid",
      "qtype": "mcq" | "open",
      "text": "domanda di comprensione sulla versione",
      "options": [ { "id": "A", "text": "...", "is_correct": true/false } ],
      "ideal_answer": "...",
      "explanation": "max 30 parole"
    }
  ]
}
Regole:
- Genera ESATTAMENTE 5 domande di comprensione riferite al testo della versione.
- Una sola opzione is_correct:true per ogni MCQ.
- Non scrivere nulla prima o dopo il JSON.
"""

_JSON_RE = re.compile(r"\{[\s\S]+\}")

def _parse_json(raw: str) -> dict:
    m = _JSON_RE.search(raw)
    if not m:
        raise ValueError("No JSON found")
    return json.loads(m.group(0))

# ─────────────────────────────────────────────────────────────
# RAG: recupero criteri da "valutazione-versioni.pdf"
# ─────────────────────────────────────────────────────────────
def _rag_guidelines_for_latino() -> str:
    """
    Recupera linee guida per la valutazione delle versioni di latino
    da 'valutazione-versioni.pdf' via RAG. Ritorna un testo breve.
    """
    try:
        try:
            from clients.query_rag_tool import query_rag  
            txt = query_rag("criteri valutazione versioni latino file:valutazione-versioni.pdf", k=4)
            return (txt or "")[:2000]
        except Exception:
            pass

        import os
        from sqlalchemy import create_engine
        from langchain_postgres.vectorstores import PGVector
        from langchain_openai import OpenAIEmbeddings

        DATABASE_URL = os.getenv("PGVECTOR_CONNECTION_STRING")
        if not DATABASE_URL:
            return ""
        engine = create_engine(DATABASE_URL)
        embeddings = OpenAIEmbeddings()
        vs = PGVector(
            embedding_function=embeddings,
            collection_name="documents",
            connection=engine,
        )
        docs = vs.similarity_search(
            "criteri valutazione versioni latino valutazione-versioni.pdf rubric griglia",
            k=4
        )
        joined = "\n\n".join(getattr(d, "page_content", "") for d in docs)
        return joined[:2000]
    except Exception:
        return ""

# ─────────────────────────────────────────────────────────────
# Generazione esame
# ─────────────────────────────────────────────────────────────
def generate_exam(topic: str, n: int = 5, level: str = "medium", subject: Optional[str] = None) -> Exam:
    """
    - Se subject == 'latino': genera una versione + 5 domande di comprensione,
      includendo 'version_latin' e 'solution_translation', con supporto RAG.
    - Altrimenti: usa lo schema generico con n domande.
    """
    if (subject or "").lower() == "latino":
        guidelines = _rag_guidelines_for_latino()
        user_prompt = (
            f"MATERIA: LATINO\n"
            f"ARGOMENTO: {topic}\n"
            f"DIFFICOLTA': {level.upper()}\n"
            f"ISTRUZIONI RAG (criteri valutazione versioni):\n{guidelines}\n\n"
            "Genera una versione (80-150 parole) e 5 domande di comprensione riferite al testo."
        )
        raw = llm.invoke([
            {"role": "system", "content": _SYSTEM_LATINO},
            {"role": "user", "content": user_prompt}
        ]).content
        parsed = _parse_json(raw)

        if "questions" in parsed:
            parsed["questions"] = (parsed["questions"] or [])[:5]

    else:
        prompt = f"ARGOMENTO: {topic}\nNUM_DOMANDE: {n}\nDIFFICOLTÀ: {level.upper()}"
        raw = llm.invoke([
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt}
        ]).content
        parsed = _parse_json(raw)
        if "questions" in parsed:
            parsed["questions"] = (parsed["questions"] or [])[:n]

    # IDs robusti
    for q in parsed.get("questions", []):
        q.setdefault("id", str(uuid.uuid4()))
        if q.get("qtype") == "mcq" and q.get("options"):
            for o in q["options"]:
                o.setdefault("id", str(uuid.uuid4())[:4])

    return Exam(**parsed)

# ─────────────────────────────────────────────────────────────
# AI-grading per domande aperte
# ─────────────────────────────────────────────────────────────
def _judge_open_ai(question: Question, student_answer: str) -> bool:
    """
    Chiede all'LLM di valutare la risposta aperta. True se sostanzialmente corretta.
    """
    if not student_answer or not student_answer.strip():
        return False
    prompt = (
        "Sei un insegnante.\n"
        f"Domanda: {question.text}\n"
        f"Risposta ideale: {question.ideal_answer}\n"
        f"Risposta studente: {student_answer}\n"
        "Rispondi solo YES se la risposta dello studente è sostanzialmente corretta, altrimenti NO."
    )
    try:
        resp = llm.invoke(prompt).content.strip().upper()
        return resp.startswith("Y")
    except Exception:
        return False  # prudenziale

# ─────────────────────────────────────────────────────────────
# Feedback traduzione (Latino) basato su RAG
# ─────────────────────────────────────────────────────────────
def _judge_translation_ai(latin_text: str, student_translation: str, ref_translation: str) -> Dict[str, str]:
    """
    Fornisce un feedback sintetico sulla traduzione dello studente rispetto alla
    traduzione di riferimento, basandosi anche su criteri recuperati via RAG.
    """
    if not student_translation or not student_translation.strip():
        return {"ok": "NO", "feedback": "Traduzione assente."}

    guidelines = _rag_guidelines_for_latino()
    prompt = (
        "Sei un docente di latino. Fornisci un giudizio sintetico (3-5 righe) "
        "sulla traduzione dello studente rispetto alla traduzione di riferimento, "
        "basandoti sui criteri indicati.\n\n"
        f"[CRITERI RAG]\n{guidelines}\n\n"
        f"[TESTO LATINO]\n{latin_text}\n\n"
        f"[TRADUZIONE RIFERIMENTO]\n{ref_translation}\n\n"
        f"[TRADUZIONE STUDENTE]\n{student_translation}\n\n"
        "Output: JSON con chiavi {\"ok\": \"SI/NO/PARZIALE\", \"feedback\": \"...\"}. "
        "Non aggiungere altro testo."
    )
    try:
        resp = llm.invoke(prompt).content
        m = re.search(r"\{[\s\S]+\}", resp)
        if m:
            return json.loads(m.group(0))
        return {"ok": "PARZIALE", "feedback": resp[:500]}
    except Exception:
        return {"ok": "PARZIALE", "feedback": "Feedback non disponibile."}

# ─────────────────────────────────────────────────────────────
# Valutazione / grading
# ─────────────────────────────────────────────────────────────
def grade_exam(exam: Exam, answers: Dict[str, str | None]) -> dict:
    """
    - Valuta MCQ e OPEN.
    - Se l'esame contiene una versione (Latino), ritorna la traduzione di riferimento
      e, se presente 'answers[\"translation\"]', un feedback sintetico.
    """
    details = []
    score = 0

    for q in exam.questions:
        user_ans = answers.get(q.id, "") or ""

        if q.qtype == "mcq":
            try:
                correct_opt = next(o for o in (q.options or []) if o.is_correct)
                correct = (user_ans == correct_opt.id)
                details.append({
                    "qid": q.id,
                    "correct": correct,
                    "correct_text": correct_opt.text,
                    "explanation": q.explanation
                })
                score += int(correct)
            except StopIteration:
                details.append({
                    "qid": q.id,
                    "correct": False,
                    "correct_text": "(opzione corretta mancante)",
                    "explanation": q.explanation
                })

        else:  # open
            correct = _judge_open_ai(q, user_ans)
            details.append({
                "qid": q.id,
                "correct": correct,
                "correct_text": q.ideal_answer or "(risposta attesa)",
                "explanation": q.explanation
            })
            score += int(correct)

    result = {"score": score, "max": len(exam.questions), "details": details}

    if exam.version_latin and exam.solution_translation:
        student_tr = (answers.get("translation", "") or "").strip()
        translation_block: Dict[str, object] = {
            "solution_translation": exam.solution_translation
        }
        if student_tr:
            fb = _judge_translation_ai(exam.version_latin, student_tr, exam.solution_translation)
            translation_block["student_feedback"] = fb
        result["translation"] = translation_block

    return result

# ─────────────────────────────────────────────────────────────
# LangChain tool
# ─────────────────────────────────────────────────────────────
generate_exam_tool = StructuredTool.from_function(
    func=generate_exam,
    name="Generate_Exam",
    description=("Genera un esame; per Latino produce una versione da tradurre + 5 domande di comprensione "
                 "e include solution_translation. Per altre materie genera MCQ/open con ideal_answer ed explanation."),
    return_direct=True,
    output_schema=Exam,
)
