"""课表抓取与解析。

数据来源（实测自肇庆学院教学管理系统「课表查询 → 我的课表」）：
课表页用 entss_Calendar 组件异步取数：

    GET  xsgrkbcx!getKbRq.action?xnxqdm=<学年学期>&zc=<周次>&xsdm=
    →[ [课程...], [日期...] ]

返回结构：
[0] 课程数组，每项关键字段
    kcmc     课程名称
    teaxms   任课教师姓名
    xq       星期（1=周一 … 7=周日）
    jcdm     节次代码（如"0102" 表示 1-2 节）
    jcdm2    节次（"01,02"）
    jxcdmc   上课教室
    jxbmc    教学班名称
    zc       周次
    xnxqdm   学年学期代码（如 202601）
    kcbh     课程编号
    kxh      开课学时
    zxs      总学时
    pkrs     排课人数
    sknrjj   上课内容/进度
    jxhjmc   教学环节（理论教学/实践教学…）
    flfzmc   分类负责人
    tkbz     听课标志
    jxcddm   教室代码
    kcdm     课程代码
    dgksd工号
[1] 日期数组，每项 {xqmc: 星期几, rq: YYYY-MM-DD}

因为接口直接给结构化 JSON，所以无需解析 DOM 表格，稳定且省时。
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

WEEKDAY_CN = ["", "周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# 课表页面/组件相关地址（相对路径）
KB_MAIN = "xsgrkbcx!xsgrkbMain.action"
KB_DATA = "xsgrkbcx!getKbRq.action"
KB_LIST = "xsgrkbcx!xskbList.action"
KB_TUNE = "xsgrkbcx!getKbRq.action"


def _abs(base: str, path: str) -> str:
    """把教务系统相对路径拼成绝对 URL。"""
    if path.startswith("http"):
        return path
    return base.rstrip("/") + "/" + path.lstrip("/")


@dataclass
class Course:
    """一条课程安排（一门课在一个星期的一个节次段）。"""

    name: str = ""              # 课程名称
    teacher: str = ""           # 任课教师
    weekday: int = 0            # 1..7
    weekday_cn: str = ""        # 周一...
    date: str = ""              # 该周对应日期 YYYY-MM-DD
    week: int = 0               # 周次
    periods: list = field(default_factory=list)   # 节次，如 [1, 2]
    period_text: str = ""       # 节次原文
    classroom: str = ""         # 上课教室
    class_name: str = ""        # 教学班
    content: str = ""           # 上课内容/进度
    course_type: str = ""       # 教学环节
    course_code: str = ""       # 课程编号
    weeks_text: str = ""        # 周次原文
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class WeekSchedule:
    """某一周的课表。"""

    week: int
    week_label: str = ""
    term: str = ""              # 学年学期代码
    term_name: str = ""         # 学年学期名称
    dates: list = field(default_factory=list)    # [{weekday, date}]
    courses: list = field(default_factory=list)  # [Course]

    def to_dict(self) -> dict:
        return {
            "week": self.week,
            "week_label": self.week_label,
            "term": self.term,
            "term_name": self.term_name,
            "dates": self.dates,
            "courses": [c.to_dict() for c in self.courses],
        }


@dataclass
class TermSchedule:
    """整个学期所有周的课表。"""

    term: str
    term_name: str = ""
    total_weeks: int = 0
    weeks: list = field(default_factory=list)  # [WeekSchedule]
    dedupe_removed: int = 0   # dedupe() 去掉的重复条数

    def all_courses(self) -> list:
        out = []
        for w in self.weeks:
            out.extend(w.courses)
        return out

    def dedupe(self) -> int:
        """就地去除各周内部的重复排课，返回被删除的条数。

        服务端在某些周次会重复下发同一条排课记录，
        这里在数据层就清掉，导出层无需再处理。
        """
        removed = 0
        for w in self.weeks:
            seen = set()
            kept = []
            for c in w.courses:
                key = (c.week, c.weekday, tuple(sorted(c.periods or [])),
                       c.name, c.teacher, c.classroom, c.course_code)
                if key in seen:
                    removed += 1
                    continue
                seen.add(key)
                kept.append(c)
            w.courses = kept
        return removed

    def unique_courses(self) -> list:
        """按「课程名+教师+教室+星期+节次」去重的课程列表。"""
        seen = set()
        out = []
        for c in self.all_courses():
            key = (c.name, c.teacher, c.classroom, c.weekday, tuple(c.periods))
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
        return out

    def active_weekdays(self) -> list:
        """全学期真正有课的星期（1..7升序），用于隐藏空白周末列。"""
        wds = {c.weekday for c in self.all_courses()
               if c.weekday and c.periods}
        return sorted(wds) or [1, 2, 3, 4, 5]

    def to_dict(self) -> dict:
        return {
            "term": self.term,
            "term_name": self.term_name,
            "total_weeks": self.total_weeks,
            "weeks": [w.to_dict() for w in self.weeks],
        }


def _parse_periods(jcdm2: str, jcdm: str) -> tuple[list, str]:
    """把节次字段解析成节号列表。

    jcdm2 形如 "01,02,03" 或 "01,02"；jcdm 形如 "0102"。
    返回 (节号列表, 原文)。
    """
    txt = (jcdm2 or jcdm or "").strip()
    nums: list[int] = []
    for part in re.split(r"[,\s]+", txt):
        part = part.strip()
        if not part:
            continue
        # 可能是 "01"，也可能是 "0102" 这种连写
        if part.isdigit():
            if len(part) == 2:
                n = int(part)
                if n not in nums:
                    nums.append(n)
            else:
                # 连写：每两位一节
                for i in range(0, len(part) - 1, 2):
                    n = int(part[i:i + 2])
                    if n not in nums:
                        nums.append(n)
    nums.sort()
    if nums:
        # 1-2 节连堂显示为 "1-2节"
        run = []
        text_parts = []
        for n in nums:
            if run and n == run[-1] + 1:
                run.append(n)
            else:
                if run:
                    text_parts.append(f"{run[0]}-{run[-1]}" if len(run) > 1 else f"{run[0]}")
                run = [n]
        if run:
            text_parts.append(f"{run[0]}-{run[-1]}" if len(run) > 1 else f"{run[0]}")
        return nums, "-".join(text_parts) + "节"
    return [], txt


def parse_payload(payload, week: int, term: str, term_name: str = "",
                  week_label: str = "") -> WeekSchedule:
    """把 getKbRq 返回的 JSON 转成 WeekSchedule。"""
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, list) or len(payload) < 2:
        return WeekSchedule(week=week, week_label=week_label, term=term,
                            term_name=term_name)

    raw_courses = payload[0] or []
    raw_dates = payload[1] or []

    # 日期表：weekday -> YYYY-MM-DD
    date_map: dict[int, str] = {}
    dates = []
    for d in raw_dates:
        try:
            wd = int(d.get("xqmc"))
            rq = d.get("rq") or ""
            date_map[wd] = rq
            dates.append({"weekday": wd, "weekday_cn": WEEKDAY_CN[wd] if wd < len(WEEKDAY_CN) else str(wd),
                          "date": rq})
        except Exception:
            continue

    courses = []
    for c in raw_courses:
        if not isinstance(c, dict):
            continue
        try:
            wd = int(c.get("xq") or 0)
        except Exception:
            wd = 0
        periods, ptext = _parse_periods(c.get("jcdm2"), c.get("jcdm"))
        try:
            wk = int(c.get("zc") or week or 0)
        except Exception:
            wk = week

        known = {"dgksdm", "kbdm", "kcbh", "kcmc", "teaxms", "jxbdm", "xnxqdm",
                 "jxbmc", "zc", "jcdm", "jcdm2", "xq", "jxcdmc", "sknrjj", "teadms",
                 "jxcddm", "kcdm", "zxs", "xs", "pkrs", "kxh", "flfzmc", "jxhjmc", "tkbz"}

        courses.append(Course(
            name=c.get("kcmc") or "",
            teacher=c.get("teaxms") or "",
            weekday=wd,
            weekday_cn=WEEKDAY_CN[wd] if 0 < wd < len(WEEKDAY_CN) else "",
            date=date_map.get(wd, ""),
            week=wk,
            periods=periods,
            period_text=ptext,
            classroom=c.get("jxcdmc") or "",
            class_name=c.get("jxbmc") or "",
            content=c.get("sknrjj") or "",
            course_type=c.get("jxhjmc") or "",
            course_code=c.get("kcbh") or "",
            weeks_text=str(c.get("zc") or ""),
            extra={k: v for k, v in c.items() if k not in known},
        ))

    return WeekSchedule(week=week, week_label=week_label, term=term,
                        term_name=term_name, dates=dates, courses=courses)


def open_kb_page(page, wait_ms: int = 8000, verbose: bool = True) -> bool:
    """打开「课表查询 → 我的课表」页。

    ===== 为什么直接用导航，而不是点菜单 =====
    实测（_scratch/_home.log）登录成功后停在 login!welcome.action，
    主 frame 的 innerText 只有「选课报名 业务办理 信息查询」这类一级导航，
    **没有「课表查询」**；真正的菜单在 desktop!newDesktop.action 这个子 iframe
    里，而且「课表查询」还藏在「信息查询」二级菜单下、要 hover 才展开。
    靠文本匹配 + selectedM3 点击既慢又不稳（实测等了 25 秒都没等到菜单文本，
    只能走 60 秒兜底）。

    而**直接导航** `xsgrkbcx!xsgrkbMain.action` 一次就成功：
    标题变成「课表查询」，frames 里出现 wdkb / list，#xnxqdm 立即可见。
    所以这里改为：先直接导航（几秒内完成），失败才退回点击菜单。

    每一步都不依赖 page 的默认超时（8000ms），避免 frame 导航时被放大成"卡住"。
    """
    import time as _t

    t_start = _t.time()
    HARD_LIMIT = 30.0        # 总时限：超过就放弃

    def _log(msg: str) -> None:
        if verbose:
            print(f"  [{_t.time() - t_start:5.1f}s] {msg}")

    def _have_kb() -> bool:
        try:
            return any(f.name in ("wdkb", "list") for f in page.frames)
        except Exception:
            return False

    try:
        if page.locator("#account").count():
            raise RuntimeError("当前停在教务登录页，请先登录")
    except RuntimeError:
        raise
    except Exception:
        pass

    # 已在课表页则直接返回
    if _find_frame_with(page, "#xnxqdm", 800):
        _log("课表页已打开")
        return True

    # ---- 1) 首选：直接导航到课表页（实测最稳最快） ----
    _log("导航到课表查询页 ...")
    try:
        url = _abs(base_url_of(page), KB_MAIN)
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
    except Exception as e:
        _log(f"直接导航异常（继续尝试点击）：{e}")

    deadline = min(_t.time() + 12, t_start + HARD_LIMIT)
    while _t.time() < deadline:
        if _find_frame_with(page, "#xnxqdm", 600):
            _log(f"课表就绪（用时 {_t.time() - t_start:.1f}s）")
            return True
        _t.sleep(0.3)

    # ---- 2) 兜底：回首页点菜单（selectedM3） ----
    _log("直接导航未就绪，改回首页点菜单 ...")
    try:
        page.goto(_abs(base_url_of(page), "login!welcome.action"),
                  wait_until="domcontentloaded", timeout=20000)
    except Exception:
        pass
    deadline = min(_t.time() + 8, t_start + HARD_LIMIT)
    while _t.time() < deadline:
        try:
            hit = page.evaluate("""() => {
                // 菜单可能在主 frame，也可能在 desktop iframe 里，这里只查主 frame
                const els = [...document.querySelectorAll('td,div,a,span')];
                const el = els.find(e => (e.innerText||'').trim() === '课表查询'
                                     && (e.getAttribute('onclick')||'').includes('xsgrkb'));
                if (!el) return false;
                if (typeof window.selectedM3 === 'function') {
                    window.selectedM3(el, 'xsgrkbcx!xsgrkbMain.action', '课表查询');
                } else { el.click(); }
                return true;
            }""")
        except Exception:
            hit = False
        if hit or _have_kb():
            break
        _t.sleep(0.4)

    deadline = min(_t.time() + 10, t_start + HARD_LIMIT)
    while _t.time() < deadline:
        if _find_frame_with(page, "#xnxqdm", 600):
            _log("点菜单方式成功")
            return True
        _t.sleep(0.3)

    _log(f"课表页打开失败（用时 {_t.time() - t_start:.1f}s）")
    return False


def base_url_of(page) -> str:
    """返回教务系统的站点根地址（去掉具体页面路径）。

    登录后页面 URL 形如
    https://webvpn.zqu.edu.cn/https/<加密串>/login!welcome.action
    这里解析出 https://webvpn.zqu.edu.cn/https/<加密串> 作为 base。
    """
    url = page.url
    for marker in ("login!welcome.action", "desktop!newDesktop.action",
                   "xsgrkbcx!xsgrkbMain.action"):
        idx = url.find(marker)
        if idx > 0:
            return url[:idx].rstrip("/")
    # 兜底：去掉最后一段路径
    return url.rsplit("/", 1)[0]


def _frame_has(f, selector: str, timeout_ms: int = 800) -> bool:
    """判断某个 frame 里是否有选择器，**带短超时**。

    为什么不用 `f.locator(sel).count()`：page 的默认超时是 45 秒
    （见 login.py `set_default_timeout(45000)`）。当 frame 正在导航、
    或已从 DOM detach 时，count() 会一直等到超时才抛错 ——
    全量扫描 20+ 个 frame 时，这一处就能让程序"卡住"好几分钟。

    这里传显式短超时 + 吞掉异常，保证单次探测最多花 timeout_ms。
    """
    try:
        return f.locator(selector).count() > 0
    except Exception:
        pass
    # locator 失败时退回 DOM 查询（同样带超时）
    try:
        return bool(f.evaluate(
            "(sel) => !!document.querySelector(sel)", selector))
    except Exception:
        return False


def _find_frame_with(page, selector: str, timeout_ms: int = 800):
    """找到包含指定选择器的 iframe（优先 wdkb/list，再全量扫描）。

    只扫带名字的 frame，跳过 about:blank 之类的空 frame，减少无谓等待。
    """
    # 1) 优先按名字找（课表相关 frame 的名字是固定的）
    for nm in ("wdkb", "list", "frmlist", "qxkb",
               "xsgrkbcx!xsgrkbMain.action"):
        try:
            f = page.frame(name=nm)
        except Exception:
            f = None
        if f and _frame_has(f, selector, timeout_ms):
            return f

    # 2) 全量扫描，跳过空中转页
    try:
        frames = list(page.frames)
    except Exception:
        return None
    for f in frames:
        try:
            if f.url in ("about:blank", "") or f.url.startswith("data:"):
                continue
        except Exception:
            continue
        if _frame_has(f, selector, timeout_ms):
            return f
    return None


def read_terms(page) -> dict:
    """读取「课表查询」页的学期下拉框。

    返回 {code: name, ...}，并把当前学期挂到 read_terms._cur_term 上。
    """
    f = _find_frame_with(page, "#xnxqdm")
    if not f:
        raise RuntimeError("未找到学期下拉框 #xnxqdm（课表页可能没打开）")
    data = f.evaluate("""() => {
        const s = document.querySelector('#xnxqdm');
        if (!s) return null;
        return {cur: s.value,
                opts: [...s.options].map(o => ({v: o.value, t: o.text.trim()}))};
    }""")
    if not data:
        raise RuntimeError("读取学期下拉框失败")
    terms = {o["v"]: o["t"] for o in data["opts"] if o["v"]}
    read_terms._cur_term = data["cur"]
    return terms


def read_weeks(page) -> tuple[int, dict]:
    """读取周次下拉框，返回 (总周数, {周次: 标签})。

    下拉第一项是「全部」（值为空），不计入周数。
    """
    f = _find_frame_with(page, "#zc")
    if not f:
        raise RuntimeError("未找到周次下拉框 #zc（课表页可能没打开）")
    data = f.evaluate("""() => {
        const s = document.querySelector('#zc');
        if (!s) return null;
        return {cur: s.value,
                opts: [...s.options].map(o => ({v: o.value, t: o.text.trim()}))};
    }""")
    if not data:
        raise RuntimeError("读取周次下拉框失败")
    weeks = {}
    for o in data["opts"]:
        v = str(o["v"]).strip()
        if v.isdigit():
            weeks[int(v)] = o["t"]
    total = max(weeks) if weeks else 0
    read_weeks._cur_week = data["cur"]
    return total, weeks


def fetch_week(page, base_url: str, term: str, week: int, term_name: str = "",
               week_label: str = "", timeout: int = 30000,
               vpn_marker: str = True):
    """请求某一周的课表数据，返回 WeekSchedule。

    直接调用后台接口，不依赖页面渲染，比抓 DOM 稳定得多。

    vpn_marker 控制是否附加 `vpn-12-o2-` 标记参数。
    该参数是 WebVPN 深信服代理用来识别「此请求来自被代理的教务系统」的标记，
    实测校内直连时带上也能正常返回（服务端忽略未知参数），
    但校园网版本会显式关掉它，避免携带一个语义上不成立的代理标记。
    """
    marker = "vpn-12-o2-jwgl.zqu.edu.cn&" if vpn_marker else ""
    url = _abs(base_url, KB_DATA) + f"?{marker}xnxqdm={term}&zc={week}&xsdm="
    resp = page.context.request.get(url, headers={
        "Referer": _abs(base_url, KB_LIST) + f"?xnxqdm={term}&zc={week}",
        "X-Requested-With": "XMLHttpRequest",
    })
    if not resp.ok:
        raise RuntimeError(f"课表接口返回 {resp.status}")
    try:
        payload = json.loads(resp.text())
    except Exception as e:
        raise RuntimeError(f"课表接口返回非JSON: {resp.text()[:200]}") from e
    return parse_payload(payload, week=week, term=term, term_name=term_name,
                         week_label=week_label)


def fetch_all_weeks(page, base_url: str, term: str, weeks: list | None = None,
                    term_name: str = "", verbose: bool = True,
                    progress=None, dedupe: bool = True,
                    vpn_marker: bool = True) -> TermSchedule:
    """抓取该学期所有周的课表。

    weeks 省略时自动读取周次下拉框的 1~总周数。
    dedupe=True 时在返回前自动去除重复排课。
    vpn_marker 透传给 fetch_week，校园网直连时置 False。
    """
    if weeks is None:
        total, week_map = read_weeks(page)
        weeks = sorted(week_map)
        if verbose:
            print(f"[课表] 共 {total} 周，将抓取第 {weeks[0]}~{weeks[-1]} 周")
    else:
        _, week_map = read_weeks(page)
        weeks = sorted(weeks)

    term_obj = TermSchedule(term=term, term_name=term_name, total_weeks=len(weeks))
    for w in weeks:
        label = week_map.get(w, f"第{w}周")
        try:
            ws = fetch_week(page, base_url, term, w, term_name=term_name,
                            week_label=label, vpn_marker=vpn_marker)
            term_obj.weeks.append(ws)
            if verbose:
                n = len(ws.courses)
                ds = sorted([d["date"] for d in ws.dates if d.get("date")])
                span = f"{ds[0]}~{ds[-1]}" if ds else "-"
                print(f"  第{w:>2}周 ({span}): {n} 条记录")
            if progress:
                progress(w, ws)
        except Exception as e:
            if verbose:
                print(f"  第{w:>2}周:抓取失败 {e}")

    if dedupe:
        removed = term_obj.dedupe()
        term_obj.dedupe_removed = removed
        if verbose and removed:
            print(f"[课表] 去重：移除 {removed} 条重复排课")

    if verbose:
        _report(term_obj)
    return term_obj


def _report(sched: TermSchedule) -> None:
    """抓取完成后的体检报告：帮助发现教务数据里的异常项。"""
    allc = sched.all_courses()
    print(f"[课表] 合计 {len(allc)} 条排课，去重后 {len(sched.unique_courses())} 门")

    wds = sched.active_weekdays()
    hidden = [w for w in range(1, 8) if w not in wds]
    if hidden:
        names = "、".join(WEEKDAY_CN[w] for w in hidden)
        print(f"[课表] 有课日：{' '.join(WEEKDAY_CN[w] for w in wds)}"
              f"（{names} 全学期无课，导出时自动隐藏）")

    pending = [c for c in allc if not (c.classroom or "").strip()]
    if pending:
        #按「课程+星期+节次」归并，避免同一安排刷屏
        agg: dict = {}
        for c in pending:
            k = (c.name, c.weekday, tuple(sorted(c.periods or [])))
            agg.setdefault(k, []).append(c.week)
        print(f"[课表] 注意：{len(pending)} 条排课未指定教室"
              f"（教务系统已排课但教室待定，非抓取错误）：")
        for (name, wd, ps), wks in sorted(agg.items(), key=lambda t: (t[0][1], t[0][2])):
            ptext = "-".join(str(p) for p in (ps[0], ps[-1])) if ps else "?"
            wk_txt = f"第{wks[0]}周" if len(wks) == 1 else \
                f"第{min(wks)}~{max(wks)}周"
            print(f"    {WEEKDAY_CN[wd]} {ptext}节 {name}（{wk_txt}）")