/* ====================== main.js ====================== */
document.addEventListener('DOMContentLoaded', () => {
  /* --------- cache DOM --------- */
  const planPanel = document.getElementById('plan-config');
  const conceptPanel = document.getElementById('concept-config');

  const outBox = document.getElementById('output-box');

  const planBox = document.getElementById('plan-box');
  const planTbl = document.getElementById('plan-table');

  const quizBox = document.getElementById('quiz-box');
  const quizList = document.getElementById('quiz-list');
  const btnSubmitQuiz = document.getElementById('submit-quiz');
  const quizResult = document.getElementById('quiz-result');

  const conceptBox = document.getElementById('concept-box');
  const btnConceptFit = document.getElementById('concept-fit');
  const btnConceptExport = document.getElementById('concept-export');

  let currentPlan = null;
  let currentQuiz = null;
  let currentAns  = {};
  let conceptDiagram = null;   // GoJS Diagram instance

  /* --------- utils --------- */
  const showOut  = () => outBox.classList.remove('d-none');
  const hideAllOutputs = () => {
    quizBox.classList.add('d-none');
    planBox.classList.add('d-none');
    conceptBox.classList.add('d-none');
  };
  const addChat  = (who, msg) => {
    const box = document.getElementById('chat-box');
    box.insertAdjacentHTML('beforeend', `<div class="mb-2"><strong>${who}:</strong> ${msg}</div>`);
    box.scrollTop = box.scrollHeight;
  };

  /* --------- open/close panels --------- */
  document.getElementById('open-plan-panel').onclick = () => {
    const src = document.getElementById('quiz-subject');
    const dest = document.getElementById('plan-subject');
    if (src && dest) dest.value = src.value;
    planPanel.classList.remove('d-none');
  };
  document.getElementById('close-plan-panel').onclick = () => planPanel.classList.add('d-none');

  document.getElementById('open-concept-panel').onclick = () => {
    const s = document.getElementById('quiz-subject')?.value || '';
    const t = document.getElementById('quiz-topic')?.value || '';
    document.getElementById('concept-subject').value = s;
    document.getElementById('concept-topic').value = t;
    conceptPanel.classList.remove('d-none');
  };
  document.getElementById('close-concept-panel').onclick = () => conceptPanel.classList.add('d-none');

  /* --------- chat to backend --------- */
  window.sendMessage = async () => {
    const inp = document.getElementById('user-input');
    const msg = inp.value.trim();
    if (!msg) return;

    addChat('👤 Tu', msg);
    inp.value = '';

    try {
      const data = await fetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: msg })
      }).then(r => r.json());

      renderAssistant(data);
    } catch {
      addChat('🤖 Assistant', '⚠️ Errore di connessione al server.');
    }
  };

  function renderAssistant(data) {
    if (data.answer) {
      addChat('🤖 Assistant', data.answer);
      return;
    }
    if (data.concept_map) {
      renderConceptMap(data.concept_map);
      addChat('🤖 Assistant', 'Ecco la mappa concettuale.');
      return;
    }
    if (data.exam) {
      currentQuiz = data.exam;
      currentAns = {};
      renderQuiz(currentQuiz);
      addChat('🤖 Assistant', 'Ecco un quiz per te!');
      showOut();
      return;
    }
    if (data.error) {
      addChat('🤖 Assistant', `⚠️ ${data.error}`);
    } else {
      addChat('🤖 Assistant', 'Non ho capito, puoi riformulare?');
    }
  }

  /* ================= QUIZ ================= */
  document.getElementById('quiz-btn').onclick = async () => {
    const subject = document.getElementById('quiz-subject').value;
    const topic   = document.getElementById('quiz-topic').value.trim() || subject;
    const n       = +document.getElementById('quiz-n').value || 5;
    const level   = document.getElementById('quiz-level').value;

    const quiz = await fetch('/generate_exam', {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({ subject, topic, n, level })
    }).then(r => r.json());

    currentQuiz = quiz;
    currentAns  = {};
    renderQuiz(quiz);
    addChat('🤖 Assistant', `Ecco il quiz su <strong>${topic}</strong>. Compila e premi <b>Invia risposte</b>.`);
    showOut();
  };

  function renderQuiz(quiz) {
    hideAllOutputs();
    quizResult.innerHTML = '';
    quizList.innerHTML = (quiz.questions || []).map(q =>
      q.qtype === 'mcq' ? renderMCQ(q) : renderOpen(q)
    ).join('');
    btnSubmitQuiz.classList.remove('d-none');
    quizBox.classList.remove('d-none');
    showOut();
  }

  const renderMCQ = q => `
    <li class="list-group-item border-0" data-qid="${q.id}">
      <p class="fw-semibold mb-2">${q.text}</p>
      ${q.options.map(o => `
        <div class="form-check">
          <input class="form-check-input" type="radio" name="${q.id}" value="${o.id}">
          <label class="form-check-label">${o.text}</label>
        </div>`).join('')}
    </li>`;

  const renderOpen = q => `
    <li class="list-group-item border-0" data-qid="${q.id}">
      <p class="fw-semibold mb-2">${q.text}</p>
      <textarea class="form-control" name="${q.id}" rows="3"></textarea>
    </li>`;

  btnSubmitQuiz.onclick = async () => {
    currentAns = {};
    currentQuiz.questions.forEach(q => {
      if (q.qtype === 'mcq') {
        const sel = document.querySelector(`input[name="${q.id}"]:checked`);
        currentAns[q.id] = sel ? sel.value : '';
      } else {
        const ta  = document.querySelector(`textarea[name="${q.id}"]`);
        currentAns[q.id] = ta ? ta.value.trim() : '';
      }
    });

    const res = await fetch('/grade_exam', {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({ exam: currentQuiz, answers: currentAns })
    }).then(r => r.json());

    showQuizResult(res);
  };

  function showQuizResult(res) {
    quizResult.innerHTML =
      `<div class="alert alert-info">Punteggio: <strong>${res.score}/${res.max}</strong></div>`;

    document.querySelectorAll('#quiz-list li .quiz-feedback').forEach(el => el.remove());

    res.details.forEach(d => {
      const li = document.querySelector(`li[data-qid="${d.qid}"]`);
      if (!li) return;

      const ok = d.correct;
      const icon = ok ? '✅' : '❌';
      const cls = ok ? 'text-success' : 'text-danger';
      const html = ok
        ? `<div class="quiz-feedback ${cls} mt-2">${icon} Risposta corretta</div>`
        : `<div class="quiz-feedback ${cls} mt-2">
             ${icon} Risposta errata<br>
             <em>Corretta:</em> ${d.correct_text}<br>
             <small>${d.explanation}</small>
           </div>`;
      li.insertAdjacentHTML('beforeend', html);
    });
  }

  /* ================= PIANO LEZIONI ================= */
  document.getElementById('plan-btn').onclick = async () => {
    const subject        = document.getElementById('plan-subject').value.trim();
    const topic          = document.getElementById('plan-topic').value.trim();
    const grade          = document.getElementById('plan-grade').value;
    const lesson_minutes = +document.getElementById('plan-duration').value;
    const global_goals   = document.getElementById('plan-goals').value.trim();

    if (!subject || !topic) { alert('Compila almeno materia e argomento'); return; }

    const plan = await fetch('/generate_plan', {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({ subject, topic, grade, lesson_minutes, global_goals })
    }).then(r => r.json());

    renderPlan(plan);
    planPanel.classList.add('d-none');
  };

  function renderPlan(plan) {
    hideAllOutputs();
    currentPlan = plan;
    document.getElementById('plan-title').textContent = `Piano • ${plan.subject} • ${plan.topic}`;
    planTbl.innerHTML =
      `<thead class="table-light"><tr><th>#</th><th>Titolo</th><th>Obiettivi</th><th>Attività</th><th>Materiali</th></tr></thead><tbody></tbody>`;
    const tbody = planTbl.querySelector('tbody');
    (plan.lessons || []).forEach((l, i) => {
      tbody.insertAdjacentHTML('beforeend',
        `<tr><td>${i + 1}</td><td>${l.title}</td><td>${(l.objectives || []).join('<br>')}</td><td>${(l.activities || []).join('<br>')}</td><td>${(l.materials || []).join('<br>')}</td></tr>`);
    });
    planBox.classList.remove('d-none');
    showOut();
  }

  document.getElementById('pdf-btn').onclick = async () => {
    if (!currentPlan) return;
    const blob = await fetch('/plan_pdf', {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({ plan: currentPlan })
    }).then(r => r.blob());
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'piano.pdf'; a.click();
    URL.revokeObjectURL(url);
  };

  /* ================= CONCEPT MAP ================= */
  // inizializza diagram al primo uso
  function ensureConceptDiagram() {
    if (conceptDiagram) return;

    const $ = go.GraphObject.make;
    conceptDiagram = $(go.Diagram, "conceptDiagram", {
      layout: $(go.TreeLayout, {
        angle: 90,                 // top -> down
        layerSpacing: 40,
        nodeSpacing: 30
      }),
      "toolManager.mouseWheelBehavior": go.ToolManager.WheelZoom,
      allowCopy: false,
      allowDelete: false
    });

    // Link: ortogonali con freccia
    conceptDiagram.linkTemplate =
      $(go.Link,
        { routing: go.Link.Orthogonal, corner: 6, selectable: false },
        $(go.Shape, { strokeWidth: 1.5 }),
        $(go.Shape, { toArrow: "Standard", scale: 1 })
      );

    // Node template generico
    conceptDiagram.nodeTemplate =
      $(go.Node, "Auto",
        {
          selectionAdorned: true,
          cursor: "pointer",
          fromSpot: go.Spot.Bottom, toSpot: go.Spot.Top
        },
        $(go.Shape, "RoundedRectangle",
          new go.Binding("fill", "key", k => k === "root" ? "#E8F1FF" : "white"),
          { stroke: "#CBD5E1", strokeWidth: 1 }
        ),
        $(go.Panel, "Horizontal",
          { padding: 8 },
          // expander (nascosto se foglia)
          $("TreeExpanderButton",
            {
              margin: new go.Margin(0, 6, 0, 0)
            },
            new go.Binding("visible", "isTreeLeaf", l => !l).ofObject()
          ),
          $(go.TextBlock,
            {
              wrap: go.TextBlock.WrapFit,
              maxSize: new go.Size(220, NaN),
              editable: false,
              stroke: "#111827"
            },
            new go.Binding("font", "key", k => k === "root" ? "bold 14px Inter, system-ui, -apple-system" : "13px Inter, system-ui, -apple-system"),
            new go.Binding("text", "text")
          )
        )
      );
  }

  // genera via backend
  document.getElementById('concept-btn').onclick = async () => {
    const subject = document.getElementById('concept-subject').value.trim();
    const topic   = document.getElementById('concept-topic').value.trim();
    const max_nodes = +document.getElementById('concept-nodes').value || 24;

    if (!topic) { alert('Inserisci l\'argomento della mappa'); return; }

    const data = await fetch('/generate_concept_map', {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({ subject, topic, max_nodes })
    }).then(r => r.json());

    if (data.error) {
      addChat('🤖 Assistant', '⚠️ Errore nella generazione della mappa.');
      return;
    }

    renderConceptMap(data);
    conceptPanel.classList.add('d-none');
    addChat('🤖 Assistant', `Ho creato la mappa concettuale su <strong>${topic}</strong>.`);
  };

  function renderConceptMap(cm) {
    ensureConceptDiagram();
    hideAllOutputs();
    conceptDiagram.model = new go.GraphLinksModel(cm.nodeDataArray, cm.linkDataArray);
    conceptDiagram.zoomToFit();
    conceptBox.classList.remove('d-none');
    showOut();
  }

  // toolbar: fit & export
  btnConceptFit.onclick = () => conceptDiagram && conceptDiagram.zoomToFit();
  btnConceptExport.onclick = () => {
    if (!conceptDiagram) return;
    const dataUrl = conceptDiagram.makeImageData({ scale: 1, background: "white" });
    const a = document.createElement('a');
    a.href = dataUrl; a.download = 'mappa_concettuale.png'; a.click();
  };
});
