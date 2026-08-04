(() => {
  "use strict";

  const app = document.getElementById("todo-app");
  const checklist = document.getElementById("checklist");
  const categoryFilters = document.getElementById("category-filters");
  const priorityFilters = document.getElementById("priority-filters");
  const grouping = document.getElementById("grouping");
  const saveStatus = document.getElementById("save-status");
  const message = document.getElementById("message");
  let documentState;
  let revision;
  let priorities = [];
  let saveQueue = Promise.resolve();
  let focusRequest = null;
  const selectedCategories = new Set();
  const selectedPriorities = new Set();
  const openDescriptions = new Set();
  const timers = new Map();

  const escapeHtml = value => String(value).replace(/[&<>"]/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;"
  })[character]);

  function taskMap() { return new Map(documentState.tasks.map(task => [task.id, task])); }
  function categoryMap() { return new Map(documentState.categories.map(category => [category.id, category])); }
  function categoriesFor(taskId) {
    return documentState.category_memberships.filter(item => item.tasks.includes(taskId)).map(item => item.category);
  }
  function descendants(id, tasks, found = new Set()) {
    for (const dependency of tasks.get(id).dependencies) {
      if (!found.has(dependency)) { found.add(dependency); descendants(dependency, tasks, found); }
    }
    return found;
  }
  function roots(ids, tasks) {
    const candidates = [...ids];
    const candidateSet = new Set(candidates);
    const nested = new Set();
    for (const id of candidates) for (const child of descendants(id, tasks)) if (candidateSet.has(child)) nested.add(child);
    return candidates.filter(id => !nested.has(id));
  }
  function primaryIds() {
    return documentState.tasks.filter(task => {
      const categories = categoriesFor(task.id);
      const categoryMatch = !selectedCategories.size || categories.some(category => selectedCategories.has(category));
      const priority = task.priority || "";
      return categoryMatch && (!selectedPriorities.size || selectedPriorities.has(priority));
    }).map(task => task.id);
  }
  function visibleIds(primary, tasks) {
    const visible = new Set(primary);
    for (const id of primary) for (const child of descendants(id, tasks)) visible.add(child);
    return visible;
  }
  function categoryOptions(selected) {
    const categories = categoryMap();
    return documentState.categories.map(category => `<option value="${escapeHtml(category.id)}" ${selected.includes(category.id) ? "selected" : ""}>${escapeHtml(categories.get(category.id).display_name)}</option>`).join("");
  }
  function dueText(task) {
    if (!task.due) return "";
    const values = [task.due.year, task.due.month, task.due.day].filter(value => value !== undefined);
    return values.map((value, index) => index ? String(value).padStart(2, "0") : value).join("-") + (task.due.time ? ` ${task.due.time}` : "");
  }
  function renderBranch(id, parentId, contextCategory, primary, visible, tasks, seen = new Set()) {
    if (!visible.has(id) || seen.has(id)) return "";
    const task = tasks.get(id);
    const nextSeen = new Set(seen); nextSeen.add(id);
    const categories = categoriesFor(id);
    const descriptionShown = task.description !== undefined || openDescriptions.has(id);
    const priorityOptions = [`<option value="">Unprioritized</option>`, ...priorities.map(priority => `<option value="${escapeHtml(priority)}" ${task.priority === priority ? "selected" : ""}>${escapeHtml(priority[0].toUpperCase() + priority.slice(1))}</option>`)].join("");
    const draft = task._draft === true;
    return `<div class="branch" data-id="${id}" data-parent="${parentId || ""}" data-category="${contextCategory || categories[0] || ""}">
      <div class="task-row ${primary.has(id) ? "" : "contextual"}" data-id="${id}" data-parent="${parentId || ""}">
        <input class="task-check" type="checkbox" aria-label="Mark ${escapeHtml(task.name || "new task")} complete" ${task.completed ? "checked" : ""} ${draft ? "disabled" : ""}>
        <div class="task-fields">
          <input class="task-name" value="${escapeHtml(task.name)}" placeholder="New task" aria-label="Task name">
          ${descriptionShown ? `<input class="task-description" value="${escapeHtml(task.description || "")}" placeholder="Description" aria-label="Task description">` : ""}
        </div>
        ${draft ? `<div class="task-meta"></div>` : `<div class="task-meta">${task.due ? `<span class="due ${task.deadline_kind || ""}">${escapeHtml(dueText(task))}</span>` : ""}
          <div class="task-menu"><button class="menu-toggle" type="button" aria-label="Task options" aria-expanded="false">···</button>
            <div class="menu-panel" hidden>
              <label>Priority<select data-field="priority">${priorityOptions}</select></label>
              <label>Categories<select data-field="categories" multiple>${categoryOptions(categories)}</select></label>
              <label>Due date<input data-field="due" value="${escapeHtml(dueText(task).split(" ")[0])}" placeholder="YYYY, YYYY-MM, or YYYY-MM-DD"></label>
              <label>Due time<input data-field="due-time" value="${escapeHtml(task.due?.time || "")}" placeholder="HH:MM"></label>
              <label>Deadline<select data-field="deadline-kind"><option value="">None</option><option value="hard" ${task.deadline_kind === "hard" ? "selected" : ""}>Hard</option><option value="soft" ${task.deadline_kind === "soft" ? "selected" : ""}>Soft</option></select></label>
              <button class="remove-task" type="button">Remove task</button>
            </div>
          </div>
        </div>`}
      </div>
      <div class="children">${task.dependencies.map(child => renderBranch(child, id, contextCategory, primary, visible, tasks, nextSeen)).join("")}</div>
    </div>`;
  }
  function render() {
    const tasks = taskMap();
    const primary = new Set(primaryIds());
    const visible = visibleIds(primary, tasks);
    const groups = [];
    if (grouping.value === "category") {
      for (const category of documentState.categories) {
        const membership = documentState.category_memberships.find(item => item.category === category.id);
        const candidates = (membership?.tasks || []).filter(id => primary.has(id));
        if (candidates.length) groups.push([category.display_name, roots(candidates, tasks), category.id]);
      }
    } else if (grouping.value === "priority") {
      for (const priority of [...priorities, ""]) {
        const candidates = [...primary].filter(id => (tasks.get(id).priority || "") === priority);
        if (candidates.length) groups.push([priority ? priority[0].toUpperCase() + priority.slice(1) : "Unprioritized", roots(candidates, tasks), null]);
      }
    } else {
      groups.push(["", roots(primary, tasks), null]);
    }
    checklist.innerHTML = groups.length ? groups.map(([label, ids, category]) => `<section class="check-group">${label ? `<h2 class="group-title">${escapeHtml(label)}</h2>` : ""}${ids.map(id => renderBranch(id, null, category, primary, visible, tasks)).join("")}</section>`).join("") : `<p class="empty">No tasks match these filters.</p>`;
    if (focusRequest) {
      const target = checklist.querySelector(`.task-row[data-id="${CSS.escape(focusRequest.id)}"] .${focusRequest.field}`);
      if (target) {
        target.focus();
        if (focusRequest.select) target.select();
        else if (target.setSelectionRange) target.setSelectionRange(target.value.length, target.value.length);
      }
      focusRequest = null;
    }
  }
  function renderFilters() {
    categoryFilters.querySelectorAll("button").forEach(button => button.remove());
    for (const category of documentState.categories) categoryFilters.insertAdjacentHTML("beforeend", `<button class="filter-chip" type="button" data-value="${escapeHtml(category.id)}" aria-pressed="false">${escapeHtml(category.display_name)}</button>`);
    priorityFilters.querySelectorAll("button").forEach(button => button.remove());
    for (const priority of priorities) priorityFilters.insertAdjacentHTML("beforeend", `<button class="filter-chip" type="button" data-value="${escapeHtml(priority)}" aria-pressed="false">${escapeHtml(priority[0].toUpperCase() + priority.slice(1))}</button>`);
    priorityFilters.insertAdjacentHTML("beforeend", `<button class="filter-chip" type="button" data-value="" aria-pressed="false">Unprioritized</button>`);
  }
  function showError(error) { message.textContent = error.message; message.hidden = false; saveStatus.textContent = "Not saved"; }
  function clearError() { message.hidden = true; message.textContent = ""; }
  async function requestJson(url, options = {}) {
    const response = await fetch(url, {headers: {"Content-Type": "application/json"}, ...options});
    const data = await response.json();
    if (!response.ok) { const error = new Error(data.error || "Save failed"); error.code = data.code; throw error; }
    return data;
  }
  function queueSave(operation, rerender = false) {
    saveStatus.textContent = "Saving…"; clearError();
    saveQueue = saveQueue.catch(() => {}).then(operation).then(data => {
      documentState = data.document; revision = data.revision; priorities = data.priorities;
      saveStatus.textContent = "Saved"; if (rerender) render(); return data;
    }).catch(error => { showError(error); throw error; });
    saveQueue.catch(() => {});
    return saveQueue;
  }
  function patchTask(id, fields, rerender = false) {
    return queueSave(() => requestJson(`/api/tasks/${encodeURIComponent(id)}`, {method: "PATCH", body: JSON.stringify({revision, ...fields})}), rerender);
  }
  function discardDraft(id) {
    documentState.tasks = documentState.tasks.filter(task => task.id !== id);
    for (const task of documentState.tasks) task.dependencies = task.dependencies.filter(child => child !== id);
    for (const membership of documentState.category_memberships) membership.tasks = membership.tasks.filter(taskId => taskId !== id);
    render();
  }
  function persistDraft(id) {
    const task = taskMap().get(id);
    if (!task?._draft || !task.name.trim()) return Promise.resolve(null);
    const realIds = new Set(documentState.tasks.filter(item => !item._draft).map(item => item.id));
    return queueSave(() => requestJson("/api/tasks", {method: "POST", body: JSON.stringify({
      revision,
      name: task.name.trim(),
      categories: task._categories,
      priority: task.priority || null,
      parent_id: task._parentId,
      after_id: task._afterId,
      context_category: task._contextCategory
    })}), false).then(data => {
      const created = data.document.tasks.find(item => !realIds.has(item.id)) || null;
      if (created) focusRequest = {id: created.id, field: "task-name"};
      render();
      return created;
    });
  }
  function closeMenus(except = null) {
    document.querySelectorAll(".menu-panel").forEach(panel => { if (panel !== except) panel.hidden = true; });
    document.querySelectorAll(".menu-toggle").forEach(button => { if (!except || button.nextElementSibling !== except) button.setAttribute("aria-expanded", "false"); });
  }
  function parseDue(row) {
    const raw = row.querySelector('[data-field="due"]').value.trim();
    const time = row.querySelector('[data-field="due-time"]').value.trim();
    const kind = row.querySelector('[data-field="deadline-kind"]').value || null;
    if (!raw) return {due: null, deadline_kind: null};
    const parts = raw.split("-").map(Number);
    if (!parts.length || parts.some(Number.isNaN) || parts.length > 3) throw new Error("Use YYYY, YYYY-MM, or YYYY-MM-DD for the due date");
    const due = {year: parts[0]};
    if (parts[1] !== undefined) due.month = parts[1];
    if (parts[2] !== undefined) due.day = parts[2];
    if (time) due.time = time;
    if (!kind) throw new Error("Choose hard or soft when setting a due date");
    return {due, deadline_kind: kind};
  }
  function addSibling(row) {
    const task = taskMap().get(row.dataset.id);
    const parentId = row.dataset.parent || null;
    const branch = row.closest(".branch");
    const contextCategory = branch.dataset.category || categoriesFor(task.id)[0] || null;
    const id = `draft-${crypto.randomUUID()}`;
    const categories = categoriesFor(task.id);
    const draft = {id, name: "", completed: false, dependencies: [], priority: task.priority, _draft: true, _categories: categories, _parentId: parentId, _afterId: task.id, _contextCategory: contextCategory};
    documentState.tasks.push(draft);
    for (const membership of documentState.category_memberships) {
      if (!categories.includes(membership.category)) continue;
      const position = membership.tasks.indexOf(task.id);
      membership.tasks.splice(position < 0 ? membership.tasks.length : position + 1, 0, id);
    }
    if (parentId) {
      const parent = taskMap().get(parentId);
      const position = parent.dependencies.indexOf(task.id);
      parent.dependencies.splice(position < 0 ? parent.dependencies.length : position + 1, 0, id);
    }
    focusRequest = {id, field: "task-name"};
    render();
  }
  function move(row, newParentId, afterId) {
    const branch = row.closest(".branch");
    return queueSave(() => requestJson(`/api/tasks/${encodeURIComponent(row.dataset.id)}/move`, {method: "POST", body: JSON.stringify({revision, old_parent_id: row.dataset.parent || null, new_parent_id: newParentId, after_id: afterId, context_category: branch.dataset.category || null})}), true);
  }

  categoryFilters.addEventListener("click", event => {
    const chip = event.target.closest(".filter-chip"); if (!chip) return;
    chip.getAttribute("aria-pressed") === "true" ? selectedCategories.delete(chip.dataset.value) : selectedCategories.add(chip.dataset.value);
    chip.setAttribute("aria-pressed", String(selectedCategories.has(chip.dataset.value))); render();
  });
  priorityFilters.addEventListener("click", event => {
    const chip = event.target.closest(".filter-chip"); if (!chip) return;
    chip.getAttribute("aria-pressed") === "true" ? selectedPriorities.delete(chip.dataset.value) : selectedPriorities.add(chip.dataset.value);
    chip.setAttribute("aria-pressed", String(selectedPriorities.has(chip.dataset.value))); render();
  });
  grouping.addEventListener("change", render);
  checklist.addEventListener("pointerdown", event => { if (!event.target.closest(".menu-panel") && !event.target.closest(".menu-toggle")) closeMenus(); }, true);
  document.addEventListener("pointerdown", event => { if (!event.target.closest(".menu-panel") && !event.target.closest(".menu-toggle")) closeMenus(); }, true);
  checklist.addEventListener("click", event => {
    const toggle = event.target.closest(".menu-toggle");
    if (toggle) { const panel = toggle.nextElementSibling; const opening = panel.hidden; closeMenus(panel); panel.hidden = !opening; toggle.setAttribute("aria-expanded", String(opening)); return; }
    const remove = event.target.closest(".remove-task");
    if (remove) { const row = remove.closest(".task-row"); if (confirm("Remove this task?")) queueSave(() => requestJson(`/api/tasks/${encodeURIComponent(row.dataset.id)}`, {method: "DELETE", body: JSON.stringify({revision})}), true); }
  });
  checklist.addEventListener("input", event => {
    const row = event.target.closest(".task-row"); if (!row) return;
    const id = row.dataset.id;
    if (!event.target.matches(".task-name, .task-description")) return;
    const task = taskMap().get(id);
    if (task._draft) {
      task.name = event.target.value;
      clearTimeout(timers.get(event.target));
      timers.set(event.target, setTimeout(() => persistDraft(id), 650));
      return;
    }
    clearTimeout(timers.get(event.target));
    timers.set(event.target, setTimeout(() => {
      const fields = event.target.matches(".task-name") ? {name: event.target.value} : {description: event.target.value || null};
      patchTask(id, fields);
    }, 650));
  });
  checklist.addEventListener("change", event => {
    const row = event.target.closest(".task-row"); if (!row) return;
    const id = row.dataset.id;
    if (event.target.matches(".task-check")) { patchTask(id, {completed: event.target.checked}).catch(() => { event.target.checked = !event.target.checked; }); return; }
    if (event.target.dataset.field === "priority") { patchTask(id, {priority: event.target.value || null}, true); return; }
    if (event.target.dataset.field === "categories") { patchTask(id, {categories: [...event.target.selectedOptions].map(option => option.value)}, true); return; }
    if (["due", "due-time", "deadline-kind"].includes(event.target.dataset.field)) {
      try { patchTask(id, parseDue(row), true); } catch (error) { showError(error); }
    }
  });
  checklist.addEventListener("keydown", event => {
    if (event.key === "Escape" && !event.target.matches(".task-name")) { closeMenus(); return; }
    if (!event.target.matches(".task-name")) return;
    const row = event.target.closest(".task-row");
    const task = taskMap().get(row.dataset.id);
    if ((event.key === "Backspace" || event.key === "Escape") && task._draft && !event.target.value) {
      event.preventDefault(); discardDraft(task.id); return;
    }
    if (event.key === "Enter" && event.shiftKey) { event.preventDefault(); openDescriptions.add(row.dataset.id); focusRequest = {id: row.dataset.id, field: "task-description"}; render(); return; }
    if (event.key === "Enter") {
      event.preventDefault();
      if (task._draft) {
        clearTimeout(timers.get(event.target));
        task.name = event.target.value;
        persistDraft(task.id).then(created => {
          if (!created) return;
          const createdRow = checklist.querySelector(`.task-row[data-id="${CSS.escape(created.id)}"]`);
          if (createdRow) addSibling(createdRow);
        });
      } else addSibling(row);
      return;
    }
    if (event.key === "Tab" && event.shiftKey) {
      event.preventDefault(); const branch = row.closest(".branch"); const parentBranch = branch.parentElement.closest(".branch");
      if (parentBranch) move(row, parentBranch.dataset.parent || null, parentBranch.dataset.id);
      return;
    }
    if (event.key === "Tab") {
      event.preventDefault(); const branch = row.closest(".branch"); const previous = branch.previousElementSibling;
      if (previous?.matches(".branch")) move(row, previous.dataset.id, null);
    }
  });

  requestJson("/api/todo").then(data => {
    documentState = data.document; revision = data.revision; priorities = data.priorities;
    renderFilters(); render(); saveStatus.textContent = "Saved"; app.setAttribute("aria-busy", "false");
  }).catch(showError);
})();
