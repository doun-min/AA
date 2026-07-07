(function () {
  const sidebar = document.getElementById("sidebar");
  const toggleBtn = document.getElementById("sidebar-toggle");
  const backdrop = document.getElementById("sidebar-backdrop");
  if (!sidebar || !toggleBtn) return;

  function openSidebar() {
    sidebar.classList.add("open");
    backdrop.hidden = false;
  }

  function closeSidebar() {
    sidebar.classList.remove("open");
    backdrop.hidden = true;
  }

  toggleBtn.addEventListener("click", () => {
    if (sidebar.classList.contains("open")) {
      closeSidebar();
    } else {
      openSidebar();
    }
  });

  backdrop.addEventListener("click", closeSidebar);
})();
