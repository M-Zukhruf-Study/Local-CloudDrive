/* Thin wrapper around fetch() that adds the auth token and parses JSON.
   Token is kept in localStorage so a page refresh doesn't log you out. */

const API = {
  TOKEN_KEY: "clouddrive_token",

  getToken() {
    return localStorage.getItem(this.TOKEN_KEY);
  },

  setToken(token) {
    localStorage.setItem(this.TOKEN_KEY, token);
  },

  clearToken() {
    localStorage.removeItem(this.TOKEN_KEY);
  },

  isLoggedIn() {
    return !!this.getToken();
  },

  /* Adds ?token=... to a URL — used for plain download links. */
  withToken(url) {
    const sep = url.includes("?") ? "&" : "?";
    return `${url}${sep}token=${encodeURIComponent(this.getToken() || "")}`;
  },

  async request(path, options = {}) {
    const headers = options.headers || {};
    const token = this.getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const resp = await fetch(path, { ...options, headers });

    if (resp.status === 401 && !path.includes("/api/auth/login")) {
      this.clearToken();
      showLoginScreen();
      throw new Error("Session expired. Please log in again.");
    }

    if (!resp.ok) {
      let detail = `Request failed (${resp.status})`;
      try {
        const body = await resp.json();
        if (body.detail) detail = body.detail;
      } catch (_) {}
      throw new Error(detail);
    }

    if (resp.status === 204) return null;
    return resp.json();
  },

  login(username, password) {
    return this.request("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
  },

  browse(folderId) {
    const qs = folderId != null ? `?folder_id=${folderId}` : "";
    return this.request(`/api/folders/browse${qs}`);
  },

  createFolder(name, parentId) {
    return this.request("/api/folders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, parent_id: parentId }),
    });
  },

  deleteFolder(folderId) {
    return this.request(`/api/folders/${folderId}`, { method: "DELETE" });
  },

  deleteFile(fileId) {
    return this.request(`/api/files/${fileId}`, { method: "DELETE" });
  },

  search(query) {
    return this.request(`/api/files/search?q=${encodeURIComponent(query)}`);
  },

  quota() {
    return this.request("/api/files/quota");
  },

  initUpload(payload) {
    return this.request("/api/files/upload/init", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  uploadStatus(sessionId) {
    return this.request(`/api/files/upload/status?session_id=${sessionId}`);
  },

  completeUpload(sessionId) {
    return this.request(`/api/files/upload/complete?session_id=${sessionId}`, {
      method: "POST",
    });
  },

  abortUpload(sessionId) {
    return this.request(`/api/files/upload/${sessionId}`, { method: "DELETE" });
  },

  downloadUrl(fileId) {
    return this.withToken(`/api/files/download/${fileId}`);
  },
};
