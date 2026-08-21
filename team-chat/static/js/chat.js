(function () {
  // notify.js가 "채팅 페이지면 인앱 토스트로 충분하다"고 판단할 수 있도록 표시.
  window.__chatPageActive = true;

  const page = document.querySelector(".chat-page");
  const roomId = page.dataset.roomId;
  const nickname = page.dataset.nickname;
  const isAdmin = page.dataset.isAdmin === "true";

  const messagesEl = document.getElementById("messages");
  const form = document.getElementById("message-form");
  const input = document.getElementById("message-input");
  const fileInput = document.getElementById("file-input");
  const attachBtn = document.getElementById("btn-attach");
  const deleteBtn = document.getElementById("btn-delete");
  const transferBtn = document.getElementById("btn-transfer");
  const mentionSuggest = document.getElementById("mention-suggest");

  // 실시간으로 append되는 메시지도 SSR(chat.html)과 똑같은 아이콘을 쓰도록 여기 한 곳에서만
  // 관리한다 — 하드코딩된 이모지 대신 currentColor를 쓰는 SVG라 버튼 색(hover 포함)을 그대로 물려받는다.
  const ICON_SMILE = '<svg class="icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>';
  const ICON_USERS = '<svg class="icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>';
  const ICON_TRASH = '<svg class="icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>';
  const ICON_PAPERCLIP = '<svg class="icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>';
  const ICON_IMAGE_BROKEN = '<svg class="icon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>';

  const MENTION_ALL = "전체";
  let roomMembers = [];
  try {
    roomMembers = JSON.parse(page.dataset.roomMembers || "[]");
  } catch (e) {
    roomMembers = [];
  }
  const mentionCandidates = [MENTION_ALL, ...roomMembers];

  // 참여 인원 모달의 온라인/오프라인 점 표시를 실시간으로 갱신하기 위한 현재 접속자 집합
  let onlineUsers = new Set();
  try {
    onlineUsers = new Set(JSON.parse(page.dataset.onlineUsers || "[]"));
  } catch (e) {
    onlineUsers = new Set();
  }

  const socket = (window.ChatNotify && window.ChatNotify.getSocket()) || io();

  let latestMessageId = Number(page.dataset.lastMessageId) || 0;

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  // 이미지 메시지가 깨졌을 때(네트워크 오류, 삭제된 파일, 손상된 파일) 브라우저 기본 깨짐
  // 아이콘 대신 테마에 맞는 안내로 바꾼다. scopeEl 안의 .msg-image만 훑으므로 SSR로 이미
  // 그려진 메시지 전체와, 실시간으로 새로 붙는 메시지 한 건 양쪽에 다 쓸 수 있다.
  function bindImageFallback(scopeEl) {
    scopeEl.querySelectorAll("img.msg-image").forEach((img) => {
      function showFallback() {
        const fallback = document.createElement("div");
        fallback.className = "msg-image-fallback";
        fallback.innerHTML = `${ICON_IMAGE_BROKEN}<span>이미지를 불러올 수 없습니다</span>`;
        img.replaceWith(fallback);
      }
      if (img.complete) {
        if (img.naturalWidth === 0) showFallback();
        return;
      }
      img.addEventListener("load", () => {
        if (img.naturalWidth === 0) showFallback();
      }, { once: true });
      img.addEventListener("error", showFallback, { once: true });
    });
  }
  bindImageFallback(messagesEl);

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

  // notify.js가 이 페이지의 스크립트보다 먼저 소켓을 만들어두므로, DOM/메시지 렌더링에
  // 걸리는 시간 동안 소켓이 이미 connect돼버릴 수 있다. 그 경우 여기서 등록하는
  // connect 리스너는 다시 호출되지 않아 join emit이 영영 안 나가고(=이 방의 실시간
  // 메시지/리액션을 못 받음), 개인 대상 이벤트(배지 등)만 살아있어 원인이 잘 안 보인다.
  // 이미 연결돼 있으면 즉시 join하고, 이후 재연결(네트워크 끊김 등)에 대비해
  // connect 리스너도 계속 유지한다.
  function joinCurrentRoom() {
    socket.emit("join", { room_id: Number(roomId) });
    markReadIfVisible();
  }
  socket.on("connect", joinCurrentRoom);
  if (socket.connected) joinCurrentRoom();

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
        body = `<div class="msg-body"><a class="msg-file-link" href="/files/${roomId}/${msg.file_path}" download="${escapeHtml(msg.original_filename)}">${ICON_PAPERCLIP}${escapeHtml(msg.original_filename)}</a></div>`;
      }
      const unreadCount = msg.unread_count || 0;
      const unreadAttr = unreadCount ? "" : " hidden";
      const deleteBtnHtml = mine || isAdmin
        ? `<button type="button" class="msg-delete-btn" data-msg-id="${msg.id}" title="메시지 삭제" aria-label="메시지 삭제">${ICON_TRASH}</button>`
        : "";
      div.innerHTML =
        `<div class="msg-meta"><span class="msg-sender">${escapeHtml(msg.sender)}</span>` +
        `<span class="msg-unread" data-msg-id="${msg.id}"${unreadAttr}>${unreadCount}</span>` +
        `<span class="msg-time">${time}</span>` +
        `<button type="button" class="msg-react-btn" data-msg-id="${msg.id}" title="반응 남기기" aria-label="반응 남기기">${ICON_SMILE}</button>` +
        `<button type="button" class="msg-reactors-btn" data-msg-id="${msg.id}" title="반응자 보기" aria-label="반응자 보기" hidden>${ICON_USERS}</button>${deleteBtnHtml}</div>` +
        body +
        `<div class="msg-reactions"></div>` +
        `<div class="msg-reactors-detail" hidden></div>`;
      bindImageFallback(div);
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

  // ---- 메시지 반응(O/X/좋아요/싫어요/체크) ----
  const REACTIONS = [
    { key: "o", icon: "⭕" },
    { key: "x", icon: "❌" },
    { key: "like", icon: "👍" },
    { key: "dislike", icon: "👎" },
    { key: "check", icon: "✅" },
  ];
  // msgId(문자열) -> 내가 이미 남긴 반응 종류의 Set. 반응 종류별로 한 번씩만
  // 남길 수 있으므로(토글), 서버 응답이 아니라 이 클라이언트 상태로 pill의
  // "내가 남긴 반응" 표시 여부를 판단한다.
  const myReactions = new Map();

  function getMyReactionSet(msgId) {
    const key = String(msgId);
    if (!myReactions.has(key)) myReactions.set(key, new Set());
    return myReactions.get(key);
  }

  function renderReactions(msgDiv, counts, reactors) {
    const row = msgDiv.querySelector(".msg-reactions");
    if (!row) return;
    const msgId = msgDiv.dataset.msgId;
    const mine = getMyReactionSet(msgId);
    row.innerHTML = "";
    let hasAny = false;
    REACTIONS.forEach(({ key, icon }) => {
      const count = (counts || {})[key] || 0;
      if (count <= 0) return;
      hasAny = true;
      const names = (reactors || {})[key] || [];
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "reaction-pill" + (mine.has(key) ? " mine" : "");
      btn.dataset.reaction = key;
      btn.dataset.msgId = msgId;
      btn.textContent = `${icon} ${count}`;
      if (names.length) btn.title = names.join(", ");
      row.appendChild(btn);
    });

    const reactorsBtn = msgDiv.querySelector(".msg-reactors-btn");
    const detail = msgDiv.querySelector(".msg-reactors-detail");
    detail.innerHTML = "";
    REACTIONS.forEach(({ key, icon }) => {
      const names = (reactors || {})[key] || [];
      if (!names.length) return;
      const line = document.createElement("div");
      line.className = "msg-reactors-line";
      line.textContent = `${icon} ${names.join(", ")}`;
      detail.appendChild(line);
    });
    if (reactorsBtn) reactorsBtn.hidden = !hasAny;
    if (!hasAny) detail.hidden = true;
  }

  // 서버 렌더링(SSR)된 메시지들의 초기 반응 상태를 화면에 반영한다.
  messagesEl.querySelectorAll(".message[data-reactions]").forEach((msgDiv) => {
    let counts = {};
    let mine = [];
    let reactors = {};
    try {
      counts = JSON.parse(msgDiv.dataset.reactions || "{}");
      mine = JSON.parse(msgDiv.dataset.myReactions || "[]");
      reactors = JSON.parse(msgDiv.dataset.reactionUsers || "{}");
    } catch (e) {
      counts = {};
      mine = [];
      reactors = {};
    }
    mine.forEach((key) => getMyReactionSet(msgDiv.dataset.msgId).add(key));
    renderReactions(msgDiv, counts, reactors);
  });

  // 입장 시 맨 아래로: 반응 pill/멘션 렌더링까지 다 끝난 뒤에 재야 실제 높이 기준으로 맞는다
  // (반응이 있는 메시지가 뒤에 있으면 pill이 늘어나면서 이보다 먼저 스크롤하면 살짝 위에서 멈췄었다).
  // 이미지 메시지는 로딩되면서 나중에 더 늘어날 수 있어 로드될 때마다 한 번 더 보정한다.
  scrollToBottom();
  messagesEl.querySelectorAll("img.msg-image").forEach((img) => {
    if (img.complete) return;
    img.addEventListener("load", scrollToBottom, { once: true });
    img.addEventListener("error", scrollToBottom, { once: true });
  });

  async function toggleReaction(msgId, reaction) {
    try {
      const res = await fetch(`/api/messages/${msgId}/reactions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reaction }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        showToast(data.error || "반응을 남기지 못했습니다.");
      }
      // 실제 카운트/내 반응 상태 갱신은 reaction_update 소켓 이벤트로 처리한다.
    } catch (err) {
      showToast("반응을 남기는 중 오류가 발생했습니다.");
    }
  }

  function applyDeletedMessage(msgDiv) {
    msgDiv.querySelector(".msg-react-btn")?.remove();
    msgDiv.querySelector(".msg-delete-btn")?.remove();
    msgDiv.querySelector(".msg-reactors-btn")?.remove();
    msgDiv.querySelector(".msg-reactions")?.remove();
    msgDiv.querySelector(".msg-reactors-detail")?.remove();
    const body = msgDiv.querySelector(".msg-body");
    if (body) {
      body.className = "msg-body msg-body-deleted";
      body.textContent = "삭제된 메시지입니다.";
    }
  }

  async function deleteMessage(msgId) {
    if (!(await window.confirmDialog("메시지를 삭제할까요?"))) return;
    try {
      const res = await fetch(`/api/messages/${msgId}`, { method: "DELETE" });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        showToast(data.error || "메시지를 삭제하지 못했습니다.");
        return;
      }
      // 화면 갱신은 message_deleted 소켓 이벤트로 처리한다.
    } catch (err) {
      showToast("메시지를 삭제하는 중 오류가 발생했습니다.");
    }
  }

  messagesEl.addEventListener("click", (e) => {
    const delBtn = e.target.closest(".msg-delete-btn");
    if (delBtn) deleteMessage(delBtn.dataset.msgId);
  });

  socket.on("message_deleted", (data) => {
    if (Number(data.room_id) !== Number(roomId)) return;
    const msgDiv = messagesEl.querySelector(`.message[data-msg-id="${data.message_id}"]`);
    if (!msgDiv) return;
    if (data.hard) {
      msgDiv.remove();
    } else {
      applyDeletedMessage(msgDiv);
    }
  });

  const clearLogBtn = document.getElementById("btn-clear-log");
  const clearLogModal = document.getElementById("clear-log-modal");
  const clearLogModalClose = document.getElementById("clear-log-modal-close");
  const clearLogCancelBtn = document.getElementById("clear-log-cancel");
  const clearLogConfirmBtn = document.getElementById("clear-log-confirm");
  const clearLogStart = document.getElementById("clear-log-start");
  const clearLogEnd = document.getElementById("clear-log-end");
  const clearLogError = document.getElementById("clear-log-error");

  function openClearLogModal() {
    if (!clearLogModal) return;
    clearLogStart.value = "";
    clearLogEnd.value = "";
    clearLogError.textContent = "";
    clearLogModal.hidden = false;
  }

  function closeClearLogModal() {
    if (clearLogModal) clearLogModal.hidden = true;
  }

  if (clearLogBtn) clearLogBtn.addEventListener("click", openClearLogModal);
  if (clearLogModalClose) clearLogModalClose.addEventListener("click", closeClearLogModal);
  if (clearLogCancelBtn) clearLogCancelBtn.addEventListener("click", closeClearLogModal);
  if (clearLogModal) {
    clearLogModal.addEventListener("click", (e) => {
      if (e.target === clearLogModal) closeClearLogModal();
    });
  }

  if (clearLogConfirmBtn) {
    clearLogConfirmBtn.addEventListener("click", async () => {
      const start = clearLogStart.value;
      const end = clearLogEnd.value;
      clearLogError.textContent = "";
      if (!start || !end) {
        clearLogError.textContent = "시작일과 종료일을 모두 선택해주세요.";
        return;
      }
      if (start > end) {
        clearLogError.textContent = "시작일이 종료일보다 늦을 수 없습니다.";
        return;
      }
      if (!(await window.confirmDialog(`${start}부터 ${end}까지의 로그를 삭제합니다.\n계속하시겠습니까?`))) return;

      try {
        const res = await fetch(`/api/rooms/${roomId}/messages`, {
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ start_date: start, end_date: end }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          clearLogError.textContent = data.error || "로그를 삭제하지 못했습니다.";
          return;
        }
        closeClearLogModal();
      } catch (err) {
        clearLogError.textContent = "로그를 삭제하는 중 오류가 발생했습니다.";
      }
    });
  }

  socket.on("room_log_cleared", (data) => {
    if (Number(data.room_id) !== Number(roomId)) return;
    (data.deleted_message_ids || []).forEach((id) => {
      messagesEl.querySelector(`.message[data-msg-id="${id}"]`)?.remove();
    });
    if (data.system_message) appendMessage(data.system_message);
  });

  const reactionPicker = document.getElementById("reaction-picker");
  let pickerTargetMsgId = null;

  function openReactionPicker(anchorEl, msgId) {
    pickerTargetMsgId = msgId;
    const rect = anchorEl.getBoundingClientRect();
    reactionPicker.hidden = false;
    const pickerWidth = reactionPicker.offsetWidth || 220;
    const left = Math.min(Math.max(rect.left, 4), window.innerWidth - pickerWidth - 4);
    const top = rect.top - reactionPicker.offsetHeight - 8;
    reactionPicker.style.left = `${left}px`;
    reactionPicker.style.top = `${Math.max(top, 4)}px`;
  }

  function closeReactionPicker() {
    reactionPicker.hidden = true;
    pickerTargetMsgId = null;
  }

  messagesEl.addEventListener("click", (e) => {
    const pill = e.target.closest(".reaction-pill");
    if (pill) {
      toggleReaction(pill.dataset.msgId, pill.dataset.reaction);
      return;
    }
    const reactBtn = e.target.closest(".msg-react-btn");
    if (reactBtn) {
      openReactionPicker(reactBtn, reactBtn.dataset.msgId);
      return;
    }
    const reactorsBtn = e.target.closest(".msg-reactors-btn");
    if (reactorsBtn) {
      const msgDiv = reactorsBtn.closest(".message");
      const detail = msgDiv && msgDiv.querySelector(".msg-reactors-detail");
      if (detail) detail.hidden = !detail.hidden;
    }
  });

  reactionPicker.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-reaction]");
    if (!btn || !pickerTargetMsgId) return;
    toggleReaction(pickerTargetMsgId, btn.dataset.reaction);
    closeReactionPicker();
  });

  document.addEventListener("click", (e) => {
    if (reactionPicker.hidden) return;
    if (reactionPicker.contains(e.target) || e.target.closest(".msg-react-btn")) return;
    closeReactionPicker();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !reactionPicker.hidden) closeReactionPicker();
  });

  socket.on("reaction_update", (data) => {
    if (Number(data.room_id) !== Number(roomId)) return;
    const msgDiv = messagesEl.querySelector(`.message[data-msg-id="${data.message_id}"]`);
    if (!msgDiv) return;
    if (data.nickname === nickname) {
      const mine = getMyReactionSet(data.message_id);
      if (data.added) mine.add(data.reaction);
      else mine.delete(data.reaction);
    }
    renderReactions(msgDiv, data.counts, data.reactors);
  });

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
      showToast("이 방이 삭제되었습니다. 목록으로 이동합니다.");
      setTimeout(() => { window.location.href = "/rooms"; }, 1500);
    }
  });

  socket.on("owner_changed", (data) => {
    if (Number(data.room_id) === Number(roomId)) {
      window.location.reload();
    }
  });

  socket.on("room_member_added", (data) => {
    if (Number(data.room_id) !== Number(roomId)) return;
    if (data.nickname) addMemberToUI(data.nickname, !!data.online);
  });

  socket.on("active_users_update", (data) => {
    onlineUsers = new Set(data.users || []);
    refreshParticipantStatusDots();
  });

  socket.on("room_member_removed", (data) => {
    if (Number(data.room_id) !== Number(roomId)) return;
    if (data.nickname === nickname) {
      showToast("이 방에서 제외되었습니다. 목록으로 이동합니다.");
      setTimeout(() => { window.location.href = "/rooms"; }, 1500);
      return;
    }
    removeMemberFromUI(data.nickname);
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

  function autoResizeInput() {
    input.style.height = "auto";
    input.style.height = input.scrollHeight + "px";
  }
  input.addEventListener("input", autoResizeInput);

  input.addEventListener("keydown", (e) => {
    if (!mentionSuggest.hidden) {
      const items = mentionSuggest.querySelectorAll("li");
      if (items.length) {
        if (e.key === "ArrowDown") {
          e.preventDefault();
          setActiveItem(items, (mentionActiveIndex + 1) % items.length);
          return;
        } else if (e.key === "ArrowUp") {
          e.preventDefault();
          setActiveItem(items, (mentionActiveIndex - 1 + items.length) % items.length);
          return;
        } else if (e.key === "Enter" || e.key === "Tab") {
          if (mentionActiveIndex >= 0) {
            e.preventDefault();
            selectMention(items[mentionActiveIndex].dataset.name);
            return;
          }
        } else if (e.key === "Escape") {
          closeMentionSuggest();
          return;
        }
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    socket.emit("send_message", { room_id: Number(roomId), text });
    input.value = "";
    autoResizeInput();
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
        showToast(data.error || "업로드에 실패했습니다.");
      }
    } catch (err) {
      showToast("업로드 중 오류가 발생했습니다.");
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
      if (!(await window.confirmDialog("정말 이 방을 삭제하시겠습니까?"))) return;
      const res = await fetch(`/api/rooms/${roomId}`, { method: "DELETE" });
      const data = await res.json();
      if (res.ok) {
        window.location.href = "/rooms";
      } else {
        showToast(data.error || "삭제에 실패했습니다.");
      }
    });
  }

  // 방장 위임: 예전엔 prompt()로 닉네임을 직접 입력받아서(오타/존재하지 않는 사용자 검증도
  // 안 됨) 데스크톱 빌드에서 입력 먹통을 일으키던 그 API를 그대로 썼다. 참여 인원 초대와
  // 같은 방식으로, 실제 방 멤버(roomMembers) 중에서만 고르는 select로 바꿨다.
  const transferModal = document.getElementById("transfer-modal");
  const transferSelect = document.getElementById("transfer-select");
  const transferError = document.getElementById("transfer-error");
  const transferEmptyHint = document.getElementById("transfer-empty-hint");
  const transferConfirmBtn = document.getElementById("transfer-confirm");

  function openTransferModal() {
    if (!transferModal) return;
    if (transferError) transferError.textContent = "";
    const hasMembers = roomMembers.length > 0;
    if (transferSelect) {
      transferSelect.innerHTML = roomMembers.map((n) => `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`).join("");
      transferSelect.hidden = !hasMembers;
    }
    if (transferEmptyHint) transferEmptyHint.hidden = hasMembers;
    if (transferConfirmBtn) transferConfirmBtn.hidden = !hasMembers;
    transferModal.hidden = false;
  }
  function closeTransferModal() {
    if (transferModal) transferModal.hidden = true;
  }
  if (transferBtn) transferBtn.addEventListener("click", openTransferModal);
  if (transferModal) {
    transferModal.addEventListener("click", (e) => {
      if (e.target === transferModal) closeTransferModal();
    });
    const closeBtn = transferModal.querySelector(".modal-close");
    if (closeBtn) closeBtn.addEventListener("click", closeTransferModal);
  }
  const transferCancelBtn = document.getElementById("transfer-cancel");
  if (transferCancelBtn) transferCancelBtn.addEventListener("click", closeTransferModal);
  if (transferConfirmBtn) {
    transferConfirmBtn.addEventListener("click", async () => {
      const target = transferSelect.value;
      if (!target) return;
      if (!(await window.confirmDialog(`${target}님에게 방장을 위임할까요?`))) return;
      const res = await fetch(`/api/rooms/${roomId}/transfer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_owner: target }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        closeTransferModal();
        window.location.reload();
      } else if (transferError) {
        transferError.textContent = data.error || "위임에 실패했습니다.";
      }
    });
  }

  // ---- 참여 인원 조회/관리 모달 ----
  const participantsBtn = document.getElementById("btn-participants");
  const participantsModal = document.getElementById("participants-modal");

  function statusDot(online) {
    const dot = document.createElement("span");
    dot.className = "status-dot " + (online ? "online" : "offline");
    return dot;
  }

  function refreshParticipantStatusDots() {
    if (!participantsModal) return;
    participantsModal.querySelectorAll("#participants-list [data-nickname]").forEach((li) => {
      const dot = li.querySelector(".status-dot");
      if (!dot) return;
      const isOnline = li.dataset.nickname === nickname || onlineUsers.has(li.dataset.nickname);
      dot.classList.toggle("online", isOnline);
      dot.classList.toggle("offline", !isOnline);
    });
  }

  function addMemberToUI(memberNickname, online) {
    if (!participantsModal) return;
    const list = document.getElementById("participants-list");
    if (!list || list.querySelector(`[data-nickname="${CSS.escape(memberNickname)}"]`)) return;
    const li = document.createElement("li");
    li.className = "room-item";
    li.dataset.nickname = memberNickname;

    const span = document.createElement("span");
    span.className = "room-name";
    span.appendChild(statusDot(online));
    span.appendChild(document.createTextNode(memberNickname));
    li.appendChild(span);

    const canManage = !!document.getElementById("invite-select");
    if (canManage) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn-danger btn-remove-member";
      btn.dataset.nickname = memberNickname;
      btn.textContent = "삭제";
      li.appendChild(btn);
    }
    list.appendChild(li);
    const inviteSelect = document.getElementById("invite-select");
    if (inviteSelect) {
      const opt = inviteSelect.querySelector(`option[value="${CSS.escape(memberNickname)}"]`);
      if (opt) opt.remove();
    }
  }

  function removeMemberFromUI(memberNickname) {
    if (!participantsModal) return;
    const list = document.getElementById("participants-list");
    const li = list && list.querySelector(`[data-nickname="${CSS.escape(memberNickname)}"]`);
    if (li) li.remove();
    const inviteSelect = document.getElementById("invite-select");
    if (inviteSelect && !inviteSelect.querySelector(`option[value="${CSS.escape(memberNickname)}"]`)) {
      const opt = document.createElement("option");
      opt.value = memberNickname;
      opt.textContent = `${onlineUsers.has(memberNickname) ? "🟢" : "⚪"} ${memberNickname}`;
      inviteSelect.appendChild(opt);
    }
  }

  if (participantsBtn && participantsModal) {
    const participantsModalClose = document.getElementById("participants-modal-close");
    const participantsError = document.getElementById("participants-error");
    const inviteBtn = document.getElementById("btn-invite");
    const inviteSelect = document.getElementById("invite-select");

    participantsBtn.addEventListener("click", () => {
      if (participantsError) participantsError.textContent = "";
      refreshParticipantStatusDots();
      participantsModal.hidden = false;
    });
    participantsModalClose.addEventListener("click", () => {
      participantsModal.hidden = true;
    });
    participantsModal.addEventListener("click", (e) => {
      if (e.target === participantsModal) participantsModal.hidden = true;
    });

    if (inviteBtn && inviteSelect) {
      inviteBtn.addEventListener("click", async () => {
        const target = inviteSelect.value;
        if (participantsError) participantsError.textContent = "";
        if (!target) return;
        try {
          const res = await fetch(`/api/rooms/${roomId}/members`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ nickname: target }),
          });
          const data = await res.json();
          if (!res.ok) {
            if (participantsError) participantsError.textContent = data.error || "초대에 실패했습니다.";
            return;
          }
          addMemberToUI(target, onlineUsers.has(target));
        } catch (err) {
          if (participantsError) participantsError.textContent = "초대 중 오류가 발생했습니다.";
        }
      });
    }

    document.getElementById("participants-list").addEventListener("click", async (e) => {
      const btn = e.target.closest(".btn-remove-member");
      if (!btn) return;
      const target = btn.dataset.nickname;
      if (!(await window.confirmDialog(`${target}님을 방에서 제외하시겠습니까?`))) return;
      if (participantsError) participantsError.textContent = "";
      try {
        const res = await fetch(`/api/rooms/${roomId}/members/${encodeURIComponent(target)}`, {
          method: "DELETE",
        });
        const data = await res.json();
        if (!res.ok) {
          if (participantsError) participantsError.textContent = data.error || "제외에 실패했습니다.";
          return;
        }
        removeMemberFromUI(target);
      } catch (err) {
        if (participantsError) participantsError.textContent = "제외 중 오류가 발생했습니다.";
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
