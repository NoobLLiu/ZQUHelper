"""教务系统登录：自动填账号密码 + OCR 识别图形验证码 + 失败重试。

实测要点
- 登录表单：#login_form / #account / #password / #j_captcha / #submit_btn
- 验证码图片：<img id="captcha_img" src=".../yzm?d=...">
- 验证码为 4~5 位大写字母或数字，带旋转与干扰线
- 填错时弹出 layer 提示「验证码不正确」，并刷新验证码，可无限重试（不锁账号）
- 登录成功标志：URL 跳转到教务系统内部页面（不再是登录页）
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import ocr

# 登录成功后 URL 中会出现的关键字
_INNER_MARKERS = ("/index", "/js/", "/student", "kbzx", "xtgl", "main")


@dataclass
class JwglLoginResult:
    ok: bool
    url: str
    title: str = ""
    message: str = ""
    attempts: int = 0
    history: list = field(default_factory=list)


def _is_login_page(page) -> bool:
    """判断是否仍停留在登录页。"""
    try:
        return page.locator("#account").count() > 0 and page.locator("#j_captcha").count() > 0
    except Exception:
        return False


def _dismiss_layer(page) -> None:
    """关掉 layer 弹窗（'确定' 按钮），避免遮挡后续操作。"""
    for sel in (".layui-layer-btn0", ".layui-layer .layui-layer-btn a",
                ".layui-layer-close", "a[onclick*='close']"):
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                loc.click()
                page.wait_for_timeout(400)
                return
        except Exception:
            continue


def _get_captcha_bytes(page, bot=None) -> bytes | None:
    """取当前验证码图片的原始字节。

    两种途径，优先用网络响应（可靠）：
    1. WebVPN 会重写页面里的 fetch，调用后拿不到 Response 对象，因此不可靠；
       改为拦截 /yzm 请求的响应体，直接拿原始 PNG 字节。
    2. 退路：用 Playwright 请求上下文按同URL 取图（带 cookies）。
    注意：不能对元素截图，页面用 CSS 拉伸过验证码，截图会失真。
    """
    # ---- 途径1：网络响应拦截 ----
    if bot is not None:
        store = _install_captcha_listener(bot)
        store["data"] = None
        _refresh_captcha(page)
        try:
            page.wait_for_function(
                "() => true", timeout=100)  # 让事件循环跑一拍
        except Exception:
            pass
        page.wait_for_timeout(900)
        if store.get("data"):
            return store["data"]

    # ---- 途径2：Playwright 请求上下文 ----
    try:
        src = page.evaluate("() => { const e=document.querySelector('#captcha_img');"
                            "return e?e.src:null; }")
        if not src:
            return None
        ctx = page.context.request
        resp = ctx.get(src, headers={"Referer": page.url})
        if resp.ok:
            return resp.body()
    except Exception:
        pass

    # ---- 途径3：页面内canvas 重绘（去掉 CSS 拉伸影响）----
    try:
        b64 = page.evaluate("""() => {
            const img = document.querySelector('#captcha_img');
            if (!img || !img.naturalWidth) return null;
            const c = document.createElement('canvas');
            c.width = img.naturalWidth; c.height = img.naturalHeight;
            c.getContext('2d').drawImage(img, 0, 0);
            try { return c.toDataURL('image/png'); } catch (e) { return null; }
        }""")
        if b64 and "," in b64:
            import base64
            return base64.b64decode(b64.split(",", 1)[1])
    except Exception:
        pass

    return None


def _install_captcha_listener(bot) -> dict:
    """在 context 上安装一次性的验证码响应监听，返回共享存储 dict。"""
    store = getattr(bot, "_captcha_store", None)
    if store is not None:
        return store

    store = {"data": None}
    bot._captcha_store = store

    def _on_response(resp):
        try:
            if "/yzm" in resp.url:
                store["data"] = resp.body()
        except Exception:
            pass

    bot.ctx.on("response", _on_response)
    return store


def _refresh_captcha(page) -> None:
    """换一张验证码。"""
    page.evaluate("""() => {
        const img = document.querySelector('#captcha_img');
        if (!img) return;
        try {
            const u = new URL(img.src, location.href);
            u.searchParams.set('d', Date.now());
            img.src = u.toString();
        } catch (e) {
            if (typeof changeVerifyCode === 'function') changeVerifyCode(img);
        }
    }""")
    page.wait_for_timeout(700)


def _alert_text(page) -> str:
    """读取弹窗提示文本。"""
    try:
        return page.evaluate("""() => {
            const els = document.querySelectorAll('.layui-layer-content, .layui-layer');
            let out = [];
            els.forEach(e => { const t = (e.innerText||'').trim(); if (t) out.push(t); });
            return out.join(' | ');
        }""") or ""
    except Exception:
        return ""


def login_jwgl(page, bot, username: str, password: str,
               max_attempts: int = 12, verbose: bool = True,
               on_captcha_saved=None) -> JwglLoginResult:
    """自动登录教务系统：填账号密码 + OCR 验证码 + 重试。

    on_captcha_saved: 可选回调，参数为 (验证码图片bytes, 识别结果, 尝试序号)，
                      用于保存样本以积累训练数据。
    """
    history = []

    if not _is_login_page(page):
        return JwglLoginResult(False, page.url, page.title(),
                               message="当前不在教务登录页，无法提交登录")

    for attempt in range(1, max_attempts + 1):
        _dismiss_layer(page)

        # 1) 确保账号密码已填（失败重试时页面会清空）
        if attempt > 1:
            page.wait_for_timeout(400)
        try:
            if not page.input_value("#account"):
                page.fill("#account", username)
            if not page.input_value("#password"):
                page.fill("#password", password)
        except Exception:
            page.fill("#account", username)
            page.fill("#password", password)

        # 2) 取验证码并识别
        img = _get_captcha_bytes(page, bot)
        if not img:
            if verbose:
                print(f"[教务] 第{attempt}次：未能取得验证码图，刷新重试")
            _refresh_captcha(page)
            continue

        code = ocr.recognize(img)
        if on_captcha_saved:
            try:
                on_captcha_saved(img, code, attempt)
            except Exception:
                pass

        if not code:
            if verbose:
                print(f"[{attempt}] 验证码识别为空，刷新重试")
            history.append((attempt, "", "识别为空"))
            _refresh_captcha(page)
            continue

        if verbose:
            print(f"[{attempt}] 识别验证码: {code}")

        # 3) 提交
        try:
            page.fill("#j_captcha", code)
        except Exception:
            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            continue

        try:
            page.click("#submit_btn")
        except Exception:
            page.keyboard.press("Enter")

        page.wait_for_timeout(2600)

        # 4) 判断结果
        if not _is_login_page(page):
            if verbose:
                print(f"[{attempt}] 登录成功 -> {page.url}")
            return JwglLoginResult(True, page.url, page.title(),
                                   attempts=attempt, history=history)

        msg = _alert_text(page).strip()
        if verbose:
            print(f"[{attempt}] 仍在登录页，提示: {msg[:60] or '(无)'}")
        history.append((attempt, code, msg[:80]))

        if "验证码" in msg or not msg:
            _refresh_captcha(page)
        elif "密码" in msg or "账号" in msg or "学号" in msg:
            return JwglLoginResult(False, page.url, page.title(),
                                   message=f"账号密码问题: {msg[:120]}",
                                   attempts=attempt, history=history)
        else:
            _refresh_captcha(page)

    return JwglLoginResult(False, page.url, page.title(),
                           message=f"尝试 {max_attempts} 次仍未登录成功",
                           attempts=max_attempts, history=history)