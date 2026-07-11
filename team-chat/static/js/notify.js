// 로그인한 모든 페이지(방 목록, 채팅방)에서 공유하는 소켓 연결 + 멘션 알림 처리.
// base.html에서 chat.js/rooms.js보다 먼저 로드되어 window.ChatNotify로 노출된다.
window.ChatNotify = (function () {
  const nickname = document.body.dataset.nickname;
  const baseTitle = document.title;
  let unreadCount = 0;
  let socket = null;

  function updateTitle() {
    document.title = unreadCount > 0 ? `(${unreadCount}) ${baseTitle}` : baseTitle;
  }

  function bumpUnread() {
    unreadCount += 1;
    updateTitle();
  }

  function resetUnread() {
    unreadCount = 0;
    updateTitle();
  }

  // document.hidden(visibilityState)은 "탭이 다른 탭에 가려졌는지"만 알려줄 뿐,
  // 브라우저 창 자체가 다른 앱에 밀려 백그라운드에 있는 경우(탭은 여전히 visible)는
  // 잡아내지 못한다. 그래서 창 포커스 여부(hasFocus)까지 함께 확인해야 실제로
  // 사용자가 화면을 보고 있는지 판단할 수 있다.
  function isBackgrounded() {
    return document.hidden || !document.hasFocus();
  }

  function showNotification(data) {
    if (!("Notification" in window)) return;
    if (Notification.permission !== "granted") {
      console.warn("[notify] OS 알림 권한이 허용되지 않아 팝업을 표시할 수 없습니다:", Notification.permission);
      return;
    }
    const noti = new Notification(`${data.sender}님이 회원님을 멘션했습니다`, {
      body: `[${data.room_name}] ${data.text}`,
      tag: `mention-room-${data.room_id}`,
      renotify: true,
    });
    noti.onclick = () => {
      window.focus();
      window.location.href = `/chat/${data.room_id}`;
      noti.close();
    };
  }

  function requestPermissionIfNeeded() {
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }

  function updateSidebarMentionBadge(total) {
    const badge = document.getElementById("sidebar-mention-badge");
    if (!badge) return;
    if (total > 0) {
      badge.hidden = false;
      badge.textContent = total;
    } else {
      badge.hidden = true;
      badge.textContent = "";
    }
  }

  if (nickname) {
    requestPermissionIfNeeded();
    // Safari 등 일부 브라우저는 사용자 제스처 없이 호출된 requestPermission을 무시하므로
    // 최초 클릭 시 한 번 더 시도한다.
    document.addEventListener("click", requestPermissionIfNeeded, { once: true });

    socket = io();

    socket.on("mention_count_update", (data) => {
      updateSidebarMentionBadge(data.total || 0);
    });

    socket.on("mention", (data) => {
      // 채팅 페이지(chat.js)가 로드되어 있고 화면을 보고 있는 중이면 그쪽 인앱 토스트로
      // 충분하므로 여기서는 무시한다. 방 목록/일정/엑셀 등 chat.js가 없는 페이지에서는
      // 토스트가 뜰 곳이 없으므로, focus 여부와 무관하게 항상 OS 알림을 띄운다.
      const handledByChatToast = window.__chatPageActive === true && !isBackgrounded();
      if (!handledByChatToast) {
        bumpUnread();
        showNotification(data);
      }
    });

    const handleForegroundReturn = () => {
      if (!isBackgrounded()) {
        resetUnread();
      }
    };
    document.addEventListener("visibilitychange", handleForegroundReturn);
    window.addEventListener("focus", handleForegroundReturn);
  }

  return {
    getSocket: () => socket,
    isBackgrounded,
  };
})();
