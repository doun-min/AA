(function () {
  const createForm = document.getElementById("create-room-form");
  const nameInput = document.getElementById("new-room-name");
  const errorEl = document.getElementById("room-error");

  if (createForm) {
    createForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      errorEl.textContent = "";
      const name = nameInput.value.trim();
      if (!name) return;
      const res = await fetch("/api/rooms", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const data = await res.json();
      if (res.ok) {
        window.location.reload();
      } else {
        errorEl.textContent = data.error || "방 생성에 실패했습니다.";
      }
    });
  }

  document.querySelectorAll(".btn-delete-room").forEach((btn) => {
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
  });

  document.querySelectorAll(".btn-dm").forEach((btn) => {
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
  });

  const socket = window.ChatNotify && window.ChatNotify.getSocket();
  if (socket) {
    socket.on("mention_count_update", (data) => {
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
  }
})();
