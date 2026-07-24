import re
import json
from datetime import datetime

import pandas as pd
from playwright.sync_api import Playwright, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

questions = [
    "I heard the Z Flip8 just came out, what are its key features?",
    "질문 2",
    "질문 3",
    "질문 4",
]

results = []


def open_chat_if_needed(page) -> None:
    """Open chat 버튼이 뜨면 클릭, 이미 챗봇 화면이 노출돼 있으면 그냥 넘어감"""
    try:
        page.get_by_role("button", name="Open chat").wait_for(state="visible", timeout=5000)
        page.get_by_role("button", name="Open chat").click()
    except PlaywrightTimeoutError:
        pass


def ask_and_get_answer(page, question: str) -> str:
    page.get_by_role("textbox", name="Ask me anything").click()
    page.get_by_role("textbox", name="Ask me anything").fill(question)
    page.get_by_role("button", name="Send message").click()

    # TODO: 임시 고정 대기 -> 로딩 인디케이터 셀렉터로 교체 권장
    page.wait_for_timeout(3000)

    return page.locator("div.chatbot-main-cont").inner_text()


def reset_chat(page) -> None:
    """채팅 닫고 다시 열어서 새 대화로 초기화"""
    page.get_by_role("button", name="Options").click()
    page.get_by_role("button", name="Close Chat Close Chat").click()
    page.get_by_role("button", name="Close").nth(2).click()
    page.get_by_role("button").filter(has_text=re.compile(r"^$")).nth(5).click()
    open_chat_if_needed(page)
    page.get_by_role("button", name="Cancel").click()
    page.get_by_role("button", name="Options").click()
    page.get_by_role("button", name="New Chat New Chat").click()


def run(playwright: Playwright) -> None:
    context = playwright.chromium.launch_persistent_context(
        user_data_dir="C:\\automation-profile",
        channel="chrome",
        headless=False,
    )
    page = context.new_page()
    page.goto("https://www.samsung.com/uk/")
    open_chat_if_needed(page)

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
df.to_excel(excel_filename, index=False, engine="openpyxl")
