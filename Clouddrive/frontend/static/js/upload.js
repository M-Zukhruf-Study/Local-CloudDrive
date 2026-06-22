/*
 * Chunked resumable upload manager.
 *
 * Why chunked: browsers/servers struggle to reliably push a 100GB file in
 * one HTTP request. Slicing the File object (File.slice — this does NOT
 * load the file into memory, it's a lazy view) into fixed-size pieces and
 * PUTting them one at a time keeps memory flat regardless of file size.
 *
 * Why resumable: each chunk is tracked server-side (see upload_chunks
 * table). If the tab closes, wifi drops, or you just want to pause, calling
 * resumeUpload() with the same session_id asks the server "what do you
 * already have?" and only sends what's missing — so a 100GB upload doesn't
 * have to restart from zero after an interruption.
 *
 * Active sessions are kept in localStorage (id -> {fileName, folderId,
 * totalSize, chunkSize}) purely so the *next* page load can offer to
 * resume. The actual File object can't be persisted across a reload (the
 * browser doesn't allow that) — so on reload the user has to re-pick the
 * same file, but the upload then skips every chunk the server already has.
 */

const CHUNK_SIZE = 8 * 1024 * 1024; // 8MB — matches backend default
const SESSIONS_KEY = "clouddrive_upload_sessions";

const UploadManager = {
  active: new Map(), // sessionId -> { file, controller, cancelled }

  _loadSessions() {
    try {
      return JSON.parse(localStorage.getItem(SESSIONS_KEY) || "{}");
    } catch (_) {
      return {};
    }
  },

  _saveSessions(sessions) {
    localStorage.setItem(SESSIONS_KEY, JSON.stringify(sessions));
  },

  _rememberSession(sessionId, meta) {
    const sessions = this._loadSessions();
    sessions[sessionId] = meta;
    this._saveSessions(sessions);
  },

  _forgetSession(sessionId) {
    const sessions = this._loadSessions();
    delete sessions[sessionId];
    this._saveSessions(sessions);
  },

  getResumableSessions() {
    return this._loadSessions();
  },

  findMatchingSession(file) {
    const sessions = this._loadSessions();
    for (const [sessionId, meta] of Object.entries(sessions)) {
      if (meta.fileName === file.name && Number(meta.totalSize) === file.size) {
        return sessionId;
      }
    }
    return null;
  },

  /**
   * Kicks off (or resumes, if sessionId already exists server-side) the
   * upload of `file` into `folderId`. `callbacks` lets the UI react to
   * progress without this module knowing anything about the DOM.
   *
   * callbacks: { onProgress({pct, uploadedBytes, totalBytes, speedBps}),
   *              onComplete(fileRecord), onError(message) }
   */
  async startUpload(file, folderId, callbacks, existingSessionId = null) {
    const localId = existingSessionId || `local-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const state = { file, cancelled: false };
    this.active.set(localId, state);

    try {
      let sessionId = existingSessionId;
      let totalChunks;
      let uploadedSet = new Set();

      if (sessionId) {
        // Resuming: ask the server what it already has.
        const status = await API.uploadStatus(sessionId);
        totalChunks = status.total_chunks;
        uploadedSet = new Set(status.uploaded_chunks);
      } else {
        const initResp = await API.initUpload({
          file_name: file.name,
          folder_id: folderId,
          total_size: file.size,
          chunk_size: CHUNK_SIZE,
          mime_type: file.type || "application/octet-stream",
        });
        sessionId = initResp.session_id;
        totalChunks = initResp.total_chunks;
        this._rememberSession(sessionId, {
          fileName: file.name,
          folderId,
          totalSize: file.size,
          chunkSize: CHUNK_SIZE,
        });
      }

      // Re-key the active-uploads map under the real session id so
      // cancelUpload() can find it by the id the UI displays.
      if (localId !== sessionId) {
        this.active.delete(localId);
        this.active.set(sessionId, state);
      }

      let uploadedBytes = [...uploadedSet].length * CHUNK_SIZE;
      if (uploadedBytes > file.size) uploadedBytes = file.size;
      const startTime = Date.now();
      let lastTick = startTime;
      let bytesAtLastTick = uploadedBytes;

      for (let i = 0; i < totalChunks; i++) {
        if (state.cancelled) {
          callbacks.onError("Upload cancelled");
          return;
        }
        if (uploadedSet.has(i)) continue; // already on server — skip (this IS the resume logic)

        const start = i * CHUNK_SIZE;
        const end = Math.min(start + CHUNK_SIZE, file.size);
        const blob = file.slice(start, end); // lazy view, no memory copy

        await this._uploadChunkWithRetry(sessionId, i, blob);

        uploadedBytes += blob.size;
        const now = Date.now();
        if (now - lastTick > 250) {
          const speedBps = ((uploadedBytes - bytesAtLastTick) / ((now - lastTick) / 1000)) || 0;
          callbacks.onProgress({
            pct: Math.min(100, (uploadedBytes / file.size) * 100),
            uploadedBytes,
            totalBytes: file.size,
            speedBps,
          });
          lastTick = now;
          bytesAtLastTick = uploadedBytes;
        }
      }

      callbacks.onProgress({ pct: 100, uploadedBytes: file.size, totalBytes: file.size, speedBps: 0 });

      const completeResp = await API.completeUpload(sessionId);
      this._forgetSession(sessionId);
      this.active.delete(sessionId);
      callbacks.onComplete(completeResp.file);
    } catch (err) {
      callbacks.onError(err.message || "Upload failed");
    }
  },

  async _uploadChunkWithRetry(sessionId, index, blob, maxRetries = 4) {
    let attempt = 0;
    let lastErr;
    while (attempt <= maxRetries) {
      try {
        const formData = new FormData();
        formData.append("session_id", sessionId);
        formData.append("chunk_index", String(index));
        formData.append("chunk", blob);

        await API.request("/api/files/upload/chunk", {
          method: "PUT",
          body: formData,
        });
        return;
      } catch (err) {
        lastErr = err;
        attempt++;
        // Exponential backoff: network hiccup or server momentarily busy —
        // this is what makes the upload survive brief connectivity drops
        // without the user having to do anything.
        await new Promise((r) => setTimeout(r, Math.min(8000, 500 * 2 ** attempt)));
      }
    }
    throw lastErr;
  },

  cancelUpload(sessionId) {
    const state = this.active.get(sessionId);
    if (state) state.cancelled = true;
    this.active.delete(sessionId);
    this._forgetSession(sessionId);
    API.abortUpload(sessionId).catch(() => {});
  },
};


/* ---------------------------------------------------------------------- *
 * Streaming download with a real progress bar.
 *
 * A plain <a href=download> gives you the browser's native download UI
 * but no in-page progress bar. To show our own bar we fetch() the file
 * and read its ReadableStream in chunks, tracking bytes as they arrive,
 * then assemble a Blob at the end and trigger a save. This still streams
 * off the network in pieces (no giant single buffer held mid-flight) and
 * Content-Length from the server gives us the total for the percentage.
 * ---------------------------------------------------------------------- */
const DownloadManager = {
  async downloadFile(fileId, fileName, totalBytes, callbacks) {
    const url = API.downloadUrl(fileId);
    const resp = await fetch(url);
    if (!resp.ok) {
      callbacks.onError(`Download failed (${resp.status})`);
      return;
    }

    const contentLength = Number(resp.headers.get("Content-Length")) || totalBytes || 0;
    const reader = resp.body.getReader();
    const chunks = [];
    let received = 0;
    let lastTick = Date.now();
    let bytesAtLastTick = 0;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      received += value.length;

      const now = Date.now();
      if (now - lastTick > 250) {
        const speedBps = ((received - bytesAtLastTick) / ((now - lastTick) / 1000)) || 0;
        callbacks.onProgress({
          pct: contentLength ? Math.min(100, (received / contentLength) * 100) : 0,
          downloadedBytes: received,
          totalBytes: contentLength,
          speedBps,
        });
        lastTick = now;
        bytesAtLastTick = received;
      }
    }

    callbacks.onProgress({ pct: 100, downloadedBytes: received, totalBytes: contentLength, speedBps: 0 });

    const blob = new Blob(chunks);
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = blobUrl;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(blobUrl);

    callbacks.onComplete();
  },
};
