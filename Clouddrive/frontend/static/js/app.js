/* Main application state + UI wiring. */

let currentFolderId = null;
let currentItems = { folders: [], files: [], breadcrumb: [] };
let contextTarget = null; // { type: 'file'|'folder', id, name, size }
const transferRows = new Map(); // transferId -> DOM element
let autoRefreshHandle = null;

// ----------------------------------------------------------------- utils --

function formatBytes(bytes) {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function formatSpeed(bps) {
  if (!bps || bps < 1) return "";
  return `${formatBytes(bps)}/s`;
}

function formatETA(seconds) {
  if (!Number.isFinite(seconds) || seconds < 1) return "";
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  if (mins > 0) return `${mins}m ${secs}s`;
  return `${secs}s`;
}

function showToast(message, type = "") {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.className = `toast show ${type}`;
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => toast.classList.remove("show"), 3000);
}

function iconFor(mimeType, isFolder) {
  if (isFolder) return "📁";
  if (!mimeType) return "📄";
  if (mimeType.startsWith("image/")) return "🖼️";
  if (mimeType.startsWith("video/")) return "🎬";
  if (mimeType.startsWith("audio/")) return "🎵";
  if (mimeType.includes("pdf")) return "📕";
  if (mimeType.includes("zip") || mimeType.includes("compressed") || mimeType.includes("tar")) return "🗜️";
  if (mimeType.includes("word") || mimeType.includes("document")) return "📘";
  if (mimeType.includes("sheet") || mimeType.includes("excel")) return "📗";
  return "📄";
}

// -------------------------------------------------------------- auth flow --

function showLoginScreen() {
  document.getElementById("login-screen").style.display = "flex";
  document.getElementById("app-screen").style.display = "none";
}

function refreshAppState() {
  if (!API.isLoggedIn()) return;
  loadFolder(currentFolderId).catch(() => {});
  refreshQuota().catch(() => {});
}

function startAutoRefresh() {
  if (autoRefreshHandle) clearInterval(autoRefreshHandle);
  autoRefreshHandle = setInterval(refreshAppState, 5000);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refreshAppState();
  });
  window.addEventListener("focus", refreshAppState);
}

function showAppScreen() {
  document.getElementById("login-screen").style.display = "none";
  document.getElementById("app-screen").style.display = "block";
  loadFolder(null);
  refreshQuota();
  checkResumableUploads();
  startAutoRefresh();
}

async function doLogin() {
  const username = document.getElementById("login-username").value.trim();
  const password = document.getElementById("login-password").value;
  const errorEl = document.getElementById("login-error");
  errorEl.textContent = "";

  if (!username || !password) {
    errorEl.textContent = "Please enter both fields";
    return;
  }

  try {
    const resp = await API.login(username, password);
    API.setToken(resp.access_token);
    showAppScreen();
  } catch (err) {
    errorEl.textContent = err.message;
  }
}

function togglePasswordVisibility() {
  const passwordInput = document.getElementById("login-password");
  const toggleButton = document.getElementById("password-toggle");
  if (!passwordInput || !toggleButton) return;

  const isHidden = passwordInput.type === "password";
  passwordInput.type = isHidden ? "text" : "password";
  toggleButton.textContent = isHidden ? "🙈" : "👁";
  toggleButton.setAttribute("aria-label", isHidden ? "Hide password" : "Show password");
}

function doLogout() {
  API.clearToken();
  showLoginScreen();
}

// ------------------------------------------------------------- navigation --

async function loadFolder(folderId) {
  try {
    const data = await API.browse(folderId);
    currentFolderId = folderId;
    currentItems = data;
    renderBreadcrumb(data.breadcrumb);
    renderGrid(data.folders, data.files);
  } catch (err) {
    showToast(err.message, "error");
  }
}

function renderBreadcrumb(trail) {
  const el = document.getElementById("breadcrumb");
  el.innerHTML = "";
  const rootLink = document.createElement("a");
  rootLink.textContent = "🏠 My Drive";
  rootLink.onclick = () => loadFolder(null);
  el.appendChild(rootLink);

  trail.forEach((folder) => {
    const sep = document.createElement("span");
    sep.textContent = " / ";
    el.appendChild(sep);
    const link = document.createElement("a");
    link.textContent = folder.name;
    link.onclick = () => loadFolder(folder.id);
    el.appendChild(link);
  });
}

function renderGrid(folders, files) {
  const grid = document.getElementById("item-grid");
  const empty = document.getElementById("empty-state");
  grid.innerHTML = "";

  if (folders.length === 0 && files.length === 0) {
    empty.style.display = "block";
  } else {
    empty.style.display = "none";
  }

  folders.forEach((folder) => {
    const card = document.createElement("div");
    card.className = "item-card";
    card.innerHTML = `
      <button class="item-menu-btn" data-menu="folder" data-id="${folder.id}" data-name="${escapeHtml(folder.name)}">⋮</button>
      <div class="item-icon">📁</div>
      <div class="item-name">${escapeHtml(folder.name)}</div>
      <div class="item-meta">Folder</div>
    `;
    card.addEventListener("dblclick", () => loadFolder(folder.id));
    card.addEventListener("click", (e) => {
      if (e.target.closest(".item-menu-btn")) return;
      loadFolder(folder.id);
    });
    grid.appendChild(card);
  });

  files.forEach((file) => {
    const card = document.createElement("div");
    card.className = "item-card";
    card.innerHTML = `
      <button class="item-menu-btn" data-menu="file" data-id="${file.id}" data-name="${escapeHtml(file.name)}" data-size="${file.size_bytes}">⋮</button>
      <div class="item-icon">${iconFor(file.mime_type, false)}</div>
      <div class="item-name">${escapeHtml(file.name)}</div>
      <div class="item-meta">${formatBytes(file.size_bytes)}</div>
    `;
    card.addEventListener("dblclick", () => triggerDownload(file.id, file.name, file.size_bytes));
    grid.appendChild(card);
  });

  grid.querySelectorAll(".item-menu-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      openContextMenu(e, btn.dataset);
    });
  });
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// ----------------------------------------------------------------- search --

let searchDebounce = null;
function onSearchInput(e) {
  clearTimeout(searchDebounce);
  const q = e.target.value.trim();
  searchDebounce = setTimeout(async () => {
    if (!q) {
      loadFolder(currentFolderId);
      return;
    }
    try {
      const results = await API.search(q);
      document.getElementById("breadcrumb").innerHTML = `<span>🔍 Search results for "${escapeHtml(q)}"</span>`;
      renderGrid([], results);
    } catch (err) {
      showToast(err.message, "error");
    }
  }, 350);
}

// ------------------------------------------------------------- quota bar --

async function refreshQuota() {
  try {
    const q = await API.quota();
    const fill = document.getElementById("quota-fill");
    const text = document.getElementById("quota-text");
    fill.style.width = `${Math.min(100, q.percent_used)}%`;
    fill.className = "quota-fill" + (q.percent_used > 90 ? " danger" : q.percent_used > 70 ? " warn" : "");
    text.textContent = `${q.used_gb} GB of ${q.quota_gb} GB used (${q.percent_used}%)`;
  } catch (err) {
    // non-fatal
  }
}

// ----------------------------------------------------------- context menu --

function openContextMenu(event, data) {
  contextTarget = data; // { menu: 'file'|'folder', id, name, size }
  const menu = document.getElementById("context-menu");
  menu.classList.add("open");
  const rect = event.target.getBoundingClientRect();
  const menuWidth = 170;
  let left = rect.left;
  if (left + menuWidth > window.innerWidth) left = window.innerWidth - menuWidth - 10;
  menu.style.left = `${left}px`;
  menu.style.top = `${rect.bottom + 4}px`;

  document.getElementById("ctx-download").style.display = data.menu === "file" ? "block" : "none";
}

function closeContextMenu() {
  document.getElementById("context-menu").classList.remove("open");
  contextTarget = null;
}

document.addEventListener("click", (e) => {
  if (!e.target.closest("#context-menu") && !e.target.closest(".item-menu-btn")) {
    closeContextMenu();
  }
});

document.getElementById("ctx-download").addEventListener("click", () => {
  if (contextTarget) triggerDownload(contextTarget.id, contextTarget.name, Number(contextTarget.size));
  closeContextMenu();
});

document.getElementById("ctx-delete").addEventListener("click", async () => {
  if (!contextTarget) return;
  const { menu, id, name } = contextTarget;
  closeContextMenu();
  if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
  try {
    if (menu === "folder") {
      await API.deleteFolder(id);
    } else {
      await API.deleteFile(id);
    }
    showToast(`Deleted "${name}"`, "success");
    loadFolder(currentFolderId);
    refreshQuota();
  } catch (err) {
    showToast(err.message, "error");
  }
});

// ------------------------------------------------------------ new folder --

function openFolderModal() {
  document.getElementById("folder-name-input").value = "";
  document.getElementById("folder-modal").classList.add("open");
  document.getElementById("folder-name-input").focus();
}

function closeFolderModal() {
  document.getElementById("folder-modal").classList.remove("open");
}

async function submitNewFolder() {
  const name = document.getElementById("folder-name-input").value.trim();
  if (!name) return;
  try {
    await API.createFolder(name, currentFolderId);
    closeFolderModal();
    loadFolder(currentFolderId);
    showToast("Folder created", "success");
  } catch (err) {
    showToast(err.message, "error");
  }
}

// -------------------------------------------------------- transfer panel --

function ensureTransferPanelOpen() {
  document.getElementById("transfer-panel").classList.add("open");
}

function ensureTransferPanelClosed() {
  document.getElementById("transfer-panel").classList.remove("open");
}

function addTransferRow(id, name, kind) {
  const list = document.getElementById("transfer-list");
  const row = document.createElement("div");
  row.className = "transfer-item";
  row.innerHTML = `
    <div class="transfer-row">
      <span class="transfer-name">${kind === "upload" ? "⬆️" : "⬇️"} ${escapeHtml(name)}</span>
      <span class="transfer-pct">0%</span>
    </div>
    <div class="progress-track"><div class="progress-fill" style="width:0%"></div></div>
    <div class="transfer-sub"></div>
  `;
  list.prepend(row);
  transferRows.set(id, row);
  ensureTransferPanelOpen();
  return row;
}

function maybeHideTransferPanel() {
  if (transferRows.size === 0) {
    ensureTransferPanelClosed();
  }
}

function updateTransferRow(id, pct, sub, state = "active") {
  const row = transferRows.get(id);
  if (!row) return;
  row.querySelector(".transfer-pct").textContent = `${Math.round(pct)}%`;
  const fill = row.querySelector(".progress-fill");
  fill.style.width = `${pct}%`;
  fill.className = "progress-fill" + (state === "done" ? " done" : state === "error" ? " error" : "");
  row.querySelector(".transfer-sub").textContent = sub || "";

  if (state === "done" || state === "error") {
    row.querySelector(".transfer-sub").textContent = sub || (state === "done" ? "Completed" : "Failed");
  }
}

// ------------------------------------------------------------ upload flow --

function triggerFileInput() {
  document.getElementById("file-input").click();
}

async function handleFilesSelected(fileList) {
  for (const file of fileList) {
    const existingSessionId = UploadManager.findMatchingSession(file);
    startSingleUpload(file, existingSessionId || null);
  }
}

function startSingleUpload(file, existingSessionId = null) {
  const transferId = existingSessionId || `pending-${Date.now()}-${Math.random()}`;
  addTransferRow(transferId, file.name, "upload");

  UploadManager.startUpload(
    file,
    currentFolderId,
    {
      onProgress: ({ pct, uploadedBytes, totalBytes, speedBps }) => {
        const remainingBytes = Math.max(0, totalBytes - uploadedBytes);
        const etaText = speedBps > 0 ? ` · ETA ${formatETA(remainingBytes / speedBps)}` : "";
        updateTransferRow(
          transferId,
          pct,
          `${formatBytes(uploadedBytes)} / ${formatBytes(totalBytes)} · ${formatSpeed(speedBps)}${etaText}`
        );
      },
      onComplete: (fileRecord) => {
        updateTransferRow(transferId, 100, "Upload completed", "done");
        showToast(`Uploaded "${fileRecord.name}"`, "success");
        if (fileRecord.folder_id === currentFolderId || (fileRecord.folder_id == null && currentFolderId == null)) {
          loadFolder(currentFolderId);
        }
        refreshQuota();
      },
      onError: (message) => {
        const friendlyMessage = message.includes("Failed to fetch") || message.includes("Network")
          ? "Connection lost. Re-select the same file to resume."
          : message;
        updateTransferRow(transferId, 0, friendlyMessage, "error");
        showToast(`Upload failed: ${friendlyMessage}`, "error");
      },
    },
    existingSessionId
  );
}

async function checkResumableUploads() {
  const sessions = UploadManager.getResumableSessions();
  const ids = Object.keys(sessions);
  if (ids.length === 0) return;

  for (const sessionId of ids) {
    const meta = sessions[sessionId];
    try {
      const status = await API.uploadStatus(sessionId);
      if (status.status !== "uploading") continue;
      const remaining = status.total_chunks - status.uploaded_chunks.length;
      showToast(
        `Found an interrupted upload: "${meta.fileName}" (${remaining} chunk(s) left). Re-select the file to resume.`,
        ""
      );
    } catch (_) {
      // session no longer exists server-side, nothing to do
    }
  }
}

// ---------------------------------------------------------- download flow --

function triggerDownload(fileId, fileName, sizeBytes) {
  const transferId = `dl-${fileId}-${Date.now()}`;
  addTransferRow(transferId, fileName, "download");

  DownloadManager.downloadFile(fileId, fileName, sizeBytes, {
    onProgress: ({ pct, downloadedBytes, totalBytes, speedBps }) => {
      const remainingBytes = Math.max(0, totalBytes - downloadedBytes);
      const etaText = speedBps > 0 ? ` · ETA ${formatETA(remainingBytes / speedBps)}` : "";
      updateTransferRow(
        transferId,
        pct,
        `${formatBytes(downloadedBytes)} / ${formatBytes(totalBytes)} · ${formatSpeed(speedBps)}${etaText}`
      );
    },
    onComplete: () => {
      updateTransferRow(transferId, 100, "Download completed", "done");
    },
    onError: (message) => {
      updateTransferRow(transferId, 0, message, "error");
      showToast(`Download failed: ${message}`, "error");
    },
  });
}

// --------------------------------------------------------- drag and drop --

function setupDragDrop() {
  const dropZone = document.getElementById("drop-zone");
  ["dragenter", "dragover"].forEach((evt) =>
    dropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropZone.classList.add("drag-active");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropZone.classList.remove("drag-active");
    })
  );
  dropZone.addEventListener("drop", (e) => {
    const files = e.dataTransfer.files;
    if (files && files.length) handleFilesSelected(files);
  });
}

// ------------------------------------------------------------------ init --

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("login-btn").addEventListener("click", doLogin);
  document.getElementById("login-password").addEventListener("keydown", (e) => {
    if (e.key === "Enter") doLogin();
  });
  document.getElementById("password-toggle").addEventListener("click", togglePasswordVisibility);
  document.getElementById("logout-btn").addEventListener("click", doLogout);

  document.getElementById("search-input").addEventListener("input", onSearchInput);

  document.getElementById("upload-file-btn").addEventListener("click", triggerFileInput);
  document.getElementById("file-input").addEventListener("change", (e) => {
    handleFilesSelected(e.target.files);
    e.target.value = "";
  });

  document.getElementById("new-folder-btn").addEventListener("click", openFolderModal);
  document.getElementById("folder-cancel-btn").addEventListener("click", closeFolderModal);
  document.getElementById("folder-create-btn").addEventListener("click", submitNewFolder);
  document.getElementById("folder-name-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") submitNewFolder();
  });

  document.getElementById("transfer-close-btn").addEventListener("click", () => {
    document.getElementById("transfer-panel").classList.remove("open");
    document.getElementById("transfer-list").innerHTML = "";
    transferRows.clear();
  });

  setupDragDrop();

  if (API.isLoggedIn()) {
    showAppScreen();
  } else {
    showLoginScreen();
  }
});
