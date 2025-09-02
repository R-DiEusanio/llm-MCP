
/* ---------- Helpers DOM ---------- */
const $ = (sel) => document.querySelector(sel);
const chatBox = $("#chat-box");
const userInput = $("#user-input");

const outputBox = $("#output-box");
const quizBox = $("#quiz-box");
const planBox = $("#plan-box");
const conceptBox = $("#concept-box");

function showOutputSection(sectionEl) {
  outputBox?.classList.remove("d-none");
  [quizBox, planBox, conceptBox].forEach((el) => el?.classList.add("d-none"));
  sectionEl?.classList.remove("d-none");
}

function escapeHtml(str) {
  return (str ?? "")
    .toString()
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

/* ---------- Chat ---------- */
function appendMessage(role, text) {
  const wrapper = document.createElement("div");
  wrapper.className = role === "user" ? "mb-2 text-end" : "mb-2";
  const bubble = document.createElement("div");
  bubble.className =
    "d-inline-block px-3 py-2 rounded-3 " +
    (role === "user" ? "bg-primary text-white" : "bg-white border");
  bubble.style.maxWidth = "100%";
  bubble.style.whiteSpace = "pre-wrap";
  bubble.innerText = text;
  wrapper.appendChild(bubble);
  chatBox?.appendChild(wrapper);
  chatBox?.scrollTo({ top: chatBox.scrollHeight, behavior: "smooth" });
}

async function sendMessage() {
  const q = userInput.value.trim();
  if (!q) return;
  appendMessage("user", q);
  userInput.value = "";

  try {
    const res = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      appendMessage("ai", err.error || "Errore server.");
      return;
    }
    const data = await res.json();

    // Possibili chiavi: {answer}, {exam}, {concept_map}
    if (data.exam) {
      renderQuiz(data.exam);
      showOutputSection(quizBox);
      appendMessage("ai", "Ho generato un quiz rapido sull’argomento richiesto.");
    } else if (data.concept_map) {
      renderConceptMap(data.concept_map);
      showOutputSection(conceptBox);
      appendMessage("ai", "Ecco la mappa concettuale.");
    } else if (data.answer !== undefined) {
      appendMessage("ai", String(data.answer));
    } else {
      appendMessage("ai", JSON.stringify(data, null, 2));
    }
  } catch (e) {
    console.error(e);
    appendMessage("ai", "Problema di rete. Riprova più tardi.");
  }
}
window.sendMessage = sendMessage;

userInput?.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && !ev.shiftKey) {
    ev.preventDefault();
    sendMessage();
  }
});

/* ---------- QUIZ ---------- */
const quizBtn = $("#quiz-btn");
const quizList = $("#quiz-list");
const submitQuizBtn = $("#submit-quiz");
const quizResult = $("#quiz-result");
const versionWrapper = $("#version-wrapper");
const versionLatin = $("#version-latin");
const latinTranslationBox = $("#latino-translation-box");
const translationInput = $("#translation-input");

let CURRENT_EXAM = null;

function renderQuiz(exam) {
  CURRENT_EXAM = exam;
  quizList.innerHTML = "";
  quizResult.innerHTML = "";
  versionWrapper.classList.add("d-none");
  latinTranslationBox.classList.add("d-none");
  submitQuizBtn.classList.add("d-none");

  // Eventuale testo "versione" per Latino
  const maybeVersion =
    exam.version_text || exam.version || (exam.meta && exam.meta.version_text);
  if (maybeVersion) {
    versionWrapper.classList.remove("d-none");
    versionLatin.textContent = maybeVersion;
    latinTranslationBox.classList.remove("d-none");
  }

  const questions = exam.questions || exam.ques || [];
  if (!questions.length) {
    // Se il backend avesse un altro schema, fallback
    const fallback = exam.items || [];
    fallback.forEach((q, idx) => createQuestionRow(q, idx));
  } else {
    questions.forEach((q, idx) => createQuestionRow(q, idx));
  }

  if (quizList.children.length > 0) {
    submitQuizBtn.classList.remove("d-none");
  }
}

function createQuestionRow(q, idx) {
  const li = document.createElement("li");
  li.className = "list-group-item";
  const qid = q.id || q.key || `q_${idx}`;
  const qtext = q.question || q.prompt || q.text || `Domanda ${idx + 1}`;

  let html = `<div class="fw-semibold mb-2">${escapeHtml(qtext)}</div>`;

  const options = q.options || q.choices || q.alternatives;
  if (Array.isArray(options) && options.length) {
    // Multiple-choice
    html += `<div class="d-flex flex-column gap-1">`;
    options.forEach((opt, j) => {
      const optId = `${qid}_${j}`;
      html += `
        <div class="form-check">
          <input class="form-check-input" type="radio" name="${qid}" id="${optId}" value="${escapeHtml(
        opt
      )}">
          <label class="form-check-label" for="${optId}">${escapeHtml(opt)}</label>
        </div>`;
    });
    html += `</div>`;
  } else {
    // Aperta
    html += `<textarea class="form-control" rows="3" name="${qid}" placeholder="Risposta..."></textarea>`;
  }

  li.innerHTML = html;
  quizList.appendChild(li);
}

quizBtn?.addEventListener("click", async () => {
  const subject = $("#quiz-subject").value;
  const topic = $("#quiz-topic").value.trim() || subject;
  const n = parseInt($("#quiz-n").value || "5", 10);
  const level = $("#quiz-level").value || "medium";

  try {
    const res = await fetch("/generate_exam", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subject, topic, n, level }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.error || "Errore generazione quiz.");
      return;
    }
    const data = await res.json();
    renderQuiz(data);
    showOutputSection(quizBox);
  } catch (e) {
    console.error(e);
    alert("Problema di rete durante la generazione del quiz.");
  }
});

submitQuizBtn?.addEventListener("click", async () => {
  if (!CURRENT_EXAM) return;

  // Raccogli risposte
  const answers = {};
  // radio + textarea
  quizList.querySelectorAll("[name]").forEach((el) => {
    const name = el.getAttribute("name");
    if (el.type === "radio") {
      if (el.checked) answers[name] = el.value;
    } else if (el.tagName === "TEXTAREA" || el.type === "text") {
      if (el.value.trim()) answers[name] = el.value.trim();
    }
  });
  // Eventuale traduzione Latino
  const translation = translationInput?.value?.trim();
  if (translation) {
    answers.translation = translation;
  }

  try {
    const res = await fetch("/grade_exam", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ exam: CURRENT_EXAM, answers }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      quizResult.innerHTML =
        `<div class="alert alert-danger">` +
        escapeHtml(err.error || "Errore correzione.") +
        `</div>`;
      return;
    }
    const result = await res.json();
    renderQuizResult(result);
  } catch (e) {
    console.error(e);
    quizResult.innerHTML =
      `<div class="alert alert-danger">Problema di rete durante la correzione.</div>`;
  }
});

function renderQuizResult(result) {
  // Proviamo a leggere campi comuni, e facciamo fallback al JSON
  const correct = result.correct_count ?? result.correct ?? null;
  const total = result.total ?? (CURRENT_EXAM?.questions?.length || null);
  const score = result.score ?? result.grade ?? null;
  const feedback = result.feedback ?? result.report ?? null;

  let html = `<div class="alert alert-info">`;
  if (correct !== null && total !== null) {
    html += `<div><strong>Punteggio:</strong> ${correct}/${total}</div>`;
  }
  if (score !== null) {
    html += `<div><strong>Voto/Score:</strong> ${escapeHtml(String(score))}</div>`;
  }
  if (feedback) {
    html += `<hr><pre class="mb-0" style="white-space:pre-wrap;">${escapeHtml(
      typeof feedback === "string" ? feedback : JSON.stringify(feedback, null, 2)
    )}</pre>`;
  } else {
    html += `<pre class="mb-0" style="white-space:pre-wrap;">${escapeHtml(
      JSON.stringify(result, null, 2)
    )}</pre>`;
  }
  html += `</div>`;
  quizResult.innerHTML = html;
}

/* ---------- PIANO LEZIONI ---------- */
const openPlanPanel = $("#open-plan-panel");
const closePlanPanel = $("#close-plan-panel");
const planBtn = $("#plan-btn");
const planTitle = $("#plan-title");
const planTable = $("#plan-table");
const pdfBtn = $("#pdf-btn");

let CURRENT_PLAN = null;

openPlanPanel?.addEventListener("click", () => {
  $("#plan-config")?.classList.remove("d-none");
  outputBox?.classList.remove("d-none");
});
closePlanPanel?.addEventListener("click", () => {
  $("#plan-config")?.classList.add("d-none");
});

planBtn?.addEventListener("click", async () => {
  const subject = $("#plan-subject").value.trim() || "Materia";
  const topic = $("#plan-topic").value.trim() || "Argomento";
  const grade = $("#plan-grade").value;
  const lesson_minutes = parseInt($("#plan-duration").value || "45", 10);
  const global_goals = $("#plan-goals").value.trim();

  try {
    const res = await fetch("/generate_plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        subject,
        topic,
        grade,
        lesson_minutes,
        global_goals,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.error || "Errore generazione piano.");
      return;
    }
    const plan = await res.json();
    CURRENT_PLAN = plan;
    renderPlan(plan);
    showOutputSection(planBox);
  } catch (e) {
    console.error(e);
    alert("Problema di rete durante la generazione del piano.");
  }
});

function renderPlan(plan) {
  planTitle.textContent = `${plan.subject} – ${plan.topic}`;
  planTable.innerHTML = "";

  // Header
  const thead = document.createElement("thead");
  thead.innerHTML = `
    <tr class="table-light">
      <th style="width: 60px;">#</th>
      <th>Titolo</th>
      <th>Obiettivi</th>
      <th>Attività</th>
      <th>Materiali</th>
    </tr>`;
  planTable.appendChild(thead);

  // Body
  const tbody = document.createElement("tbody");
  (plan.lessons || []).forEach((l, i) => {
    const tr = document.createElement("tr");
    const objectives = Array.isArray(l.objectives)
      ? l.objectives.join("\n")
      : (l.objectives || "");
    const activities = Array.isArray(l.activities)
      ? l.activities.join("\n")
      : (l.activities || "");
    const materials = Array.isArray(l.materials)
      ? l.materials.join("\n")
      : (l.materials || "");
    tr.innerHTML = `
      <td class="text-center">${i + 1}</td>
      <td>${escapeHtml(l.title || "")}</td>
      <td style="white-space:pre-wrap">${escapeHtml(objectives)}</td>
      <td style="white-space:pre-wrap">${escapeHtml(activities)}</td>
      <td style="white-space:pre-wrap">${escapeHtml(materials)}</td>
    `;
    tbody.appendChild(tr);
  });
  planTable.appendChild(tbody);
}

pdfBtn?.addEventListener("click", async () => {
  if (!CURRENT_PLAN) return;
  try {
    const res = await fetch("/plan_pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan: CURRENT_PLAN }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.error || "Errore generazione PDF.");
      return;
    }
    // Scarica il PDF
    const blob = await res.blob();
    const dispo = res.headers.get("Content-Disposition") || "";
    let filename = "piano.pdf";
    const m = dispo.match(/filename\*=UTF-8''([^;]+)|filename="?([^"]+)"?/i);
    if (m) filename = decodeURIComponent(m[1] || m[2]);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    console.error(e);
    alert("Problema di rete durante il download del PDF.");
  }
});

/* ---------- MAPPA CONCETTUALE (GoJS) ---------- */
const openConceptPanel = $("#open-concept-panel");
const closeConceptPanel = $("#close-concept-panel");
const conceptBtn = $("#concept-btn");
const conceptFitBtn = $("#concept-fit");
const conceptExportBtn = $("#concept-export");

let diagram = null;

// Inizializza quando serve
function ensureDiagram() {
  if (diagram) return diagram;
  const $go = go.GraphObject.make;
  diagram = $go(go.Diagram, "conceptDiagram", {
    "undoManager.isEnabled": true,
    layout: $go(go.ForceDirectedLayout, { defaultSpringLength: 80 }),
    initialContentAlignment: go.Spot.Center,
  });

  diagram.nodeTemplate = $go(
    go.Node,
    "Auto",
    $go(go.Shape, "RoundedRectangle", {
      fill: "whitesmoke",
      stroke: "#999",
      strokeWidth: 1.5,
    }),
    $go(
      go.TextBlock,
      {
        margin: 8,
        wrap: go.TextBlock.WrapFit,
        editable: false,
        font: "bold 12pt Inter, system-ui, sans-serif",
      },
      new go.Binding("text", "text")
    )
  );

  diagram.linkTemplate = $go(
    go.Link,
    { routing: go.Link.AvoidsNodes, corner: 6 },
    $go(go.Shape, { strokeWidth: 1.2 }),
    $go(go.Shape, { toArrow: "OpenTriangle" }),
    $go(go.TextBlock, { segmentOffset: new go.Point(0, -8) }, new go.Binding("text", "label"))
  );

  return diagram;
}

function renderConceptMap(payload) {
  ensureDiagram();
  const nda = payload.nodeDataArray || payload.nodes || [];
  // Link: chiave 'from' potrebbe essere aliasata; nel backend usi by_alias=True, quindi è 'from'
  const lda = payload.linkDataArray || payload.links || [];
  diagram.model = new go.GraphLinksModel(nda, lda);
  diagram.zoomToFit();
}

openConceptPanel?.addEventListener("click", () => {
  $("#concept-config")?.classList.remove("d-none");
  outputBox?.classList.remove("d-none");
});
closeConceptPanel?.addEventListener("click", () => {
  $("#concept-config")?.classList.add("d-none");
});

conceptBtn?.addEventListener("click", async () => {
  const subject = $("#concept-subject").value.trim();
  const topic = $("#concept-topic").value.trim();
  const max_nodes = parseInt($("#concept-nodes").value || "24", 10);
  const top_k = Math.min(12, Math.max(4, Math.floor(max_nodes / 2)));

  if (!topic) {
    alert("Inserisci l'argomento (titolo della mappa).");
    return;
  }

  try {
    const res = await fetch("/generate_concept_map", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subject, topic, max_nodes, top_k }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.error || "Errore generazione mappa.");
      return;
    }
    const data = await res.json();
    renderConceptMap(data);
    showOutputSection(conceptBox);
  } catch (e) {
    console.error(e);
    alert("Problema di rete durante la generazione della mappa.");
  }
});

conceptFitBtn?.addEventListener("click", () => {
  ensureDiagram();
  diagram.zoomToFit();
});

conceptExportBtn?.addEventListener("click", () => {
  ensureDiagram();
  const dataUrl = diagram.makeImageData({
    scale: 2,
    background: "white",
  });
  const a = document.createElement("a");
  a.href = dataUrl;
  a.download = "mappa_concettuale.png";
  document.body.appendChild(a);
  a.click();
  a.remove();
});

/* ---------- SLIDE (PPTX) ---------- */
const openSlidesPanel = $("#open-slides-panel");
const closeSlidesPanel = $("#close-slides-panel");
const slidesBtn = $("#slides-btn");

openSlidesPanel?.addEventListener("click", () => {
  $("#slides-config")?.classList.remove("d-none");
  outputBox?.classList.remove("d-none");
});
closeSlidesPanel?.addEventListener("click", () => {
  $("#slides-config")?.classList.add("d-none");
});

slidesBtn?.addEventListener("click", async () => {
  const subject = $("#slides-subject").value.trim();
  const topic = $("#slides-topic").value.trim();
  const n = parseInt($("#slides-n").value || "10", 10);

  if (!topic) {
    alert("Inserisci l'argomento.");
    return;
  }

  try {
    const res = await fetch("/generate_slides", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subject, topic, n_slides: n }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.error || "Errore durante la generazione.");
      return;
    }

    // Scarica PPTX
    const blob = await res.blob();
    const dispo = res.headers.get("Content-Disposition") || "";
    let filename = "slides.pptx";
    const m = dispo.match(/filename\*=UTF-8''([^;]+)|filename="?([^"]+)"?/i);
    if (m) filename = decodeURIComponent(m[1] || m[2]);

    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  } catch (e) {
    console.error(e);
    alert("Problema di rete durante la generazione delle slide.");
  }
});

/* ---------- RIASSUNTO ---------- */
const openSummaryPanel = document.getElementById("open-summary-panel");
const closeSummaryPanel = document.getElementById("close-summary-panel");
const summaryBtn = document.getElementById("summary-btn");
const summaryBox = document.getElementById("summary-box");
const summaryContent = document.getElementById("summary-content");

openSummaryPanel?.addEventListener("click", () => {
  document.getElementById("summary-config")?.classList.remove("d-none");
  document.getElementById("output-box")?.classList.remove("d-none");
});
closeSummaryPanel?.addEventListener("click", () => {
  document.getElementById("summary-config")?.classList.add("d-none");
});

function showSummary(markdown) {
  // visualizza semplicemente come testo preformattato;
  // se vuoi markdown ricco, puoi integrare una libreria md (marked.js)
  summaryContent.innerText = markdown;
  // mostra solo il box riassunto
  [document.getElementById("quiz-box"),
  document.getElementById("plan-box"),
  document.getElementById("concept-box")].forEach(el => el?.classList.add("d-none"));
  summaryBox?.classList.remove("d-none");
}

summaryBtn?.addEventListener("click", async () => {
  const topic = document.getElementById("summary-topic").value.trim();
  const length = document.getElementById("summary-length").value || "medium";
  const fileEl = document.getElementById("summary-file");
  const file = fileEl?.files?.[0];

  if (!topic && !file) {
    alert("Inserisci un argomento o allega un file.");
    return;
  }

  try {
    let res;
    if (file) {
      const fd = new FormData();
      fd.append("topic", topic);
      fd.append("length", length);
      fd.append("file", file);
      res = await fetch("/summarize", { method: "POST", body: fd });
    } else {
      res = await fetch("/summarize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, length })
      });
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.error || "Errore durante il riassunto.");
      return;
    }

    const data = await res.json(); // {topic, length, summary_md}
    showSummary(data.summary_md || "Nessun contenuto generato.");
  } catch (e) {
    console.error(e);
    alert("Problema di rete durante la generazione del riassunto.");
  }
});

