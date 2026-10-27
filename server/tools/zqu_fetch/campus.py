"""校园网直连访问教务系统（Playwright 驱动真实浏览器）。

与 `login.py`（WebVPN 版）的实测差异
------------------------------------
在校园网内实测（2026-10-14），两条链路**只有两处不同**，其余完全一致：

1. **不需要 WebVPN 滑块**。校内直连直接就是教务登录页
   （`https://jwgl.zqu.edu.cn/`），表单结构与经代理访问时逐字节相同：
   `#account` / `#password` / `#j_captcha` / `#submit_btn`，验证码为
   `<img id="captcha_img" src="/yzm?d=...">`。
2. **站点根路径就是域名根**，没有 WebVPN 的 `/https/<加密串>/` 代理层。
   经代理时是 `https://webvpn.zqu.edu.cn/https/<密串>`，直连时是
   `https://jwgl.zqu.edu.cn`。

而登录成功后的内部页面、课表接口 `xsgrkbcx!getKbRq.action`、返回字段、
单请求取整学期（`zc=` 传空）等行为，两条链路实测**逐字段一致**。

因此校园网版本不需要重写抓取逻辑，只要一个更短的连接层：
本模块负责「连通性判定 → 直连登录 → 站点根推导」，
课表解析与导出直接复用 `timetable.py` / `export.py`。
"""
from __future__ import annotations

import socket
import time
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

from playwright.sync_api import Page, sync_playwright

from . import jwgl

# 教务系统域名（校内直连）
JWGL_HOST = "https://jwgl.zqu.edu.cn"

# 教务系统登录页（实测校园网内直接返回 200，不跳 VPN）
JWGL_LOGIN_PAGE = JWGL_HOST + "/"

# 常见浏览器安装位置（按优先级），与 WebVPN 版保持一致
_BROWSER_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# 登录成功后 URL 里会出现的教务内部页面标记
INNER_MARKERS = ("login!welcome.action", "desktop!newDesktop.action",
                 "xsgrkbcx!xsgrkbMain.action")


def _find_browser() -> str | None:
    import os
    for p in _BROWSER_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


@dataclass
class CampusLoginResult:
    """校园网直连登录结果。"""
    ok: bool
    url: str
    title: str = ""
    message: str = ""
    attempts: int = 0


class CampusDirect:
    """校园网直连会话：连通性判定 + 教务登录 + 站点根推导。

    与 `login.ZQUWebVPN` 的关系
    -------------------------
    `ZQUWebVPN` 是「校外场景为主」的一等公民：它要处理滑块、二次认证、
    WebVPN 加密地址改写。本类只服务于校园网，不需要这些，
    因此不复用 ZQUWebVPN 的滑块/代理逻辑，避免两条链路互相污染。

    但浏览器启动参数、反检测注入、默认超时等浏览器层面的设置是通用的，
    这里保持与 ZQUWebVPN 一致，避免出现「换个入口行为就变了」的情况。
    """

    def __init__(self, headless: bool = False, verbose: bool = True,
                 logger: Callable[[str], None] | None = None,
                 force: bool = False):
        """
        force=True 时跳过连通性探测，直接登录。
        适用于已知身处校园网、想省掉一次探测往返的场景。
        """
        self.headless = headless
        self.verbose = verbose
        self.force = force
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
        # 与 WebVPN 版一致：默认超时压短，避免 frame 导航/detach 时
        # 把一次「卡住」放大成几分钟。需要长等待的地方都传显式 timeout。
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
            self._logger(msg)

    # ---------- 连通性判定 ----------
    def probe(self) -> bool:
        """确认当前网络能直连教务系统。

        判定方式按代价从低到高依次尝试：
        1. DNS 解析 —— 最快，能挡掉「根本没连校园网」的情况；
        2. 浏览器实际导航 —— 权威判据，能识别「能解析但被重定向到 VPN」。

        任何一步判定为不可用，都返回 False 并给出可操作的提示。
        """
        host = urlparse(JWGL_HOST).hostname or "jwgl.zqu.edu.cn"

        # 1) DNS 解析
        dns_ok = True
        try:
            ip = socket.gethostbyname(host)
            self._log(f"[网络] DNS 解析 {host} → {ip}")
        except Exception as e:
            dns_ok = False
            self._log(f"[网络] DNS 解析失败: {type(e).__name__}: {e}")

        # 2) 浏览器实际导航（权威）
        pg = self.page
        assert pg, "请先调用 start()"
        nav_ok = False
        try:
            pg.goto(JWGL_LOGIN_PAGE, wait_until="domcontentloaded", timeout=30000)
            final = pg.url
            if "webvpn" in final:
                self._log(f"[网络] 被重定向到 WebVPN: {final}")
            else:
                has_form = pg.locator("#account").count() > 0
                if has_form:
                    nav_ok = True
                    self._log(f"[网络] 教务登录页可达: {final}")
                else:
                    self._log(f"[网络] 页面可达但未见登录表单: {final}")
            pg.goto("about:blank")
        except Exception as e:
            self._log(f"[网络] 导航探测失败: {type(e).__name__}: {e}")
            try:
                pg.goto("about:blank")
            except Exception:
                pass

        ok = dns_ok and nav_ok
        if not ok:
            self._log("[网络] 当前不在校园网内，或教务系统不可达。"
                      "校园网版本请先接入校园网；校外请改用 WebVPN 版本。")
        return ok

    # ---------- 登录 ----------
    def login(self, username: str, password: str,
              max_attempts: int = 15) -> CampusLoginResult:
        """直连教务登录页并完成登录（账号密码 + 图形验证码 OCR 重试）。

        复用 `jwgl.login_jwgl`：该函数只依赖 `#account` / `#password` /
        `#j_captcha` / `#submit_btn` 这几个选择器，实测校内直连与经 WebVPN
        代理时页面结构完全相同，因此无需另写一套表单逻辑。
        """
        pg = self.page
        assert pg, "请先调用 start()"

        if self.force:
            self._log("[流程] 已指定校园网模式，跳过连通性探测")
        elif not self.probe():
            return CampusLoginResult(False, pg.url, message="当前无法直连教务系统")

        self._log("[流程] 打开教务登录页（校园网直连）")
        try:
            pg.goto(JWGL_LOGIN_PAGE, wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(1500)
        except Exception as e:
            return CampusLoginResult(False, pg.url, message=f"打开登录页失败: {e}")

        if not pg.locator("#account").count():
            return CampusLoginResult(
                False, pg.url, pg.title(),
                message="未找到教务登录表单（#account），请确认已接入校园网")

        res = jwgl.login_jwgl(pg, self, username, password,
                              max_attempts=max_attempts, verbose=self.verbose)
        if not res.ok:
            return CampusLoginResult(False, res.url, res.title,
                                     message=res.message, attempts=res.attempts)

        self._log(f"[流程] 登录成功: {pg.url}")
        return CampusLoginResult(True, pg.url, pg.title(), attempts=res.attempts)

    # ---------- 站点根推导 ----------
    def site_base(self) -> str:
        """返回教务站点根地址（不含具体页面路径）。

        校园网直连实测：
            https://jwgl.zqu.edu.cn/login!welcome.action
              → https://jwgl.zqu.edu.cn
            https://jwgl.zqu.edu.cn/xsgrkbcx!xsgrkbMain.action
              → https://jwgl.zqu.edu.cn

        与 WebVPN 版的差别仅在于不需要剥离 `/https/<加密串>/` 代理层，
        这里按教务内部页面标记定位，标记找不到时退回「去掉最后一段路径」。
        """
        url = (self.page.url if self.page else "") or JWGL_HOST
        for marker in INNER_MARKERS:
            idx = url.find(marker)
            if idx > 0:
                return url[:idx].rstrip("/")
        # 兜底：去掉最后一段路径
        return url.rsplit("/", 1)[0] or JWGL_HOST

    # ---------- 登录态自检 ----------
    def is_logged_in(self) -> bool:
        """判断当前页面是否已处于登录后的教务系统内。

        用于多轮定时刷新时避免重复登录，也用于程序重启后快速判定。
        """
        pg = self.page
        if not pg:
            return False
        try:
            if pg.locator("#account").count() > 0:
                return False
            if any(m in pg.url for m in INNER_MARKERS):
                return True
            # URL 不含标记时，退而求其次看有没有登录后的 iframe
            return any(f.name == "desktop!newDesktop.action" for f in pg.frames)
        except Exception:
            return False
