(function () {
  const sidebar = document.getElementById("sidebar");
  const toggleBtn = document.getElementById("sidebar-toggle");
  const backdrop = document.getElementById("sidebar-backdrop");
  const chatRoomRail = document.getElementById("chat-room-rail");
  const chatRoomsToggle = document.getElementById("chat-rooms-toggle");
  const chatRoomsBackdrop = document.getElementById("chat-rooms-backdrop");
  if (!sidebar || !toggleBtn) return;

  function closeRoomRail() {
    if (!chatRoomRail) return;
    chatRoomRail.classList.remove("open");
    chatRoomsBackdrop.hidden = true;
    chatRoomsToggle.setAttribute("aria-expanded", "false");
  }

  function openSidebar() {
    closeRoomRail();
    sidebar.classList.add("open");
    backdrop.hidden = false;
    toggleBtn.setAttribute("aria-expanded", "true");
    toggleBtn.setAttribute("aria-label", "사이드바 닫기");
  }

  function closeSidebar() {
    sidebar.classList.remove("open");
    backdrop.hidden = true;
    toggleBtn.setAttribute("aria-expanded", "false");
    toggleBtn.setAttribute("aria-label", "사이드바 열기");
  }

  toggleBtn.addEventListener("click", () => {
    if (sidebar.classList.contains("open")) {
      closeSidebar();
    } else {
      openSidebar();
    }
  });

  backdrop.addEventListener("click", closeSidebar);
  if (chatRoomsToggle) {
    chatRoomsToggle.addEventListener("click", () => {
      if (chatRoomRail.classList.contains("open")) {
        closeRoomRail();
      } else {
        closeSidebar();
        chatRoomRail.classList.add("open");
        chatRoomsBackdrop.hidden = false;
        chatRoomsToggle.setAttribute("aria-expanded", "true");
      }
    });
    chatRoomsBackdrop.addEventListener("click", closeRoomRail);
    window.matchMedia("(min-width: 1024px)").addEventListener("change", closeRoomRail);
  }
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (sidebar.classList.contains("open")) closeSidebar();
    else closeRoomRail();
  });

  const list = document.getElementById("sidebar-room-list");
  const socket = window.ChatNotify && window.ChatNotify.getSocket();
  if (!list || !socket) return;
  const currentRoomId = Number(list.dataset.currentRoomId);
  let refreshTimer;
  let requestId = 0;

  function renderSection(rooms) {
    const section = document.createElement("section");
    section.className = "sidebar-room-section";
    const heading = document.createElement("h2");
    heading.textContent = "최근 대화 · 최대 8개";
    section.appendChild(heading);
    if (!rooms.length) {
      const empty = document.createElement("p");
      empty.className = "sidebar-room-empty";
      empty.textContent = "최근 대화가 없습니다.";
      section.appendChild(empty);
    }
    rooms.forEach((room) => {
      const link = document.createElement("a");
      link.className = "sidebar-room-link";
      link.href = `/chat/${room.id}`;
      link.dataset.roomId = room.id;
      if (Number(room.id) === currentRoomId) {
        link.classList.add("active");
        link.setAttribute("aria-current", "page");
      }
      const top = document.createElement("span");
      top.className = "sidebar-room-top";
      const name = document.createElement("span");
      name.className = "sidebar-room-name";
      name.textContent = room.name;
      const badge = document.createElement("span");
      badge.className = "badge-count";
      badge.hidden = !room.unread_count;
      badge.textContent = room.unread_count || "";
      top.append(name, badge);
      const preview = document.createElement("span");
      preview.className = "sidebar-room-preview";
      preview.textContent = room.preview;
      preview.title = room.preview;
      link.append(top, preview);
      section.appendChild(link);
    });
    return section;
  }

  async function refreshRooms() {
    const id = ++requestId;
    try {
      const response = await fetch(`/api/sidebar/rooms?current_room_id=${currentRoomId}`);
      if (!response.ok) return;
      const rooms = await response.json();
      if (id !== requestId) return;
      list.replaceChildren(renderSection(rooms.rooms || []));
      const total = Number(rooms.total_unread) || 0;
      const toggleBadge = document.getElementById("sidebar-toggle-badge");
      if (toggleBadge) {
        toggleBadge.hidden = !total;
        toggleBadge.textContent = total || "";
      }
    } catch (error) {
      // 연결이 복구되면 connect 이벤트에서 다시 불러온다.
    }
  }

  function scheduleRefresh() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(refreshRooms, 80);
  }

  socket.on("unread_count_update", (data) => {
    const counts = data.rooms || {};
    list.querySelectorAll(".sidebar-room-link").forEach((link) => {
      const badge = link.querySelector(".badge-count");
      const count = counts[link.dataset.roomId] || 0;
      badge.hidden = !count;
      badge.textContent = count || "";
    });
    scheduleRefresh();
  });
  ["sidebar_rooms_updated", "room_list_updated", "room_member_added", "room_member_removed", "user_account_deleted"].forEach((event) => socket.on(event, scheduleRefresh));
  socket.on("connect", scheduleRefresh);
})();
