"""Exercise actual Chrome and Edge UI workflows and capture real local evidence."""

import json
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "screenshots"
BASE = "http://127.0.0.1:8000"


def login(page, username, password="CampusDemo2026!"):
    page.goto(BASE + "/login")
    page.locator("#login-form input[name=username]").fill(username)
    page.locator("#login-form input[name=password]").fill(password)
    page.locator("#login-form button[type=submit]").click()
    page.wait_for_url("**/market")
    page.locator(".card").first.wait_for()


def trade_action(page, label):
    page.get_by_role("button", name=label, exact=True).click()
    page.get_by_text("操作已保存", exact=True).wait_for()


def screenshot(page, name):
    page.evaluate("window.scrollTo(0, 0)")
    page.screenshot(path=str(OUT / name), full_page=False)


def run_browser(playwright, name, executable):
    browser = playwright.chromium.launch(executable_path=executable, headless=True)
    contexts = [browser.new_context(viewport={"width": 1366, "height": 768}) for _ in range(3)]
    seller, admin, buyer = [context.new_page() for context in contexts]
    errors = []
    for page in (seller, admin, buyer):
        page.on("pageerror", lambda error: errors.append(str(error)))
    prefix = name.lower()
    product_title = "浏览器验收教材 " + uuid4().hex[:6]
    buyer_name = "browser_" + uuid4().hex[:10]
    buyer.goto(BASE + "/login")
    buyer.locator("#register-form input[name=username]").fill(buyer_name)
    buyer.locator("#register-form input[name=password]").fill("CampusDemo2026!")
    buyer.locator("#register-form input[name=nickname]").fill("浏览器测试买家")
    buyer.locator("#register-form button[type=submit]").click()
    buyer.get_by_text("注册成功，请使用左侧表单登录。", exact=True).wait_for()
    login(buyer, buyer_name)
    login(seller, "seller_demo")
    login(admin, "admin_demo")
    seller.goto(BASE + "/my-products")
    seller.get_by_role("button", name="＋ 发布商品").click()
    form = seller.locator("#product-form")
    form.locator("input[name=title]").fill(product_title)
    form.locator("select[name=category]").select_option(label="教材书籍")
    form.locator("select[name=condition]").select_option(label="九成新")
    form.locator("input[name=price]").fill("49.50")
    form.locator("textarea[name=description]").fill("真实浏览器验收数据，非用户发布的实际交易。")
    form.get_by_role("button", name="保存草稿").click()
    seller.wait_for_url("**/product/*")
    product_url = seller.url
    trade_action(seller, "提交审核")
    admin.goto(product_url)
    trade_action(admin, "审核通过")
    screenshot(admin, f"{prefix}-review.png")
    buyer.goto(BASE + "/market")
    buyer.locator("input[name=keyword]").fill(product_title)
    buyer.locator("#filters button[type=submit]").click()
    buyer.get_by_role("link", name=product_title, exact=True).wait_for()
    screenshot(buyer, f"{prefix}-search.png")
    buyer.get_by_role("link", name=product_title, exact=True).click()
    buyer.locator("textarea[name=message]").fill("明天下午图书馆门口面交，可以吗？")
    buyer.get_by_role("button", name="提交预约", exact=True).click()
    buyer.wait_for_url("**/reservation/*")
    reservation_url = buyer.url
    screenshot(buyer, f"{prefix}-reservation.png")
    seller.goto(reservation_url)
    trade_action(seller, "确认预约")
    buyer.reload()
    buyer.get_by_role("button", name="取消预约", exact=True).click()
    buyer.locator("#reason-form textarea").fill("验证取消后恢复在售")
    buyer.locator("#reason-form button[type=submit]").click()
    buyer.locator(".badge.CANCELLED").wait_for()
    buyer.goto(product_url)
    buyer.locator("textarea[name=message]").fill("重新预约这件教材")
    buyer.get_by_role("button", name="提交预约", exact=True).click()
    buyer.wait_for_url("**/reservation/*")
    second_url = buyer.url
    assert second_url != reservation_url
    seller.goto(second_url)
    trade_action(seller, "确认预约")
    seller.once("dialog", lambda dialog: dialog.accept())
    trade_action(seller, "标记完成")
    seller.locator(".badge.COMPLETED").wait_for()
    screenshot(seller, f"{prefix}-completed.png")
    seller.goto(BASE + "/statistics")
    seller.locator(".number").first.wait_for()
    screenshot(seller, f"{prefix}-statistics.png")
    admin.goto(second_url)
    assert admin.locator("#private-output").text_content() == ""
    admin.get_by_role("button", name="填写原因并查看留言").click()
    admin.locator("#private-form textarea").fill("浏览器测试核查，验证访问先留痕")
    admin.locator("#private-form button[type=submit]").click()
    admin.locator("#private-output").get_by_text("重新预约这件教材", exact=True).wait_for()
    screenshot(admin, f"{prefix}-private-access.png")
    admin.goto(BASE + "/history")
    admin.locator("tbody tr").first.wait_for()
    screenshot(admin, f"{prefix}-audit.png")
    buyer.goto(BASE + "/market")
    buyer.locator(".card").first.wait_for()
    screenshot(buyer, f"{prefix}-market.png")
    overflow = buyer.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    assert not overflow and not errors, (overflow, errors)
    version = browser.version
    for context in contexts:
        context.close()
    browser.close()
    return {"browser": name, "version": version, "viewport": "1366x768", "passed": True,
            "scenarios": ["register", "login", "draft", "submit", "approve", "search", "reserve",
                          "confirm", "cancel", "reserve-again", "complete", "statistics", "private-audit"],
            "horizontal_overflow": overflow, "javascript_errors": errors}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as playwright:
        for name, executable in [
            ("Chrome", "C:/Program Files/Google/Chrome/Application/chrome.exe"),
            ("Edge", "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
        ]:
            results.append(run_browser(playwright, name, executable))
    (ROOT / "artifacts" / "browser-results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
