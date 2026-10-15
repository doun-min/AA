import argparse
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from playwright.sync_api import Playwright, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

questions = [
    "I heard the Z Flip8 just came out, what are its key features?",
    "질문 2",
    "질문 3",
    "질문 4",
]

OUTPUT_DIR = Path(os.environ.get("AUTO_ASK_OUTPUT_DIR", "results"))
PROFILE_DIR = Path(os.environ.get("AUTO_ASK_PROFILE_DIR", "automation-profile"))
BROWSER_CHANNEL = os.environ.get("AUTO_ASK_BROWSER_CHANNEL", "chrome")
HEADLESS = os.environ.get("AUTO_ASK_HEADLESS", "0").lower() in {"1", "true", "yes"}
FEEDBACK_SELECTOR = ".feedback-tolltip-wrapper, .feedback-tooltip-wrapper"



def click_if_visible(locator, timeout: int = 3000) -> bool:
    """locator가 timeout 안에 나타나면 클릭하고 True, 안 나타나면 스킵하고 False"""
    try:
        locator.wait_for(state="visible", timeout=timeout)
        locator.click()
        return True
    except PlaywrightTimeoutError:
        return False


def chat_inputs(page):
    """접근성 이름 또는 placeholder로 챗봇 입력창을 찾습니다."""
    return page.get_by_role("textbox", name=re.compile(r"Ask me anything", re.I)).or_(
        page.get_by_placeholder(re.compile(
            r"Ask me anything|(?:type|enter|write)(?: your| a)? (?:message|question)", re.I
        ))
    )


def find_editable_chat_input(page):
    candidates = chat_inputs(page)
    for i in range(candidates.count()):
        textbox = candidates.nth(i)
        if textbox.is_visible() and textbox.is_enabled() and textbox.is_editable():
            return textbox
    return None


def open_chat_if_needed(page):
    """입력 가능한 창을 먼저 찾고, 없으면 열기 버튼을 확인합니다."""
    deadline = time.monotonic() + 30
    clicked = False
    while time.monotonic() < deadline:
        textbox = find_editable_chat_input(page)
        if textbox is not None:
            return textbox
        if not clicked:
            # 입력창이 없을 때만 버튼을 찾으며, 버튼 대기로 입력창 확인을 막지 않습니다.
            open_buttons = page.get_by_role("button", name="Open chat", exact=True)
            for i in range(open_buttons.count()):
                open_button = open_buttons.nth(i)
                if open_button.is_visible() and open_button.is_enabled():
                    # 버튼 검사 중 자동으로 입력창이 열렸을 수도 있습니다.
                    textbox = find_editable_chat_input(page)
                    if textbox is not None:
                        return textbox
                    open_button.click(timeout=3000)
                    clicked = True
                    break
        page.wait_for_timeout(200)
    if page.get_by_role("link", name="Continue on WhatsApp", exact=True).count():
        raise RuntimeError(
            "현재 페이지에는 WhatsApp 안내가 표시됩니다. "
            "이 스크립트에 필요한 웹 챗봇 입력창이 없습니다."
        )
    raise RuntimeError("웹 챗봇 입력창을 찾지 못했습니다. URL과 선택자를 확인하세요.")


def ask_and_get_answer(page, question: str) -> str:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("질문이 비어 있습니다.")
    textbox = open_chat_if_needed(page)
    feedback = page.locator(FEEDBACK_SELECTOR)
    answers = page.locator("div.chatbot-main-cont")
    old_feedback_count = feedback.count()
    old_answer_count = answers.count()
    textbox.fill(question)
    page.get_by_role("button", name="Send message").click()

    # 답변이 완료되면 피드백 툴팁(👍/👎 등)이 노출됨 -> 그걸 완료 신호로 사용
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if feedback.count() > old_feedback_count and answers.count() > old_answer_count:
            if feedback.last.is_visible():
                answer = answers.last.inner_text().strip()
                if answer:
                    return answer
        page.wait_for_timeout(200)
    raise PlaywrightTimeoutError("새 답변의 완료 표시를 기다리는 중 시간이 초과되었습니다.")


def close_chat(page) -> None:
    """Close Chat 메뉴를 누른 뒤 Close 버튼으로 종료를 확인합니다."""
    close_menu = page.get_by_role(
        "button", name=re.compile(r"^Close Chat(?: Close Chat)?$", re.I)
    )
    if not close_menu.is_visible():
        if not click_if_visible(page.get_by_role("button", name="Options", exact=True)):
            raise RuntimeError("대화 종료 메뉴를 찾지 못했습니다.")
    close_menu.click(timeout=10000)
    # 팝업의 X 버튼과 구분해 두 클래스를 모두 가진 종료 확인 버튼만 클릭합니다.
    close_button = page.get_by_role("button", name="Close", exact=True).and_(
        page.locator("button.popup-btn.popup-btn--primary:visible")
    )
    close_button.click(timeout=10000)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        candidates = chat_inputs(page)
        if not any(candidates.nth(i).is_visible() for i in range(candidates.count())):
            return
        page.wait_for_timeout(200)
    raise RuntimeError("종료 확인 후에도 챗봇 입력창이 표시되어 있습니다.")


def run(playwright: Playwright) -> Path:
    if not questions or any(not isinstance(q, str) or not q.strip() for q in questions):
        raise ValueError("질문 목록에는 비어 있지 않은 문자열이 필요합니다.")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = OUTPUT_DIR / f"results_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.xlsx"
    checkpoint = filename.with_suffix(".json")
    results = []
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR.resolve()), channel=BROWSER_CHANNEL, headless=HEADLESS,
    )
    try:
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://www.samsung.com/uk/")
        for i, question in enumerate(questions):
            answer = ask_and_get_answer(page, question)
            results.append({"question": question, "answer": answer})
            save_checkpoint(results, checkpoint)
            print(f"[{i + 1}/{len(questions)}] 완료: {question}")
            close_chat(page)
            if i < len(questions) - 1:
                page.reload(wait_until="domcontentloaded")
    finally:
        context.close()
        if results:
            print(f"중간 결과 JSON: {checkpoint}")
    # Excel은 모든 질문을 처리한 뒤 한 번만 생성합니다.
    save_results(results, filename)
    return filename


def save_checkpoint(results, filename: Path) -> None:
    """완료한 답변을 JSON으로 저장하고 기존 파일을 원자적으로 교체합니다."""
    temporary = filename.with_suffix(".tmp.json")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(results, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(filename)
    finally:
        temporary.unlink(missing_ok=True)


def recover_excel(checkpoint: Path) -> Path:
    """중단된 실행의 JSON을 읽어 브라우저 접속 없이 Excel을 생성합니다."""
    with checkpoint.open(encoding="utf-8") as stream:
        results = json.load(stream)
    if not isinstance(results, list) or not results or any(
        not isinstance(row, dict)
        or any(not isinstance(row.get(key), str) or not row[key].strip()
               for key in ("question", "answer"))
        for row in results
    ):
        raise ValueError("JSON에 유효한 질문·답변 목록이 없습니다.")
    filename = checkpoint.with_suffix(".xlsx")
    save_results(results, filename)
    return filename


FONT = Font(name="맑은 고딕", size=9)
WRAP = Alignment(wrap_text=True, vertical="top")
HEADER_FILL = PatternFill(start_color="87CEEB", end_color="87CEEB", fill_type="solid")

def save_results(results, filename: Path) -> None:
    df = pd.DataFrame(results, columns=["question", "answer"]).rename(
        columns={"question": "질문", "answer": "답변"}
    )
    temporary = filename.with_suffix(".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Sheet1")
            worksheet = writer.sheets["Sheet1"]
            worksheet.column_dimensions["A"].width = 70.7
            worksheet.column_dimensions["B"].width = 85.0
            for row in worksheet.iter_rows():
                for cell in row:
                    cell.data_type = "s"  # 응답이 '='로 시작해도 수식으로 실행하지 않습니다.
                    cell.font = FONT
                    cell.alignment = WRAP
            for cell in worksheet[1]:
                cell.fill = HEADER_FILL
        temporary.replace(filename)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="삼성 챗봇 질문 수집 및 Excel 저장")
    parser.add_argument("--recover", type=Path, metavar="JSON", help="중간 저장 JSON을 Excel로 복구")
    args = parser.parse_args()
    if args.recover is not None:
        saved_file = recover_excel(args.recover)
    else:
        with sync_playwright() as playwright:
            saved_file = run(playwright)
    print(f"결과 저장: {saved_file}")
