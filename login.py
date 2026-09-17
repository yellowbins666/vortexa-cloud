import os
import sys
import requests
import datetime
from playwright.sync_api import sync_playwright, TimeoutError

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
        # 如果存在截图，则调用 sendPhoto 接口
        if image_path and os.path.exists(image_path):
            url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            data = {
                "chat_id": chat_id,
                "caption": message,
                "parse_mode": "HTML"
            }
            # 以二进制读取图片并上传
            with open(image_path, "rb") as photo:
                response = requests.post(url, data=data, files={"photo": photo}, timeout=20)
        else:
            # 否则回退到纯文本推送调用 sendMessage 接口
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            response = requests.post(url, json=payload, timeout=10)

        if response.status_code == 200:
            print("Telegram 推送发送成功！")
        else:
            print(f"Telegram 推送失败，状态码: {response.status_code}, 详情: {response.text}")
    except Exception as e:
        print(f"请求 Telegram API 时发生异常: {e}")

def run(playwright):
    username = os.getenv('VORTEXA_USER')
    password = os.getenv('VORTEXA_PASS')
    
    current_time = get_beijing_time()

    if not username or not password:
        msg = f"❌ <b>执行失败</b>\n未找到 VORTEXA_USER 或 VORTEXA_PASS 环境变量。\n🕒 时间: <code>{current_time}</code>"
        print(msg)
        send_telegram_message(msg)
        sys.exit(1)

    # 启动无头浏览器
    browser = playwright.chromium.launch(headless=True)
    # 配置虚拟浏览器的窗口大小，确保截图比例正常（1280x720 桌面比例）
    context = browser.new_context(
        viewport={'width': 1280, 'height': 720},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    page = context.new_page()

    try:
        print("正在访问目标面板...")
        page.goto("https://www.vortexa.cloud/dashboard", wait_until="networkidle")

        print("正在输入凭据...")
        page.fill('input[type="email"]', username)
        page.fill('input[type="password"]', password)

        print("提交登录...")
        page.click('button[type="submit"]')

        # 等待 5 秒确保登录请求完整发出，页面完全渲染出登录后的主页
        page.wait_for_timeout(5000)
        
        # --- 核心新增：截取成功后的屏幕 ---
        screenshot_path = "success_screenshot.png"
        page.screenshot(path=screenshot_path)
        print(f"已保存登录截图: {screenshot_path}")
        
        current_time = get_beijing_time()
        success_msg = f"✅ <b>Vortexa 自动登录成功</b>\n任务已按时顺利执行完毕。\n🕒 时间: <code>{current_time}</code>"
        print(success_msg)
        # 将文本和截图一起发送
        send_telegram_message(success_msg, image_path=screenshot_path)

    except TimeoutError:
        # --- 核心新增：遇到超时报错时也截图，方便排查风控或死链 ---
        screenshot_path = "timeout_screenshot.png"
        page.screenshot(path=screenshot_path)
        print(f"已保存超时异常截图: {screenshot_path}")

        current_time = get_beijing_time()
        error_msg = f"⚠️ <b>Vortexa 自动登录异常</b>\n页面加载或元素定位超时，可能是网站结构更改、需要验证码验证或网络波动。\n🕒 时间: <code>{current_time}</code>"
        print(error_msg)
        send_telegram_message(error_msg, image_path=screenshot_path)
        
    except Exception as e:
        current_time = get_beijing_time()
        error_msg = f"❌ <b>Vortexa 自动登录失败</b>\n执行过程中发生未知代码异常:\n<code>{str(e)}</code>\n🕒 时间: <code>{current_time}</code>"
        print(error_msg)
        # 代码级错误通常没法截图，直接发文本
        send_telegram_message(error_msg)
        
    finally:
        browser.close()

if __name__ == "__main__":
    with sync_playwright() as playwright:
        run(playwright)
