(() => {
  "use strict";

  const app = document.getElementById("todo-app");
  const firstRun = document.getElementById("first-run");
  const editor = document.getElementById("editor");
  const createListForm = document.getElementById("create-list-form");
  const listDate = document.getElementById("list-date");
  const creationCategories = document.getElementById("creation-categories");
  const addCreationCategory = document.getElementById("add-creation-category");
  const checklist = document.getElementById("checklist");
  const categoryFilters = document.getElementById("category-filters");
  const priorityFilters = document.getElementById("priority-filters");
  const grouping = document.getElementById("grouping");
  const sorting = document.getElementById("sorting");
  const manageCategories = document.getElementById("manage-categories");
  const categoryDialog = document.getElementById("category-dialog");
  const categoryEditor = document.getElementById("category-editor");
  const addListCategory = document.getElementById("add-list-category");
  const deleteDialog = document.getElementById("delete-dialog");
  const deleteContext = document.getElementById("delete-context");
  const detachTaskButton = document.getElementById("detach-task");
  const confirmDeleteTask = document.getElementById("confirm-delete-task");
  const cancelDelete = document.getElementById("cancel-delete");
  const saveStatus = document.getElementById("save-status");
  const message = document.getElementById("message");
  const dropIndicator = document.createElement("div");
  dropIndicator.className = "drop-indicator";
  dropIndicator.hidden = true;
  let documentState;
  let revision;
  let priorities = [];
  let saveQueue = Promise.resolve();
  let focusRequest = null;
  const selectedCategories = new Set();
  const selectedPriorities = new Set();
  const openDescriptions = new Set();
  const timers = new Map();
  let pendingDeletion = null;
  let draggedTask = null;
  let pendingDrop = null;

  const escapeHtml = value => String(value).replace(/[&<>"]/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;"
  })[character]);

  function inlineMarkup(value) {
    return String(value).split("`").map((part, index) =>
      index % 2 ? `<code>${escapeHtml(part)}</code>` : escapeHtml(part)
    ).join("");
  }

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
  function duePrecision(task) {
    if (!task.due) return "none";
    if (task.due.day !== undefined) return "day";
    if (task.due.month !== undefined) return "month";
    return "year";
  }
  function dueInput(task) {
    const precision = duePrecision(task);
    const value = dueText(task).split(" ")[0];
    if (precision === "year") return `<input data-field="due-value" type="number" min="1" max="9999" value="${escapeHtml(value)}" placeholder="YYYY">`;
    if (precision === "month") return `<input data-field="due-value" type="month" value="${escapeHtml(value)}">`;
    if (precision === "day") return `<input data-field="due-value" type="date" value="${escapeHtml(value)}">`;
    return `<input data-field="due-value" type="text" value="" disabled aria-label="No due date">`;
  }
  function effectiveDue(task) {
    if (!task.due) return null;
    const year = task.due.year;
    const month = task.due.month || 12;
    const day = task.due.day || new Date(Date.UTC(year, month, 0)).getUTCDate();
    const [hour, minute] = task.due.time ? task.due.time.split(":").map(Number) : [23, 59];
    return Date.UTC(year, month - 1, day, hour, minute);
  }
  function sortedIds(ids, tasks) {
    if (sorting.value === "manual") return [...ids];
    const direction = sorting.value === "due-asc" ? 1 : -1;
    return [...ids].map((id, index) => ({id, index, due: effectiveDue(tasks.get(id))})).sort((left, right) => {
      if (left.due === null && right.due === null) return left.index - right.index;
      if (left.due === null) return 1;
      if (right.due === null) return -1;
      return direction * (left.due - right.due) || left.index - right.index;
    }).map(item => item.id);
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
      <div class="task-row ${primary.has(id) ? "" : "contextual"}" data-id="${id}" data-parent="${parentId || ""}" data-category="${contextCategory || categories[0] || ""}">
        ${draft ? `<span class="drag-spacer"></span>` : `<button type="button" class="drag-handle" draggable="${sorting.value === "manual"}" aria-label="Drag to move ${escapeHtml(task.name)}" title="${sorting.value === "manual" ? "Drag to move task" : "Switch to manual sorting to drag"}">⋮⋮</button>`}
        <input class="task-check" type="checkbox" aria-label="Mark ${escapeHtml(task.name || "new task")} complete" ${task.completed ? "checked" : ""} ${draft ? "disabled" : ""}>
        <div class="task-fields">
          <div class="task-heading">
            <button type="button" class="task-rendered task-name-rendered" ${draft ? "hidden" : ""} aria-label="Edit task name">${inlineMarkup(task.name)}</button>
            <input class="task-name" value="${escapeHtml(task.name)}" placeholder="New task" aria-label="Task name" ${draft ? "" : "hidden"}>
            ${draft ? "" : `<div class="task-menu"><button class="menu-toggle" type="button" aria-label="Task options" aria-expanded="false">···</button>
              <div class="menu-panel" hidden>
                <label>Priority<select data-field="priority">${priorityOptions}</select></label>
                <label>Categories<select data-field="categories" multiple>${categoryOptions(categories)}</select></label>
                <fieldset class="due-controls">
                  <legend>Deadline</legend>
                  <label>Precision<select data-field="due-precision"><option value="none" ${!task.due ? "selected" : ""}>No deadline</option><option value="year" ${duePrecision(task) === "year" ? "selected" : ""}>Year</option><option value="month" ${duePrecision(task) === "month" ? "selected" : ""}>Month</option><option value="day" ${duePrecision(task) === "day" ? "selected" : ""}>Day</option></select></label>
                  <label class="due-value-label">Date${dueInput(task)}</label>
                  <label class="due-time-label" ${duePrecision(task) === "day" ? "" : "hidden"}>Time (optional)<input data-field="due-time" type="time" value="${escapeHtml(task.due?.time || "")}"></label>
                  <label class="deadline-kind-label" ${task.due ? "" : "hidden"}>Kind<select data-field="deadline-kind"><option value="soft" ${task.deadline_kind === "soft" ? "selected" : ""}>Soft</option><option value="hard" ${task.deadline_kind === "hard" ? "selected" : ""}>Hard</option></select></label>
                </fieldset>
                <button class="remove-task" type="button">Remove task</button>
              </div>
            </div>`}
          </div>
          ${descriptionShown ? `<button type="button" class="task-rendered task-description-rendered" aria-label="Edit task description" ${task.description ? "" : "hidden"}>${inlineMarkup(task.description || "")}</button><input class="task-description" value="${escapeHtml(task.description || "")}" placeholder="Description" aria-label="Task description" ${task.description ? "hidden" : ""}>` : ""}
        </div>
        ${draft ? `<div class="task-meta"></div>` : `<div class="task-meta">${grouping.value !== "priority" ? `<span class="priority-indicator">${escapeHtml(task.priority ? task.priority[0].toUpperCase() + task.priority.slice(1) : "Unprioritized")}</span>` : ""}${task.due ? `<span class="due ${task.deadline_kind || ""}">${escapeHtml(dueText(task))}</span>` : ""}</div>`}
      </div>
      <div class="children">${sortedIds(task.dependencies, tasks).map(child => renderBranch(child, id, contextCategory, primary, visible, tasks, nextSeen)).join("")}</div>
    </div>`;
  }
  function renderEmptyCategory(categoryId) {
    if (selectedPriorities.size > 1) return `<p class="empty">Select one priority to add a task here.</p>`;
    const priority = selectedPriorities.size === 1 ? [...selectedPriorities][0] : "";
    return `<div class="empty-category-row" data-category="${escapeHtml(categoryId)}" data-priority="${escapeHtml(priority)}">
      <input class="empty-category-name" placeholder="New task" aria-label="New task in ${escapeHtml(categoryMap().get(categoryId).display_name)}">
    </div>`;
  }
  function activeEditorState() {
    const input = document.activeElement;
    if (!input?.matches?.(".task-name, .task-description")) return null;
    const row = input.closest(".task-row");
    return {
      id: row.dataset.id,
      parentId: row.dataset.parent || null,
      category: row.dataset.category || null,
      field: input.matches(".task-name") ? "task-name" : "task-description",
      value: input.value,
      selectionStart: input.selectionStart,
      selectionEnd: input.selectionEnd
    };
  }
  function restoreEditor(state) {
    const parent = CSS.escape(state.parentId || "");
    const category = CSS.escape(state.category || "");
    const target = checklist.querySelector(`.task-row[data-id="${CSS.escape(state.id)}"][data-parent="${parent}"][data-category="${category}"] .${state.field}`)
      || checklist.querySelector(`.task-row[data-id="${CSS.escape(state.id)}"] .${state.field}`);
    if (!target) return;
    const rendered = target.parentElement.querySelector(state.field === "task-name" ? ".task-name-rendered" : ".task-description-rendered");
    if (rendered) rendered.hidden = true;
    target.hidden = false;
    if (state.value !== undefined) target.value = state.value;
    target.focus();
    if (state.select) target.select();
    else if (target.setSelectionRange) {
      const start = state.selectionStart ?? target.value.length;
      const end = state.selectionEnd ?? start;
      target.setSelectionRange(start, end);
    }
  }
  function render() {
    const activeEditor = activeEditorState();
    const tasks = taskMap();
    const primary = new Set(primaryIds());
    const visible = visibleIds(primary, tasks);
    const groups = [];
    if (grouping.value === "category") {
      for (const category of documentState.categories) {
        if (selectedCategories.size && !selectedCategories.has(category.id)) continue;
        const membership = documentState.category_memberships.find(item => item.category === category.id);
        const candidates = (membership?.tasks || []).filter(id => primary.has(id));
        groups.push([category.display_name, sortedIds(roots(candidates, tasks), tasks), category.id]);
      }
    } else if (grouping.value === "priority") {
      for (const priority of [...priorities, ""]) {
        const candidates = [...primary].filter(id => (tasks.get(id).priority || "") === priority);
        if (candidates.length) groups.push([priority ? priority[0].toUpperCase() + priority.slice(1) : "Unprioritized", sortedIds(roots(candidates, tasks), tasks), null]);
      }
    } else {
      groups.push(["", sortedIds(roots(primary, tasks), tasks), null]);
    }
    checklist.innerHTML = groups.length ? groups.map(([label, ids, category]) => `<section class="check-group">${label ? `<h2 class="group-title">${escapeHtml(label)}</h2>` : ""}${ids.length ? ids.map(id => renderBranch(id, null, category, primary, visible, tasks)).join("") : category ? renderEmptyCategory(category) : `<p class="empty">No tasks match these filters.</p>`}</section>`).join("") : `<p class="empty">No tasks match these filters.</p>`;
    checklist.append(dropIndicator);
    const editorToRestore = focusRequest || activeEditor;
    if (editorToRestore) restoreEditor(editorToRestore);
    focusRequest = null;
  }
  function renderFilters() {
    categoryFilters.querySelectorAll("button").forEach(button => button.remove());
    for (const category of documentState.categories) categoryFilters.insertAdjacentHTML("beforeend", `<button class="filter-chip" type="button" data-value="${escapeHtml(category.id)}" aria-pressed="false">${escapeHtml(category.display_name)}</button>`);
    priorityFilters.querySelectorAll("button").forEach(button => button.remove());
    for (const priority of priorities) priorityFilters.insertAdjacentHTML("beforeend", `<button class="filter-chip" type="button" data-value="${escapeHtml(priority)}" aria-pressed="false">${escapeHtml(priority[0].toUpperCase() + priority.slice(1))}</button>`);
    priorityFilters.insertAdjacentHTML("beforeend", `<button class="filter-chip" type="button" data-value="" aria-pressed="false">Unprioritized</button>`);
  }
  function renderCategoryEditor() {
    categoryEditor.innerHTML = documentState.categories.map(category => `<div class="category-editor-row" data-id="${escapeHtml(category.id)}">
      <input value="${escapeHtml(category.display_name)}" aria-label="Category name">
      <button type="button" data-action="up" aria-label="Move ${escapeHtml(category.display_name)} up">↑</button>
      <button type="button" data-action="down" aria-label="Move ${escapeHtml(category.display_name)} down">↓</button>
      <button type="button" data-action="remove" aria-label="Remove ${escapeHtml(category.display_name)}">×</button>
    </div>`).join("");
  }
  function showError(error) {
    if (error.code === "task_required" && error.details?.blockers && documentState) {
      const categories = categoryMap();
      const blockers = error.details.blockers.map(blocker => {
        const context = [
          blocker.categories.map(id => categories.get(id)?.display_name || id).join(", "),
          blocker.priority ? blocker.priority[0].toUpperCase() + blocker.priority.slice(1) : "Unprioritized"
        ].filter(Boolean).join(" · ");
        return `${blocker.name}${context ? ` (${context})` : ""}`;
      });
      message.textContent = `Cannot delete this task. Outdent it from: ${blockers.join("; ")}.`;
    } else message.textContent = error.message;
    message.hidden = false; saveStatus.textContent = "Not saved";
  }
  function clearError() { message.hidden = true; message.textContent = ""; }
  async function requestJson(url, options = {}) {
    const response = await fetch(url, {headers: {"Content-Type": "application/json"}, ...options});
    const data = await response.json();
    if (!response.ok) { const error = new Error(data.error || "Save failed"); error.code = data.code; error.details = data; throw error; }
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
  function persistDraft(id, restoreFocus = true) {
    const task = taskMap().get(id);
    if (!task?._draft || !task.name.trim()) return Promise.resolve(null);
    if (task._persistPromise) return task._persistPromise;
    task._persistPromise = queueSave(() => requestJson("/api/tasks", {method: "POST", body: JSON.stringify({
      revision,
      name: task.name.trim(),
      categories: task._categories,
      priority: task.priority || null,
      parent_id: task._parentId,
      after_id: task._afterId,
      context_category: task._contextCategory
    })}), false).then(data => {
      const created = data.document.tasks.find(item => item.id === data.created_id) || null;
      if (created && restoreFocus) focusRequest = {id: created.id, field: "task-name", parentId: task._parentId, category: task._contextCategory};
      render();
      return created;
    });
    return task._persistPromise;
  }
  function persistEmptyCategory(row, restoreFocus = true) {
    const name = row.querySelector(".empty-category-name").value.trim();
    if (!name) return Promise.resolve(null);
    if (row._persistPromise) return row._persistPromise;
    const category = row.dataset.category;
    const priority = row.dataset.priority || null;
    row._persistPromise = queueSave(() => requestJson("/api/tasks", {method: "POST", body: JSON.stringify({
      revision, name, categories: [category], priority,
      parent_id: null, after_id: null, context_category: category
    })}), false).then(data => {
      const created = data.document.tasks.find(item => item.id === data.created_id) || null;
      if (created && restoreFocus) focusRequest = {id: created.id, field: "task-name", parentId: null, category};
      render();
      return created;
    });
    return row._persistPromise;
  }
  function closeMenus(except = null) {
    document.querySelectorAll(".menu-panel").forEach(panel => { if (panel !== except) panel.hidden = true; });
    document.querySelectorAll(".menu-toggle").forEach(button => { if (!except || button.nextElementSibling !== except) button.setAttribute("aria-expanded", "false"); });
  }
  function parseDue(row) {
    const precision = row.querySelector('[data-field="due-precision"]').value;
    if (precision === "none") return {due: null, deadline_kind: null};
    const raw = row.querySelector('[data-field="due-value"]').value.trim();
    const time = row.querySelector('[data-field="due-time"]').value.trim();
    const kind = row.querySelector('[data-field="deadline-kind"]').value;
    if (!raw) throw new Error(`Choose a ${precision} for the deadline.`);
    const parts = raw.split("-").map(Number);
    const expectedParts = {year: 1, month: 2, day: 3}[precision];
    if (parts.length !== expectedParts || parts.some(Number.isNaN)) throw new Error(`Choose a valid ${precision}.`);
    const due = {year: parts[0]};
    if (parts[1] !== undefined) due.month = parts[1];
    if (parts[2] !== undefined) due.day = parts[2];
    if (precision === "day" && time) due.time = time;
    return {due, deadline_kind: kind};
  }

  function configureDueControls(row) {
    const precision = row.querySelector('[data-field="due-precision"]').value;
    const label = row.querySelector(".due-value-label");
    const previous = label.querySelector('[data-field="due-value"]')?.value || "";
    const types = {none: "text", year: "number", month: "month", day: "date"};
    label.innerHTML = `Date<input data-field="due-value" type="${types[precision]}" ${precision === "year" ? 'min="1" max="9999" placeholder="YYYY"' : ""} ${precision === "none" ? "disabled" : ""}>`;
    const input = label.querySelector('[data-field="due-value"]');
    if (precision !== "none" && previous) input.value = previous;
    row.querySelector(".due-time-label").hidden = precision !== "day";
    row.querySelector(".deadline-kind-label").hidden = precision === "none";
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
    focusRequest = {id, field: "task-name", parentId, category: contextCategory};
    render();
  }
  function move(row, newParentId, afterId, beforeId = null, contextCategory = null) {
    const branch = row.closest(".branch");
    return queueSave(() => requestJson(`/api/tasks/${encodeURIComponent(row.dataset.id)}/move`, {method: "POST", body: JSON.stringify({revision, old_parent_id: row.dataset.parent || null, new_parent_id: newParentId, after_id: afterId, before_id: beforeId, context_category: contextCategory || branch.dataset.category || null})}), true);
  }

  function clearDropIndicators() {
    dropIndicator.hidden = true;
    pendingDrop = null;
  }
  function dropPosition(row, clientY) {
    const bounds = row.getBoundingClientRect();
    const fraction = (clientY - bounds.top) / bounds.height;
    return fraction < .3 ? "before" : fraction > .7 ? "after" : "child";
  }
  function showDropIndicator(row, position) {
    const checklistBounds = checklist.getBoundingClientRect();
    const rowBounds = row.getBoundingClientRect();
    const branchBounds = row.closest(".branch").getBoundingClientRect();
    const indent = position === "child" ? 28 : 0;
    const left = rowBounds.left - checklistBounds.left + indent;
    const top = (position === "before" ? rowBounds.top : branchBounds.bottom) - checklistBounds.top;
    dropIndicator.style.left = `${left}px`;
    dropIndicator.style.top = `${top}px`;
    dropIndicator.style.width = `${Math.max(24, checklistBounds.right - rowBounds.left - indent)}px`;
    dropIndicator.hidden = false;
    pendingDrop = {
      newParentId: position === "child" ? row.dataset.id : row.dataset.parent || null,
      afterId: position === "after" ? row.dataset.id : null,
      beforeId: position === "before" ? row.dataset.id : null,
      category: row.dataset.category
    };
  }
  function moveDragged(newParentId, afterId, beforeId, contextCategory) {
    if (!draggedTask) return;
    const source = checklist.querySelector(`.task-row[data-id="${CSS.escape(draggedTask.id)}"][data-parent="${CSS.escape(draggedTask.parentId || "")}"][data-category="${CSS.escape(draggedTask.category || "")}"]`)
      || checklist.querySelector(`.task-row[data-id="${CSS.escape(draggedTask.id)}"]`);
    if (!source) return;
    if (!newParentId && !categoriesFor(draggedTask.id).includes(contextCategory)) {
      showError(new Error("Assign this task to the destination category before moving it there."));
      return;
    }
    move(source, newParentId, afterId, beforeId, contextCategory);
  }
  function reorderTask(row, offset) {
    if (sorting.value !== "manual") { showError(new Error("Switch to manual sorting before reordering tasks.")); return; }
    const task = taskMap().get(row.dataset.id);
    if (task._draft) {
      const siblings = task._parentId
        ? taskMap().get(task._parentId).dependencies
        : documentState.category_memberships.find(item => item.category === task._contextCategory).tasks;
      const index = siblings.indexOf(task.id);
      const target = Math.max(0, Math.min(siblings.length - 1, index + offset));
      siblings.splice(index, 1); siblings.splice(target, 0, task.id);
      focusRequest = {id: task.id, field: "task-name", parentId: task._parentId, category: task._contextCategory};
      render(); return;
    }
    queueSave(() => requestJson(`/api/tasks/${encodeURIComponent(task.id)}/reorder`, {method: "POST", body: JSON.stringify({
      revision, parent_id: row.dataset.parent || null, category_id: row.dataset.category || null, offset
    })}), true);
  }
  function indentDraft(row) {
    const task = taskMap().get(row.dataset.id);
    const branch = row.closest(".branch");
    const previous = branch.previousElementSibling;
    if (!previous?.matches(".branch")) return;
    const newParent = taskMap().get(previous.dataset.id);
    if (newParent._draft) { showError(new Error("Name the preceding task before nesting beneath it.")); return; }
    if (task._parentId) taskMap().get(task._parentId).dependencies = taskMap().get(task._parentId).dependencies.filter(id => id !== task.id);
    task._parentId = newParent.id; task._afterId = null;
    if (!newParent.dependencies.includes(task.id)) newParent.dependencies.push(task.id);
    focusRequest = {id: task.id, field: "task-name", parentId: newParent.id, category: task._contextCategory};
    render();
  }
  function outdentDraft(row) {
    const task = taskMap().get(row.dataset.id);
    if (!task._parentId) return;
    const oldParentId = task._parentId;
    const parentBranch = row.closest(".branch").parentElement.closest(".branch");
    const grandparentId = parentBranch?.dataset.parent || null;
    taskMap().get(oldParentId).dependencies = taskMap().get(oldParentId).dependencies.filter(id => id !== task.id);
    task._parentId = grandparentId; task._afterId = oldParentId;
    if (grandparentId) {
      const siblings = taskMap().get(grandparentId).dependencies;
      siblings.splice(siblings.indexOf(oldParentId) + 1, 0, task.id);
    }
    focusRequest = {id: task.id, field: "task-name", parentId: grandparentId, category: task._contextCategory};
    render();
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
  sorting.addEventListener("change", render);
  checklist.addEventListener("dragstart", event => {
    const handle = event.target.closest(".drag-handle");
    if (!handle || sorting.value !== "manual") { event.preventDefault(); return; }
    const row = handle.closest(".task-row");
    draggedTask = {id: row.dataset.id, parentId: row.dataset.parent || null, category: row.dataset.category || null};
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", row.dataset.id);
    requestAnimationFrame(() => row.classList.add("dragging"));
  });
  checklist.addEventListener("dragover", event => {
    if (!draggedTask || sorting.value !== "manual") return;
    const row = event.target.closest(".task-row");
    if (!row || row.dataset.id === draggedTask.id) { clearDropIndicators(); return; }
    event.preventDefault(); event.dataTransfer.dropEffect = "move";
    showDropIndicator(row, dropPosition(row, event.clientY));
  });
  checklist.addEventListener("dragleave", event => {
    if (!checklist.contains(event.relatedTarget)) clearDropIndicators();
  });
  checklist.addEventListener("drop", event => {
    if (!draggedTask || !pendingDrop) return;
    event.preventDefault();
    moveDragged(
      pendingDrop.newParentId,
      pendingDrop.afterId,
      pendingDrop.beforeId,
      pendingDrop.category
    );
    clearDropIndicators();
  });
  checklist.addEventListener("dragend", () => {
    clearDropIndicators();
    checklist.querySelectorAll(".dragging").forEach(element => element.classList.remove("dragging"));
    draggedTask = null;
  });
  checklist.addEventListener("pointerdown", event => { if (!event.target.closest(".menu-panel") && !event.target.closest(".menu-toggle")) closeMenus(); }, true);
  document.addEventListener("pointerdown", event => { if (!event.target.closest(".menu-panel") && !event.target.closest(".menu-toggle")) closeMenus(); }, true);
  checklist.addEventListener("click", event => {
    const rendered = event.target.closest(".task-rendered");
    if (rendered) {
      const input = rendered.parentElement.querySelector(rendered.matches(".task-name-rendered") ? ".task-name" : ".task-description");
      rendered.hidden = true; input.hidden = false; input.focus();
      input.setSelectionRange(input.value.length, input.value.length);
      return;
    }
    const toggle = event.target.closest(".menu-toggle");
    if (toggle) { const panel = toggle.nextElementSibling; const opening = panel.hidden; closeMenus(panel); panel.hidden = !opening; toggle.setAttribute("aria-expanded", String(opening)); return; }
    const remove = event.target.closest(".remove-task");
    if (remove) {
      const row = remove.closest(".task-row");
      const task = taskMap().get(row.dataset.id);
      pendingDeletion = {id: task.id, parentId: row.dataset.parent || null, category: row.dataset.category || null};
      deleteContext.textContent = `${task.name} · ${task.priority ? task.priority[0].toUpperCase() + task.priority.slice(1) : "Unprioritized"}`;
      detachTaskButton.hidden = !pendingDeletion.parentId;
      deleteDialog.showModal();
    }
  });
  cancelDelete.addEventListener("click", () => deleteDialog.close());
  deleteDialog.addEventListener("click", event => { if (event.target === deleteDialog) deleteDialog.close(); });
  detachTaskButton.addEventListener("click", () => {
    if (!pendingDeletion?.parentId) return;
    queueSave(() => requestJson(`/api/tasks/${encodeURIComponent(pendingDeletion.id)}/detach`, {method: "POST", body: JSON.stringify({revision, parent_id: pendingDeletion.parentId})}), true)
      .then(() => deleteDialog.close());
  });
  confirmDeleteTask.addEventListener("click", () => {
    if (!pendingDeletion) return;
    queueSave(() => requestJson(`/api/tasks/${encodeURIComponent(pendingDeletion.id)}`, {method: "DELETE", body: JSON.stringify({revision})}), true)
      .then(() => deleteDialog.close());
  });
  manageCategories.addEventListener("click", () => { renderCategoryEditor(); categoryDialog.showModal(); });
  categoryDialog.addEventListener("click", event => { if (event.target === categoryDialog) categoryDialog.close(); });
  categoryEditor.addEventListener("change", event => {
    if (!event.target.matches("input") || event.target.closest(".new-category")) return;
    const row = event.target.closest(".category-editor-row");
    queueSave(() => requestJson(`/api/categories/${encodeURIComponent(row.dataset.id)}`, {method: "PATCH", body: JSON.stringify({revision, display_name: event.target.value})}), false)
      .then(() => { renderFilters(); render(); renderCategoryEditor(); });
  });
  categoryEditor.addEventListener("click", event => {
    const button = event.target.closest("button"); if (!button) return;
    if (button.dataset.action === "save-new") return;
    const row = button.closest(".category-editor-row");
    if (button.dataset.action === "remove") {
      queueSave(() => requestJson(`/api/categories/${encodeURIComponent(row.dataset.id)}`, {method: "DELETE", body: JSON.stringify({revision})}), false)
        .then(() => { selectedCategories.delete(row.dataset.id); renderFilters(); render(); renderCategoryEditor(); });
    } else {
      const offset = button.dataset.action === "up" ? -1 : 1;
      queueSave(() => requestJson(`/api/categories/${encodeURIComponent(row.dataset.id)}`, {method: "PATCH", body: JSON.stringify({revision, offset})}), false)
        .then(() => { renderFilters(); render(); renderCategoryEditor(); });
    }
  });
  addListCategory.addEventListener("click", () => {
    categoryEditor.insertAdjacentHTML("beforeend", `<div class="category-editor-row new-category">
      <input class="new-category-name" placeholder="Category name" aria-label="New category name">
      <input class="new-category-id" placeholder="category-id" aria-label="New category ID">
      <button type="button" data-action="save-new">Add</button><span></span>
    </div>`);
    categoryEditor.querySelector(".new-category:last-child .new-category-name").focus();
  });
  categoryEditor.addEventListener("input", event => {
    if (!event.target.matches(".new-category-name")) return;
    const id = event.target.closest(".new-category").querySelector(".new-category-id");
    if (!id.dataset.manual) id.value = categorySlug(event.target.value);
  });
  categoryEditor.addEventListener("input", event => {
    if (event.target.matches(".new-category-id")) event.target.dataset.manual = "true";
  });
  categoryEditor.addEventListener("click", event => {
    const button = event.target.closest('[data-action="save-new"]'); if (!button) return;
    const row = button.closest(".new-category");
    queueSave(() => requestJson("/api/categories", {method: "POST", body: JSON.stringify({
      revision, id: row.querySelector(".new-category-id").value, display_name: row.querySelector(".new-category-name").value
    })}), false).then(() => { renderFilters(); render(); renderCategoryEditor(); });
  });
  checklist.addEventListener("input", event => {
    const emptyRow = event.target.closest(".empty-category-row");
    if (emptyRow && event.target.matches(".empty-category-name")) {
      return;
    }
    const row = event.target.closest(".task-row"); if (!row) return;
    const id = row.dataset.id;
    if (!event.target.matches(".task-name, .task-description")) return;
    const task = taskMap().get(id);
    if (task._draft) {
      task.name = event.target.value;
      return;
    }
    if (event.target.matches(".task-name")) task.name = event.target.value;
    else if (event.target.value) task.description = event.target.value;
    else delete task.description;
    const timerKey = `${id}:${event.target.matches(".task-name") ? "name" : "description"}`;
    clearTimeout(timers.get(timerKey));
    timers.set(timerKey, setTimeout(() => {
      const fields = event.target.matches(".task-name") ? {name: event.target.value} : {description: event.target.value || null};
      patchTask(id, fields);
    }, 650));
  });
  checklist.addEventListener("focusout", event => {
    const emptyRow = event.target.closest(".empty-category-row");
    if (emptyRow && event.target.matches(".empty-category-name")) {
      persistEmptyCategory(emptyRow, false);
      return;
    }
    if (!event.target.matches(".task-name, .task-description")) return;
    const input = event.target;
    const row = input.closest(".task-row");
    const id = row.dataset.id;
    const task = taskMap().get(id);
    if (task?._draft) {
      task.name = input.value;
      persistDraft(id, false);
      return;
    }
    const field = input.matches(".task-name") ? "name" : "description";
    const timerKey = `${id}:${field}`;
    clearTimeout(timers.get(timerKey));
    timers.delete(timerKey);
    if (field === "description" && !input.value.trim()) {
      openDescriptions.delete(id);
      delete task.description;
      patchTask(id, {description: null});
      input.parentElement.querySelector(".task-description-rendered")?.remove();
      input.remove();
      return;
    }
    if (field === "description") openDescriptions.delete(id);
    patchTask(id, field === "name" ? {name: input.value} : {description: input.value});
    const rendered = input.parentElement.querySelector(input.matches(".task-name") ? ".task-name-rendered" : ".task-description-rendered");
    if (!rendered) return;
    rendered.innerHTML = inlineMarkup(input.value);
    input.hidden = true; rendered.hidden = false;
  });
  checklist.addEventListener("change", event => {
    const row = event.target.closest(".task-row"); if (!row) return;
    const id = row.dataset.id;
    if (event.target.matches(".task-check")) { patchTask(id, {completed: event.target.checked}).catch(() => { event.target.checked = !event.target.checked; }); return; }
    if (event.target.dataset.field === "priority") { patchTask(id, {priority: event.target.value || null}, true); return; }
    if (event.target.dataset.field === "categories") { patchTask(id, {categories: [...event.target.selectedOptions].map(option => option.value)}, true); return; }
    if (event.target.dataset.field === "due-precision") {
      configureDueControls(row);
      if (event.target.value === "none") patchTask(id, {due: null, deadline_kind: null}, true);
      else row.querySelector('[data-field="due-value"]').focus();
      return;
    }
    if (["due-value", "due-time", "deadline-kind"].includes(event.target.dataset.field)) {
      try { patchTask(id, parseDue(row), true); } catch (error) { showError(error); }
    }
  });
  checklist.addEventListener("keydown", event => {
    const emptyRow = event.target.closest(".empty-category-row");
    if (emptyRow && event.target.matches(".empty-category-name") && event.key === "Enter") {
      event.preventDefault();
      persistEmptyCategory(emptyRow, false).then(created => {
        if (!created) return;
        const createdRow = checklist.querySelector(`.task-row[data-id="${CSS.escape(created.id)}"]`);
        if (createdRow) addSibling(createdRow);
      });
      return;
    }
    if (event.target.matches(".task-description") && event.key === "Escape" && !event.target.value) {
      event.preventDefault(); event.target.blur(); return;
    }
    if (event.key === "Escape" && !event.target.matches(".task-name")) { closeMenus(); return; }
    if (!event.target.matches(".task-name")) return;
    const row = event.target.closest(".task-row");
    const task = taskMap().get(row.dataset.id);
    if (event.altKey && event.key === "ArrowUp") { event.preventDefault(); reorderTask(row, -1); return; }
    if (event.altKey && event.key === "ArrowDown") { event.preventDefault(); reorderTask(row, 1); return; }
    if ((event.key === "Backspace" || event.key === "Escape") && task._draft && !event.target.value) {
      event.preventDefault(); discardDraft(task.id); return;
    }
    if (event.key === "Enter" && event.shiftKey) {
      event.preventDefault(); openDescriptions.add(row.dataset.id);
      focusRequest = {id: row.dataset.id, field: "task-description", parentId: row.dataset.parent || null, category: row.dataset.category || null};
      render(); return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      if (task._draft) {
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
      if (task._draft) { event.preventDefault(); outdentDraft(row); return; }
      event.preventDefault(); const branch = row.closest(".branch"); const parentBranch = branch.parentElement.closest(".branch");
      if (parentBranch) move(row, parentBranch.dataset.parent || null, parentBranch.dataset.id);
      return;
    }
    if (event.key === "Tab") {
      if (task._draft) { event.preventDefault(); indentDraft(row); return; }
      event.preventDefault(); const branch = row.closest(".branch"); const previous = branch.previousElementSibling;
      if (previous?.matches(".branch")) move(row, previous.dataset.id, null);
    }
  });

  function startEditor(data) {
    documentState = data.document; revision = data.revision; priorities = data.priorities;
    firstRun.hidden = true; editor.hidden = false;
    renderFilters(); render(); saveStatus.textContent = "Saved"; app.setAttribute("aria-busy", "false");
  }
  function showCreation(data) {
    priorities = data.priorities;
    listDate.value = data.default_date;
    creationCategories.innerHTML = "";
    editor.hidden = true; firstRun.hidden = false; app.setAttribute("aria-busy", "false");
    addCreationCategoryRow();
  }
  function categorySlug(name) {
    return name.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  }
  function addCreationCategoryRow(name = "", id = "") {
    creationCategories.insertAdjacentHTML("beforeend", `<div class="creation-category">
      <input class="creation-category-name" value="${escapeHtml(name)}" placeholder="Category name" aria-label="Category name">
      <input class="creation-category-id" value="${escapeHtml(id)}" placeholder="category-id" aria-label="Category ID">
    </div>`);
    creationCategories.querySelector(".creation-category:last-child .creation-category-name").focus();
  }
  addCreationCategory.addEventListener("click", () => addCreationCategoryRow());
  creationCategories.addEventListener("input", event => {
    if (!event.target.matches(".creation-category-name")) return;
    const id = event.target.closest(".creation-category").querySelector(".creation-category-id");
    if (!id.dataset.manual) id.value = categorySlug(event.target.value);
  });
  creationCategories.addEventListener("input", event => {
    if (event.target.matches(".creation-category-id")) event.target.dataset.manual = "true";
  });
  creationCategories.addEventListener("keydown", event => {
    if (event.key === "Enter") { event.preventDefault(); addCreationCategoryRow(); }
  });
  createListForm.addEventListener("submit", event => {
    event.preventDefault(); clearError(); app.setAttribute("aria-busy", "true");
    const categories = [...creationCategories.querySelectorAll(".creation-category")]
      .map(row => ({id: row.querySelector(".creation-category-id").value.trim(), display_name: row.querySelector(".creation-category-name").value.trim()}))
      .filter(category => category.id || category.display_name);
    requestJson("/api/todo", {method: "POST", body: JSON.stringify({date: listDate.value, categories})})
      .then(startEditor)
      .catch(error => { app.setAttribute("aria-busy", "false"); showError(error); });
  });
  requestJson("/api/todo").then(data => {
    if (data.exists === false) showCreation(data);
    else startEditor(data);
  }).catch(showError);
})();
