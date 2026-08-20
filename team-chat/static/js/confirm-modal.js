// 삭제 등 위험한 동작을 확인하는 공용 모달. 네이티브 confirm()/prompt()은 데스크톱
// (Electron) 앱에서 대화상자를 닫은 뒤 렌더러 입력이 먹통이 되는 경우가 있어(창을
// 트레이로 숨겼다 복원하는 구조와 상호작용하는 것으로 추정), 삭제 확인은 전부
// 이 window.confirmDialog(message)로 통일한다. 사용법은 기존 confirm()과 동일하게
// await로 감싸서 취소 시 false를 반환받으면 된다: if (!(await confirmDialog(msg))) return;
(function () {
  const overlay = document.getElementById("confirm-modal");
  if (!overlay) return;

  const messageEl = document.getElementById("confirm-modal-message");
  const okBtn = document.getElementById("confirm-modal-ok");
  const cancelBtn = document.getElementById("confirm-modal-cancel");

  let resolvePending = null;

  function close(result) {
    overlay.hidden = true;
    const resolve = resolvePending;
    resolvePending = null;
    if (resolve) resolve(result);
  }

  okBtn.addEventListener("click", () => close(true));
  cancelBtn.addEventListener("click", () => close(false));
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) close(false);
  });
  document.addEventListener("keydown", (e) => {
    if (overlay.hidden) return;
    if (e.key === "Escape") close(false);
    if (e.key === "Enter") close(true);
  });

  window.confirmDialog = function confirmDialog(message) {
    // 직전 호출이 아직 안 닫혔으면(있을 수 없는 상황이지만) 취소로 정리하고 새로 연다.
    if (resolvePending) close(false);
    messageEl.textContent = message;
    overlay.hidden = false;
    okBtn.focus();
    return new Promise((resolve) => {
      resolvePending = resolve;
    });
  };
})();
