from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()
import logging, re
from io import BytesIO

from flask import Flask, render_template, request, jsonify, send_file
from dotenv import load_dotenv
from pydantic import BaseModel

from agent import create_agent
from clients.exam_tool import Exam, generate_exam, grade_exam
from clients.concept_map_tool import generate_concept_map, ConceptMap
from clients.lesson_plan_tool import (
    LessonPlan,
    generate_custom_lesson_plan,
)
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors
from clients.slide_tool import generate_slides_pptx
from clients.summarize_tool import summarize_topic_and_optional_file



# ───────────────────────── Config ──────────────────────────
load_dotenv()
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
agent = create_agent()

# ─────────────── Helper: Concept-map Pydantic ──────────────

def _is_concept_map(obj) -> bool:
    return (
        isinstance(obj, BaseModel)
        and hasattr(obj, "nodeDataArray")
        and hasattr(obj, "linkDataArray")
    )

# regex tipo “esame di storia”
EXAM_RE = re.compile(r"(?:esame|quiz|test)\s+(?:di|su|in)\s+([\w\sàèéìòù]+)", re.I)

# ───────────────────────── Routes ──────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

# -------------- /ask (chat + quick-quiz) -------------------
@app.post("/ask")
def ask():
    data = request.get_json() or {}
    query = data.get("question", "").strip()
    if not query:
        return jsonify({"error": "No question provided."}), 400

    # Quick-quiz?
    m = EXAM_RE.search(query)
    if m:
        subject = m.group(1).strip().title()
        try:
            exam = generate_exam(subject, 5, "medium")
            return jsonify({"exam": exam.model_dump()})
        except Exception:
            logging.exception("Exam generation failed")
            return jsonify({"error": "Exam generation failed"}), 500

    # LLM / tools
    try:
        response = agent.invoke({"input": query, "chat_history": []})
        if _is_concept_map(response):
            return jsonify({"concept_map": response.model_dump(by_alias=True)})

        if isinstance(response, dict):
            out = response.get("output")
            if _is_concept_map(out):
                return jsonify({"concept_map": out.model_dump(by_alias=True)})
            if isinstance(out, dict) and {"nodeDataArray", "linkDataArray"} <= out.keys():
                return jsonify({"concept_map": out})
            if out is not None:
                return jsonify({"answer": out})
            if {"nodeDataArray", "linkDataArray"} <= response.keys():
                return jsonify({"concept_map": response})
        return jsonify({"answer": response})
    except Exception:
        logging.exception("Agent error")
        return jsonify({"error": "Internal server error."}), 500

# -------------- quiz endpoints -----------------------------

@app.post("/generate_exam")
def generate_exam_ep():
    req = request.get_json() or {}
    subject = req.get("subject", "Storia")
    topic = req.get("topic", subject)
    n = int(req.get("n", 5))
    level = req.get("level", "medium")
    try:
        exam = generate_exam(f"{subject}: {topic}", n, level)
        return jsonify(exam.model_dump())
    except Exception:
        logging.exception("Exam generation failed")
        return jsonify({"error": "generation failed"}), 500

@app.post("/grade_exam")
def grade_exam_ep():
    data = request.get_json() or {}
    exam = Exam(**data["exam"])
    answers = data.get("answers", {})
    result = grade_exam(exam, answers)
    return jsonify(result)

# -------------- lesson-plan endpoint -----------------------

@app.post("/generate_plan")
def generate_plan():
    data = request.get_json() or {}
    plan = generate_custom_lesson_plan(
        subject        = data.get("subject", "Storia"),
        topic          = data.get("topic",   "Argomento"),
        grade          = data.get("grade",   "Scuola Elementare"),
        lesson_minutes = int(data.get("lesson_minutes", 45)),
        global_goals   = data.get("global_goals", ""),
    )
    return jsonify(plan.model_dump())

# -------------- PDF exporter -------------------------------

@app.post("/plan_pdf")
def plan_pdf():
    data = request.get_json() or {}
    plan = LessonPlan(**data["plan"])

    rows = [["#", "Titolo", "Obiettivi", "Attività", "Materiali"]]
    for i, l in enumerate(plan.lessons, start=1):
        rows.append([
            str(i),
            l.title,
            "\n".join(l.objectives),
            "\n".join(l.activities),
            "\n".join(l.materials or []),
        ])

    buf = BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4)
    tbl = Table(rows, repeatRows=1)
    tbl.setStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#E0E0E0")),
        ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
    ])
    pdf.build([tbl])
    buf.seek(0)

    fname = f"piano_{plan.subject}_{plan.topic}.pdf"
    return send_file(buf, download_name=fname, as_attachment=True)


# -------------- concept-map endpoint -----------------------
@app.post("/generate_concept_map")
def generate_concept_map_ep():
    data = request.get_json() or {}
    # topic è obbligatorio; subject solo estetico (puoi concatenarlo se vuoi)
    subject = (data.get("subject") or "").strip()
    topic   = (data.get("topic") or subject or "Argomento").strip()
    max_nodes = int(data.get("max_nodes", 20))
    top_k     = int(data.get("top_k", 8))

    if not topic:
        return jsonify({"error": "topic mancante"}), 400

    try:
        cm: ConceptMap = generate_concept_map(topic=topic, max_nodes=max_nodes, top_k=top_k)
        # by_alias=True per avere "from" nei link
        return jsonify(cm.model_dump(by_alias=True))
    except Exception:
        logging.exception("Concept map generation failed")
        return jsonify({"error": "generation failed"}), 500

# -------------- slide-deck endpoint ------------------------
@app.post("/generate_slides")
def generate_slides_ep():
    data = request.get_json() or {}
    subject  = (data.get("subject") or "Materia").strip()
    topic    = (data.get("topic")   or "Argomento").strip()
    n_slides = int(data.get("n_slides", 10))
    try:
        buf = generate_slides_pptx(subject, topic, n_slides)
        fname = f"slides_{subject}_{topic}.pptx".replace(" ", "_")
        return send_file(
            buf,
            as_attachment=True,
            download_name=fname,
            mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
    except Exception:
        logging.exception("Slide generation failed")
        return jsonify({"error": "generation failed"}), 500


# -------------- summarize endpoint -------------------------
@app.post("/summarize")
def summarize_ep():
    # Supporta sia JSON (senza file) che multipart/form-data (con file)
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        topic  = (request.form.get("topic") or "").strip()
        length = (request.form.get("length") or "medium").strip().lower()
        upfile = request.files.get("file")  # opzionale
        if not topic and not upfile:
            return jsonify({"error": "Specifica un argomento o allega un file."}), 400
        try:
            payload = summarize_topic_and_optional_file(topic=topic, length=length, file_storage=upfile)
            return jsonify(payload.model_dump())
        except Exception:
            logging.exception("Summarization failed (multipart)")
            return jsonify({"error": "summarization failed"}), 500
    else:
        data   = request.get_json() or {}
        topic  = (data.get("topic") or "").strip()
        length = (data.get("length") or "medium").strip().lower()
        text   = (data.get("text") or "").strip() or None
        if not topic and not text:
            return jsonify({"error": "Specifica un argomento o del testo."}), 400
        try:
            payload = summarize_topic_and_optional_file(topic=topic, length=length, file_storage=None, plain_text=text)
            return jsonify(payload.model_dump())
        except Exception:
            logging.exception("Summarization failed (json)")
            return jsonify({"error": "summarization failed"}), 500


# ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True)