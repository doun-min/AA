import re
import json
from datetime import datetime

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

results = []


def click_if_visible(locator, timeout: int = 3000) -> bool:
    """locator가 timeout 안에 나타나면 클릭하고 True, 안 나타나면 스킵하고 False"""
    try:
        locator.wait_for(state="visible", timeout=timeout)
        locator.click()
        return True
    except PlaywrightTimeoutError:
        return False


def open_chat_if_needed(page) -> None:
    """Open chat 버튼이 뜨면 클릭, 이미 챗봇 화면이 노출돼 있으면 그냥 넘어감"""
    click_if_visible(page.get_by_role("button", name="Open chat"), timeout=5000)


def ask_and_get_answer(page, question: str) -> str:
    page.get_by_role("textbox", name="Ask me anything").click()
    page.get_by_role("textbox", name="Ask me anything").fill(question)
    page.get_by_role("button", name="Send message").click()

    # 답변이 완료되면 피드백 툴팁(👍/👎 등)이 노출됨 -> 그걸 완료 신호로 사용
    page.locator(".feedback-tolltip-wrapper").last.wait_for(state="visible", timeout=30000)

    return page.locator("div.chatbot-main-cont").last.inner_text()


def reset_chat(page) -> None:
    """채팅 닫고 다시 열어서 새 대화로 초기화 (상황에 따라 안 뜨는 버튼은 스킵)"""
    click_if_visible(page.get_by_role("button", name="Options"))
    click_if_visible(page.get_by_role("button", name="Close Chat Close Chat"))
    click_if_visible(page.get_by_role("button", name="Close").nth(2))
    click_if_visible(page.get_by_role("button").filter(has_text=re.compile(r"^$")).nth(5))
    open_chat_if_needed(page)
    click_if_visible(page.get_by_role("button", name="Cancel"))
    click_if_visible(page.get_by_role("button", name="Options"))
    click_if_visible(page.get_by_role("button", name="New Chat New Chat"))


def run(playwright: Playwright) -> None:
    context = playwright.chromium.launch_persistent_context(
        user_data_dir="C:\\automation-profile",
        channel="chrome",
        headless=False,
    )
    page = context.new_page()
    page.goto("https://www.samsung.com/uk/")
    open_chat_if_needed(page)

    # 피드백 툴팁이 이미 떠있으면 이전 실행에서 남은 대화 세션 -> 초기화
    if page.locator(".feedback-tolltip-wrapper").count() > 0:
        reset_chat(page)

    for i, q in enumerate(questions):
        answer = ask_and_get_answer(page, q)
        results.append({
            "question": q,
            "answer": answer,
            "timestamp": datetime.now().isoformat(),
        })
        print(f"[{i + 1}/{len(questions)}] 완료: {q}")

        if i < len(questions) - 1:
            reset_chat(page)

    context.close()


with sync_playwright() as playwright:
    run(playwright)

with open("results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

df = pd.DataFrame(results)[["question", "answer"]].rename(
    columns={"question": "질문", "answer": "답변"}
)
excel_filename = f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

FONT = Font(name="맑은 고딕", size=9)
WRAP = Alignment(wrap_text=True, vertical="top")
HEADER_FILL = PatternFill(start_color="87CEEB", end_color="87CEEB", fill_type="solid")

with pd.ExcelWriter(excel_filename, engine="openpyxl") as writer:
    df.to_excel(writer, index=False, sheet_name="Sheet1")
    worksheet = writer.sheets["Sheet1"]

    worksheet.column_dimensions["A"].width = 70.7  # 약 500px
    worksheet.column_dimensions["B"].width = 85.0  # 약 600px

    for row in worksheet.iter_rows():
        for cell in row:
            cell.font = FONT
            cell.alignment = WRAP

    for cell in worksheet[1]:
        cell.fill = HEADER_FILL
