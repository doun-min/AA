(function () {
  const sidebar = document.getElementById("sidebar");
  if (!sidebar) return;

  const convertInput = document.getElementById("excel-convert-input");
  const convertBtn = document.getElementById("excel-convert-btn");
  const convertStatus = document.getElementById("excel-convert-status");

  const mergeInput = document.getElementById("excel-merge-input");
  const mergeBtn = document.getElementById("excel-merge-btn");
  const mergeStatus = document.getElementById("excel-merge-status");

  function filenameFromResponse(res, fallback) {
    const disposition = res.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
    if (match) {
      try {
        return decodeURIComponent(match[1]);
      } catch (e) {
        return match[1];
      }
    }
    return fallback;
  }

  function triggerDownload(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  convertBtn.addEventListener("click", async () => {
    convertStatus.textContent = "";
    const file = convertInput.files[0];
    if (!file) {
      convertStatus.textContent = "변환할 파일을 선택해주세요.";
      return;
    }
    const formData = new FormData();
    formData.append("file", file);
    convertStatus.textContent = "변환 중...";
    try {
      const res = await fetch("/api/excel/convert", { method: "POST", body: formData });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        convertStatus.textContent = data.error || "변환에 실패했습니다.";
        return;
      }
      const blob = await res.blob();
      triggerDownload(blob, filenameFromResponse(res, "converted"));
      convertStatus.textContent = "변환 완료. 다운로드를 확인해주세요.";
      convertInput.value = "";
    } catch (err) {
      convertStatus.textContent = "변환 중 오류가 발생했습니다.";
    }
  });

  async function doMerge(force) {
    const formData = new FormData();
    Array.from(mergeInput.files).forEach((f) => formData.append("files", f));
    if (force) formData.append("force", "1");
    return fetch("/api/excel/merge", { method: "POST", body: formData });
  }

  mergeBtn.addEventListener("click", async () => {
    mergeStatus.textContent = "";
    if (mergeInput.files.length < 2) {
      mergeStatus.textContent = "병합할 파일을 2개 이상 선택해주세요.";
      return;
    }
    mergeStatus.textContent = "병합 중...";
    try {
      let res = await doMerge(false);

      if (res.status === 409) {
        const data = await res.json();
        const lines = (data.mismatches || []).map(
          (m) => `- ${m.filename}: [${m.columns.join(", ")}]`
        );
        const msg =
          `${data.message}\n\n` +
          `기준 파일: ${data.base_file}\n[${(data.base_header || []).join(", ")}]\n\n` +
          `헤더가 다른 파일:\n${lines.join("\n")}\n\n` +
          `기준 파일의 헤더로 강제 병합하시겠습니까? (취소를 누르면 병합하지 않습니다)`;
        const proceed = confirm(msg);
        if (!proceed) {
          mergeStatus.textContent = "병합이 취소되었습니다.";
          return;
        }
        res = await doMerge(true);
      }

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        mergeStatus.textContent = data.error || "병합에 실패했습니다.";
        return;
      }

      const blob = await res.blob();
      triggerDownload(blob, filenameFromResponse(res, "merged.xlsx"));
      mergeStatus.textContent = "병합 완료. 다운로드를 확인해주세요.";
      mergeInput.value = "";
    } catch (err) {
      mergeStatus.textContent = "병합 중 오류가 발생했습니다.";
    }
  });
})();
