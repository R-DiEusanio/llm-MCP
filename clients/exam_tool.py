from __future__ import annotations
import json, re, uuid
from typing import List, Literal, Dict, Optional

from pydantic import BaseModel
from langchain.tools import StructuredTool
from langchain_openai import ChatOpenAI

# Pydantic schema
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

# LLM settings
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

_JSON_RE = re.compile(r"\{[\s\S]+\}")

def _parse_json(raw: str) -> dict:
    m = _JSON_RE.search(raw)
    if not m:
        raise ValueError("No JSON found")
    return json.loads(m.group(0))

# Generazione esame
def generate_exam(topic: str, n: int = 5, level: str = "medium") -> Exam:
    prompt = f"ARGOMENTO: {topic}\nNUM_DOMANDE: {n}\nDIFFICOLTÀ: {level.upper()}"
    raw = llm.invoke([
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": prompt}
    ]).content
    parsed = _parse_json(raw)

    for q in parsed["questions"]:
        q.setdefault("id", str(uuid.uuid4()))
        if q["qtype"] == "mcq":
            for o in q["options"]:
                o.setdefault("id", str(uuid.uuid4())[:4])

    return Exam(**parsed)

# AI‑grading per domande aperte
def _judge_open_ai(question: Question, student_answer: str) -> bool:
    """
    Chiede all'LLM di valutare la risposta aperta. Ritorna True se sostanzialmente corretta.
    """
    if not student_answer.strip():
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

# Valutazione / grading
def grade_exam(exam: Exam, answers: Dict[str, str | None]) -> dict:
    details = []
    score = 0

    for q in exam.questions:
        user_ans = answers.get(q.id, "")

        if q.qtype == "mcq":
            correct_opt = next(o for o in q.options if o.is_correct)
            correct = user_ans == correct_opt.id
            details.append({
                "qid": q.id,
                "correct": correct,
                "correct_text": correct_opt.text,
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

    return {"score": score, "max": len(exam.questions), "details": details}

# LangChain tool
generate_exam_tool = StructuredTool.from_function(
    func=generate_exam,
    name="Generate_Exam",
    description="Genera un esame con domande MCQ e aperte, includendo ideal_answer ed explanation.",
    return_direct=True,
    output_schema=Exam,
)
