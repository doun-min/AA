// 공용 확인 모달(confirm-modal.js)은 자체 Esc 처리가 있으니 여기서는 건드리지 않는다.
// 그 외 .modal-overlay(참여 인원, 로그 삭제, 이미지 미리보기, 방 만들기 등)는 페이지마다
// 따로 Esc를 안 붙여놔서 일부만 닫히던 문제가 있었다 — 이미 있는 닫기 버튼(.modal-close)을
// 그대로 클릭해서, 모달마다 다른 정리 로직(예: 이미지 src 비우기)을 그대로 재사용한다.
(function () {
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    const overlay = document.querySelector(".modal-overlay:not([hidden]):not(#confirm-modal)");
    if (!overlay) return;
    const closeBtn = overlay.querySelector(".modal-close");
    if (closeBtn) closeBtn.click();
  });
})();
