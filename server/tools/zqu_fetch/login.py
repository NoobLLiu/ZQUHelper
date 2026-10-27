"""WebVPN 登录 + 教务系统访问（Playwright 驱动真实浏览器）。

设计要点
- 复用本机已安装的 Edge/Chrome，不额外下载 Chromium；
- 登录方式与人工一致：填表单 → 若弹出滑块则自动识别缺口并用真实鼠标轨迹拖动；
- 两种网络场景都覆盖：
    校内直连：直接访问 jwgl.zqu.edu.cn（不走VPN）
    校外访问：先登录 WebVPN，再访问被代理加密的教务地址
"""
from __future__ import annotations

import math
import random
import re
import time
from dataclasses import dataclass, field
from typing import Callable

from playwright.sync_api import Page, sync_playwright

from . import captcha

# 常见浏览器安装位置（按优先级）
_BROWSER_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

JWGL_HOST = "https://jwgl.zqu.edu.cn"
WEBVPN_HOST = "https://webvpn.zqu.edu.cn"

# 滑块落点微调量（像素）。正值=往右。理论值算出后仍需按服务端判定微调。
SLIDER_DX_ADJ = 10


def _find_browser() -> str | None:
    import os
    for p in _BROWSER_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


@dataclass
class LoginResult:
    ok: bool
    url: str
    title: str = ""
    page_html: str = ""
    message: str = ""
    cookies: list = field(default_factory=list)


def _human_drag(page: Page, start_xy: tuple[float, float], target_dx: float,
                steps: int = 32, min_dur: float = 0.6, max_dur: float = 1.4) -> None:
    """用带缓动的真实鼠标轨迹拖动，避免被识别为机器行为。"""
    x0, y0 = start_xy
    page.mouse.move(x0, y0)
    page.mouse.down()
    # 起始停顿，模拟手指按下
    page.wait_for_timeout(random.randint(80, 160))

    n = random.randint(steps - 8, steps + 8)
    for i in range(1, n + 1):
        p = i / n
        # ease-out 曲线：起步快、收尾慢
        eased = 1 - math.pow(1 - p, 2.4)
        # 中段轻微横向抖动，纵向小幅浮动
        jitter_x = random.uniform(-1.0, 1.0) if 0.2 < p < 0.9 else 0.0
        jitter_y = random.uniform(-2.0, 2.0)
        page.mouse.move(x0 + target_dx * eased + jitter_x, y0 + jitter_y)
        page.wait_for_timeout(random.randint(12, 26))

    # 末端微调回正
    page.mouse.move(x0 + target_dx, y0, steps=3)
    page.wait_for_timeout(random.randint(40, 90))
    page.mouse.up()


class ZQUWebVPN:
    """封装 WebVPN 会话与教务系统页面访问。"""

    def __init__(self, headless: bool = False, verbose: bool = True,
                 logger: Callable[[str], None] | None = None):
        self.headless = headless
        self.verbose = verbose
        self._logger = logger or (lambda m: print(m, flush=True))
        self._pw = None
        self.browser = None
        self.ctx = None
        self.page: Page | None = None

    # ---------- 生命周期 ----------
    def start(self) -> None:
        self._pw = sync_playwright().start()
        exe = _find_browser()
        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--no-sandbox",
            "--disable-gpu",
            "--lang=zh-CN",
        ]
        kwargs = dict(headless=self.headless, args=args)
        if exe:
            self._log(f"使用本机浏览器: {exe}")
            kwargs["executable_path"] = exe
        else:
            self._log("未找到系统浏览器，回退到 Playwright 自带 Chromium")
        self.browser = self._pw.chromium.launch(**kwargs)
        self.ctx = self.browser.new_context(
            user_agent=UA,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            viewport={"width": 1440, "height": 900},
            ignore_https_errors=True,
        )
        self.ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )
        self.page = self.ctx.new_page()
        # 默认超时保持较短：page 上的 locator/evaluate 在 frame 导航、
        # detach 时都会一直等到超时才返回，45 秒会让"卡住"被放大成好几分钟。
        # 需要长等待的地方（导航、登录提交）都单独传了显式 timeout。
        self.page.set_default_timeout(8000)
        self.page.set_default_navigation_timeout(45000)

    def close(self) -> None:
        for obj, meth in ((self.ctx, "close"), (self.browser, "close")):
            try:
                if obj:
                    getattr(obj, meth)()
            except Exception:
                pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

    def _log(self, msg: str) -> None:
        if self.verbose:
            self._log_impl(msg)

    def _log_impl(self, msg: str) -> None:
        self._logger(msg)

    # ---------- 网络判定 ----------
    def detect_route(self) -> str:
        """判断当前是否已在校园网内：能直连教务首页则返回 'intranet'。"""
        pg = self.page
        assert pg
        try:
            resp = pg.goto(JWGL_HOST + "/", wait_until="domcontentloaded", timeout=30000)
            final = pg.url
            # 直连成功（未跳到 webvpn）即说明在校园网
            if "webvpn" not in final:
                self._log(f"[网络] 校园网直连可用: {final}")
                return "intranet"
            self._log(f"[网络] 校外访问，需走 WebVPN: {final}")
            pg.goto("about:blank")
            return "webvpn"
        except Exception as e:
            self._log(f"[网络] 直连探测失败({type(e).__name__})，按校外 WebVPN 处理")
            try:
                pg.goto("about:blank")
            except Exception:
                pass
            return "webvpn"

    # ---------- 滑块 ----------
    def solve_slider(self) -> bool:
        """处理弹出的拖动滑块验证码。"""
        pg = self.page
        assert pg
        try:
            pg.wait_for_selector(".drag-captcha-layer", state="visible", timeout=8000)
        except Exception:
            return True  # 没有验证码，直接算通过

        # 用颜色分割定位背景图中已绘制的缺口色块；失败时刷新验证码重试
        for _ in range(6):
            # 等背景图真正加载完成（src 变化且 naturalWidth>0），否则读到旧图/占位图
            try:
                pg.wait_for_function(
                    """() => { const e=document.querySelector('.drag-captcha-bg img');
                        return e && e.src && e.src.startsWith('data:') && e.complete
                               && e.naturalWidth > 100; }""",
                    timeout=5000)
            except Exception:
                pass

            bg_url = pg.evaluate("() => { const e=document.querySelector('.drag-captcha-bg img'); return e?e.src:null; }")
            if not bg_url:
                self._log("[滑块] 未能取得验证码图片")
                return False
            try:
                cx, cy, score = captcha.solve_from_pair(bg_url)
                break
            except ValueError as e:
                self._log(f"[滑块] 定位失败({e})，刷新验证码重试")
                try:
                    pg.evaluate("() => { if (window.loadCaptcha) loadCaptcha(); }")
                except Exception:
                    pass
                pg.wait_for_timeout(900)
        else:
            return False
        self._log(f"[滑块] 缺口中心 x={cx} y={cy} score={score:.2f}")

        # 滑块可拖动距离 = 轨道宽度 - 按钮宽度；缺口 x 需换算成位移量
        metrics = pg.evaluate("""() => {
            const footer = document.querySelector('.drag-captcha-footer');
            const btn = document.querySelector('.drap-captcha-slidetrigger');
            if (!footer || !btn) return null;
            const fb = footer.getBoundingClientRect(), bb = btn.getBoundingClientRect();
            const bg = document.querySelector('.drag-captcha-bg img').getBoundingClientRect();
            return {trackWidth: fb.width, btnWidth: bb.width,
                    btnX: bb.x + bb.width/2, btnY: bb.y + bb.height/2,
                    bgScale: bg.width / 280};
        }""")
        if not metrics:
            self._log("[滑块] 无法获取滑块几何信息")
            return False

        # 页面里 .drag-slide-identity 初始 left = 10px，拖动时 left = offset + 10。
        # 让拼图块中心对齐缺口色块中心：
        #   拼图块中心 = offset + 10 + 20   (10=初始left, 20=拼图块半宽)
        #   缺口中心   = cx * scale
        # 理论 offset = cx*scale - 30；实测服务端判定略偏左，统一右移 SLIDER_DX_ADJ 像素。
        scale = metrics["bgScale"] or 1.0
        target_dx = cx * scale - 30 + SLIDER_DX_ADJ
        self._log(f"[滑块] 缺口中心 x={cx} y={cy} scale={scale:.2f} "
                  f"→ 目标位移={target_dx:.1f}px (含微调 {SLIDER_DX_ADJ:+.0f})")

        _human_drag(pg, (metrics["btnX"], metrics["btnY"]), target_dx)

        # 等待验证结果
        try:
            pg.wait_for_function(
                "() => document.querySelector('#drag-captcha-layer') === null || "
                "document.querySelector('.drag-slide-message.succes-message') !== null",
                timeout=12000,
            )
        except Exception:
            pass
        msg = pg.evaluate("() => { const e=document.querySelector('.drag-slide-message');"
                          "return e? e.textContent.trim() : ''; }")
        self._log(f"[滑块] 验证提示: {msg or '(无)'}")
        return "成功" in (msg or "") or msg == ""

    # ---------- 登录 ----------
    def login_webvpn(self, username: str, password: str) -> LoginResult:
        pg = self.page
        assert pg
        pg.goto(WEBVPN_HOST + "/login", wait_until="domcontentloaded")

        # 填账号密码
        pg.fill("#user_name", username)
        pg.fill('input[name="password"]', password)
        pg.wait_for_timeout(random.randint(200, 400))

        pg.click("#login")

        # 首次登录 / 验证码 / 已登录确认 都要处理
        for _ in range(6):
            pg.wait_for_timeout(1500)
            url_now = pg.url

            # 滑块
            if pg.locator(".drag-captcha-layer").count() and \
                    pg.locator(".drag-captcha-layer").first.is_visible():
                if not self.solve_slider():
                    continue
                continue

            # 二次认证
            if pg.locator("#second_login_layer").count() and pg.locator("#second_login_layer").first.is_visible():
                msg = pg.locator(".layui-layer-content").first.inner_text() if pg.locator(".layui-layer-content").count() else ""
                return LoginResult(False, pg.url, pg.title(), message=f"需要二次认证: {msg.strip()[:200]}")

            # 重复登录确认
            if pg.locator(".layui-layer").count():
                try:
                    btn = pg.locator(".layui-layer-btn0, .layui-layer .layui-layer-btn a").first
                    if btn.count() and btn.is_visible():
                        self._log("[登录] 检测到确认弹窗，点击确认")
                        btn.click()
                        pg.wait_for_timeout(2500)
                        continue
                except Exception:
                    pass

            err = pg.evaluate("() => { const e=document.querySelector('#error-message');"
                              "return e && e.style.display!=='none' ? e.innerText.trim() : ''; }")
            if err:
                return LoginResult(False, pg.url, pg.title(), message=f"登录失败: {err}")

            if "webvpn" not in pg.url or "/login" not in pg.url:
                break

        cookies = [{"name": c["name"], "value": c["value"][:24] + "..."} for c in self.ctx.cookies()]
        title = pg.title()
        self._log(f"[登录] 当前 URL: {pg.url} | 标题: {title}")
        ok = "webvpn" in pg.url and "/login" not in pg.url
        return LoginResult(ok, pg.url, title, pg.content(), cookies=cookies)

    def goto_jwgl(self) -> LoginResult:
        """跳转到教务系统首页（已登录 WebVPN 状态下会经过加密代理）。"""
        pg = self.page
        assert pg
        pg.goto(JWGL_HOST + "/", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(2500)
        return LoginResult(True, pg.url, pg.title(), pg.content())

    def try_direct_jwgl_login(self, username: str, password: str) -> LoginResult:
        """校内直连场景：教务系统自带登录页时直接登录。"""
        pg = self.page
        assert pg
        pg.goto(JWGL_HOST + "/", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(2000)

        # 常见教务系统登录表单探测
        user_sel = None
        for sel in ["#userCode", "#xh", "#username", "#loginName", "input[name='userCode']",
                    "input[name='xh']", "input[name='username']", "#zjh", "#j_username"]:
            if pg.locator(sel).count():
                user_sel = sel
                break
        pwd_sel = None
        for sel in ["#password", "#pwd", "input[name='password']", "input[type='password']"]:
            if pg.locator(sel).count():
                pwd_sel = sel
                break

        if not user_sel or not pwd_sel:
            return LoginResult(False, pg.url, pg.title(), pg.content(),
                               message="未在教务首页找到登录表单（可能需要 VPN，或为统一身份认证）")

        self._log(f"[教务] 探测到登录表单: {user_sel} / {pwd_sel}")
        pg.fill(user_sel, username)
        pg.fill(pwd_sel, password)

        clicked = False
        for sel in ["#loginBtn", "#btnSubmit", "#submit_btn", "button[type='submit']",
                    "input[type='submit']", ".login-btn", "#submit"]:
            if pg.locator(sel).count():
                pg.locator(sel).first.click()
                clicked = True
                break
        if not clicked:
            pg.keyboard.press("Enter")

        pg.wait_for_timeout(4000)
        return LoginResult(True, pg.url, pg.title(), pg.content())

    # ---------- 教务系统图形验证码（4位数字/字母）----------
    def read_jwgl_captcha(self) -> str | None:
        """定位教务登录页的图形验证码元素，返回其选择器。

        该验证码是 <img id="captcha_img" src=".../yzm?...">，由服务端动态生成，
        不是 data URL；调用方可用 Playwright 截图或抓取网络响应取图。
        """
        pg = self.page
        assert pg
        sel = pg.evaluate("""() => {
            const e = document.querySelector('#captcha_img');
            if (e) return '#captcha_img';
            for (const s of ['img.j_captcha', 'img[src*="yzm"]', 'img[src*="captcha"]']) {
                const x = document.querySelector(s);
                if (x) return s;
            }
            return null;
        }""")
        if sel:
            src = pg.evaluate("s => { const e=document.querySelector(s); return e?e.src:null; }", sel)
            self._log(f"[教务] 验证码元素 {sel} → {str(src)[:90]}")
        else:
            self._log("[教务] 未找到验证码图片元素")
        return sel

    def capture_jwgl_captcha(self, path: str = "_captcha_jwgl.png") -> str | None:
        """把教务图形验证码的原始图片保存到本地，返回路径。

        注意：不能直接对元素截图——教务页面用 CSS 把验证码图拉伸过，
        截图会得到失真图像。这里在页面上下文里 fetch 原图并转成 base64，
        拿到的是未经缩放的原始像素，便于后续 OCR。
        """
        pg = self.page
        assert pg
        sel = self.read_jwgl_captcha()
        if not sel:
            return None
        try:
            b64 = pg.evaluate(
                """async (s) => {
                    const img = document.querySelector(s);
                    if (!img) return null;
                    const url = img.src;
                    const resp = await fetch(url, {credentials: 'include', cache: 'no-store'});
                    const blob = await resp.blob();
                    return await new Promise(res => {
                        const fr = new FileReader();
                        fr.onload = () => res(fr.result);
                        fr.onerror = () => res(null);
                        fr.readAsDataURL(blob);
                    });
                }""", sel)
        except Exception as e:
            self._log(f"[教务] 验证码抓取失败: {e}")
            return None
        if not b64 or "," not in b64:
            self._log("[教务] 验证码抓取返回空")
            return None
        import base64
        raw = base64.b64decode(b64.split(",", 1)[1])
        with open(path, "wb") as f:
            f.write(raw)
        self._log(f"[教务] 验证码原图已保存 {path} ({len(raw)} 字节)")
        return path

    def refresh_jwgl_captcha(self) -> None:
        """点击验证码图片换一张。"""
        pg = self.page
        assert pg
        sel = self.read_jwgl_captcha()
        if sel:
            try:
                pg.locator(sel).first.click()
                pg.wait_for_timeout(800)
            except Exception:
                pass

    # ---------- 一站式流程 ----------
    def reach_jwgl_home(self, username: str, password: str,
                        max_slider_tries: int = 8) -> LoginResult:
        """自动完成：网络判定 → WebVPN 登录(含滑块) → 到达教务系统登录页。

        返回的 LoginResult.page_html 即教务登录页源码，url 为 WebVPN 加密代理地址。
        """
        route = self.detect_route()
        if route == "intranet":
            self._log("[流程] 当前在校内网，直连教务系统")
            return self.try_direct_jwgl_login(username, password)

        self._log("[流程] 校外网络，走 WebVPN 代理")
        vpn = self.login_webvpn(username, password)
        if not vpn.ok:
            return vpn

        # 滑块可能多次出现（失败会刷新），循环处理
        for _ in range(max_slider_tries):
            pg = self.page
            assert pg
            if not (pg.locator(".drag-captcha-layer").count()
                    and pg.locator(".drag-captcha-layer").first.is_visible()):
                break
            if not self.solve_slider():
                pg.wait_for_timeout(1200)
                continue
            pg.wait_for_timeout(2000)
            if "webvpn" in pg.url and "/login" not in pg.url:
                break

        self._log("[流程] WebVPN 已登录，进入教务系统")
        return self.goto_jwgl()