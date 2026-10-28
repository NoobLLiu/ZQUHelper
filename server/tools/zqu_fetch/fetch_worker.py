"""ZQU 课表抓取 worker —— 由 Go 服务端以子进程方式调用。

用法::

    python fetch_worker.py --mode auto|campus|webvpn
                           --user <学号> --pass <密码>
                           --out <输出JSON路径>
                           [--term 202601] [--weeks 1,2,3]
                           [--headless]

mode 说明:
    campus   校园网直连 jwgl.zqu.edu.cn
    webvpn   校外 WebVPN（深信服，含滑块破解）
    auto     先探测校内直连，探测失败再走 WebVPN

输出: 把结果 JSON 写入 --out 文件（不走 stdout，stdout 只留给进度日志，
      避免与 Go 侧管道解析互相干扰）::

    {
      "ok": true,
      "mode": "campus",
      "error": "",
      "term": "202601",
      "term_name": "2026-2027学年第一学期",
      "total_weeks": 22,
      "timetable": { ... TermSchedule.to_dict() ... },
      "fetched_at": "2026-10-27T18:30:00"
    }

抓取核心来自自研项目 GetTimeTable/zqu-timetable-scraper（Python + Playwright，
登录/滑块/验证码 OCR 依赖真实浏览器，无法用纯 HTTP 重写），本 worker 只做
「登录 → 打开课表页 → 读学期/周次 → 单请求取整学期 → 输出 JSON」的编排。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# 保证 UTF-8 输出（Windows 控制台默认 GBK，进度日志含中文）
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 以包方式引入（campus/login/timetable 内部使用相对导入）。
# 本文件位于 server/tools/zqu_fetch/，故把 server/tools 加入 sys.path。
_TOOLS_DIR = str(Path(__file__).resolve().parent.parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from zqu_fetch.campus import CampusDirect            # noqa: E402
from zqu_fetch.login import ZQUWebVPN                # noqa: E402
from zqu_fetch import timetable as tt_mod            # noqa: E402
from zqu_fetch.timetable import (fetch_all_weeks,    # noqa: E402
                                 open_kb_page, read_terms, read_weeks)
from zqu_fetch import jwgl as jwgl_login             # noqa: E402


def log(msg: str) -> None:
    print(f"[worker] {msg}", flush=True)


def run_campus(args) -> tuple[object | None, str]:
    """校园网直连一轮抓取，返回 (TermSchedule, "") 或 (None, 错误信息)。"""
    bot = CampusDirect(headless=args.headless, verbose=True)
    try:
        bot.start()
        res = bot.login(args.user, args.password, max_attempts=args.attempts)
        if not res.ok:
            return None, f"教务登录失败: {res.message}"
        pg = bot.page
        if not open_kb_page(pg):
            return None, "课表页打开失败"
        base = bot.site_base()
        return _fetch(pg, base, args, vpn_marker=False)
    finally:
        bot.close()


def run_webvpn(args) -> tuple[object | None, str]:
    """WebVPN 一轮抓取，返回 (TermSchedule, "") 或 (None, 错误信息)。"""
    bot = ZQUWebVPN(headless=args.headless, verbose=True)
    try:
        bot.start()
        bot.reach_jwgl_home(args.user, args.password)
        res = jwgl_login.login_jwgl(bot.page, bot, args.user, args.password,
                                    max_attempts=args.attempts)
        if not res.ok:
            return None, f"教务登录失败: {res.message}"
        pg = bot.page
        if not open_kb_page(pg):
            return None, "课表页打开失败"
        base = bot.site_base() if hasattr(bot, "site_base") else None
        if not base:
            from zqu_fetch.timetable import base_url_of
            base = base_url_of(pg)
        return _fetch(pg, base, args, vpn_marker=True)
    finally:
        bot.close()


def _fetch(pg, base: str, args, vpn_marker: bool):
    terms = read_terms(pg)
    cur_term = read_terms._cur_term
    term = args.term or cur_term
    term_name = terms.get(term, "")

    total_weeks, week_map = read_weeks(pg)
    if args.weeks:
        weeks = [int(x) for x in args.weeks.split(",") if x.strip().isdigit()]
    else:
        weeks = list(range(1, total_weeks + 1))

    log(f"学期 {term} ({term_name})，共 {total_weeks} 周，抓取 {len(weeks)} 周")
    sched = fetch_all_weeks(pg, base, term, weeks=weeks, term_name=term_name,
                            verbose=True, dedupe=True, vpn_marker=vpn_marker)
    if not sched.weeks:
        return None, "抓取结果为空"
    return sched, ""


def main() -> int:
    ap = argparse.ArgumentParser(description="ZQU timetable fetch worker")
    ap.add_argument("--mode", choices=["auto", "campus", "webvpn"], default="auto")
    ap.add_argument("--user", required=True)
    ap.add_argument("--pass", dest="password", required=True)
    ap.add_argument("--out", required=True, help="结果 JSON 输出路径")
    ap.add_argument("--term", default="")
    ap.add_argument("--weeks", default="")
    ap.add_argument("--attempts", type=int, default=10, help="验证码最大重试次数")
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()

    result = {"ok": False, "mode": args.mode, "error": "",
              "term": "", "term_name": "", "total_weeks": 0,
              "timetable": None,
              "fetched_at": datetime.now().isoformat(timespec="seconds")}

    modes = ["campus", "webvpn"] if args.mode == "auto" else [args.mode]
    sched = None
    for i, mode in enumerate(modes):
        log(f"---- 尝试模式: {mode} ----")
        t0 = time.time()
        try:
            if mode == "campus":
                sched, err = run_campus(args)
            else:
                sched, err = run_webvpn(args)
        except Exception as e:  # 浏览器启动失败、网络异常等都兜到这里
            sched, err = None, f"{type(e).__name__}: {e}"
        if sched is not None:
            result["mode"] = mode
            break
        result["error"] = err
        log(f"模式 {mode} 失败: {err} (用时 {time.time() - t0:.0f}s)")
        if i < len(modes) - 1:
            log("切换下一种模式重试 ...")

    if sched is not None:
        result.update(ok=True, error="",
                      term=sched.term, term_name=sched.term_name,
                      total_weeks=sched.total_weeks,
                      timetable=sched.to_dict())
    else:
        result["ok"] = False

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    log(f"结果已写入 {out} (ok={result['ok']})")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
