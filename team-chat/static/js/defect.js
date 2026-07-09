(function () {
  const page = document.querySelector(".defect-page");
  if (!page) return;
  const nickname = page.dataset.nickname;

  const filterSubject = document.getElementById("filter-subject");
  const filterReporter = document.getElementById("filter-reporter");
  const tableHead = document.getElementById("issue-table-head");
  const tableBody = document.getElementById("issue-table-body");
  const errorEl = document.getElementById("defect-error");
  const addBtn = document.getElementById("defect-add-btn");

  const subjectAddBtn = document.getElementById("subject-add-btn");
  const subjectModal = document.getElementById("subject-modal");
  const subjectModalClose = document.getElementById("subject-modal-close");
  const subjectAddCancelBtn = document.getElementById("subject-add-cancel-btn");
  const subjectAddForm = document.getElementById("subject-add-form");
  const subjectAddName = document.getElementById("subject-add-name");
  const subjectAddError = document.getElementById("subject-add-error");

  const modal = document.getElementById("issue-modal");
  const modalTitle = document.getElementById("issue-modal-title");
  const modalClose = document.getElementById("issue-modal-close");
  const cancelBtn = document.getElementById("issue-cancel-btn");
  const form = document.getElementById("issue-form");
  const formError = document.getElementById("issue-form-error");
  const issueIdInput = document.getElementById("issue-id");
  const issueSubjectSelect = document.getElementById("issue-subject");
  const issueTcNum = document.getElementById("issue-tc-num");
  const issueBody = document.getElementById("issue-body");
  const issueSteps = document.getElementById("issue-steps");
  const issueReporter = document.getElementById("issue-reporter");
  const customFieldsContainer = document.getElementById("issue-custom-fields");

  const subjectForm = document.getElementById("subject-form");
  const fieldForm = document.getElementById("field-form");

  let subjects = [];
  let fields = [];
  let issues = [];

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : str;
    return div.innerHTML;
  }

  function subjectById(id) {
    return subjects.find((s) => s.id === id);
  }

  function renderFilterSubjectOptions() {
    const current = filterSubject.value;
    filterSubject.innerHTML = '<option value="">전체 주제</option>';
    subjects.forEach((s) => {
      const opt = document.createElement("option");
      opt.value = s.id;
      opt.textContent = s.status === "archived" ? `(아카이브) ${s.name}` : s.name;
      filterSubject.appendChild(opt);
    });
    filterSubject.value = current;
  }

  function renderIssueSubjectSelectOptions() {
    issueSubjectSelect.innerHTML = "";
    subjects
      .filter((s) => s.status === "active")
      .forEach((s) => {
        const opt = document.createElement("option");
        opt.value = s.id;
        opt.textContent = s.name;
        issueSubjectSelect.appendChild(opt);
      });
  }

  function renderAdminSubjectChips() {
    const container = document.getElementById("subject-chip-list");
    if (!container) return;
    container.innerHTML = "";
    subjects.forEach((s) => {
      const chip = document.createElement("span");
      chip.className = "admin-chip" + (s.status === "archived" ? " archived" : "");
      const label = document.createElement("span");
      label.textContent = s.name + (s.status === "archived" ? " (아카이브)" : "");
      chip.appendChild(label);
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = s.status === "archived" ? "활성화" : "아카이브";
      btn.addEventListener("click", async () => {
        const action = s.status === "archived" ? "activate" : "archive";
        await fetch(`/api/subjects/${s.id}/${action}`, { method: "POST" });
        await loadSubjects();
      });
      chip.appendChild(btn);
      container.appendChild(chip);
    });
  }

  function renderAdminFieldChips() {
    const container = document.getElementById("field-chip-list");
    if (!container) return;
    container.innerHTML = "";
    fields.forEach((f) => {
      const chip = document.createElement("span");
      chip.className = "admin-chip";
      chip.textContent = f.label;
      container.appendChild(chip);
    });
  }

  function renderTableHead() {
    const cols = ["주제", "TC번호", "Defect 내용", "재현 방법", "보고자"]
      .concat(fields.map((f) => f.label))
      .concat(["등록일"]);
    tableHead.innerHTML = cols.map((c) => `<th>${escapeHtml(c)}</th>`).join("");
  }

  function renderTableBody() {
    tableBody.innerHTML = "";
    if (!issues.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.className = "issue-empty";
      td.colSpan = 6 + fields.length;
      td.textContent = "등록된 이슈가 없습니다.";
      tr.appendChild(td);
      tableBody.appendChild(tr);
      return;
    }
    issues.forEach((issue) => {
      const tr = document.createElement("tr");
      const subject = subjectById(issue.subject_id);
      const subjectLabel = subject
        ? `<span class="issue-subject-badge ${subject.status === "archived" ? "archived" : ""}">${escapeHtml(subject.name)}</span>`
        : "";
      const cells = [
        subjectLabel,
        escapeHtml(issue.tc_num || ""),
        escapeHtml(issue.body || ""),
        escapeHtml(issue.steps_to_reproduce || ""),
        escapeHtml(issue.reporter || ""),
      ];
      fields.forEach((f) => cells.push(escapeHtml((issue.custom_fields || {})[f.label] || "")));
      cells.push(escapeHtml((issue.created_at || "").replace("T", " ").split("+")[0]));
      tr.innerHTML = cells.map((c) => `<td>${c}</td>`).join("");
      tr.addEventListener("click", () => openModal(issue));
      tableBody.appendChild(tr);
    });
  }

  function renderCustomFieldInputs(values) {
    customFieldsContainer.innerHTML = "";
    fields.forEach((f) => {
      const label = document.createElement("label");
      label.textContent = f.label;
      const input = document.createElement("input");
      input.type = "text";
      input.dataset.fieldLabel = f.label;
      input.value = (values && values[f.label]) || "";
      label.appendChild(input);
      customFieldsContainer.appendChild(label);
    });
  }

  function collectCustomFields() {
    const result = {};
    customFieldsContainer.querySelectorAll("input[data-field-label]").forEach((input) => {
      result[input.dataset.fieldLabel] = input.value;
    });
    return result;
  }

  function openModal(issue) {
    formError.textContent = "";
    renderIssueSubjectSelectOptions();
    if (issue) {
      modalTitle.textContent = "이슈 수정";
      issueIdInput.value = issue.id;
      issueSubjectSelect.value = issue.subject_id;
      issueTcNum.value = issue.tc_num || "";
      issueBody.value = issue.body || "";
      issueSteps.value = issue.steps_to_reproduce || "";
      issueReporter.value = issue.reporter;
      renderCustomFieldInputs(issue.custom_fields);
    } else {
      modalTitle.textContent = "이슈 등록";
      issueIdInput.value = "";
      issueTcNum.value = "";
      issueBody.value = "";
      issueSteps.value = "";
      issueReporter.value = nickname;
      renderCustomFieldInputs(null);
    }
    modal.hidden = false;
  }

  function closeModal() {
    modal.hidden = true;
  }

  function openSubjectModal() {
    subjectAddError.textContent = "";
    subjectAddName.value = "";
    subjectModal.hidden = false;
    subjectAddName.focus();
  }

  function closeSubjectModal() {
    subjectModal.hidden = true;
  }

  subjectAddBtn.addEventListener("click", openSubjectModal);
  subjectModalClose.addEventListener("click", closeSubjectModal);
  subjectAddCancelBtn.addEventListener("click", closeSubjectModal);
  subjectModal.addEventListener("click", (e) => {
    if (e.target === subjectModal) closeSubjectModal();
  });

  subjectAddForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    subjectAddError.textContent = "";
    const name = subjectAddName.value.trim();
    if (!name) return;
    try {
      const res = await fetch("/api/subjects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const data = await res.json();
      if (!res.ok) {
        subjectAddError.textContent = data.error || "주제 등록에 실패했습니다.";
        return;
      }
      closeSubjectModal();
      await loadSubjects();
    } catch (err) {
      subjectAddError.textContent = "주제 등록 중 오류가 발생했습니다.";
    }
  });

  addBtn.addEventListener("click", () => openModal(null));
  modalClose.addEventListener("click", closeModal);
  cancelBtn.addEventListener("click", closeModal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    formError.textContent = "";
    const body = {
      subject_id: Number(issueSubjectSelect.value),
      tc_num: issueTcNum.value.trim(),
      body: issueBody.value.trim(),
      steps_to_reproduce: issueSteps.value.trim(),
      custom_fields: collectCustomFields(),
    };
    if (!body.body) {
      formError.textContent = "Defect 내용을 입력해주세요.";
      return;
    }
    const id = issueIdInput.value;
    const url = id ? `/api/issues/${id}` : "/api/issues";
    const method = id ? "PUT" : "POST";
    try {
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) {
        formError.textContent = data.error || "저장에 실패했습니다.";
        return;
      }
      closeModal();
      await loadIssues();
    } catch (err) {
      formError.textContent = "저장 중 오류가 발생했습니다.";
    }
  });

  filterSubject.addEventListener("change", loadIssues);
  filterReporter.addEventListener("change", loadIssues);

  if (subjectForm) {
    subjectForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const input = document.getElementById("subject-name-input");
      const name = input.value.trim();
      if (!name) return;
      const res = await fetch("/api/subjects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const data = await res.json();
      if (res.ok) {
        input.value = "";
        await loadSubjects();
      } else {
        alert(data.error || "주제 생성에 실패했습니다.");
      }
    });
  }

  if (fieldForm) {
    fieldForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const input = document.getElementById("field-label-input");
      const label = input.value.trim();
      if (!label) return;
      const res = await fetch("/api/issue_fields", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label }),
      });
      const data = await res.json();
      if (res.ok) {
        input.value = "";
        await loadFields();
        await loadIssues();
      } else {
        alert(data.error || "필드 생성에 실패했습니다.");
      }
    });
  }

  async function loadSubjects() {
    try {
      const res = await fetch("/api/subjects");
      const data = await res.json();
      subjects = data.subjects || [];
      renderFilterSubjectOptions();
      renderAdminSubjectChips();
    } catch (err) {
      errorEl.textContent = "주제 목록을 불러오지 못했습니다.";
    }
  }

  async function loadFields() {
    try {
      const res = await fetch("/api/issue_fields");
      const data = await res.json();
      fields = data.fields || [];
      renderAdminFieldChips();
      renderTableHead();
    } catch (err) {
      errorEl.textContent = "커스텀 필드를 불러오지 못했습니다.";
    }
  }

  async function refreshReporterOptions() {
    try {
      const res = await fetch("/api/issues");
      const data = await res.json();
      const reporters = Array.from(new Set((data.issues || []).map((i) => i.reporter))).sort();
      const current = filterReporter.value;
      filterReporter.innerHTML = '<option value="">전체 담당자</option>';
      reporters.forEach((r) => {
        const opt = document.createElement("option");
        opt.value = r;
        opt.textContent = r;
        filterReporter.appendChild(opt);
      });
      filterReporter.value = current;
    } catch (err) {
      /* ignore */
    }
  }

  async function loadIssues() {
    try {
      const params = new URLSearchParams();
      if (filterSubject.value) params.set("subject_id", filterSubject.value);
      if (filterReporter.value) params.set("reporter", filterReporter.value);
      const res = await fetch(`/api/issues?${params.toString()}`);
      const data = await res.json();
      issues = data.issues || [];
      renderTableBody();
    } catch (err) {
      errorEl.textContent = "이슈 목록을 불러오지 못했습니다.";
    }
  }

  const socket = window.ChatNotify && window.ChatNotify.getSocket();
  if (socket) {
    socket.on("issue_created", () => {
      loadIssues();
      refreshReporterOptions();
    });
    socket.on("issue_updated", () => loadIssues());
    socket.on("subject_updated", () => loadSubjects());
    socket.on("issue_field_created", () => {
      loadFields();
      loadIssues();
    });
  }

  (async function init() {
    await Promise.all([loadSubjects(), loadFields()]);
    await refreshReporterOptions();
    await loadIssues();
  })();
})();
