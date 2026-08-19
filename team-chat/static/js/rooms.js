(function () {
  const openBtn = document.getElementById("btn-open-create-room");
  const modal = document.getElementById("create-room-modal");
  const modalCloseBtn = document.getElementById("create-room-modal-close");
  const cancelBtn = document.getElementById("create-room-cancel");
  const createForm = document.getElementById("create-room-form");
  const nameInput = document.getElementById("new-room-name");
  const errorEl = document.getElementById("room-error");
  const privateToggle = document.getElementById("new-room-private");
  const visibilityIcon = document.getElementById("room-visibility-icon");
  const visibilityLabel = document.getElementById("room-visibility-label");
  const inviteRow = document.getElementById("new-room-invite-row");
  const memberSelect = document.getElementById("new-room-member-select");
  const addMemberBtn = document.getElementById("btn-add-room-member");
  const memberList = document.getElementById("new-room-member-list");
  const noUsersHint = document.getElementById("new-room-no-users-hint");
  const activeUsersList = document.getElementById("active-users-list");
  const groupRoomList = document.getElementById("group-room-list");

  const selectedMembers = new Set();
  // 방 생성 초대 후보(DB에 등록된 전체 사용자)의 최신 온라인 상태를 기억해뒀다가
  // 선택 목록/드롭다운의 점 표시를 갱신할 때 쓴다.
  const nicknameOnlineMap = new Map();

  function statusDot(online) {
    const dot = document.createElement("span");
    dot.className = "status-dot " + (online ? "online" : "offline");
    return dot;
  }

  function updateVisibilityUI() {
    const isPrivate = !!(privateToggle && privateToggle.checked);
    const hasOptions = !!memberSelect && memberSelect.options.length > 1;
    if (visibilityIcon) visibilityIcon.textContent = isPrivate ? "🔒" : "🔓";
    if (visibilityLabel) visibilityLabel.textContent = isPrivate ? "비공개 방" : "공개 방";
    if (inviteRow) inviteRow.hidden = !isPrivate || !hasOptions;
    if (noUsersHint) noUsersHint.hidden = !isPrivate || hasOptions;
    if (memberList) memberList.hidden = !isPrivate || selectedMembers.size === 0;
  }

  function renderMemberList() {
    if (!memberList) return;
    memberList.innerHTML = "";
    selectedMembers.forEach((nickname) => {
      const li = document.createElement("li");
      li.className = "room-item";
      li.dataset.nickname = nickname;

      const span = document.createElement("span");
      span.className = "room-name";
      span.appendChild(statusDot(!!nicknameOnlineMap.get(nickname)));
      span.appendChild(document.createTextNode(nickname));

      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "btn-danger";
      removeBtn.textContent = "제거";
      removeBtn.addEventListener("click", () => {
        selectedMembers.delete(nickname);
        if (memberSelect) {
          const opt = memberSelect.querySelector(`option[value="${CSS.escape(nickname)}"]`);
          if (opt) opt.hidden = false;
        }
        renderMemberList();
      });

      li.appendChild(span);
      li.appendChild(removeBtn);
      memberList.appendChild(li);
    });
    memberList.hidden = !(privateToggle && privateToggle.checked) || selectedMembers.size === 0;
  }

  // 방 생성 시 초대 후보(select) 목록을 DB에 등록된 전체 사용자로 다시 그린다.
  // 온라인/오프라인 여부는 🟢/⚪ 표시로만 구분하고, 선택 자체는 오프라인 사용자도 가능하다.
  function applyAllUsers(users) {
    nicknameOnlineMap.clear();
    users.forEach((u) => nicknameOnlineMap.set(u.nickname, u.online));

    if (memberSelect) {
      const currentValue = memberSelect.value;
      memberSelect.innerHTML = "";
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "초대할 사용자 선택";
      memberSelect.appendChild(placeholder);

      users.forEach((u) => {
        const opt = document.createElement("option");
        opt.value = u.nickname;
        opt.textContent = `${u.online ? "🟢" : "⚪"} ${u.nickname}`;
        if (selectedMembers.has(u.nickname)) opt.hidden = true;
        memberSelect.appendChild(opt);
      });
      memberSelect.value = users.some((u) => u.nickname === currentValue) ? currentValue : "";
    }

    renderMemberList();
    updateVisibilityUI();
  }

  // 소켓으로 접속자 목록이 바뀔 때는 전체 목록을 다시 받아오지 않고, 이미 그려둔
  // select/선택 목록의 🟢/⚪ 표시만 최신 상태로 갱신한다.
  function refreshOnlineDots(onlineSet) {
    nicknameOnlineMap.forEach((_, nickname) => nicknameOnlineMap.set(nickname, onlineSet.has(nickname)));
    if (memberSelect) {
      Array.from(memberSelect.options).forEach((opt) => {
        if (!opt.value) return;
        opt.textContent = `${onlineSet.has(opt.value) ? "🟢" : "⚪"} ${opt.value}`;
      });
    }
    renderMemberList();
  }

  function applyActiveUsersPanel(users) {
    if (!activeUsersList) return;
    activeUsersList.innerHTML = "";
    if (users.length === 0) {
      const li = document.createElement("li");
      li.className = "empty";
      li.textContent = "다른 접속자가 없습니다.";
      activeUsersList.appendChild(li);
      return;
    }
    users.forEach((u) => {
      const li = document.createElement("li");
      li.className = "room-item";

      const span = document.createElement("span");
      span.className = "room-name";
      span.textContent = u;

      const btn = document.createElement("button");
      btn.className = "btn-secondary btn-dm";
      btn.dataset.target = u;
      btn.textContent = "1:1 대화";
      bindDmButton(btn);

      li.appendChild(span);
      li.appendChild(btn);
      activeUsersList.appendChild(li);
    });
  }

  async function fetchAllUsers() {
    try {
      const res = await fetch("/api/all_users");
      if (!res.ok) return;
      const data = await res.json();
      applyAllUsers(data.users || []);
    } catch (err) {
      // 네트워크 오류 시에는 마지막으로 알고 있던 목록을 그대로 둔다.
    }
  }

  if (privateToggle) {
    privateToggle.addEventListener("change", updateVisibilityUI);
  }

  if (addMemberBtn && memberSelect) {
    addMemberBtn.addEventListener("click", () => {
      const value = memberSelect.value;
      if (!value || selectedMembers.has(value)) return;
      selectedMembers.add(value);
      const opt = memberSelect.querySelector(`option[value="${CSS.escape(value)}"]`);
      if (opt) opt.hidden = true;
      memberSelect.value = "";
      renderMemberList();
    });
  }

  function resetCreateRoomForm() {
    if (createForm) createForm.reset();
    if (errorEl) errorEl.textContent = "";
    selectedMembers.clear();
    if (memberSelect) {
      Array.from(memberSelect.options).forEach((opt) => { opt.hidden = false; });
      memberSelect.value = "";
    }
    renderMemberList();
    updateVisibilityUI();
  }

  function openCreateRoomModal() {
    resetCreateRoomForm();
    if (modal) modal.hidden = false;
    if (nameInput) nameInput.focus();
    // 모달을 열 때마다 전체 사용자 목록을 한 번 더 재조회해서, 혹시 놓쳤을 수도 있는
    // 실시간 이벤트(소켓 유실 등)와 무관하게 항상 최신 상태로 시작하게 한다.
    fetchAllUsers();
  }

  function closeCreateRoomModal() {
    if (modal) modal.hidden = true;
  }

  if (openBtn && modal) {
    openBtn.addEventListener("click", openCreateRoomModal);
    if (modalCloseBtn) modalCloseBtn.addEventListener("click", closeCreateRoomModal);
    if (cancelBtn) cancelBtn.addEventListener("click", closeCreateRoomModal);
    modal.addEventListener("click", (e) => {
      if (e.target === modal) closeCreateRoomModal();
    });
  }

  if (createForm) {
    createForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      errorEl.textContent = "";
      const name = nameInput.value.trim();
      if (!name) return;
      const isPrivate = !!(privateToggle && privateToggle.checked);
      const members = isPrivate ? Array.from(selectedMembers) : [];
      const res = await fetch("/api/rooms", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, is_private: isPrivate, members }),
      });
      const data = await res.json();
      if (res.ok) {
        window.location.reload();
      } else {
        errorEl.textContent = data.error || "방 생성에 실패했습니다.";
      }
    });
  }

  function bindDeleteButton(btn) {
    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (!confirm("정말 이 방을 삭제하시겠습니까?")) return;
      const roomId = btn.dataset.roomId;
      const res = await fetch(`/api/rooms/${roomId}`, { method: "DELETE" });
      const data = await res.json();
      if (res.ok) {
        window.location.reload();
      } else {
        alert(data.error || "삭제에 실패했습니다.");
      }
    });
  }

  function bindDeleteButtons() {
    document.querySelectorAll(".btn-delete-room").forEach(bindDeleteButton);
  }

  function bindDmButton(btn) {
    btn.addEventListener("click", async () => {
      const target = btn.dataset.target;
      const res = await fetch("/api/rooms/direct", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target }),
      });
      const data = await res.json();
      if (res.ok) {
        window.location.href = `/chat/${data.room.id}`;
      } else {
        alert(data.error || "1:1 대화를 시작할 수 없습니다.");
      }
    });
  }

  function bindDeleteUserButton(btn) {
    btn.addEventListener("click", async () => {
      const target = btn.dataset.nickname;
      if (!confirm(`${target}님의 계정을 완전히 삭제할까요? 되돌릴 수 없습니다.`)) return;
      const res = await fetch(`/api/users/${encodeURIComponent(target)}`, { method: "DELETE" });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        btn.closest("li")?.remove();
      } else {
        alert(data.error || "계정을 삭제하지 못했습니다.");
      }
    });
  }

  function bindDemoteAdminButton(btn) {
    btn.addEventListener("click", async () => {
      const target = btn.dataset.nickname;
      if (!confirm(`${target}님의 관리자 권한을 해제할까요?`)) return;
      const res = await fetch(`/api/admins/${encodeURIComponent(target)}`, { method: "DELETE" });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        window.location.reload();
      } else {
        alert(data.error || "관리자 해제에 실패했습니다.");
      }
    });
  }

  const promoteAdminBtn = document.getElementById("btn-promote-admin");
  const promoteAdminSelect = document.getElementById("promote-admin-select");
  const adminManageError = document.getElementById("admin-manage-error");
  if (promoteAdminBtn && promoteAdminSelect) {
    promoteAdminBtn.addEventListener("click", async () => {
      if (adminManageError) adminManageError.textContent = "";
      const target = promoteAdminSelect.value;
      if (!target) return;
      if (!confirm(`${target}님을 관리자로 지정할까요?`)) return;
      const res = await fetch("/api/admins", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nickname: target }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        window.location.reload();
      } else if (adminManageError) {
        adminManageError.textContent = data.error || "관리자 지정에 실패했습니다.";
      } else {
        alert(data.error || "관리자 지정에 실패했습니다.");
      }
    });
  }

  bindDeleteButtons();
  document.querySelectorAll(".btn-dm").forEach(bindDmButton);
  document.querySelectorAll(".btn-delete-user").forEach(bindDeleteUserButton);
  document.querySelectorAll(".btn-demote-admin").forEach(bindDemoteAdminButton);

  // room_member_added/removed(비공개 방에 초대되거나 방에서 빠짐) 발생 시
  // 예전에는 전체 새로고침(window.location.reload)으로 처리했는데, 화면이
  // 통째로 깜빡이고 스크롤/모달 상태가 날아가는 게 부자연스러워서 채팅방
  // 목록 부분(#group-room-list)만 서버에서 다시 받아 그 자리만 갈아끼운다.
  async function refreshGroupRoomsPanel() {
    if (!groupRoomList) {
      window.location.reload();
      return;
    }
    try {
      const res = await fetch(window.location.pathname);
      if (!res.ok) throw new Error("refresh failed");
      const html = await res.text();
      const freshList = new DOMParser().parseFromString(html, "text/html").getElementById("group-room-list");
      if (!freshList) throw new Error("group-room-list not found");
      document.getElementById("group-room-list").replaceWith(freshList);
      bindDeleteButtons();
    } catch (err) {
      // 부분 갱신이 실패하면 예전처럼 전체 새로고침으로 안전하게 폴백한다.
      window.location.reload();
    }
  }

  const socket = window.ChatNotify && window.ChatNotify.getSocket();
  if (socket) {
    socket.on("unread_count_update", (data) => {
      const rooms = data.rooms || {};
      document.querySelectorAll(".badge-count[data-room-id]").forEach((badge) => {
        const count = rooms[badge.dataset.roomId] || 0;
        if (count > 0) {
          badge.hidden = false;
          badge.textContent = count;
        } else {
          badge.hidden = true;
          badge.textContent = "";
        }
      });
    });

    socket.on("room_member_added", refreshGroupRoomsPanel);
    socket.on("room_member_removed", refreshGroupRoomsPanel);

    socket.on("active_users_update", (data) => {
      const myNickname = document.body.dataset.nickname;
      const users = data.users || [];
      applyActiveUsersPanel(users.filter((u) => u !== myNickname));
      refreshOnlineDots(new Set(users));
    });

    socket.on("user_account_deleted", (data) => {
      document
        .querySelector(`#manageable-users-list li[data-nickname="${CSS.escape(data.nickname)}"]`)
        ?.remove();
    });

    // 본인의 권한 변경(알림+새로고침)은 notify.js가 처리하므로, 여기서는 다른 사람의
    // 변경 사항만 반영한다 — 이 화면(관리자 관리 패널)을 최신 상태로 새로고침한다.
    socket.on("admin_role_changed", (data) => {
      const myNickname = document.body.dataset.nickname;
      if (data.nickname !== myNickname) {
        window.location.reload();
      }
    });
  }
})();
