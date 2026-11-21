"""立体声宽度处理核心。

约定
----
* 立体声信号表示为 ``(left, right)`` 两个等长的 ``list[float]``，样本归一化
  到 ``-1.0 .. 1.0``（含端点）。
* M/S 增益：``M = (L + R) / 2``，``S = (L - R) / 2``；反变换为
  ``L = M + S``、``R = M - S``。两个分量都是半增益。
* 宽度：``0.0`` 为完全单声道，``1.0`` 为原样，``2.0`` 为侧信号加倍；
  合法范围是 ``0.0 .. 2.0``（含端点）。
* 容差：浮点比较使用绝对容差 ``1e-6``；``width == 1.0`` 时要求逐样本原样。
* 异常：长度不一致、宽度越界、频率/阈值等参数非法时统一抛出
  :class:`WidthError`。
* 输出：处理函数返回新列表，不修改输入；可产生过冲的结果统一钳制到
  ``-1.0 .. 1.0``。

本模块实现 8 个公开函数：M/S 分解与还原、宽度处理、低频单声道化、
相位保护、相关性计算、输入校验以及批量处理。
"""

from __future__ import annotations

import math


class WidthError(ValueError):
    """立体声输入、宽度或批量配置非法时抛出的异常。"""


_MIN_WIDTH = 0.0
_MAX_WIDTH = 2.0
_EPS = 1e-12


def _check_pair(l: list[float], r: list[float]) -> None:
    """校验左右声道长度一致，否则抛出 :class:`WidthError`。"""
    if len(l) != len(r):
        raise WidthError(
            f"左右声道长度不一致：left={len(l)}，right={len(r)}"
        )


def _width_value(width) -> float:
    """把宽度转成浮点数并校验其位于合法范围，否则抛 WidthError。"""
    if isinstance(width, bool) or not isinstance(width, (int, float)):
        raise WidthError(f"width 必须是有限数值，得到 {width!r}")
    value = float(width)
    if not math.isfinite(value) or not (_MIN_WIDTH <= value <= _MAX_WIDTH):
        raise WidthError(
            f"width 必须在 {_MIN_WIDTH} .. {_MAX_WIDTH} 内，得到 {width!r}"
        )
    return value


def _clamp(x: float) -> float:
    """把单个样本钳制到 -1.0 .. 1.0。"""
    if x > 1.0:
        return 1.0
    if x < -1.0:
        return -1.0
    return x


def mid_side(l: list[float], r: list[float]) -> tuple:
    """把左右声道分解为 mid/side，返回 ``(m, s)``。

    契约
    ----
    * ``l``、``r`` 为等长立体声样本；长度不一致时抛出 :class:`WidthError`。
    * 逐样本计算半增益分量：``m[i] = (l[i] + r[i]) / 2``、
      ``s[i] = (l[i] - r[i]) / 2``。``s`` 不能退化成 ``l[i] - r[i]``，
      否则侧信号会丢失一半或恒为 0。
    * 空输入返回 ``([], [])``；返回新列表，不修改输入。
    * 浮点结果与公式的误差不超过 ``1e-6``。
    """

    _check_pair(l, r)
    return _mid_side(l, r)


def _mid_side(l: list[float], r: list[float]) -> tuple:
    """内部 M/S 分解，不做长度校验。"""
    m = [(a + b) / 2.0 for a, b in zip(l, r)]
    s = [(a - b) / 2.0 for a, b in zip(l, r)]
    return m, s


def _from_mid_side(m: list[float], s: list[float]) -> tuple:
    """内部 M/S 还原，不做长度校验。"""
    l = [a + b for a, b in zip(m, s)]
    r = [a - b for a, b in zip(m, s)]
    return l, r


def from_mid_side(m: list[float], s: list[float]) -> tuple:
    """把 mid/side 还原为左右声道，返回 ``(l, r)``。

    契约
    ----
    * ``m``、``s`` 为等长序列；长度不一致时抛出 :class:`WidthError`。
    * 由于 ``m``、``s`` 都是半增益，反变换为 ``l[i] = m[i] + s[i]``、
      ``r[i] = m[i] - s[i]``，不再对 ``s`` 额外除以 2。
    * 与 :func:`mid_side` 构成往返：对合法 ``(l, r)``，
      ``from_mid_side(*mid_side(l, r))`` 的每个样本与原值误差不超过
      ``1e-6``。
    * 空输入返回 ``([], [])``；返回新列表，不修改输入，不做幅度归一。
    """

    if len(m) != len(s):
        raise WidthError(
            f"mid/side 长度不一致：mid={len(m)}，side={len(s)}"
        )
    return _from_mid_side(m, s)


def widen(l: list[float], r: list[float], width: float) -> tuple:
    """按 ``width`` 扩展立体声宽度，返回 ``(l_out, r_out)``。

    契约
    ----
    * ``l``、``r`` 等长；不等长时抛出 :class:`WidthError`。
    * ``width`` 必须是有限数值且在 ``0.0 .. 2.0`` 内，否则抛出
      :class:`WidthError`。
    * 先做 M/S 分解，再按 ``l_out = M + width * S``、
      ``r_out = M - width * S`` 还原。
    * ``width == 0.0`` 时左右都等于 ``M``，即单声道；``width == 1.0`` 时
      输出与输入逐样本一致（容差 ``1e-6``）；``width == 2.0`` 时侧信号
      加倍（相对 mid，而不是把整个声道乘 2）。
    * 输出逐样本钳制到 ``-1.0 .. 1.0``，防止宽度 2 时过冲失真；返回新
      列表，不修改输入。空输入返回 ``([], [])``。
    """

    _check_pair(l, r)
    w = _width_value(width)
    if w == 1.0:
        return list(l), list(r)
    m, s = _mid_side(l, r)
    out_l = [_clamp(a + w * b) for a, b in zip(m, s)]
    out_r = [_clamp(a - w * b) for a, b in zip(m, s)]
    return out_l, out_r


def bass_mono(
    l: list[float],
    r: list[float],
    freq: float,
    sample_rate: int,
) -> tuple:
    """把 ``freq`` 以下的低频收成单声道，同时保护低频相位。

    契约
    ----
    * ``l``、``r`` 等长；不等长时抛出 :class:`WidthError`。
    * ``sample_rate`` 必须为正数，``freq`` 必须满足
      ``0 < freq < sample_rate / 2``；否则抛出 :class:`WidthError`。
    * 用一阶低通分离低频，系数为
      ``alpha = 1 - exp(-2 * pi * freq / sample_rate)``，每个声道的滤波
      状态用该声道首个样本初始化；空输入返回 ``([], [])``。
    * 取低频段 ``lo_l``、``lo_r``。若两者的协方差为负，先把 ``lo_r`` 取反
      得到与 ``lo_l`` 同相的版本，再计算单声道低频
      ``lo_m = (lo_l + oriented_lo_r) / 2``；这样反相低频不会在单声道下
      互相抵消，属于相位保护。
    * 每个声道去掉自己的原始低频、加上 ``lo_m``：
      ``out_l = (l - lo_l) + lo_m``、``out_r = (r - lo_r) + lo_m``；
      输出钳制到 ``-1.0 .. 1.0``，高频空间信息保持不变。
    * 合并后的低频在左右声道中完全相同，单声道兼容；浮点误差不超过
      ``1e-6``，返回新列表且不修改输入。
    """

    _check_pair(l, r)
    if sample_rate <= 0:
        raise WidthError(f"sample_rate 必须为正数，得到 {sample_rate!r}")
    if not math.isfinite(freq) or not (0.0 < freq < sample_rate / 2.0):
        raise WidthError(
            f"freq 必须满足 0 < freq < sample_rate / 2，得到 {freq!r}"
        )
    if not l:
        return [], []

    alpha = 1.0 - math.exp(-2.0 * math.pi * freq / sample_rate)
    lo_l = _low_pass(l, alpha)
    lo_r = _low_pass(r, alpha)

    # 相位保护：低频反相时先把 side 翻正，避免单声道合并时抵消。
    mean_l = sum(lo_l) / len(lo_l)
    mean_r = sum(lo_r) / len(lo_r)
    cov = sum((a - mean_l) * (b - mean_r) for a, b in zip(lo_l, lo_r))
    oriented_lo_r = [-b for b in lo_r] if cov < 0.0 else lo_r
    lo_m = [(a + b) / 2.0 for a, b in zip(lo_l, oriented_lo_r)]

    out_l = [_clamp((a - lo_a) + mono) for a, lo_a, mono in zip(l, lo_l, lo_m)]
    out_r = [_clamp((b - lo_b) + mono) for b, lo_b, mono in zip(r, lo_r, lo_m)]
    return out_l, out_r


def _low_pass(samples: list[float], alpha: float) -> list[float]:
    """一阶低通，状态用首个样本初始化。"""
    state = samples[0]
    out = [state]
    for x in samples[1:]:
        state = state + alpha * (x - state)
        out.append(state)
    return out


def phase_guard(l: list[float], r: list[float], threshold: float) -> tuple:
    """相关性过低时收窄侧信号，防止反相；阈值由调用方给出。

    契约
    ----
    * ``l``、``r`` 等长；不等长时抛出 :class:`WidthError`。
    * ``threshold`` 必须是有限数值且在 ``0.0 .. 1.0`` 内，否则抛出
      :class:`WidthError`。
    * 用 :func:`correlation` 计算相关系数 ``c``。当 ``c >= threshold`` 时，
      返回输入的原样副本，不做任何收窄（慢歌、高相关素材不应被误伤）。
    * 当 ``c < threshold`` 时，侧信号增益
      ``g = max(0.0, (c + 1.0) / (threshold + 1.0))``；用 ``g`` 缩放
      ``S`` 后按 M/S 还原。``c == -1`` 时 ``g == 0``，完全收成单声道。
    * 输出钳制到 ``-1.0 .. 1.0``；空输入返回 ``([], [])``。容差
      ``1e-6``，返回新列表且不修改输入。
    """

    _check_pair(l, r)
    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, (int, float))
        or not math.isfinite(float(threshold))
        or not (0.0 <= float(threshold) <= 1.0)
    ):
        raise WidthError(f"threshold 必须在 0.0 .. 1.0 内，得到 {threshold!r}")
    if not l:
        return [], []

    c = correlation(l, r)
    th = float(threshold)
    if c >= th:
        return list(l), list(r)

    g = max(0.0, (c + 1.0) / (th + 1.0))
    m, s = _mid_side(l, r)
    out_l = [_clamp(a + g * b) for a, b in zip(m, s)]
    out_r = [_clamp(a - g * b) for a, b in zip(m, s)]
    return out_l, out_r


def correlation(l: list[float], r: list[float]) -> float:
    """返回左右声道的皮尔逊相关系数，范围 ``-1.0 .. 1.0``。

    契约
    ----
    * ``l``、``r`` 等长；不等长时抛出 :class:`WidthError`。
    * 先分别减去均值，再计算归一化点积：
      ``sum((l - mean_l) * (r - mean_r)) /
      sqrt(sum((l - mean_l) ** 2) * sum((r - mean_r) ** 2))``。不能直接用
      未去均值的点积，否则直流偏置会被误判成相关。
    * 空输入、任一声道为零方差（含全静音）时返回 ``0.0``，绝不做除零。
    * 结果钳制在 ``-1.0 .. 1.0``；容差 ``1e-6``。
    """

    _check_pair(l, r)
    if not l:
        return 0.0

    mean_l = sum(l) / len(l)
    mean_r = sum(r) / len(r)
    dl = [x - mean_l for x in l]
    dr = [x - mean_r for x in r]
    num = sum(a * b for a, b in zip(dl, dr))
    den = math.sqrt(sum(a * a for a in dl) * sum(b * b for b in dr))
    if den <= 0.0:
        return 0.0
    return max(-1.0, min(1.0, num / den))


def validate(l: list[float], r: list[float], width: float) -> list[str]:
    """检查一对立体声输入和宽度，返回问题描述列表；合法时返回 ``[]``。

    契约
    ----
    * 只报告问题，不抛异常。调用方可根据列表决定是否拒绝输入。
    * 检查项：``l`` 与 ``r`` 长度不等；``width`` 不是有限数值或不在
      ``0.0 .. 2.0`` 内；非空输入中左右声道同时为静音（所有
      ``abs(sample) <= 1e-12``）。
    * 空输入是合法的，返回 ``[]``，不能被误判为全静音。
    * 每条问题为可读字符串，多个问题按长度、宽度、静音的顺序全部列出；
      不修改输入。
    """

    problems: list[str] = []

    if len(l) != len(r):
        problems.append(
            f"左右声道长度不一致：left={len(l)}，right={len(r)}"
        )

    valid_width = False
    if not isinstance(width, bool) and isinstance(width, (int, float)):
        value = float(width)
        if math.isfinite(value) and _MIN_WIDTH <= value <= _MAX_WIDTH:
            valid_width = True
    if not valid_width:
        problems.append(
            f"width 必须是 {_MIN_WIDTH} .. {_MAX_WIDTH} 内的有限数值，"
            f"得到 {width!r}"
        )

    # 只在非空输入上判断静音；空输入是合法的。
    if l and r and all(abs(x) <= _EPS for x in l) and all(
        abs(x) <= _EPS for x in r
    ):
        problems.append("左右声道同时为静音，无法计算宽度")

    return problems


def width_batch(pairs: list[tuple[list[float], list[float]]], config: dict) -> dict:
    """批量应用宽度处理，任一对非法时整体回滚。

    契约
    ----
    * ``pairs`` 是 ``(left, right)`` 对的列表，每一项的两个声道都是
      ``list[float]``；``config`` 是配置字典，只读取 ``width``（默认
      ``1.0``，合法范围 ``0.0 .. 2.0``），其他键忽略。
    * 先对全部输入对调用 :func:`validate` 做整体校验；只要任一对有问题，
      立即抛出 :class:`WidthError`，错误信息包含该对的索引。此时不返回
      任何部分结果，即整体回滚。
    * 校验通过后按输入顺序逐对调用 :func:`widen`。每对必须独立计算自己的
      M/S，不得共用侧信号缓冲，避免对与对之间串音。
    * 返回 ``{"pairs": [(l_out, r_out), ...], "count": len(pairs)}``；
      成功时输出顺序与输入一致，不修改输入。空 ``pairs`` 返回
      ``{"pairs": [], "count": 0}``。每对的浮点误差不超过 ``1e-6``。
    """

    w = _width_value(config.get("width", 1.0))

    # 先整体校验；任一非法立即失败，不产生部分结果（整体回滚）。
    for index, (l, r) in enumerate(pairs):
        problems = validate(l, r, w)
        if problems:
            raise WidthError(
                f"第 {index} 对输入非法：" + "；".join(problems)
            )

    # 每对独立调用 widen，各自计算 M/S，不复用缓冲、不串音。
    out_pairs = [widen(l, r, w) for l, r in pairs]
    return {"pairs": out_pairs, "count": len(out_pairs)}
