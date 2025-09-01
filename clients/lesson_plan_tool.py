from __future__ import annotations
"""
lesson_plan_tool.py – versione senza date/start/end
--------------------------------------------------
Schema ridotto per riflettere il mock-up: ogni lezione ha solo
lesson_number, title, objectives, activities, materials, assessment.
"""

import json, re, ast, logging
from typing import List, Optional

from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain.tools import StructuredTool

from clients.query_rag_tool import query_rag

# ──────────────────────────── Pydantic ─────────────────────────────
class Lesson(BaseModel):
    lesson_number: int
    title: str
    objectives: List[str]
    activities: List[str]
    materials: Optional[List[str]] = None
    assessment: Optional[str] = None

class LessonPlan(BaseModel):
    subject: str
    topic: str
    grade: str
    lesson_minutes: int
    global_goals: Optional[str] = None
    lessons: List[Lesson]

# ─────────────────────────── LLM & prompt ──────────────────────────
llm = ChatOpenAI(model="gpt-4o", temperature=0.2)

_SYSTEM = """
Sei un docente di {grade} italiano.
Genera un LESSON PLAN in JSON **senza alcun testo extra**.
✔ Ogni lezione dura {lesson_minutes} minuti e tratta "{topic}" ({subject}).
✔ DEVI produrre **almeno 6 lezioni**.
✔ Ogni 'title' deve essere specifico (niente “Lezione 1” o “Introduzione”).
✔ Per ogni lezione scrivi:
   • min 3 'objectives' (≤12 parole l’uno)
   • min 3 'activities'  (≤12 parole l’una)
   • facoltativo 'materials' (max 3) e 'assessment' breve.
Schema da seguire (NON modificare i nomi campi):

{{
  "subject": "...",
  "topic": "...",
  "grade": "...",
  "lesson_minutes": 45,
  "lessons": [
    {{
      "lesson_number": 1,
      "title": "...",
      "objectives": ["...","...","..."],
      "activities":  ["...","...","..."],
      "materials":   ["..."],
      "assessment":  "..."
    }}
  ]
}}
"""

# ─────────────────── helper estrazione JSON ───────────────────────

def _extract_json(raw: str) -> dict:
    text = re.sub(r"```[a-zA-Z0-9]*|```", "", raw).strip()
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        text = m.group(0)
    try:
        return json.loads(text)
    except Exception:
        try:
            return ast.literal_eval(text)
        except Exception as e:
            logging.error("JSON parse failed. Raw output:\n%s", raw)
            raise ValueError("Impossibile estrarre JSON dal modello") from e

# ───────────────────────── core generator ─────────────────────────

def generate_custom_lesson_plan(
    subject: str,
    topic: str,
    grade: str,
    lesson_minutes: int,
    global_goals: str = "",
):
    rag = query_rag(topic, top_k=10)
    raw = llm.invoke([
        {"role": "system", "content": _SYSTEM.format(
            grade=grade, lesson_minutes=lesson_minutes, subject=subject, topic=topic
        )},
        {"role": "user", "content": f"OBIETTIVI GLOBALI: {global_goals}\nCONTESTO:\n{rag}"}
    ]).content

    plan_dict = _extract_json(raw)

    # assicurati dei campi base
    plan_dict.setdefault("subject", subject)
    plan_dict.setdefault("topic", topic)
    plan_dict.setdefault("grade", grade)
    plan_dict.setdefault("lesson_minutes", lesson_minutes)

    return LessonPlan(**plan_dict)

# ─────────────────────── LangChain tool ──────────────────────────
lesson_plan_tool = StructuredTool.from_function(
    func=generate_custom_lesson_plan,
    name="Generate_LessonPlan",
    description="Genera un piano lezioni (JSON) senza date/start/end.",
    return_direct=True,
    output_schema=LessonPlan,
)