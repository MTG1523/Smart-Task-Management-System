/* ── State ─────────────────────────────────────────────────────────────── */
let allTasks = [];
let currentFilter = "all";

/* ── WebSocket ─────────────────────────────────────────────────────────── */
const socket = io();
const wsDot  = document.getElementById("ws-indicator");

socket.on("connect", () => {
  socket.emit("join", { user_id: CURRENT_USER_ID });
  wsDot.className = "ws-dot ws-dot--connected";
});
socket.on("disconnect", () => { wsDot.className = "ws-dot ws-dot--error"; });
socket.on("task_created", (task) => {
  if (!allTasks.find(t => t.id === task.id)) allTasks.unshift(task);
  renderTasks(); loadAnalytics(); showToast(`✅ Added: ${task.title}`);
});
socket.on("task_updated", (task) => {
  allTasks = allTasks.map(t => t.id === task.id ? task : t);
  renderTasks(); loadAnalytics();
});
socket.on("task_deleted", ({ id }) => {
  allTasks = allTasks.filter(t => t.id !== id);
  renderTasks(); loadAnalytics();
});

/* ── API ───────────────────────────────────────────────────────────────── */
const api = {
  get: (url)       => fetch(url, { headers: {"Content-Type":"application/json"} }),
  post:(url, body) => fetch(url, { method:"POST",   headers:{"Content-Type":"application/json"}, body:JSON.stringify(body) }),
  put: (url, body) => fetch(url, { method:"PUT",    headers:{"Content-Type":"application/json"}, body:JSON.stringify(body) }),
  del: (url)       => fetch(url, { method:"DELETE", headers:{"Content-Type":"application/json"} }),
};

/* ── Load tasks ────────────────────────────────────────────────────────── */
async function loadTasks() {
  const res  = await api.get("/api/tasks");
  const data = await res.json();
  allTasks   = data.tasks || [];
  renderTasks();
}

/* ── Render tasks ──────────────────────────────────────────────────────── */
function renderTasks() {
  const grid = document.getElementById("task-grid");

  const filtered = currentFilter === "all"
    ? allTasks
    : allTasks.filter(t => t.status === currentFilter);

  if (!filtered.length) {
    grid.innerHTML = `<div class="empty-state"><p>No tasks here. Click <strong>+ New Task</strong> to add one.</p></div>`;
    return;
  }

  grid.innerHTML = filtered.map(task => `
    <div class="task-card" id="task-${task.id}">
      <div class="task-card__top">
        <span class="task-card__title">${escHtml(task.title)}</span>
        <div class="task-card__actions">
          <button class="btn btn--sm btn--ghost" onclick="openEditModal(${task.id})">✏️</button>
          <button class="btn btn--sm btn--danger" onclick="deleteTask(${task.id})">🗑️</button>
        </div>
      </div>
      ${task.description ? `<p class="task-card__desc">${escHtml(task.description)}</p>` : ""}
      <div class="task-card__meta">
        <span class="badge badge--${task.priority}">${task.priority}</span>
        <span class="badge badge--${task.status}">${task.status.replace("_"," ")}</span>
        <span style="font-size:.75rem;color:var(--text-muted);margin-left:auto">${fmtDate(task.created_at)}</span>
      </div>
    </div>
  `).join("");
}

/* ── Analytics ─────────────────────────────────────────────────────────── */
async function loadAnalytics() {
  const res  = await api.get("/analytics/summary");
  const data = await res.json();
  document.getElementById("stat-total").textContent      = data.total_tasks;
  document.getElementById("stat-completed").textContent  = data.completed_tasks;
  document.getElementById("stat-inprogress").textContent = data.in_progress_tasks;
  document.getElementById("stat-pending").textContent    = data.pending_tasks;
  document.getElementById("stat-pct").textContent        = `${data.completion_percentage}%`;
  document.getElementById("progress-bar").style.width    = `${data.completion_percentage}%`;
}

/* ── Modal ─────────────────────────────────────────────────────────────── */
const overlay     = document.getElementById("modal-overlay");
const modalTitle  = document.getElementById("modal-title");
const editIdField = document.getElementById("edit-task-id");

function openAddModal() {
  editIdField.value = "";
  modalTitle.textContent = "New Task";
  document.getElementById("task-title").value    = "";
  document.getElementById("task-desc").value     = "";
  document.getElementById("task-priority").value = "medium";
  document.getElementById("task-status").value   = "pending";
  overlay.classList.add("open");
}

function openEditModal(id) {
  const task = allTasks.find(t => t.id === id);
  if (!task) return;
  editIdField.value = id;
  modalTitle.textContent = "Edit Task";
  document.getElementById("task-title").value    = task.title;
  document.getElementById("task-desc").value     = task.description || "";
  document.getElementById("task-priority").value = task.priority;
  document.getElementById("task-status").value   = task.status;
  overlay.classList.add("open");
}

function closeModal() { overlay.classList.remove("open"); }

document.getElementById("open-modal-btn").addEventListener("click", openAddModal);
document.getElementById("modal-close").addEventListener("click", closeModal);
document.getElementById("modal-cancel").addEventListener("click", closeModal);
overlay.addEventListener("click", e => { if (e.target === overlay) closeModal(); });

/* ── Save task ─────────────────────────────────────────────────────────── */
document.getElementById("modal-save").addEventListener("click", async () => {
  const id    = editIdField.value;
  const title = document.getElementById("task-title").value.trim();
  if (!title) { showToast("⚠️ Title is required"); return; }
  const body = {
    title,
    description: document.getElementById("task-desc").value.trim(),
    priority:    document.getElementById("task-priority").value,
    status:      document.getElementById("task-status").value,
  };
  const res = id ? await api.put(`/api/tasks/${id}`, body) : await api.post("/api/tasks", body);
  if (res.ok) {
    closeModal();
    await loadTasks();
    await loadAnalytics();
  } else {
    const err = await res.json();
    showToast("❌ " + (err.error || "Error"));
  }
});

/* ── Delete ────────────────────────────────────────────────────────────── */
async function deleteTask(id) {
  if (!confirm("Delete this task?")) return;
  const res = await api.del(`/api/tasks/${id}`);
  if (res.ok) { await loadTasks(); await loadAnalytics(); }
}

/* ── Filter nav ────────────────────────────────────────────────────────── */
document.querySelectorAll(".nav-item[data-filter]").forEach(el => {
  el.addEventListener("click", e => {
    e.preventDefault();
    document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("nav-item--active"));
    el.classList.add("nav-item--active");
    currentFilter = el.dataset.filter;
    document.getElementById("page-title").textContent =
      currentFilter === "all" ? "All Tasks" : el.textContent.trim();
    renderTasks();
  });
});

/* ── Toast ─────────────────────────────────────────────────────────────── */
let toastTimer;
function showToast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 3000);
}

/* ── Utils ─────────────────────────────────────────────────────────────── */
function escHtml(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
function fmtDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, {month:"short",day:"numeric",year:"numeric"});
}

/* ── Init ──────────────────────────────────────────────────────────────── */
loadTasks();
loadAnalytics();
