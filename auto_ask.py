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


def close_chat(page) -> None:
    """Close Chat 메뉴를 누른 뒤 Close 버튼으로 종료를 확인합니다."""
    close_menu = page.get_by_role(
        "button", name=re.compile(r"^Close Chat(?: Close Chat)?$", re.I)
    )
    if not close_menu.is_visible():
        if not click_if_visible(page.get_by_role("button", name="Options", exact=True)):
            raise RuntimeError("대화 종료 메뉴를 찾지 못했습니다.")
    close_menu.click(timeout=10000)
    # 사이트의 다른 Close 버튼 대신 화면에 표시된 대화상자의 버튼을 우선합니다.
    close_button = page.get_by_role("dialog").get_by_role("button", name="Close", exact=True)
    fallback = page.get_by_role("button", name="Close", exact=True)
    started = time.monotonic()
    deadline = started + 10
    while time.monotonic() < deadline:
        visible = [close_button.nth(i) for i in range(close_button.count())
                   if close_button.nth(i).is_visible()]
        if not visible and time.monotonic() - started >= 3:
            visible = [fallback.nth(i) for i in range(fallback.count())
                       if fallback.nth(i).is_visible()]
        if len(visible) > 1:
            raise RuntimeError("Close 버튼이 여러 개 표시되어 대화 종료 버튼을 구분할 수 없습니다.")
        if visible:
            visible[0].click(timeout=10000)
            page.get_by_role("textbox", name="Ask me anything").wait_for(
                state="hidden", timeout=10000
            )
            return
        page.wait_for_timeout(200)
    raise RuntimeError("대화 종료 확인용 Close 버튼을 찾지 못했습니다.")


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
        for i, question in enumerate(questions):
            open_chat_if_needed(page)
            answer = ask_and_get_answer(page, question)
            results.append({"question": question, "answer": answer})
            save_results(results, filename)
            print(f"[{i + 1}/{len(questions)}] 완료: {question}")
            close_chat(page)
            if i < len(questions) - 1:
                page.reload(wait_until="domcontentloaded")
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
