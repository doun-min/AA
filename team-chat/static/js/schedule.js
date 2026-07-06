(function () {
  const sidebar = document.getElementById("sidebar");
  if (!sidebar) return;

  const nickname = document.body.dataset.nickname;
  const CATEGORY_LABELS = { annual: "연차", half_day: "반차", work: "업무일정" };

  const calTitle = document.getElementById("sched-cal-title");
  const calGrid = document.getElementById("sched-cal-grid");
  const prevBtn = document.getElementById("sched-prev-month");
  const nextBtn = document.getElementById("sched-next-month");
  const listTitle = document.getElementById("sched-list-title");
  const listEl = document.getElementById("sched-list");
  const addBtn = document.getElementById("sched-add-btn");
  const form = document.getElementById("sched-form");
  const formId = document.getElementById("sched-form-id");
  const categorySelect = document.getElementById("sched-category");
  const dateInput = document.getElementById("sched-date");
  const timeRow = document.getElementById("sched-time-row");
  const startTimeInput = document.getElementById("sched-start-time");
  const titleInput = document.getElementById("sched-title");
  const errorEl = document.getElementById("sched-error");
  const deleteBtn = document.getElementById("sched-delete-btn");
  const cancelBtn = document.getElementById("sched-cancel-btn");

  function pad(n) {
    return String(n).padStart(2, "0");
  }
  function formatDate(d) {
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }
  function todayStr() {
    return formatDate(new Date());
  }
  function dotClass(category) {
    return category === "work" ? "sched-dot-work" : "sched-dot-leave";
  }
  function entryLabel(s) {
    if (s.category === "work") {
      return s.start_time ? `${s.start_time} ${s.title}` : s.title;
    }
    return `${s.nickname} ${CATEGORY_LABELS[s.category] || s.category}`;
  }

  const today = new Date();
  let viewYear = today.getFullYear();
  let viewMonth = today.getMonth() + 1;
  let selectedDate = todayStr();
  let monthSchedules = [];

  async function loadMonth() {
    const res = await fetch(`/api/schedules?year=${viewYear}&month=${viewMonth}`);
    const data = await res.json();
    monthSchedules = data.schedules || [];
    renderCalendar();
    renderList();
  }

  function renderCalendar() {
    calTitle.textContent = `${viewYear}년 ${viewMonth}월`;
    calGrid.innerHTML = "";
    const first = new Date(viewYear, viewMonth - 1, 1);
    const daysInMonth = new Date(viewYear, viewMonth, 0).getDate();
    const startWeekday = first.getDay();

    const byDate = {};
    monthSchedules.forEach((s) => {
      (byDate[s.date] = byDate[s.date] || []).push(s);
    });

    for (let i = 0; i < startWeekday; i++) {
      const cell = document.createElement("div");
      cell.className = "sched-cal-cell empty";
      calGrid.appendChild(cell);
    }

    for (let day = 1; day <= daysInMonth; day++) {
      const dateStr = `${viewYear}-${pad(viewMonth)}-${pad(day)}`;
      const cell = document.createElement("div");
      cell.className = "sched-cal-cell";
      if (dateStr === todayStr()) cell.classList.add("today");
      if (dateStr === selectedDate) cell.classList.add("selected");

      const dateEl = document.createElement("div");
      dateEl.className = "sched-cal-date";
      dateEl.textContent = String(day);
      cell.appendChild(dateEl);

      const dots = document.createElement("div");
      dots.className = "sched-cal-dots";
      (byDate[dateStr] || []).slice(0, 6).forEach((s) => {
        const dot = document.createElement("span");
        dot.className = "sched-dot " + dotClass(s.category);
        dots.appendChild(dot);
      });
      cell.appendChild(dots);

      cell.addEventListener("click", () => {
        selectedDate = dateStr;
        renderCalendar();
        renderList();
      });

      calGrid.appendChild(cell);
    }
  }

  function renderList() {
    const [, m, d] = selectedDate.split("-").map(Number);
    listTitle.textContent = `${m}월 ${d}일 일정`;
    const items = monthSchedules.filter((s) => s.date === selectedDate);
    listEl.innerHTML = "";
    if (!items.length) {
      const li = document.createElement("li");
      li.className = "empty";
      li.textContent = "등록된 일정이 없습니다.";
      listEl.appendChild(li);
      return;
    }
    items.forEach((s) => {
      const li = document.createElement("li");
      li.className = "sched-item";

      const dot = document.createElement("span");
      dot.className = "sched-dot " + dotClass(s.category);
      li.appendChild(dot);

      const body = document.createElement("div");
      body.className = "sched-item-body";
      const titleDiv = document.createElement("div");
      titleDiv.className = "sched-item-title";
      titleDiv.textContent = entryLabel(s);
      const metaDiv = document.createElement("div");
      metaDiv.className = "sched-item-meta";
      metaDiv.textContent = `${s.nickname} · ${CATEGORY_LABELS[s.category] || s.category}`;
      body.appendChild(titleDiv);
      body.appendChild(metaDiv);
      li.appendChild(body);

      if (s.nickname === nickname) {
        const actions = document.createElement("div");
        actions.className = "sched-item-actions";
        const editBtn = document.createElement("button");
        editBtn.type = "button";
        editBtn.className = "btn-secondary";
        editBtn.textContent = "수정";
        editBtn.addEventListener("click", () => openForm(s));
        actions.appendChild(editBtn);
        li.appendChild(actions);
      }

      listEl.appendChild(li);
    });
  }

  function updateTimeRowVisibility() {
    timeRow.hidden = categorySelect.value !== "work";
  }

  function openForm(schedule) {
    errorEl.textContent = "";
    form.hidden = false;
    if (schedule) {
      formId.value = schedule.id;
      categorySelect.value = schedule.category;
      dateInput.value = schedule.date;
      startTimeInput.value = schedule.start_time || "";
      titleInput.value = schedule.title;
      deleteBtn.hidden = false;
    } else {
      formId.value = "";
      categorySelect.value = "annual";
      dateInput.value = selectedDate;
      startTimeInput.value = "";
      titleInput.value = "";
      deleteBtn.hidden = true;
    }
    updateTimeRowVisibility();
  }

  function closeForm() {
    form.hidden = true;
    errorEl.textContent = "";
  }

  addBtn.addEventListener("click", () => openForm(null));
  cancelBtn.addEventListener("click", closeForm);
  categorySelect.addEventListener("change", updateTimeRowVisibility);

  prevBtn.addEventListener("click", () => {
    viewMonth -= 1;
    if (viewMonth < 1) {
      viewMonth = 12;
      viewYear -= 1;
    }
    loadMonth();
  });
  nextBtn.addEventListener("click", () => {
    viewMonth += 1;
    if (viewMonth > 12) {
      viewMonth = 1;
      viewYear += 1;
    }
    loadMonth();
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorEl.textContent = "";

    const category = categorySelect.value;
    let title = titleInput.value.trim();
    if (!title) {
      if (category === "work") {
        errorEl.textContent = "업무일정 내용을 입력해주세요.";
        return;
      }
      title = CATEGORY_LABELS[category];
    }
    if (!dateInput.value) {
      errorEl.textContent = "날짜를 선택해주세요.";
      return;
    }

    const body = {
      category,
      title,
      date: dateInput.value,
      start_time: category === "work" ? startTimeInput.value : "",
    };
    const id = formId.value;
    const url = id ? `/api/schedules/${id}` : "/api/schedules";
    const method = id ? "PUT" : "POST";

    try {
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) {
        errorEl.textContent = data.error || "저장에 실패했습니다.";
        return;
      }
      closeForm();
      selectedDate = data.schedule.date;
      await loadMonth();
    } catch (err) {
      errorEl.textContent = "저장 중 오류가 발생했습니다.";
    }
  });

  deleteBtn.addEventListener("click", async () => {
    const id = formId.value;
    if (!id) return;
    if (!confirm("이 일정을 삭제하시겠습니까?")) return;
    try {
      const res = await fetch(`/api/schedules/${id}`, { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) {
        errorEl.textContent = data.error || "삭제에 실패했습니다.";
        return;
      }
      closeForm();
      await loadMonth();
    } catch (err) {
      errorEl.textContent = "삭제 중 오류가 발생했습니다.";
    }
  });

  const socket = window.ChatNotify && window.ChatNotify.getSocket();
  if (socket) {
    socket.on("schedule_updated", (data) => {
      const [y, m] = (data.date || "").split("-").map(Number);
      if (y === viewYear && m === viewMonth) loadMonth();
    });
  }

  loadMonth();
})();
