(function () {
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

  const socket = io();

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }
  scrollToBottom();

  socket.on("connect", () => {
    socket.emit("join", { room_id: Number(roomId) });
  });

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : str;
    return div.innerHTML;
  }

  function linkifyMentions(text) {
    return escapeHtml(text).replace(/@([^\s@,]+)/g, '<span class="mention">@$1</span>');
  }

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
        body = `<div class="msg-body"><img class="msg-image" src="/files/${roomId}/${msg.file_path}" alt=""></div>`;
      } else {
        body = `<div class="msg-body"><a href="/files/${roomId}/${msg.file_path}" target="_blank">📎 ${escapeHtml(msg.original_filename)}</a></div>`;
      }
      div.innerHTML =
        `<div class="msg-meta"><span class="msg-sender">${escapeHtml(msg.sender)}</span><span class="msg-time">${time}</span></div>` +
        body;
    }
    messagesEl.appendChild(div);
    scrollToBottom();
  }

  socket.on("new_message", (msg) => {
    if (Number(msg.room_id) !== Number(roomId)) return;
    appendMessage(msg);
  });

  socket.on("mention", (data) => {
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

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    socket.emit("send_message", { room_id: Number(roomId), text });
    input.value = "";
  });

  attachBtn.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", async () => {
    const file = fileInput.files[0];
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
    fileInput.value = "";
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
