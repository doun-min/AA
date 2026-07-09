(function () {
  const convertInput = document.getElementById("excel-convert-input");
  if (!convertInput) return;

  const convertBtn = document.getElementById("excel-convert-btn");
  const convertStatus = document.getElementById("excel-convert-status");

  const mergeInput = document.getElementById("excel-merge-input");
  const mergeBtn = document.getElementById("excel-merge-btn");
  const mergeStatus = document.getElementById("excel-merge-status");
  const sheetRow = document.getElementById("excel-merge-sheet-row");
  const sheetSelect = document.getElementById("excel-merge-sheet-select");

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

  function resetSheetSelect() {
    sheetRow.hidden = true;
    sheetSelect.innerHTML = "";
  }

  mergeInput.addEventListener("change", async () => {
    mergeStatus.textContent = "";
    resetSheetSelect();
    const first = mergeInput.files[0];
    if (!first) return;

    const formData = new FormData();
    formData.append("file", first);
    try {
      const res = await fetch("/api/excel/sheets", { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) {
        mergeStatus.textContent = data.error || "시트 목록을 불러오지 못했습니다.";
        return;
      }
      if (data.is_excel && data.sheets && data.sheets.length) {
        data.sheets.forEach((name) => {
          const opt = document.createElement("option");
          opt.value = name;
          opt.textContent = name;
          sheetSelect.appendChild(opt);
        });
        sheetRow.hidden = false;
      }
    } catch (err) {
      mergeStatus.textContent = "시트 목록을 불러오는 중 오류가 발생했습니다.";
    }
  });

  async function doMerge(opts) {
    const formData = new FormData();
    Array.from(mergeInput.files).forEach((f) => formData.append("files", f));
    if (!sheetRow.hidden && sheetSelect.value) formData.append("sheet", sheetSelect.value);
    if (opts.force) formData.append("force", "1");
    if (opts.skipMissing) formData.append("skip_missing", "1");
    return fetch("/api/excel/merge", { method: "POST", body: formData });
  }

  mergeBtn.addEventListener("click", async () => {
    mergeStatus.textContent = "";
    if (mergeInput.files.length < 2) {
      mergeStatus.textContent = "병합할 파일을 2개 이상 선택해주세요.";
      return;
    }
    mergeStatus.textContent = "병합 중...";

    let force = false;
    let skipMissing = false;
    let excludedFiles = [];
    let excludedSheet = "";

    try {
      // 시트 누락(missing_sheet) / 헤더 불일치(header_mismatch) 확인 후 사용자 선택에 따라
      // 필요한 옵션을 붙여 재요청하므로 최종 성공/취소까지 반복한다.
      for (;;) {
        const res = await doMerge({ force, skipMissing });

        if (res.status === 409) {
          const data = await res.json();

          if (data.error === "missing_sheet") {
            const list = (data.missing_files || []).map((f) => `- ${f}`).join("\n");
            const msg =
              `선택한 시트('${data.sheet}')가 없는 파일이 있습니다:\n${list}\n\n` +
              `해당 파일을 제외하고 계속 병합하시겠습니까? (취소를 누르면 병합하지 않습니다)`;
            if (!confirm(msg)) {
              mergeStatus.textContent = "병합이 취소되었습니다.";
              return;
            }
            skipMissing = true;
            excludedFiles = data.missing_files || [];
            excludedSheet = data.sheet;
            continue;
          }

          if (data.error === "header_mismatch") {
            const lines = (data.mismatches || []).map(
              (m) => `- ${m.filename}: [${m.columns.join(", ")}]`
            );
            const msg =
              `${data.message}\n\n` +
              `기준 파일: ${data.base_file}\n[${(data.base_header || []).join(", ")}]\n\n` +
              `헤더가 다른 파일:\n${lines.join("\n")}\n\n` +
              `기준 파일의 헤더로 강제 병합하시겠습니까? (취소를 누르면 병합하지 않습니다)`;
            if (!confirm(msg)) {
              mergeStatus.textContent = "병합이 취소되었습니다.";
              return;
            }
            force = true;
            continue;
          }

          mergeStatus.textContent = data.message || data.error || "병합에 실패했습니다.";
          return;
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
        resetSheetSelect();

        if (excludedFiles.length === 1) {
          alert(`${excludedFiles[0]}의 '${excludedSheet}' 시트가 없어 제외하고 병합했습니다.`);
        } else if (excludedFiles.length > 1) {
          const list = excludedFiles.map((f) => `- ${f}`).join("\n");
          alert(`다음 파일에 '${excludedSheet}' 시트가 없어 제외하고 병합했습니다:\n${list}`);
        }
        return;
      }
    } catch (err) {
      mergeStatus.textContent = "병합 중 오류가 발생했습니다.";
    }
  });
})();
