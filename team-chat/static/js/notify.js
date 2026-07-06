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

  function showNotification(data) {
    if (!("Notification" in window) || Notification.permission !== "granted") return;
    const noti = new Notification(`${data.sender}님이 회원님을 멘션했습니다`, {
      body: `[${data.room_name}] ${data.text}`,
      tag: `mention-room-${data.room_id}`,
    });
    noti.onclick = () => {
      window.focus();
      window.location.href = `/chat/${data.room_id}`;
      noti.close();
    };
  }

  if (nickname) {
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }

    socket = io();

    socket.on("mention", (data) => {
      // 다른 탭을 보고 있거나 브라우저가 최소화된 상태(문서가 보이지 않는 상태)에서만
      // OS 알림과 탭 타이틀 배지를 사용한다. 현재 보고 있는 중이면 페이지 내 토스트로 충분하다.
      if (document.hidden) {
        bumpUnread();
        showNotification(data);
      }
    });

    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") {
        resetUnread();
      }
    });
  }

  return {
    getSocket: () => socket,
  };
})();
