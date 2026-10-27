"""教务系统图形验证码识别（ddddocr）。

验证码特征（实测肇庆学院教务系统）：
- 4~5 位大写字母或数字，长度不固定；
- 字符带旋转/倾斜、字距不均；
- 背景有雪花噪点与多条波浪干扰线；
- 原图 200~280 x 80，未做 CSS 缩放。

识别策略：多尺度+ 多预处理投票，取出现次数最多的结果。
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

# 教务验证码只可能出现大写字母和数字
_ALLOWED = re.compile(r"[^A-Z0-9]")

# 模型只加载一次（首次约需数秒）
_ocr = None


def _get_ocr():
    global _ocr
    if _ocr is None:
        import ddddocr
        _ocr = ddddocr.DdddOcr(show_ad=False)
    return _ocr


def _clean(text: str) -> str:
    """只保留大写字母与数字。"""
    return _ALLOWED.sub("", (text or "").upper())


def _variants(img: np.ndarray) -> list[bytes]:
    """对验证码图做多种预处理，提升识别率。"""
    out: list[bytes] = []

    def enc(a: np.ndarray) -> bytes:
        ok, buf = cv2.imencode(".png", a)
        return buf.tobytes() if ok else b""

    out.append(enc(img))

    # 放大：小图放大后 ddddocr 更稳
    for f in (2, 3):
        out.append(enc(cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)))

    # 灰度 + 自适应二值化，压暗干扰线
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    for block in (31, 51):
        binv = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, block, 5)
        out.append(enc(binv))

    # 中值滤波去椒盐噪点
    out.append(enc(cv2.medianBlur(gray, 3)))

    # 提高对比度
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    out.append(enc(clahe))

    # 去除波浪干扰线：干扰线细长、字符笔画较粗，用横向/纵向开运算提取线条后减掉
    try:
        bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
        hor = cv2.morphologyEx(bw, cv2.MORPH_OPEN,
                               cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1)))
        ver = cv2.morphologyEx(bw, cv2.MORPH_OPEN,
                               cv2.getStructuringElement(cv2.MORPH_RECT, (1, 25)))
        lines = cv2.bitwise_or(hor, ver)
        cleaned = cv2.bitwise_and(bw, cv2.bitwise_not(lines))
        out.append(enc(255 - cleaned))
    except Exception:
        pass

    return [v for v in out if v]


def recognize(img_bytes: bytes | np.ndarray) -> str:
    """识别验证码，返回清洗后的字符串（可能为空）。"""
    if isinstance(img_bytes, np.ndarray):
        ok, buf = cv2.imencode(".png", img_bytes)
        if not ok:
            return ""
        img_bytes = buf.tobytes()

    ocr = _get_ocr()
    votes: Counter[str] = Counter()
    for data in _variants(cv2.imdecode(np.frombuffer(img_bytes, np.uint8),
                                       cv2.IMREAD_COLOR)):
        try:
            votes[_clean(ocr.classification(data))] += 1
        except Exception:
            continue

    votes.pop("", None)
    if not votes:
        return ""
    # 票数优先；同票数时取更长（教务验证码多为 5 位）
    best = max(votes.items(), key=lambda kv: (kv[1], len(kv[0])))
    return best[0]


def recognize_with_detail(img_bytes: bytes, top_n: int = 4) -> tuple[str, list[tuple[str, int]]]:
    """带诊断信息的识别，返回 (最佳结果, 候选列表)。"""
    if isinstance(img_bytes, (bytes, bytearray)):
        arr = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    else:
        arr = img_bytes
    ocr = _get_ocr()
    votes: Counter[str] = Counter()
    for data in _variants(arr):
        try:
            votes[_clean(ocr.classification(data))] += 1
        except Exception:
            continue
    votes.pop("", None)
    if not votes:
        return "", []
    ranked = votes.most_common(top_n)
    best = max(ranked, key=lambda kv: (kv[1], len(kv[0])))[0]
    return best, ranked


def recognize_file(path: str | Path) -> str:
    data = Path(path).read_bytes()
    return recognize(data)