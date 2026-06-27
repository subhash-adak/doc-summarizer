"use strict";

const state = {
  files: [],
  selected: new Set(),
  results: [],
  isStreaming: false,
  downloadUrls: { csv: "", pdf: "" },
};

const $ = (selector) => document.querySelector(selector);

document.addEventListener("DOMContentLoaded", () => {
  if ($("#fileList")) {
    loadFiles();
    setDownloadButtons(false);
  }
});

async function loadFiles() {
  const list = $("#fileList");
  list.innerHTML = '<div class="loading-state"><div class="spinner"></div><span>Loading documents...</span></div>';
  state.selected.clear();
  updateSummarizeBtn();
  updateSelectedCount();

  if ($("#searchInput")) {
    $("#searchInput").value = "";
  }

  try {
    const response = await fetch("/api/documents/");
    if (!response.ok) {
      if (response.status === 401) {
        window.location.href = "/";
        return;
      }
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    state.files = data.files;
    renderFileList(state.files);
  } catch (error) {
    list.innerHTML = `<div class="loading-state" style="color:var(--c-error)">Failed to load files: ${escapeHtml(error.message)}</div>`;
  }
}

function renderFileList(files) {
  const list = $("#fileList");

  if (!files.length) {
    list.innerHTML = '<div class="loading-state">No supported documents found.</div>';
    updateSelectAllCheckboxState([]);
    return;
  }

  list.innerHTML = files.map((file) => {
    const ext = getExtension(file.name);
    const sizeLabel = file.size_kb ? `${file.size_kb} KB` : "-";
    const checked = state.selected.has(file.id) ? "checked" : "";
    const selectedClass = state.selected.has(file.id) ? "selected" : "";

    return `
      <div class="file-item ${selectedClass}" id="item-${file.id}" onclick="toggleSelect('${file.id}')">
        <input type="checkbox" id="chk-${file.id}" ${checked} onclick="event.stopPropagation(); toggleSelect('${file.id}')" />
        <span class="file-icon file-icon--${ext}">${ext.toUpperCase()}</span>
        <div class="file-info">
          <div class="file-name" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</div>
          <div class="file-meta">${escapeHtml(sizeLabel)}</div>
        </div>
      </div>`;
  }).join("");

  updateSelectAllCheckboxState(files);
}

const MAX_SELECTION = 10;

function toggleSelect(fileId) {
  if (state.isStreaming) {
    return;
  }

  const isSelected = state.selected.has(fileId);
  if (!isSelected && state.selected.size >= MAX_SELECTION) {
    alert(`Maximum selection limit of ${MAX_SELECTION} documents per batch reached. Please summarize your currently selected files first.`);
    return;
  }

  if (isSelected) {
    state.selected.delete(fileId);
  } else {
    state.selected.add(fileId);
  }

  const item = $(`#item-${fileId}`);
  const checkbox = $(`#chk-${fileId}`);
  const nowSelected = state.selected.has(fileId);

  if (item) {
    item.classList.toggle("selected", nowSelected);
  }

  if (checkbox) {
    checkbox.checked = nowSelected;
  }

  updateSummarizeBtn();

  const query = $("#searchInput") ? $("#searchInput").value.toLowerCase().trim() : "";
  const visible = state.files.filter((file) => file.name.toLowerCase().includes(query));
  updateSelectAllCheckboxState(visible);
}

function filterFiles() {
  const query = $("#searchInput") ? $("#searchInput").value.toLowerCase().trim() : "";
  const filtered = state.files.filter((file) => file.name.toLowerCase().includes(query));
  renderFileList(filtered);
}

function toggleSelectAll(checked) {
  if (state.isStreaming) {
    return;
  }

  const query = $("#searchInput") ? $("#searchInput").value.toLowerCase().trim() : "";
  const visible = state.files.filter((file) => file.name.toLowerCase().includes(query));

  if (checked) {
    let added = 0;
    const remaining = MAX_SELECTION - state.selected.size;
    
    for (const file of visible) {
      if (!state.selected.has(file.id)) {
        if (added < remaining) {
          state.selected.add(file.id);
          added++;
        } else {
          break;
        }
      }
    }
    
    if (added === 0 && remaining <= 0) {
      alert(`Maximum selection limit of ${MAX_SELECTION} documents reached.`);
      const checkbox = $("#selectAllChk");
      if (checkbox) checkbox.checked = false;
      return;
    }
    
    // Rerender the file list to show selections correctly
    renderFileList(visible);
  } else {
    visible.forEach((file) => {
      state.selected.delete(file.id);
      
      const item = $(`#item-${file.id}`);
      const checkbox = $(`#chk-${file.id}`);
      if (item) item.classList.remove("selected");
      if (checkbox) checkbox.checked = false;
    });
  }

  updateSummarizeBtn();
}

function updateSelectAllCheckboxState(visibleFiles) {
  const checkbox = $("#selectAllChk");
  if (!checkbox) {
    return;
  }

  if (visibleFiles.length === 0) {
    checkbox.checked = false;
    checkbox.disabled = true;
    return;
  }

  checkbox.disabled = state.isStreaming;
  checkbox.checked = visibleFiles.every((file) => state.selected.has(file.id));
}

function updateSummarizeBtn() {
  const button = $("#summarizeBtn");
  if (!button) {
    return;
  }

  const count = state.selected.size;
  const disabled = count === 0 || state.isStreaming;
  button.disabled = disabled;

  if (state.isStreaming) {
    button.textContent = `Summarizing ${count} document${count === 1 ? "" : "s"}...`;
  } else {
    button.textContent = count > 0 ? `Summarize ${count} document${count === 1 ? "" : "s"}` : "Summarize selected";
  }

  updateSelectedCount();
}

function updateSelectedCount() {
  const count = $("#selectedCount");
  if (count) {
    count.textContent = `${state.selected.size} selected`;
  }
}

function setSelectionControlsDisabled(disabled) {
  const refreshBtn = $("#refreshBtn");
  const searchInput = $("#searchInput");
  const selectAll = $("#selectAllChk");

  if (refreshBtn) {
    refreshBtn.disabled = disabled;
  }
  if (searchInput) {
    searchInput.disabled = disabled;
  }
  if (selectAll) {
    selectAll.disabled = disabled;
  }
}

async function summarizeDocs() {
  if (!state.selected.size || state.isStreaming) {
    return;
  }

  state.isStreaming = true;
  state.results = [];
  state.downloadUrls = { csv: "", pdf: "" };
  updateSummarizeBtn();
  setSelectionControlsDisabled(true);
  setDownloadButtons(false);
  renderStreamShell(state.selected.size);

  const fileIds = Array.from(state.selected);

  try {
    const response = await fetch("/api/documents/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_ids: fileIds }),
    });

    if (!response.ok) {
      if (response.status === 401) {
        window.location.href = "/";
        return;
      }
      const errorBody = await response.text();
      throw new Error(errorBody || `HTTP ${response.status}`);
    }

    if (!response.body) {
      throw new Error("Streaming is not available in this browser.");
    }

    await consumeEventStream(response.body);
  } catch (error) {
    handleStreamError(error.message);
  } finally {
    state.isStreaming = false;
    updateSummarizeBtn();
    setSelectionControlsDisabled(false);
    updateSelectAllCheckboxState(state.files);
  }
}

async function consumeEventStream(body) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done }).replace(/\r/g, "");

    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const rawEvent = buffer.slice(0, boundary).trim();
      buffer = buffer.slice(boundary + 2);

      if (rawEvent) {
        const parsed = parseSseEvent(rawEvent);
        handleStreamEvent(parsed.event, parsed.data);
      }

      boundary = buffer.indexOf("\n\n");
    }

    if (done) {
      break;
    }
  }
}

function parseSseEvent(rawEvent) {
  let event = "message";
  const dataLines = [];

  rawEvent.split("\n").forEach((line) => {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  });

  const data = dataLines.length ? JSON.parse(dataLines.join("\n")) : null;
  return { event, data };
}

function handleStreamEvent(eventName, payload) {
  switch (eventName) {
    case "progress":
      updateProgress(payload);
      break;
    case "summary":
      appendSummary(payload);
      break;
    case "complete":
      finishSummary(payload);
      break;
    case "error":
      throw new Error(payload && payload.message ? payload.message : "Streaming failed.");
    default:
      break;
  }
}

function renderStreamShell(total) {
  const body = $("#resultsBody");
  if (!body) {
    return;
  }

  body.innerHTML = `
    <div class="stream-layout">
      <section class="live-progress-card">
        <div class="live-progress-topline">
          <div>
            <p class="live-progress-kicker">Live Processing</p>
            <h3 class="live-progress-title" id="streamTitle">Preparing summaries...</h3>
          </div>
          <span class="status-badge status-badge--processing" id="streamRunBadge">running</span>
        </div>

        <div class="live-progress-grid">
          <div class="live-progress-item">
            <span class="live-progress-label">Current File</span>
            <strong id="streamCurrentFile">Waiting for first document...</strong>
          </div>
          <div class="live-progress-item">
            <span class="live-progress-label">Stage</span>
            <strong id="streamStage">Connecting...</strong>
          </div>
          <div class="live-progress-item">
            <span class="live-progress-label">Progress</span>
            <strong id="streamCount">0 / ${total}</strong>
          </div>
          <div class="live-progress-item">
            <span class="live-progress-label">Completion</span>
            <strong id="streamPercent">0%</strong>
          </div>
        </div>

        <div class="progress-bar-track progress-bar-track--wide">
          <div class="progress-bar-fill" id="streamProgressBar" style="width:0%"></div>
        </div>

        <p class="live-progress-note" id="streamNote">The report downloads will unlock automatically after all files finish.</p>
      </section>

      <div class="table-responsive" style="margin-top: 10px;">
        <table class="summary-table">
          <thead>
            <tr>
              <th>Document</th>
              <th>Details</th>
              <th>Status</th>
              <th>AI Summary (5-10 sentences)</th>
              <th>Drive Link</th>
            </tr>
          </thead>
          <tbody id="streamSummaryTableBody">
            <tr id="streamTablePlaceholder">
              <td colspan="5" style="text-align: center; color: var(--c-text-3); padding: 30px;">
                Processing has started. Summaries will appear in this table as they finish.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>`;
}

function updateProgress(payload) {
  const total = payload.total || 1;
  const completed = payload.completed || 0;
  const stageStep = payload.stage_step || 0;
  const stageTotal = payload.stage_total || 1;
  const percentage = Math.min(99, Math.round(((completed + (stageStep / stageTotal)) / total) * 100));

  setText("#streamCurrentFile", payload.filename || "Waiting...");
  setText("#streamStage", payload.stage || "Processing...");
  setText("#streamCount", `${completed} / ${total}`);
  setText("#streamPercent", `${percentage}%`);
  setText("#streamNote", `${payload.stage || "Processing"} ${payload.filename || "document"}...`);
  setProgressWidth(percentage);
}

function appendSummary(payload) {
  const result = payload.result;
  if (!result) {
    return;
  }

  state.results.push(result);

  const placeholder = $("#streamTablePlaceholder");
  if (placeholder) {
    placeholder.remove();
  }

  const tbody = $("#streamSummaryTableBody");
  if (!tbody) {
    return;
  }

  const ext = getExtension(result.file.name);
  const statusClass = `status-badge--${result.status}`;
  const metaParts = [
    result.file.size_kb ? `${result.file.size_kb} KB` : null,
    result.char_count ? `${Number(result.char_count).toLocaleString()} chars` : null,
    result.chunk_count > 1 ? `${result.chunk_count} chunks` : null,
    result.processing_time_ms ? `${result.processing_time_ms} ms` : null,
  ].filter(Boolean).join(" · ");

  const driveLink = result.file.web_view_link
    ? `<a class="summary-drive-link" href="${result.file.web_view_link}" target="_blank" rel="noopener">↗ Open</a>`
    : "—";

  const content = result.summary
    ? `<p class="summary-text-cell">${escapeHtml(result.summary)}</p>`
    : result.error_message
    ? `<div class="summary-error-cell">${escapeHtml(result.error_message)}</div>`
    : `<span style="color:var(--c-text-3)">No content.</span>`;

  const newRow = `
    <tr>
      <td>
        <div class="table-file-info">
          <span class="file-icon file-icon--small file-icon--${ext}">${ext.toUpperCase()}</span>
          <div class="table-file-name" title="${escapeHtml(result.file.name)}">${escapeHtml(result.file.name)}</div>
        </div>
      </td>
      <td class="font-mono text-muted">${metaParts || "—"}</td>
      <td><span class="status-badge ${statusClass}">${result.status}</span></td>
      <td>${content}</td>
      <td>${driveLink}</td>
    </tr>`;

  tbody.insertAdjacentHTML("beforeend", newRow);

  const total = payload.total || state.results.length;
  const completed = payload.completed || state.results.length;
  const percentage = Math.min(99, Math.round((completed / total) * 100));

  setText("#streamCount", `${completed} / ${total}`);
  setText("#streamPercent", `${percentage}%`);
  setText("#streamNote", `${result.file.name} finished with status ${result.status}.`);
  setProgressWidth(percentage);
}

function finishSummary(payload) {
  if (Array.isArray(payload.results)) {
    state.results = payload.results;
  }

  state.downloadUrls = {
    csv: payload.csv || "",
    pdf: payload.pdf || "",
  };

  setDownloadButtons(true);
  
  // Hide the bulky progress dashboard card
  const progressCard = $(".live-progress-card");
  if (progressCard) {
    progressCard.style.display = "none";
  }

  // Prepend a clean, compact green success banner above the table
  const streamLayout = $(".stream-layout");
  if (streamLayout && !$("#successBanner")) {
    streamLayout.insertAdjacentHTML("afterbegin", `
      <div id="successBanner" class="demo-banner" style="background-color: rgba(52, 201, 138, 0.08); border: 1px solid rgba(52, 201, 138, 0.2); color: var(--c-success); padding: 12px 24px; border-radius: var(--r-md); margin-bottom: 16px; font-weight: 500; font-size: 13.5px; display: flex; justify-content: center; align-items: center; gap: 8px;">
        <span>✨ <strong>Batch Complete:</strong> Processed ${state.results.length} document${state.results.length === 1 ? "" : "s"} successfully. Reports are ready for download!</span>
      </div>
    `);
  }
}

function handleStreamError(message) {
  const list = $("#streamSummaryList");
  const hasResults = state.results.length > 0;

  if (list) {
    list.insertAdjacentHTML("afterbegin", `
      <div class="stream-error-banner">
        <strong>Streaming interrupted.</strong>
        <span>${escapeHtml(message)}</span>
      </div>`);
  }

  const badge = $("#streamRunBadge");
  if (badge) {
    badge.textContent = "error";
    badge.classList.remove("status-badge--processing", "status-badge--completed");
    badge.classList.add("status-badge--failed");
  }

  setText("#streamStage", "Error");
  setText("#streamNote", message);

  if (!hasResults) {
    renderError(message);
  }
}

function renderError(message) {
  const body = $("#resultsBody");
  if (!body) {
    return;
  }

  body.innerHTML = `
    <div class="empty-state">
      <div class="empty-icon" style="color:var(--c-error)">!</div>
      <p style="color:var(--c-error)">${escapeHtml(message)}</p>
      <button class="btn btn--ghost btn--sm" onclick="summarizeDocs()">Retry</button>
    </div>`;
}

function buildSummaryCard(result) {
  const ext = getExtension(result.file.name);
  const statusClass = `status-badge--${result.status}`;
  const meta = [
    result.file.size_kb ? `${result.file.size_kb} KB` : null,
    result.char_count ? `${Number(result.char_count).toLocaleString()} chars` : null,
    result.chunk_count > 1 ? `${result.chunk_count} chunks` : null,
    result.processing_time_ms ? `${result.processing_time_ms} ms` : null,
  ].filter(Boolean).join(" | ");

  const summaryBody = result.summary
    ? `<p class="summary-text">${escapeHtml(result.summary)}</p>`
    : result.error_message
    ? `<div class="summary-error">${escapeHtml(result.error_message)}</div>`
    : '<p class="summary-text">No summary generated.</p>';

  const driveLink = result.file.web_view_link
    ? `<a class="summary-drive-link" href="${result.file.web_view_link}" target="_blank" rel="noopener">Open in Drive</a>`
    : "";

  return `
    <article class="summary-card summary-card--stream">
      <div class="summary-card-header">
        <div>
          <div class="table-file-info">
            <span class="file-icon file-icon--small file-icon--${ext}">${ext.toUpperCase()}</span>
            <div class="summary-file-name" title="${escapeHtml(result.file.name)}">${escapeHtml(result.file.name)}</div>
          </div>
          <div class="summary-meta">${escapeHtml(meta || "No metadata available")}</div>
        </div>
        <span class="status-badge ${statusClass}">${escapeHtml(result.status)}</span>
      </div>
      ${summaryBody}
      ${driveLink}
    </article>`;
}

function setDownloadButtons(enabled) {
  const csvButton = $("#downloadCsvBtn");
  const pdfButton = $("#downloadPdfBtn");

  if (csvButton) {
    csvButton.disabled = !enabled || !state.downloadUrls.csv;
  }

  if (pdfButton) {
    pdfButton.disabled = !enabled || !state.downloadUrls.pdf;
  }
}

function downloadReport(kind) {
  const url = state.downloadUrls[kind];
  if (!url) {
    return;
  }

  window.location.href = url;
}

function getExtension(name) {
  const ext = name.includes(".") ? name.split(".").pop().toLowerCase() : "file";
  return ["pdf", "docx", "txt", "md", "csv"].includes(ext) ? ext : "txt";
}

function setText(selector, value) {
  const node = $(selector);
  if (node) {
    node.textContent = value;
  }
}

function setProgressWidth(value) {
  const bar = $("#streamProgressBar");
  if (bar) {
    bar.style.width = `${value}%`;
  }
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderFinalTable(results) {
  const body = $("#resultsBody");
  if (!body) return;

  const rows = results.map((r) => {
    const ext = getExtension(r.file.name);
    const statusClass = `status-badge--${r.status}`;
    const metaParts = [
      r.file.size_kb ? `${r.file.size_kb} KB` : null,
      r.char_count ? `${r.char_count.toLocaleString()} chars` : null,
      r.chunk_count > 1 ? `${r.chunk_count} chunks` : null,
      r.processing_time_ms ? `${r.processing_time_ms} ms` : null,
    ].filter(Boolean).join(" · ");

    const driveLink = r.file.web_view_link
      ? `<a class="summary-drive-link" href="${r.file.web_view_link}" target="_blank" rel="noopener">↗ Open</a>`
      : "—";

    const content = r.summary
      ? `<p class="summary-text-cell">${escapeHtml(r.summary)}</p>`
      : r.error_message
      ? `<div class="summary-error-cell">${escapeHtml(r.error_message)}</div>`
      : `<span style="color:var(--c-text-3)">No content.</span>`;

    return `
      <tr>
        <td>
          <div class="table-file-info">
            <span class="file-icon file-icon--small file-icon--${ext}">${ext.toUpperCase()}</span>
            <div class="table-file-name" title="${escapeHtml(r.file.name)}">${escapeHtml(r.file.name)}</div>
          </div>
        </td>
        <td class="font-mono text-muted">${metaParts || "—"}</td>
        <td><span class="status-badge ${statusClass}">${r.status}</span></td>
        <td>${content}</td>
        <td>${driveLink}</td>
      </tr>`;
  }).join("");

  body.innerHTML = `
    <div style="margin-bottom: 20px;">
      <div class="live-progress-card" style="padding: 14px 18px; background: linear-gradient(135deg, rgba(52, 201, 138, 0.08), rgba(26, 29, 39, 0.96)); border-color: rgba(52, 201, 138, 0.2);">
        <div class="live-progress-topline" style="margin-bottom: 0; align-items: center;">
          <div>
            <p class="live-progress-kicker" style="color: var(--c-success);">Batch Complete</p>
            <h3 class="live-progress-title" style="font-size: 16px;">Processed ${results.length} document${results.length === 1 ? "" : "s"} successfully</h3>
          </div>
          <span class="status-badge status-badge--completed" style="padding: 4px 12px; font-size: 11px;">done</span>
        </div>
      </div>
    </div>
    
    <div class="table-responsive">
      <table class="summary-table">
        <thead>
          <tr>
            <th>Document</th>
            <th>Details</th>
            <th>Status</th>
            <th>AI Summary (5-10 sentences)</th>
            <th>Drive Link</th>
          </tr>
        </thead>
        <tbody>
          ${rows}
        </tbody>
      </table>
    </div>`;
}

