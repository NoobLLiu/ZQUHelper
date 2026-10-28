"""滑块验证码求解。

背景图里已经画好了目标缺口（一个高饱和度的蓝色拼图块），
因此无需对拼图块做纹理模板匹配——直接用颜色分割定位缺口更准、更稳。

坐标含义
- 背景图自然宽度固定 280，缺口横坐标 x 即相对背景图左边缘的像素偏移；
- 页面中 .drag-slide-identity 的初始 left 为 10px，拖动时 left = offset + 10，
  所以提交给服务端的 w 就是「水平位移量」，与缺口 x 的关系由 CSS 决定。
"""
from __future__ import annotations

import base64

import cv2
import numpy as np

# 缺口色块的颜色范围（HSV）。缺口为蓝/青色系，与自然背景差异极大。
HSV_LO = np.array([90, 60, 60], dtype=np.uint8)
HSV_HI = np.array([140, 255, 255], dtype=np.uint8)

# 单个连通域最小面积，滤掉噪声
MIN_AREA = 200


def decode_data_url(url: str) -> np.ndarray:
    """把 data:image/png;base64,... 解码为 numpy 数组。"""
    if "," in url:
        url = url.split(",", 1)[1]
    return cv2.imdecode(np.frombuffer(base64.b64decode(url), np.uint8), cv2.IMREAD_UNCHANGED)


def find_gap_by_color(bg: np.ndarray) -> tuple[int, int, int, int, float]:
    """在背景图中定位蓝色缺口色块。

    返回 (x, y, w, h, area)；找不到时抛 ValueError。
    """
    if bg.ndim == 3 and bg.shape[2] == 4:
        bg = bg[:, :, :3]
    hsv = cv2.cvtColor(bg, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, HSV_LO, HSV_HI)

    # 形态学闭运算，把缺口内部可能被图片纹理割断的区域连起来
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=2)

    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h
        if area < MIN_AREA:
            continue
        # 缺口块尺寸接近 40x40，过滤异常形状
        if not (25 <= w <= 55 and 25 <= h <= 55):
            continue
        if best is None or area > best[4]:
            best = (x, y, w, h, area)
    if best is None:
        raise ValueError("背景图中未找到缺口色块")
    return best


def find_gap(bg: np.ndarray, piece: np.ndarray | None = None) -> tuple[int, int, float]:
    """兼容入口：返回缺口中心点 (cx, cy) 与置信度。

    piece 参数保留仅为兼容旧调用，实际求解依赖颜色分割。
    """
    x, y, w, h, area = find_gap_by_color(bg)
    cx, cy = x + w // 2, y + h // 2
    # 置信度：用「是否接近正方形」作为合理性评分
    ratio = min(w, h) / max(w, h)
    return cx, cy, float(ratio)


def annotate(bg: np.ndarray, out_path: str) -> tuple[int, int]:
    """把缺口框画到背景图上，便于人工核对（调试用）。"""
    x, y, w, h, _ = find_gap_by_color(bg)
    img = bg[:, :, :3].copy() if bg.ndim == 3 and bg.shape[2] == 4 else bg.copy()
    cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 255), 2)
    cv2.imwrite(out_path, img)
    return x, y


def solve_from_pair(bg_data_url: str, piece_data_url: str | None = None,
                    y_hint: int | None = None) -> tuple[int, int, float]:
    """便捷入口：传入背景图 data URL，返回缺口中心 (cx, cy, score)。"""
    bg = decode_data_url(bg_data_url)
    return find_gap(bg)