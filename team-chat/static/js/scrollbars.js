// 카카오톡 채팅방처럼: 스크롤 중인 요소에만 .is-scrolling을 잠깐 붙였다 뗀다.
// 실제 겉모습(투명→반투명 막대, 페이드)은 style.css의 ::-webkit-scrollbar 규칙이 담당한다.
// scroll 이벤트는 버블링되지 않으므로 캡처 단계에서 델리게이트해 모든 스크롤 영역을 한 번에 처리한다.
(function () {
  const HIDE_DELAY_MS = 900;

  function onScroll(e) {
    const el = e.target;
    if (!(el instanceof Element)) return;
    el.classList.add("is-scrolling");
    clearTimeout(el._scrollbarHideTimer);
    el._scrollbarHideTimer = setTimeout(() => {
      el.classList.remove("is-scrolling");
    }, HIDE_DELAY_MS);
  }

  window.addEventListener("scroll", onScroll, true);
})();
