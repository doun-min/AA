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


def open_chat_if_needed(page) -> None:
    """자동 표시되는 입력창과 버튼으로 여는 챗봇을 모두 기다립니다."""
    textbox = page.get_by_role("textbox", name="Ask me anything")
    open_button = page.get_by_role("button", name="Open chat", exact=True)
    deadline = time.monotonic() + 30
    clicked = False
    while time.monotonic() < deadline:
        if textbox.is_visible():
            return
        if not clicked and open_button.is_visible():
            open_button.click(timeout=3000)
            clicked = True
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
    feedback = page.locator(FEEDBACK_SELECTOR)
    answers = page.locator("div.chatbot-main-cont")
    old_feedback_count = feedback.count()
    old_answer_count = answers.count()
    page.get_by_role("textbox", name="Ask me anything").click()
    page.get_by_role("textbox", name="Ask me anything").fill(question)
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


def reset_chat(page) -> None:
    """버튼의 위치 대신 명시적인 새 대화 메뉴를 사용합니다."""
    open_chat_if_needed(page)
    new_chat = page.get_by_role("button", name=re.compile(r"^New Chat(?: New Chat)?$", re.I))
    if not new_chat.is_visible():
        if not click_if_visible(page.get_by_role("button", name="Options", exact=True)):
            raise RuntimeError("대화 초기화 메뉴를 찾지 못했습니다.")
    if not click_if_visible(new_chat):
        raise RuntimeError("새 대화 버튼을 찾지 못했습니다.")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if page.locator(FEEDBACK_SELECTOR).count() == 0:
            page.get_by_role("textbox", name="Ask me anything").wait_for(state="visible")
            return
        page.wait_for_timeout(200)
    raise RuntimeError("이전 대화가 초기화되지 않았습니다.")


def ensure_fresh_session(page, max_attempts: int = 3) -> None:
    """이전 대화 흔적이 남아있으면 reset_chat을 반복 시도해서 확실히 새 세션으로 만듦"""
    for attempt in range(max_attempts):
        if page.locator(FEEDBACK_SELECTOR).count() == 0:
            return
        try:
            reset_chat(page)
        except (PlaywrightTimeoutError, RuntimeError):
            continue
    if page.locator(FEEDBACK_SELECTOR).count() == 0:
        return
    raise RuntimeError("이전 세션 초기화에 반복적으로 실패했습니다.")


def run(playwright: Playwright) -> Path:
    if not questions or any(not isinstance(q, str) or not q.strip() for q in questions):
        raise ValueError("질문 목록에는 비어 있지 않은 문자열이 필요합니다.")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = OUTPUT_DIR / f"results_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.xlsx"
    results = []
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR.resolve()), channel=BROWSER_CHANNEL, headless=HEADLESS,
    )
    try:
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://www.samsung.com/uk/")
        open_chat_if_needed(page)
        ensure_fresh_session(page)
        for i, question in enumerate(questions):
            if i:
                reset_chat(page)
            for attempt in range(3):
                try:
                    answer = ask_and_get_answer(page, question)
                    break
                except (PlaywrightTimeoutError, RuntimeError):
                    if attempt == 2:
                        raise
                    # 늦게 도착한 응답이 재시도 결과에 섞이지 않도록 초기화합니다.
                    reset_chat(page)
            results.append({"question": question, "answer": answer})
            save_results(results, filename)
            print(f"[{i + 1}/{len(questions)}] 완료: {question}")
    finally:
        context.close()
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
    with sync_playwright() as playwright:
        saved_file = run(playwright)
    print(f"결과 저장: {saved_file}")
