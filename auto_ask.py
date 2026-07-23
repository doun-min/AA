import re
import json
from datetime import datetime
from playwright.sync_api import Playwright, sync_playwright

questions = [
    "I heard the Z Flip8 just came out, what are its key features?",
    "질문 2",
    "질문 3",
    "질문 4",
]

results = []


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
    page.get_by_role("button", name="Open chat").click()
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
    page.get_by_role("button", name="Open chat").click()

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
