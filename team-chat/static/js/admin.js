(function () {
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

  document.querySelectorAll(".btn-delete-user").forEach(bindDeleteUserButton);
  document.querySelectorAll(".btn-demote-admin").forEach(bindDemoteAdminButton);

  const socket = window.ChatNotify && window.ChatNotify.getSocket();
  if (socket) {
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
