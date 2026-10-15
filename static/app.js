const API_BASE = ""; // same origin

// ---- Session (Conversation Memory Agent keys off this) ----
let sessionId = localStorage.getItem("rag_session_id");
if (!sessionId) {
  sessionId = "sess-" + Math.random().toString(36).slice(2, 10);
  localStorage.setItem("rag_session_id", sessionId);
}

// pending clarification state
let pendingClarification = null; // { originalQuery }

const chatLog = document.getElementById("chatLog");
const queryInput = document.getElementById("queryInput");
const submitBtn = document.getElementById("submitBtn");
const micBtn = document.getElementById("micBtn");
const ttsToggle = document.getElementById("ttsToggle");
const fileInput = document.getElementById("fileInput");
const fileName = document.getElementById("fileName");
const ingestBtn = document.getElementById("ingestBtn");
const kbStatus = document.getElementById("kbStatus");
const dropZone = document.getElementById("dropZone");
const docList = document.getElementById("docList");
const confidenceValue = document.getElementById("confidenceValue");
const confidenceBarFill = document.getElementById("confidenceBarFill");
const sourcesList = document.getElementById("sourcesList");
const panelState = document.getElementById("panelState");
const analyticsSummary = document.getElementById("analyticsSummary");

// Milestone 4 / M4.1 dashboard elements
const openDashboardBtn = document.getElementById("openDashboardBtn");
const closeDashboardBtn = document.getElementById("closeDashboardBtn");
const analyticsModal = document.getElementById("analyticsModal");
const filterQueryType = document.getElementById("filterQueryType");
const filterConfidence = document.getElementById("filterConfidence");
const filterDays = document.getElementById("filterDays");
const filterDocument = document.getElementById("filterDocument");
const applyFiltersBtn = document.getElementById("applyFiltersBtn");
const dashSummaryGrid = document.getElementById("dashSummaryGrid");
const chartQueryType = document.getElementById("chartQueryType");
const chartConfidence = document.getElementById("chartConfidence");
const chartGaps = document.getElementById("chartGaps");
const recentTableBody = document.querySelector("#recentTable tbody");

let selectedFile = null;

// ---------------- Ingestion ----------------
function selectFile(file) {
  selectedFile = file || null;
  fileName.textContent = selectedFile ? selectedFile.name : "No file chosen";
}

fileInput.addEventListener("change", () => selectFile(fileInput.files[0]));

// ---- Drag & drop ----
["dragenter", "dragover"].forEach(evt =>
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.add("drag-over");
  })
);
["dragleave", "drop"].forEach(evt =>
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.remove("drag-over");
  })
);
dropZone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) {
    selectFile(file);
    uploadSelectedFile();
  }
});

ingestBtn.addEventListener("click", uploadSelectedFile);

function renderDocList(documents) {
  if (!documents || documents.length === 0) {
    docList.innerHTML = `<p class="empty-note">No documents indexed yet.</p>`;
    return;
  }
  docList.innerHTML = documents.map(d => `
    <div class="doc-item">
      <span class="doc-item-name">📄 ${escapeHtml(d.document_name)}</span>
      <span class="doc-item-meta">${d.chunks} chunks indexed</span>
      ${d.stored_filename ? `<a class="doc-item-view" href="/uploads/${encodeURIComponent(d.stored_filename)}" target="_blank" rel="noopener">View / Download</a>` : ""}
    </div>`).join("");
}

async function uploadSelectedFile() {
  if (!selectedFile) {
    kbStatus.textContent = "Please choose or drop a file first (PDF, DOCX, TXT, or CSV).";
    return;
  }
  ingestBtn.disabled = true;
  kbStatus.textContent = `Ingesting "${selectedFile.name}" — extracting, chunking, embedding…`;

  const form = new FormData();
  form.append("file", selectedFile);
  try {
    const res = await fetch(`${API_BASE}/api/upload`, { method: "POST", body: form });
    const data = await res.json();
    if (data.error) {
      kbStatus.textContent = `Upload failed: ${data.error}`;
    } else {
      kbStatus.textContent =
        `Indexed "${data.result.document_name}" — ${data.result.chunks_indexed} chunks. ` +
        `Knowledge base: ${data.kb_stats.total_documents} docs / ${data.kb_stats.total_chunks} chunks.`;
      addMessage("system", `📄 Document "${data.result.document_name}" ingested and indexed (${data.result.chunks_indexed} chunks).`);
    }
  } catch (e) {
    kbStatus.textContent = `Upload failed: ${e}`;
  } finally {
    ingestBtn.disabled = false;
    selectFile(null);
  }
  refreshAnalytics();
  refreshStatus();
}

// ---------------- Chat ----------------
function addMessage(role, text, meta) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.innerHTML = escapeHtml(text).replace(/\n/g, "<br>");
  if (meta) {
    const m = document.createElement("span");
    m.className = "meta";
    m.textContent = meta;
    div.appendChild(m);
  }
  chatLog.appendChild(div);
  chatLog.scrollTop = chatLog.scrollHeight;
  return div;
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

async function submitQuery() {
  const text = queryInput.value.trim();
  if (!text) return;
  queryInput.value = "";
  addMessage("user", text);
  panelState.textContent = "PROCESSING";
  panelState.classList.add("active");

  const form = new FormData();
  form.append("session_id", sessionId);

  if (pendingClarification) {
    form.append("query", pendingClarification.originalQuery);
    form.append("clarification_answer", text);
  } else {
    form.append("query", text);
  }

  try {
    const res = await fetch(`${API_BASE}/api/query`, { method: "POST", body: form });
    const data = await res.json();
    handleResponse(data);
  } catch (e) {
    addMessage("error", `Request failed: ${e}`);
  } finally {
    panelState.textContent = "IDLE";
    panelState.classList.remove("active");
  }
  refreshAnalytics();
}

function handleResponse(data) {
  if (data.status === "needs_clarification") {
    pendingClarification = { originalQuery: data.original_query };
    addMessage("clarify", `🤔 ${data.clarification_question}`, "Clarification needed — reply below.");
    updateTransparency({ confidence: 0, sources: [] });
    return;
  }

  pendingClarification = null;

  if (data.status === "error") {
    addMessage("error", `⚠️ ${data.message}`);
    updateTransparency({ confidence: 0, sources: [] });
    return;
  }

  // status === "answered" — show two separate answers
  const confPct = Math.round((data.confidence || 0) * 100);
  addMessage("assistant pdf-answer", `📄 From your document:\n${data.pdf_answer}`,
    `Query type: ${data.classification.query_type} · Confidence: ${confPct}%`);
  addMessage("assistant ai-answer", `🤖 From AI knowledge:\n${data.ai_answer}`);
  updateTransparency({ confidence: data.confidence, sources: data.sources });

  if (ttsToggle.checked) speak(data.pdf_answer);
}

function updateTransparency({ confidence, sources }) {
  const pct = Math.round((confidence || 0) * 100);
  confidenceValue.textContent = `${pct}%`;
  confidenceBarFill.style.width = `${pct}%`;
  confidenceBarFill.style.background =
    pct >= 60 ? "linear-gradient(90deg,#14b8a6,#22c55e)" :
    pct >= 30 ? "linear-gradient(90deg,#f59e0b,#fbbf24)" :
    "linear-gradient(90deg,#ef4444,#f87171)";

  if (!sources || sources.length === 0) {
    sourcesList.innerHTML = `<p class="empty-note">No retrieved chunks for this query.</p>`;
    return;
  }
  sourcesList.innerHTML = sources.map(s => `
    <div class="source-card">
      <span class="score">${(s.relevance_score * 100).toFixed(0)}%</span>
      <span class="doc-name">${escapeHtml(s.document_name)}</span>
      <div class="excerpt">chunk #${s.chunk_index} (${escapeHtml(s.chunk_id)}) — "${escapeHtml(s.excerpt)}…"</div>
    </div>
  `).join("");
}

submitBtn.addEventListener("click", submitQuery);
queryInput.addEventListener("keydown", (e) => { if (e.key === "Enter") submitQuery(); });

// ---------------- Voice input (Web Speech API - Milestone 3 / M3.3) ----------------
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognizer = null;
let isRecording = false;

if (SpeechRecognition) {
  recognizer = new SpeechRecognition();
  recognizer.continuous = false;
  recognizer.interimResults = false;
  recognizer.lang = "en-US";

  recognizer.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    queryInput.value = transcript;
  };
  recognizer.onerror = (event) => {
    addMessage("error", `Voice recognition error: ${event.error}`);
  };
  recognizer.onend = () => {
    isRecording = false;
    micBtn.classList.remove("recording");
  };
} else {
  micBtn.title = "Voice input not supported in this browser";
}

micBtn.addEventListener("click", () => {
  if (!recognizer) {
    addMessage("system", "This browser does not support the Web Speech API for voice input. Try Chrome or Edge.");
    return;
  }
  if (isRecording) {
    recognizer.stop();
    isRecording = false;
    micBtn.classList.remove("recording");
  } else {
    recognizer.start();
    isRecording = true;
    micBtn.classList.add("recording");
  }
});

// ---------------- Text-to-Speech (Milestone 3 / M3.3) ----------------
function speak(text) {
  if (!("speechSynthesis" in window) || !text) return;
  const synth = window.speechSynthesis;

  const doSpeak = () => {
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = "en-US";
    utter.rate = 1.0;
    utter.onerror = (e) => console.error("TTS error:", e.error);
    // Chrome bug: calling speak() in the same tick as cancel() can silently
    // drop the utterance. A short delay avoids it.
    setTimeout(() => synth.speak(utter), 80);
  };

  synth.cancel();     // stop any prior utterance
  synth.resume();     // Chrome sometimes leaves the engine "paused" after tab switches

  // On first use, Chrome loads voices asynchronously — if the list isn't
  // ready yet, wait for it once so the utterance doesn't get silently dropped.
  if (synth.getVoices().length === 0) {
    synth.addEventListener("voiceschanged", doSpeak, { once: true });
  } else {
    doSpeak();
  }
}

// ---------------- Status + Analytics polling ----------------
async function refreshStatus() {
  try {
    const res = await fetch(`${API_BASE}/api/status`);
    const data = await res.json();
    if (data.documents_indexed > 0) {
      kbStatus.textContent = `Knowledge base: ${data.documents_indexed} docs / ${data.chunks_indexed} chunks indexed.` +
        (data.llm_key_configured ? ` LLM: ${data.llm_model}.` : " ⚠ No LLM key set (extractive mode) — see backend/config.py.");
    } else {
      kbStatus.textContent = data.llm_key_configured
        ? "No document uploaded yet. Upload a file to build your knowledge base."
        : "No document uploaded yet. ⚠ No LLM key set — see backend/config.py to enable AI-generated answers.";
    }
    renderDocList(data.documents || null);
  } catch (e) { /* backend not up yet */ }
}

async function refreshAnalytics() {
  try {
    const res = await fetch(`${API_BASE}/api/analytics`);
    const d = await res.json();
    if (!d.total_queries) {
      analyticsSummary.innerHTML = `<p class="empty-note">No queries logged yet.</p>`;
      return;
    }
    analyticsSummary.innerHTML = `
      <div class="row"><span>Total queries</span><span>${d.total_queries}</span></div>
      <div class="row"><span>Avg. confidence</span><span>${Math.round(d.avg_confidence * 100)}%</span></div>
      <div class="row"><span>Low-confidence</span><span>${d.low_confidence_count}</span></div>
      <div class="row"><span>Unanswered</span><span>${d.unanswered_count}</span></div>
      <div class="row"><span>Clarifications</span><span>${d.clarification_count}</span></div>
    `;
  } catch (e) { /* ignore */ }
}

// ---------------- Milestone 4 / M4.1: Analytics Dashboard ----------------
function renderBarChart(container, items, labelKey, countKey, maxItems = 10) {
  if (!items || items.length === 0) {
    container.innerHTML = `<p class="empty-note">No data for this filter.</p>`;
    return;
  }
  const sorted = [...items].sort((a, b) => b[countKey] - a[countKey]).slice(0, maxItems);
  const max = Math.max(...sorted.map(i => i[countKey]), 1);
  container.innerHTML = sorted.map(i => `
    <div class="bar-row">
      <span class="bar-label">${escapeHtml(String(i[labelKey]))}</span>
      <span class="bar-track"><span class="bar-fill" style="width:${Math.round((i[countKey] / max) * 100)}%"></span></span>
      <span class="bar-count">${i[countKey]}</span>
    </div>`).join("");
}

function statusPillFor(r) {
  if (r.unanswered) return `<span class="status-pill bad">unanswered</span>`;
  if (r.low_confidence) return `<span class="status-pill low">low-conf</span>`;
  return `<span class="status-pill ok">answered</span>`;
}

async function populateFilterOptions() {
  try {
    const d = await (await fetch(`${API_BASE}/api/analytics`)).json();
    const types = d.available_query_types || [];
    const docs = d.available_documents || [];
    filterQueryType.innerHTML = `<option value="all">All</option>` +
      types.map(t => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`).join("");
    filterDocument.innerHTML = `<option value="all">All</option>` +
      docs.map(doc => `<option value="${escapeHtml(doc)}">${escapeHtml(doc)}</option>`).join("");
  } catch (e) { /* ignore */ }
}

async function loadDashboard() {
  const params = new URLSearchParams();
  if (filterQueryType.value !== "all") params.set("query_type", filterQueryType.value);
  if (filterConfidence.value !== "all") params.set("confidence_level", filterConfidence.value);
  if (filterDays.value) params.set("days", filterDays.value);
  if (filterDocument.value !== "all") params.set("document", filterDocument.value);

  try {
    const [stats, recentData] = await Promise.all([
      fetch(`${API_BASE}/api/analytics?${params}`).then(r => r.json()),
      fetch(`${API_BASE}/api/analytics/recent?limit=20&${params}`).then(r => r.json()),
    ]);

    dashSummaryGrid.innerHTML = `
      <div class="dash-stat"><div class="value">${stats.total_queries}</div><div class="label">Total queries</div></div>
      <div class="dash-stat"><div class="value">${Math.round((stats.avg_confidence || 0) * 100)}%</div><div class="label">Avg confidence</div></div>
      <div class="dash-stat"><div class="value">${stats.low_confidence_count}</div><div class="label">Low confidence</div></div>
      <div class="dash-stat"><div class="value">${stats.unanswered_count}</div><div class="label">Unanswered</div></div>
      <div class="dash-stat"><div class="value">${stats.clarification_count}</div><div class="label">Clarifications</div></div>
    `;

    const typeItems = Object.entries(stats.query_type_breakdown || {}).map(([k, v]) => ({ label: k, count: v }));
    renderBarChart(chartQueryType, typeItems, "label", "count");

    const cb = stats.confidence_breakdown || { high: 0, medium: 0, low: 0 };
    renderBarChart(chartConfidence, [
      { label: "High (≥60%)", count: cb.high },
      { label: "Medium", count: cb.medium },
      { label: "Low (<35%)", count: cb.low },
    ], "label", "count");

    renderBarChart(chartGaps, (stats.knowledge_gaps || []).map(g => ({ label: g.theme, count: g.occurrences })), "label", "count");

    const recent = recentData.recent || [];
    if (recent.length === 0) {
      recentTableBody.innerHTML = `<tr><td colspan="5" class="empty-note">No queries match this filter.</td></tr>`;
    } else {
      recentTableBody.innerHTML = recent.map(r => `
        <tr>
          <td>${new Date(r.timestamp).toLocaleString()}</td>
          <td class="q-cell" title="${escapeHtml(r.query)}">${escapeHtml(r.query)}</td>
          <td>${escapeHtml(r.query_type)}</td>
          <td>${Math.round((r.confidence || 0) * 100)}%</td>
          <td>${statusPillFor(r)}</td>
        </tr>`).join("");
    }
  } catch (e) {
    dashSummaryGrid.innerHTML = `<p class="empty-note">Failed to load analytics: ${e}</p>`;
  }
}

openDashboardBtn.addEventListener("click", async () => {
  analyticsModal.hidden = false;
  await populateFilterOptions();
  loadDashboard();
});
closeDashboardBtn.addEventListener("click", () => { analyticsModal.hidden = true; });
analyticsModal.addEventListener("click", (e) => { if (e.target === analyticsModal) analyticsModal.hidden = true; });
applyFiltersBtn.addEventListener("click", loadDashboard);

refreshStatus();
refreshAnalytics();
setInterval(refreshStatus, 15000);