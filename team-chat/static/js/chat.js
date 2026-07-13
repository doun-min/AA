(function () {
  // notify.js가 "채팅 페이지면 인앱 토스트로 충분하다"고 판단할 수 있도록 표시.
  window.__chatPageActive = true;

  const page = document.querySelector(".chat-page");
  const roomId = page.dataset.roomId;
  const nickname = page.dataset.nickname;

  const messagesEl = document.getElementById("messages");
  const form = document.getElementById("message-form");
  const input = document.getElementById("message-input");
  const fileInput = document.getElementById("file-input");
  const attachBtn = document.getElementById("btn-attach");
  const deleteBtn = document.getElementById("btn-delete");
  const transferBtn = document.getElementById("btn-transfer");
  const mentionSuggest = document.getElementById("mention-suggest");

  const MENTION_ALL = "전체";
  let roomMembers = [];
  try {
    roomMembers = JSON.parse(page.dataset.roomMembers || "[]");
  } catch (e) {
    roomMembers = [];
  }
  const mentionCandidates = [MENTION_ALL, ...roomMembers];

  const socket = (window.ChatNotify && window.ChatNotify.getSocket()) || io();

  let latestMessageId = Number(page.dataset.lastMessageId) || 0;

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }
  scrollToBottom();

  // 서버 렌더링(SSR)된 과거 메시지는 멘션이 span으로 감싸져 있지 않으므로,
  // 소켓으로 오는 새 메시지(appendMessage)와 동일하게 하이라이트를 적용한다.
  messagesEl.querySelectorAll(".message.type-text .msg-body").forEach((el) => {
    el.innerHTML = linkifyMentions(el.textContent);
  });

  function markReadIfVisible() {
    if (document.visibilityState === "visible" && latestMessageId) {
      socket.emit("mark_read", { room_id: Number(roomId), up_to_message_id: latestMessageId });
    }
  }

  socket.on("connect", () => {
    socket.emit("join", { room_id: Number(roomId) });
    markReadIfVisible();
  });

  document.addEventListener("visibilitychange", markReadIfVisible);
  markReadIfVisible();

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : str;
    return div.innerHTML;
  }

  function linkifyMentions(text) {
    return escapeHtml(text).replace(/@([^\s@,]+)/g, (match, name) => {
      const cls = name === MENTION_ALL ? "mention mention-all" : "mention";
      return `<span class="${cls}">@${name}</span>`;
    });
  }

  // ---- 이미지 미리보기 모달 ----
  const imageModal = document.getElementById("image-modal");
  const imageModalImg = document.getElementById("image-modal-img");
  const imageModalDownload = document.getElementById("image-modal-download");
  const imageModalClose = document.getElementById("image-modal-close");

  function openImageModal(src, filename) {
    imageModalImg.src = src;
    imageModalImg.alt = filename || "";
    imageModalDownload.href = src;
    imageModalDownload.download = filename || "";
    imageModal.hidden = false;
  }

  function closeImageModal() {
    imageModal.hidden = true;
    imageModalImg.src = "";
  }

  messagesEl.addEventListener("click", (e) => {
    const img = e.target.closest(".msg-image");
    if (!img) return;
    openImageModal(img.getAttribute("src"), img.dataset.filename);
  });

  imageModalClose.addEventListener("click", closeImageModal);
  imageModal.addEventListener("click", (e) => {
    if (e.target === imageModal) closeImageModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !imageModal.hidden) closeImageModal();
  });

  function appendMessage(msg) {
    const div = document.createElement("div");
    const mine = msg.sender === nickname;
    div.className = "message type-" + msg.type + (mine ? " me" : "");
    div.dataset.msgId = msg.id;

    if (msg.type === "system") {
      div.innerHTML = `<div class="system-text">${escapeHtml(msg.content)}</div>`;
    } else {
      const time = (msg.created_at || "").replace("T", " ").split("+")[0];
      let body;
      if (msg.type === "text") {
        body = `<div class="msg-body">${linkifyMentions(msg.content)}</div>`;
      } else if (msg.type === "image") {
        body = `<div class="msg-body"><img class="msg-image" src="/files/${roomId}/${msg.file_path}" data-filename="${escapeHtml(msg.original_filename)}" alt="${escapeHtml(msg.original_filename)}"></div>`;
      } else {
        body = `<div class="msg-body"><a href="/files/${roomId}/${msg.file_path}" download="${escapeHtml(msg.original_filename)}">📎 ${escapeHtml(msg.original_filename)}</a></div>`;
      }
      const unreadCount = msg.unread_count || 0;
      const unreadAttr = unreadCount ? "" : " hidden";
      div.innerHTML =
        `<div class="msg-meta"><span class="msg-sender">${escapeHtml(msg.sender)}</span>` +
        `<span class="msg-unread" data-msg-id="${msg.id}"${unreadAttr}>${unreadCount}</span>` +
        `<span class="msg-time">${time}</span></div>` +
        body;
    }
    messagesEl.appendChild(div);
    scrollToBottom();
  }

  function updateUnreadBadge(msgId, count) {
    const badge = messagesEl.querySelector(`.msg-unread[data-msg-id="${msgId}"]`);
    if (!badge) return;
    if (count > 0) {
      badge.hidden = false;
      badge.textContent = count;
    } else {
      badge.hidden = true;
      badge.textContent = "";
    }
  }

  socket.on("new_message", (msg) => {
    if (Number(msg.room_id) !== Number(roomId)) return;
    appendMessage(msg);
    latestMessageId = Math.max(latestMessageId, Number(msg.id));
    markReadIfVisible();
  });

  socket.on("read_update", (data) => {
    if (Number(data.room_id) !== Number(roomId)) return;
    (data.updates || []).forEach((u) => updateUnreadBadge(u.id, u.unread_count));
  });

  const scheduleBanner = document.getElementById("schedule-banner");
  function todayStr() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }
  async function refreshScheduleBanner() {
    if (!scheduleBanner) return;
    try {
      const res = await fetch("/api/schedules/today");
      const data = await res.json();
      if (res.ok) scheduleBanner.textContent = data.banner;
    } catch (err) {
      /* ignore */
    }
  }
  socket.on("schedule_updated", (data) => {
    if (data.date === todayStr()) refreshScheduleBanner();
  });

  socket.on("mention", (data) => {
    // 백그라운드 상태(창 비활성/최소화 등)라면 notify.js가 OS 알림 + 탭 배지를 담당하므로
    // 여기서는 중복으로 토스트/비프를 울리지 않는다.
    if (window.ChatNotify && window.ChatNotify.isBackgrounded()) return;
    showToast(`${data.sender}님이 [${data.room_name}] 방에서 회원님을 멘션했습니다: ${data.text}`);
    playBeep();
  });

  socket.on("room_deleted", (data) => {
    if (Number(data.room_id) === Number(roomId)) {
      alert("이 방이 삭제되었습니다.");
      window.location.href = "/rooms";
    }
  });

  socket.on("owner_changed", (data) => {
    if (Number(data.room_id) === Number(roomId)) {
      window.location.reload();
    }
  });

  // ---- 멘션 자동완성 (@를 입력하면 방 멤버 + "전체" 후보를 보여준다) ----
  let mentionActiveIndex = -1;
  let mentionMatchStart = -1; // input.value 기준 '@' 문자의 위치

  function closeMentionSuggest() {
    mentionSuggest.hidden = true;
    mentionSuggest.innerHTML = "";
    mentionActiveIndex = -1;
    mentionMatchStart = -1;
  }

  function currentMentionQuery() {
    const pos = input.selectionStart;
    const uptoCursor = input.value.slice(0, pos);
    const match = uptoCursor.match(/(?:^|\s)@([^\s@,]*)$/);
    if (!match) return null;
    return { query: match[1], start: pos - match[1].length - 1 };
  }

  function setActiveItem(items, index) {
    mentionActiveIndex = index;
    items.forEach((li, i) => li.classList.toggle("active", i === mentionActiveIndex));
  }

  function selectMention(name) {
    if (mentionMatchStart < 0) return;
    const pos = input.selectionStart;
    const before = input.value.slice(0, mentionMatchStart);
    const after = input.value.slice(pos);
    const inserted = `@${name} `;
    input.value = before + inserted + after;
    const caret = (before + inserted).length;
    input.focus();
    input.setSelectionRange(caret, caret);
    closeMentionSuggest();
  }

  function updateMentionSuggest() {
    const ctx = currentMentionQuery();
    if (!ctx) {
      closeMentionSuggest();
      return;
    }
    const q = ctx.query.toLowerCase();
    const matches = mentionCandidates.filter((n) => n.toLowerCase().startsWith(q)).slice(0, 8);
    if (!matches.length) {
      closeMentionSuggest();
      return;
    }
    mentionMatchStart = ctx.start;
    mentionSuggest.innerHTML = "";
    matches.forEach((name) => {
      const li = document.createElement("li");
      li.textContent = name === MENTION_ALL ? `${name} (방 전원에게 멘션)` : name;
      li.dataset.name = name;
      li.addEventListener("mousedown", (e) => {
        e.preventDefault(); // blur보다 먼저 처리되도록
        selectMention(name);
      });
      mentionSuggest.appendChild(li);
    });
    setActiveItem(mentionSuggest.querySelectorAll("li"), 0);
    mentionSuggest.hidden = false;
  }

  input.addEventListener("input", updateMentionSuggest);
  input.addEventListener("click", updateMentionSuggest);
  input.addEventListener("blur", () => setTimeout(closeMentionSuggest, 100));

  input.addEventListener("keydown", (e) => {
    if (mentionSuggest.hidden) return;
    const items = mentionSuggest.querySelectorAll("li");
    if (!items.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveItem(items, (mentionActiveIndex + 1) % items.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveItem(items, (mentionActiveIndex - 1 + items.length) % items.length);
    } else if (e.key === "Enter" || e.key === "Tab") {
      if (mentionActiveIndex >= 0) {
        e.preventDefault();
        selectMention(items[mentionActiveIndex].dataset.name);
      }
    } else if (e.key === "Escape") {
      closeMentionSuggest();
    }
  });

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    socket.emit("send_message", { room_id: Number(roomId), text });
    input.value = "";
    closeMentionSuggest();
  });

  async function uploadFile(file) {
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch(`/api/rooms/${roomId}/upload`, { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) {
        alert(data.error || "업로드에 실패했습니다.");
      }
    } catch (err) {
      alert("업로드 중 오류가 발생했습니다.");
    }
  }

  attachBtn.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", async () => {
    await uploadFile(fileInput.files[0]);
    fileInput.value = "";
  });

  // ---- 파일 드래그 앤 드롭 업로드 ----
  // dragleave는 자식 엘리먼트 위를 지나갈 때도 발생하므로, 카운터로 실제
  // chat-page 영역을 완전히 벗어났을 때만 하이라이트를 해제한다.
  let dragCounter = 0;

  function isFileDrag(e) {
    return !!e.dataTransfer && Array.from(e.dataTransfer.types || []).includes("Files");
  }

  page.addEventListener("dragenter", (e) => {
    if (!isFileDrag(e)) return;
    e.preventDefault();
    dragCounter += 1;
    page.classList.add("drag-over");
  });

  page.addEventListener("dragover", (e) => {
    if (!isFileDrag(e)) return;
    e.preventDefault();
  });

  page.addEventListener("dragleave", (e) => {
    if (!isFileDrag(e)) return;
    e.preventDefault();
    dragCounter = Math.max(0, dragCounter - 1);
    if (dragCounter === 0) page.classList.remove("drag-over");
  });

  page.addEventListener("drop", async (e) => {
    if (!isFileDrag(e)) return;
    e.preventDefault();
    dragCounter = 0;
    page.classList.remove("drag-over");
    const file = e.dataTransfer.files && e.dataTransfer.files[0];
    await uploadFile(file);
  });

  if (deleteBtn) {
    deleteBtn.addEventListener("click", async () => {
      if (!confirm("정말 이 방을 삭제하시겠습니까?")) return;
      const res = await fetch(`/api/rooms/${roomId}`, { method: "DELETE" });
      const data = await res.json();
      if (res.ok) {
        window.location.href = "/rooms";
      } else {
        alert(data.error || "삭제에 실패했습니다.");
      }
    });
  }

  if (transferBtn) {
    transferBtn.addEventListener("click", async () => {
      const target = prompt("방장을 위임할 사용자의 닉네임을 입력하세요.");
      if (!target) return;
      const res = await fetch(`/api/rooms/${roomId}/transfer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_owner: target }),
      });
      const data = await res.json();
      if (res.ok) {
        alert(`${data.new_owner}님에게 방장을 위임했습니다.`);
        window.location.reload();
      } else {
        alert(data.error || "위임에 실패했습니다.");
      }
    });
  }

  function showToast(text) {
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent = text;
    container.appendChild(toast);
    setTimeout(() => toast.classList.add("show"), 10);
    setTimeout(() => {
      toast.classList.remove("show");
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  function playBeep() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.value = 880;
      gain.gain.value = 0.1;
      osc.connect(gain).connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.15);
    } catch (e) {
      /* audio not available */
    }
  }
})();
