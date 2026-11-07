import os
import sys
import datetime
import requests
from playwright.sync_api import sync_playwright, TimeoutError

# 目标地址可用环境变量覆盖（本地测试用），默认是真实控制台
TARGET_URL = os.getenv("VORTEXA_URL", "https://www.vortexa.cloud/dashboard")
# 检查页最长等待秒数：Vercel 的 JS 检查有时需要十几秒才放行
CHECKPOINT_WAIT = int(os.getenv("VORTEXA_CHECKPOINT_WAIT", "45"))
# 设为 1 时以有头模式启动（在 Actions 里配合 xvfb 使用，过检查概率更高）
HEADED = os.getenv("VORTEXA_HEADED", "0") == "1"

CHECKPOINT_MARKERS = [
    "Vercel Security Checkpoint",
    "安全检查点",
    "正在验证您的浏览器",
    "正在验证你的浏览器",
    "Verifying your browser",
]
BLOCKED_MARKERS = [
    "This request was blocked",
    "请求已被阻止",
]
LOGIN_ERROR_MARKERS = [
    "invalid credentials",
    "Invalid email or password",
    "incorrect password",
    "Invalid login",
    "密码错误",
    "账号或密码",
    "用户不存在",
]


def get_beijing_time():
    """获取格式化的当前北京时间 (UTC+8)"""
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    beijing_time = utc_now + datetime.timedelta(hours=8)
    return beijing_time.strftime("%Y-%m-%d %H:%M:%S")


def send_telegram_message(message, image_path=None):
    """发送 Telegram 推送消息（支持可选的图片截图）"""
    bot_token = os.getenv('TG_BOT_TOKEN')
    chat_id = os.getenv('TG_CHAT_ID')

    if not bot_token or not chat_id:
        print("提示: 未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，跳过 Telegram 推送。")
        return

    try:
        if image_path and os.path.exists(image_path):
            url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            data = {"chat_id": chat_id, "caption": message, "parse_mode": "HTML"}
            with open(image_path, "rb") as photo:
                response = requests.post(url, data=data, files={"photo": photo}, timeout=20)
        else:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
            response = requests.post(url, json=payload, timeout=10)

        if response.status_code == 200:
            print("Telegram 推送发送成功！")
        else:
            print(f"Telegram 推送失败，状态码: {response.status_code}, 详情: {response.text}")
    except Exception as e:
        print(f"请求 Telegram API 时发生异常: {e}")


def clean_url(page):
    """回报时去掉查询串，避免表单 GET 参数等敏感内容进入消息。"""
    return (page.url or "").split("?")[0]


def page_text(page):
    try:
        title = page.title()
    except Exception:
        title = ""
    try:
        body = page.inner_text("body", timeout=3000)
    except Exception:
        body = ""
    return title, body


def is_checkpoint(title, body):
    return any(m in title or m in body for m in CHECKPOINT_MARKERS)


def is_blocked(title, body):
    return any(m in body for m in BLOCKED_MARKERS) or title.strip().startswith("403")


def visible_password_input(page):
    try:
        pw = page.locator('input[type="password"]')
        return pw.count() > 0 and pw.first.is_visible()
    except Exception:
        return False


def fill_first(page, selectors, value, step_name):
    """按候选选择器顺序填第一个可用的输入框，全失败则抛出带步骤名的超时。"""
    last_err = None
    for sel in selectors:
        try:
            page.fill(sel, value, timeout=8000)
            print(f"{step_name}: 使用选择器 {sel}")
            return sel
        except Exception as e:
            last_err = e
    raise TimeoutError(f"{step_name} 失败：候选选择器都未命中（{selectors}）：{last_err}")


def click_first(page, selectors, step_name):
    last_err = None
    for sel in selectors:
        try:
            page.click(sel, timeout=8000)
            print(f"{step_name}: 使用选择器 {sel}")
            return sel
        except Exception as e:
            last_err = e
    raise TimeoutError(f"{step_name} 失败：候选选择器都未命中（{selectors}）：{last_err}")


def fail(page, emoji, headline, detail, shot_name):
    """统一失败出口：截图 + TG + 退出码 1。"""
    try:
        page.screenshot(path=shot_name)
    except Exception:
        shot_name = None
    msg = (f"{emoji} <b>{headline}</b>\n{detail}\n"
           f"当前地址: <code>{clean_url(page)}</code>\n🕒 时间: <code>{get_beijing_time()}</code>")
    print(msg)
    send_telegram_message(msg, image_path=shot_name)
    return 1


def run(playwright):
    username = os.getenv('VORTEXA_USER')
    password = os.getenv('VORTEXA_PASS')

    if not username or not password:
        msg = (f"❌ <b>Vortexa 执行失败</b>\n未找到 VORTEXA_USER 或 VORTEXA_PASS 环境变量。\n"
               f"🕒 时间: <code>{get_beijing_time()}</code>")
        print(msg)
        send_telegram_message(msg)
        sys.exit(1)

    launch_kw = {
        "headless": not HEADED,
        "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    }
    browser = playwright.chromium.launch(**launch_kw)
    context = browser.new_context(
        viewport={'width': 1280, 'height': 720},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        locale="en-US",
        timezone_id="Asia/Hong_Kong",
    )
    # 弱化自动化指纹
    context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    page = context.new_page()
    exit_code = 0

    try:
        # ---- 步骤 1：打开页面 ----
        print(f"步骤1 打开页面: {TARGET_URL}（{'有头' if HEADED else '无头'}模式）")
        try:
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
        except TimeoutError:
            exit_code = fail(page, "⏱️", "Vortexa 步骤1超时：打开页面",
                             "60 秒内页面未完成加载，可能网络波动或检查页未响应。",
                             "step1_timeout.png")
            browser.close()
            sys.exit(exit_code)

        # ---- 步骤 2：等检查页放行 / 识别硬拦截 ----
        print("步骤2 等待检查页放行...")
        deadline = datetime.datetime.now() + datetime.timedelta(seconds=CHECKPOINT_WAIT)
        blocked_hits = 0
        while True:
            title, body = page_text(page)
            if is_blocked(title, body):
                blocked_hits += 1
                if blocked_hits >= 2:  # 连续两次确认，避免误判瞬间状态
                    exit_code = fail(page, "⚠️", "Vortexa 被 Vercel 硬拦截（403）",
                                     "页面显示 This request was blocked，检查未放行。这一步换任何脚本都过不去，只能等站点放宽或换运行 IP。",
                                     "blocked_screenshot.png")
                    browser.close()
                    sys.exit(exit_code)
            else:
                blocked_hits = 0
            if not is_checkpoint(title, body) and not is_blocked(title, body):
                print("检查页已放行或不存在。")
                break
            if datetime.datetime.now() > deadline:
                exit_code = fail(page, "⚠️", "Vortexa 卡在 Vercel 检查页",
                                 f"等待 {CHECKPOINT_WAIT} 秒后仍停在安全检查页，未到达登录页。",
                                 "checkpoint_screenshot.png")
                browser.close()
                sys.exit(exit_code)
            page.wait_for_timeout(2000)

        # ---- 步骤 3：填账号密码 ----
        print("步骤3 填写凭据...")
        try:
            fill_first(page,
                       ['input[type="email"]', 'input[name="email"]',
                        'input[name="username"]', 'input[placeholder*="mail" i]',
                        'input[autocomplete="username"]'],
                       username, "填邮箱")
            fill_first(page,
                       ['input[type="password"]', 'input[name="password"]',
                        'input[autocomplete="current-password"]'],
                       password, "填密码")
        except TimeoutError as e:
            exit_code = fail(page, "⏱️", "Vortexa 步骤3超时：找不到登录输入框",
                             f"<code>{str(e)[:300]}</code>\n页面标题见截图，可能页面结构已变或还没跳到登录页。",
                             "step3_timeout.png")
            browser.close()
            sys.exit(exit_code)

        # ---- 步骤 4：提交 ----
        print("步骤4 提交登录...")
        try:
            click_first(page,
                        ['button[type="submit"]', 'input[type="submit"]',
                         'button:has-text("Login")', 'button:has-text("Log in")',
                         'button:has-text("Sign in")', 'button:has-text("登录")'],
                        "点提交")
        except TimeoutError as e:
            exit_code = fail(page, "⏱️", "Vortexa 步骤4超时：找不到提交按钮",
                             f"<code>{str(e)[:300]}</code>",
                             "step4_timeout.png")
            browser.close()
            sys.exit(exit_code)

        # ---- 步骤 5：验证真的登录成功（密码框消失 + 不在登录路径） ----
        print("步骤5 验证登录结果...")
        deadline = datetime.datetime.now() + datetime.timedelta(seconds=20)
        verdict = "unknown"
        err_text = ""
        while datetime.datetime.now() < deadline:
            title, body = page_text(page)
            if is_checkpoint(title, body) or is_blocked(title, body):
                verdict = "blocked_after"
                break
            if not visible_password_input(page) and "/login" not in page.url and "/sign-in" not in page.url:
                verdict = "ok"
                break
            for m in LOGIN_ERROR_MARKERS:
                if m in body:
                    err_text = m
            page.wait_for_timeout(1500)

        if verdict == "ok":
            shot = "success_screenshot.png"
            page.screenshot(path=shot)
            msg = (f"✅ <b>Vortexa 自动登录成功</b>\n已验证：密码框消失且离开登录页，不是假报。\n"
                   f"落地地址: <code>{clean_url(page)}</code>\n🕒 时间: <code>{get_beijing_time()}</code>")
            print(msg)
            send_telegram_message(msg, image_path=shot)
        elif verdict == "blocked_after":
            exit_code = fail(page, "⚠️", "Vortexa 提交后被 Vercel 拦截",
                             "登录提交触发了安全检查/403，未能进入控制台。",
                             "blocked_after_screenshot.png")
        else:
            detail = "提交 20 秒后仍停在登录页，密码框还在。"
            if err_text:
                detail += f"\n页面出现错误提示标记: <code>{err_text}</code>"
            detail += "\n多半是账号密码不对，或站点还要求额外验证（见截图）。"
            exit_code = fail(page, "❌", "Vortexa 登录未成功", detail,
                             "login_failed_screenshot.png")

    except SystemExit:
        raise
    except Exception as e:
        msg = (f"❌ <b>Vortexa 自动登录失败</b>\n执行过程中发生未知代码异常:\n"
               f"<code>{str(e)[:500]}</code>\n🕒 时间: <code>{get_beijing_time()}</code>")
        print(msg)
        send_telegram_message(msg)
        exit_code = 1
    finally:
        browser.close()

    sys.exit(exit_code)


if __name__ == "__main__":
    with sync_playwright() as playwright:
        run(playwright)
