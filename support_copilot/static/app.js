"use strict";
const $ = (id) => document.getElementById(id);
function node(tag, text, cls) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (cls) element.className = cls;
  return element;
}
async function api(path, payload) {
  const response = await fetch(path, payload === undefined ? {} : {
    method: "POST", headers: {"Content-Type": "application/json", "X-Copilot-Request": "1"},
    body: JSON.stringify(payload)
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "The request could not be completed.");
  return body;
}
function errorAt(id, error) { $(id).replaceChildren(node("p", error.message, "error")); }
function sourceCard(source) {
  const card = node("div", undefined, "source");
  card.append(node("strong", `${source.source} · lines ${source.start_line}–${source.end_line}`),
    node("blockquote", source.quote ?? source.body), node("small", `Revision ${source.version.slice(0,12)}`, "caption"));
  return card;
}
function answerContents(area, result, withFeedback) {
  const review = result.status === "needs_review";
  area.append(node("span", review ? "Needs review" : result.status === "sources_only" ? "Source search" : "AI draft", "badge" + (review ? " review" : "")));
  area.append(node("p", result.answer, "answer-text"));
  const sources = result.status === "sources_only" ? result.sources : result.citations;
  if (result.status === "sources_only" && !sources.length) area.append(node("p", "No matching passages. Try different words or enable an AI draft for semantic retrieval.", "muted"));
  for (const source of sources) area.append(sourceCard(source));
  if (withFeedback && result.id) {
    const controls = node("div", undefined, "feedback");
    for (const [label, helpful] of [["Helpful", true], ["Needs improvement", false]]) {
      const button = node("button", label); button.type = "button";
      button.addEventListener("click", async () => {
        controls.querySelectorAll("button").forEach((b) => b.disabled = true);
        try {
          await api(`/api/feedback/${result.id}`, {helpful});
          controls.replaceChildren(node("span", "Feedback saved.", "caption"));
          await Promise.all([refreshRecent(), refreshQueue()]);
        } catch (error) {
          controls.append(node("span", error.message, "error"));
          controls.querySelectorAll("button").forEach((b) => b.disabled = false);
        }
      });
      controls.append(button);
    }
    area.append(controls);
  }
}
async function refreshDocuments() {
  $("status").textContent = "Loading from your database…";
  try {
    const chunks = await api("/api/documents");
    const groups = new Map();
    for (const chunk of chunks) {
      if (!groups.has(chunk.source)) groups.set(chunk.source, []);
      groups.get(chunk.source).push(chunk);
    }
    $("documents").replaceChildren();
    for (const [filename, parts] of groups) {
      const item = node("details");
      const title = parts[0].body.split("\n")[0].replace(/^#+\s*/, "").trim() || filename;
      item.append(node("summary", title));
      const content = node("div", undefined, "detail-body");
      content.append(node("p", `${filename} · ${parts.length} passage(s) · revision ${parts[0].version.slice(0,12)}`, "caption"));
      content.append(node("div", parts.map((part) => part.body).join(""), "document-text"));
      item.append(content); $("documents").append(item);
    }
    $("status").textContent = `${groups.size} documents · ${chunks.length} passages · loaded from OriginChainDB`;
    if (!chunks.length) $("documents").append(node("p", "No documents are stored in the active snapshot.", "muted"));
  } catch (error) { $("status").textContent = "Documentation unavailable"; errorAt("documents", error); }
}
async function refreshRecent() {
  try {
    const rows = await api("/api/recent"); $("recent").replaceChildren();
    if (!rows.length) $("recent").append(node("p", "No saved questions yet. AI drafts and unanswered questions will appear here.", "muted"));
    for (const row of rows) {
      const item = node("details"); item.append(node("summary", row.question));
      const content = node("div", undefined, "detail-body");
      content.append(node("p", new Date(row.created_ms).toLocaleString(), "caption"));
      answerContents(content, row, false); item.append(content); $("recent").append(item);
    }
  } catch (error) { errorAt("recent", error); }
}
async function refreshQueue() {
  try {
    const rows = await api("/api/queue"); $("queue").replaceChildren();
    if (!rows.length) $("queue").append(node("p", "Nothing needs review yet.", "muted"));
    for (const row of rows) {
      const item = node("div", undefined, "queue-item");
      item.append(node("p", row.question), node("small", row.feedback === "not_helpful" ? "Marked unhelpful" : "Insufficient verified evidence"));
      $("queue").append(item);
    }
  } catch (error) { errorAt("queue", error); }
}
async function refreshSettings() {
  $("settings").replaceChildren(); $("settings-status").textContent = "Checking the database…";
  try {
    const config = await api("/api/settings");
    const fields = {indexed_documents: "Indexed documents", stored_passages: "Passages in database", snapshot: "Active snapshot", namespace: "Workspace namespace", embedding_model: "Embedding model", answer_model: "Answer model", inference: "Inference setting", source_bytes: "Source text (bytes)", vector_payload_bytes: "Raw vector payload (bytes)"};
    for (const [key, label] of Object.entries(fields)) $("settings").append(node("dt", label), node("dd", String(config[key])));
    $("settings-status").textContent = `Database connected · checked ${new Date().toLocaleTimeString()}. Model names show configuration, not a model health check.`;
  } catch (error) { $("settings-status").textContent = "Connection check failed"; $("settings").append(node("dt", "Error"), node("dd", error.message, "error")); }
}
function showView() {
  const view = ["faq", "review", "settings"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "faq";
  for (const name of ["faq", "review", "settings"]) $(`${name}-view`).hidden = name !== view;
  document.querySelectorAll("nav a").forEach((link) => { if (link.hash === `#${view}`) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current"); });
  if (view === "faq") { refreshDocuments(); refreshRecent(); }
  if (view === "review") refreshQueue();
  if (view === "settings") refreshSettings();
}
$("generate").addEventListener("change", () => {
  $("submit").textContent = $("generate").checked ? "Draft answer" : "Search docs";
  $("search-hint").textContent = $("generate").checked ? "Hybrid retrieval + local AI · generation can take a minute or more" : "Keyword search · no AI generation";
});
$("ask-form").addEventListener("submit", async (event) => {
  event.preventDefault(); const generate = $("generate").checked;
  $("submit").disabled = true; $("generate").disabled = true;
  $("answer-area").replaceChildren(node("p", generate ? "Finding sources and drafting an answer…" : "Searching your documentation…", "muted"));
  try {
    const result = await api("/api/ask", {question: $("question").value, generate, mode: generate ? "hybrid" : "keyword"});
    const card = node("article", undefined, "panel"); answerContents(card, result, true);
    $("answer-area").replaceChildren(card); if (generate) await refreshRecent();
  } catch (error) { errorAt("answer-area", error); }
  finally { $("submit").disabled = false; $("generate").disabled = false; }
});
$("refresh-docs").addEventListener("click", refreshDocuments);
$("refresh-queue").addEventListener("click", refreshQueue);
$("refresh-settings").addEventListener("click", refreshSettings);
window.addEventListener("hashchange", showView);
showView();