(function () {
  const nickname = document.body.dataset.nickname;
  const CATEGORY_LABELS = { annual: "연차", half_day: "반차", work: "업무일정" };
  const MINUTE_STEP = 10;

  const calTitle = document.getElementById("sched-cal-title");
  const calGrid = document.getElementById("sched-cal-grid");
  const prevBtn = document.getElementById("sched-prev-month");
  const nextBtn = document.getElementById("sched-next-month");
  const listTitle = document.getElementById("sched-list-title");
  const listEl = document.getElementById("sched-list");
  const addBtn = document.getElementById("sched-add-btn");
  const schedModal = document.getElementById("sched-modal");
  const schedModalTitle = document.getElementById("sched-modal-title");
  const schedModalClose = document.getElementById("sched-modal-close");
  const form = document.getElementById("sched-form");
  const formId = document.getElementById("sched-form-id");
  const categorySelect = document.getElementById("sched-category");

  const startYearSelect = document.getElementById("sched-start-year");
  const startMonthSelect = document.getElementById("sched-start-month");
  const startDaySelect = document.getElementById("sched-start-day");
  const startTimeRow = document.getElementById("sched-start-time-row");
  const startHourSelect = document.getElementById("sched-start-hour");
  const startMinuteSelect = document.getElementById("sched-start-minute");

  const endYearSelect = document.getElementById("sched-end-year");
  const endMonthSelect = document.getElementById("sched-end-month");
  const endDaySelect = document.getElementById("sched-end-day");
  const endTimeRow = document.getElementById("sched-end-time-row");
  const endHourSelect = document.getElementById("sched-end-hour");
  const endMinuteSelect = document.getElementById("sched-end-minute");

  const titleInput = document.getElementById("sched-title");
  const errorEl = document.getElementById("sched-error");
  const deleteBtn = document.getElementById("sched-delete-btn");
  const cancelBtn = document.getElementById("sched-cancel-btn");

  if (!form) return;

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
  function barClass(category) {
    return category === "work" ? "sched-bar-work" : "sched-bar-leave";
  }
  const MAX_BAR_TRACKS = 4;
  // 여러 날에 걸친 일정이 같은 기간 동안 서로 다른 줄(track)에 그려지도록 배정한다.
  // (전형적인 "최소 회의실 개수" 그리디 구간 스케줄링 알고리즘)
  function assignTracks(schedules) {
    const sorted = [...schedules].sort((a, b) => {
      if (a.date !== b.date) return a.date < b.date ? -1 : 1;
      const ea = endDateOf(a);
      const eb = endDateOf(b);
      return ea < eb ? -1 : ea > eb ? 1 : 0;
    });
    const trackEndDates = [];
    const trackOf = new Map();
    sorted.forEach((s) => {
      const start = s.date;
      const end = endDateOf(s);
      let track = trackEndDates.findIndex((endDate) => endDate < start);
      if (track === -1) {
        track = trackEndDates.length;
        trackEndDates.push(end);
      } else {
        trackEndDates[track] = end;
      }
      trackOf.set(s, track);
    });
    return trackOf;
  }
  function endDateOf(s) {
    return s.end_date || s.date;
  }
  function eachDateInRange(startStr, endStr) {
    const dates = [];
    let cur = new Date(startStr + "T00:00:00");
    const end = new Date(endStr + "T00:00:00");
    while (cur <= end) {
      dates.push(formatDate(cur));
      cur.setDate(cur.getDate() + 1);
    }
    return dates;
  }
  function entryLabel(s) {
    const end = endDateOf(s);
    const isRange = end !== s.date;
    if (s.category === "work") {
      let when = "";
      if (isRange) {
        when = `${s.date}${s.start_time ? " " + s.start_time : ""} ~ ${end}${s.end_time ? " " + s.end_time : ""}`;
      } else if (s.start_time) {
        when = s.end_time ? `${s.start_time}~${s.end_time}` : s.start_time;
      }
      return when ? `${when} ${s.title}` : s.title;
    }
    const label = CATEGORY_LABELS[s.category] || s.category;
    return isRange ? `${s.nickname} ${label} (${s.date} ~ ${end})` : `${s.nickname} ${label}`;
  }

  function fillHourOptions(select) {
    select.innerHTML = "";
    for (let h = 0; h < 24; h++) {
      const opt = document.createElement("option");
      opt.value = pad(h);
      opt.textContent = `${pad(h)}시`;
      select.appendChild(opt);
    }
  }
  function fillMinuteOptions(select) {
    select.innerHTML = "";
    for (let m = 0; m < 60; m += MINUTE_STEP) {
      const opt = document.createElement("option");
      opt.value = pad(m);
      opt.textContent = `${pad(m)}분`;
      select.appendChild(opt);
    }
  }
  fillHourOptions(startHourSelect);
  fillMinuteOptions(startMinuteSelect);
  fillHourOptions(endHourSelect);
  fillMinuteOptions(endMinuteSelect);

  function setTimeSelects(hourSelect, minuteSelect, timeStr, fallback) {
    const [h, m] = (timeStr || fallback).split(":");
    hourSelect.value = h;
    const roundedMinute = pad(Math.round(Number(m) / MINUTE_STEP) * MINUTE_STEP % 60);
    minuteSelect.value = roundedMinute;
  }

  // ---- 시작/종료 일자 년/월/일 드롭다운 ----
  const YEAR_RANGE = 5; // 과거에 등록된 일정 수정 화면에서도 쓰이므로 앞뒤로 넉넉하게 잡는다.
  function daysInMonth(year, month) {
    return new Date(year, month, 0).getDate();
  }
  function fillYearOptions(select) {
    select.innerHTML = "";
    const y = new Date().getFullYear();
    for (let year = y - YEAR_RANGE; year <= y + YEAR_RANGE; year++) {
      const opt = document.createElement("option");
      opt.value = String(year);
      opt.textContent = String(year);
      select.appendChild(opt);
    }
  }
  function fillMonthOptions(select) {
    select.innerHTML = "";
    for (let m = 1; m <= 12; m++) {
      const opt = document.createElement("option");
      opt.value = pad(m);
      opt.textContent = String(m);
      select.appendChild(opt);
    }
  }
  // 월이 바뀌면 그 달의 실제 일수(2월 28/29일 등)에 맞춰 일 옵션을 다시 그린다.
  // 기존에 선택돼 있던 일이 새 달에 없으면(예: 31일 -> 2월) 그 달의 마지막 날로 보정한다.
  function rebuildDayOptions(select, year, month) {
    const max = daysInMonth(year, month);
    const current = Number(select.value) || null;
    select.innerHTML = "";
    for (let d = 1; d <= max; d++) {
      const opt = document.createElement("option");
      opt.value = pad(d);
      opt.textContent = String(d);
      select.appendChild(opt);
    }
    if (current) select.value = pad(Math.min(current, max));
  }
  function getDateStr(yearSelect, monthSelect, daySelect) {
    return `${yearSelect.value}-${monthSelect.value}-${daySelect.value}`;
  }
  function setDateSelects(yearSelect, monthSelect, daySelect, dateStr) {
    const [y, m, d] = dateStr.split("-");
    yearSelect.value = y;
    monthSelect.value = m;
    rebuildDayOptions(daySelect, Number(y), Number(m));
    daySelect.value = d;
  }
  function getStartDateStr() {
    return getDateStr(startYearSelect, startMonthSelect, startDaySelect);
  }
  function setStartDate(dateStr) {
    setDateSelects(startYearSelect, startMonthSelect, startDaySelect, dateStr);
  }
  function getEndDateStr() {
    return getDateStr(endYearSelect, endMonthSelect, endDaySelect);
  }
  function setEndDate(dateStr) {
    setDateSelects(endYearSelect, endMonthSelect, endDaySelect, dateStr);
  }
  [startYearSelect, endYearSelect].forEach(fillYearOptions);
  [startMonthSelect, endMonthSelect].forEach(fillMonthOptions);
  rebuildDayOptions(startDaySelect, Number(startYearSelect.value), Number(startMonthSelect.value));
  rebuildDayOptions(endDaySelect, Number(endYearSelect.value), Number(endMonthSelect.value));

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
      eachDateInRange(s.date, endDateOf(s)).forEach((d) => {
        (byDate[d] = byDate[d] || []).push(s);
      });
    });
    const trackOf = assignTracks(monthSchedules);

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

      const bars = document.createElement("div");
      bars.className = "sched-cal-bars";
      const entries = byDate[dateStr] || [];
      const maxTrack = entries.reduce((max, s) => Math.max(max, trackOf.get(s)), -1);
      for (let t = 0; t <= Math.min(maxTrack, MAX_BAR_TRACKS - 1); t++) {
        const slot = document.createElement("div");
        slot.className = "sched-bar-slot";
        const s = entries.find((e) => trackOf.get(e) === t);
        if (s) {
          const isStart = s.date === dateStr;
          const isEnd = endDateOf(s) === dateStr;
          const bar = document.createElement("span");
          bar.className =
            "sched-bar " + barClass(s.category) +
            (isStart ? " start" : "") +
            (isEnd ? " end" : "");
          bar.title = entryLabel(s);
          slot.appendChild(bar);
        }
        bars.appendChild(slot);
      }
      cell.appendChild(bars);

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
    const items = monthSchedules.filter((s) => selectedDate >= s.date && selectedDate <= endDateOf(s));
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
    const isWork = categorySelect.value === "work";
    startTimeRow.hidden = !isWork;
    endTimeRow.hidden = !isWork;
  }

  function openForm(schedule) {
    errorEl.textContent = "";
    schedModal.hidden = false;
    schedModalTitle.textContent = schedule ? "일정 수정" : "일정 추가";
    if (schedule) {
      // 기존 일정 수정: 이미 지난 날짜의 일정도 (날짜 자체를 바꾸지 않는 한) 수정할 수
      // 있어야 하므로 과거 날짜 선택 제한을 걸지 않는다.
      formId.value = schedule.id;
      categorySelect.value = schedule.category;
      setStartDate(schedule.date);
      setEndDate(endDateOf(schedule));
      setTimeSelects(startHourSelect, startMinuteSelect, schedule.start_time, "09:00");
      setTimeSelects(endHourSelect, endMinuteSelect, schedule.end_time, "18:00");
      titleInput.value = schedule.title;
      deleteBtn.hidden = false;
    } else {
      // 신규 등록: select는 input[type=date]처럼 min 속성으로 과거 선택 자체를
      // 막을 수 없으므로, 기본값을 오늘(또는 캘린더에서 고른 미래 날짜)로 맞춰두고
      // 실제 과거 날짜 조합 방지는 제출 시점 검증(아래 submit 핸들러)에서 처리한다.
      const defaultDate = selectedDate < todayStr() ? todayStr() : selectedDate;
      formId.value = "";
      categorySelect.value = "annual";
      setStartDate(defaultDate);
      setEndDate(defaultDate);
      setTimeSelects(startHourSelect, startMinuteSelect, null, "09:00");
      setTimeSelects(endHourSelect, endMinuteSelect, null, "18:00");
      titleInput.value = "";
      deleteBtn.hidden = true;
    }
    updateTimeRowVisibility();
  }

  function closeForm() {
    schedModal.hidden = true;
    errorEl.textContent = "";
  }

  addBtn.addEventListener("click", () => openForm(null));
  cancelBtn.addEventListener("click", closeForm);
  schedModalClose.addEventListener("click", closeForm);
  schedModal.addEventListener("click", (e) => {
    if (e.target === schedModal) closeForm();
  });
  categorySelect.addEventListener("change", updateTimeRowVisibility);

  // 종료일이 시작일보다 빠르게 선택되면 시작일과 같은 날로 보정한다.
  // (select는 input[type=date]의 min 속성 같은 네이티브 제한이 없어서 직접 맞춰준다.)
  function onStartDateChange() {
    const startDateStr = getStartDateStr();
    if (getEndDateStr() < startDateStr) setEndDate(startDateStr);
  }
  startYearSelect.addEventListener("change", () => {
    rebuildDayOptions(startDaySelect, Number(startYearSelect.value), Number(startMonthSelect.value));
    onStartDateChange();
  });
  startMonthSelect.addEventListener("change", () => {
    rebuildDayOptions(startDaySelect, Number(startYearSelect.value), Number(startMonthSelect.value));
    onStartDateChange();
  });
  startDaySelect.addEventListener("change", onStartDateChange);

  endYearSelect.addEventListener("change", () => {
    rebuildDayOptions(endDaySelect, Number(endYearSelect.value), Number(endMonthSelect.value));
  });
  endMonthSelect.addEventListener("change", () => {
    rebuildDayOptions(endDaySelect, Number(endYearSelect.value), Number(endMonthSelect.value));
  });

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
    const startDateStr = getStartDateStr();
    const endDateStr = getEndDateStr();
    if (endDateStr < startDateStr) {
      errorEl.textContent = "종료 일시가 시작 일시보다 빠를 수 없습니다.";
      return;
    }
    const isEdit = !!formId.value;
    if (!isEdit && startDateStr < todayStr()) {
      errorEl.textContent = "지난 날짜에는 일정을 등록할 수 없습니다.";
      return;
    }

    const isWork = category === "work";
    const startTime = isWork ? `${startHourSelect.value}:${startMinuteSelect.value}` : "";
    const endTime = isWork ? `${endHourSelect.value}:${endMinuteSelect.value}` : "";
    if (isWork && startDateStr === endDateStr && endTime < startTime) {
      errorEl.textContent = "종료 일시가 시작 일시보다 빠를 수 없습니다.";
      return;
    }

    const body = {
      category,
      title,
      date: startDateStr,
      end_date: endDateStr,
      start_time: startTime,
      end_time: endTime,
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
