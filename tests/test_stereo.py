"""15 个红灯测试：每个测试都直接调用尚未实现的桩函数。

测试只验证公开契约，不修改实现。浮点比较统一使用 1e-6 绝对容差；
唯一例外是 ``width == 1`` 的原样返回，要求 1e-9。
"""

import math

import pytest

from width.stereo import (
    WidthError,
    bass_mono,
    correlation,
    from_mid_side,
    mid_side,
    phase_guard,
    validate,
    widen,
    width_batch,
)


def _approx(values, abs_tol=1e-6):
    """把序列包装成 pytest 的绝对容差比较。"""
    return pytest.approx(values, abs=abs_tol)


def _rms(values):
    """计算序列的均方根，用于比较低频能量。"""
    return math.sqrt(sum(x * x for x in values) / len(values))


def test_mid_side_uses_half_sum_and_half_difference():
    """缺陷 1：S 不能和 M 一样用 (L+R)，否则侧信号恒为 0。"""
    left = [0.8, -0.4, 0.2]
    right = [0.2, 0.6, -0.2]

    m, s = mid_side(left, right)

    assert m == _approx([0.5, 0.1, 0.0])
    assert s == _approx([0.3, -0.5, 0.2])


def test_from_mid_side_keeps_half_side_scale():
    """缺陷 2：还原必须使用半差 S，幅度不能翻倍。"""
    m = [0.5, 0.1, 0.0]
    s = [0.3, -0.5, 0.2]

    left, right = from_mid_side(m, s)

    assert left == _approx([0.8, -0.4, 0.2])
    assert right == _approx([0.2, 0.6, -0.2])

    src_left = [0.3, -0.7, 0.0, 0.45]
    src_right = [-0.2, 0.1, 0.6, -0.35]
    round_left, round_right = from_mid_side(*mid_side(src_left, src_right))
    assert round_left == _approx(src_left)
    assert round_right == _approx(src_right)


def test_widen_preserves_level_instead_of_scaling_channels():
    """缺陷 3：宽度处理不能把左右声道整体乘宽、抬高响度。"""
    left = [0.4, -0.2, 0.0]
    right = [0.1, 0.3, 0.2]
    width = 1.5

    out_left, out_right = widen(left, right, width)

    for i in range(len(left)):
        assert out_left[i] + out_right[i] == pytest.approx(
            left[i] + right[i], abs=1e-6
        )
        assert out_left[i] - out_right[i] == pytest.approx(
            width * (left[i] - right[i]), abs=1e-6
        )


def test_bass_mono_prevents_low_band_cancellation():
    """缺陷 4：反相低频必须做相位保护，不能原样保留后互相抵消。"""
    sample_rate = 8000
    cutoff = 200.0
    n = 800
    low = [
        0.5 * math.sin(2.0 * math.pi * 80.0 * i / sample_rate)
        for i in range(n)
    ]
    high = [
        0.05 * math.sin(2.0 * math.pi * 1000.0 * i / sample_rate)
        for i in range(n)
    ]
    left = [a + b for a, b in zip(low, high)]
    right = [-a + b for a, b in zip(low, high)]

    out_left, out_right = bass_mono(left, right, cutoff, sample_rate)

    assert len(out_left) == n
    assert len(out_right) == n
    mono_in = [(a + b) / 2.0 for a, b in zip(left, right)]
    mono_out = [(a + b) / 2.0 for a, b in zip(out_left, out_right)]
    tail = slice(n // 8, None)
    assert _rms(mono_out[tail]) > 0.2
    assert _rms(mono_out[tail]) > 3.0 * _rms(mono_in[tail])


def test_phase_guard_uses_caller_threshold_on_correlated_input():
    """缺陷 5：高相关素材在低阈值下不能被固定阈值误收窄。"""
    left = [0.5, 0.5, -0.5, -0.5]
    right = [0.5, 0.0, -0.5, 0.0]

    out_left, out_right = phase_guard(left, right, 0.3)

    assert out_left == _approx(left)
    assert out_right == _approx(right)


def test_correlation_removes_dc_bias_before_normalizing():
    """缺陷 6：相关系数必须先减均值，不能把直流偏置当成相关。"""
    left = [0.2, 0.7, 0.2, 0.7]
    right = [0.2, 0.2, 0.7, 0.7]

    assert correlation(left, right) == pytest.approx(0.0, abs=1e-6)


def test_correlation_silence_returns_zero():
    """缺陷 7：静音段相关必须返回 0，不能除零。"""
    silent = [0.0] * 16

    assert correlation(silent, silent) == pytest.approx(0.0, abs=1e-6)
    assert correlation([0.0] * 4, [0.5, -0.5, 0.5, -0.5]) == pytest.approx(
        0.0, abs=1e-6
    )


def test_widen_clamps_at_width_two():
    """缺陷 8：宽度 2 的过冲必须钳制到 -1..1，不能削波失真。"""
    out_left, out_right = widen([1.0, -1.0], [0.0, 0.0], 2.0)

    assert out_left == _approx([1.0, -1.0])
    assert out_right == _approx([-0.5, 0.5])
    assert max(abs(x) for x in out_left + out_right) <= 1.0


def test_width_batch_does_not_leak_side_buffer_between_pairs():
    """缺陷 9：批量处理每对必须独立，侧信号缓冲不能在 pair 间串。"""
    pairs = [
        ([1.0, -1.0], [0.0, 0.0]),
        ([0.2, 0.2], [-0.1, -0.1]),
    ]

    result = width_batch(pairs, {"width": 2.0})

    assert result["count"] == 2
    first_left, first_right = result["pairs"][0]
    second_left, second_right = result["pairs"][1]
    expected_left, expected_right = widen(pairs[1][0], pairs[1][1], 2.0)
    assert first_left == _approx([1.0, -1.0])
    assert first_right == _approx([-0.5, 0.5])
    assert second_left == _approx(expected_left)
    assert second_right == _approx(expected_right)


def test_validate_rejects_negative_width():
    """缺陷 10：width < 0 必须被校验拒绝，不能反相。"""
    left = [0.1, -0.2]
    right = [0.0, 0.2]

    problems = validate(left, right, -0.5)

    assert problems
    assert any("width" in p.lower() or "宽度" in p for p in problems)
    with pytest.raises(WidthError):
        widen(left, right, -0.5)


def test_width_one_is_identity():
    """组合：width == 1 时输出必须等于输入，容差 1e-9。"""
    left = [0.1, -0.4, 0.7, 0.0]
    right = [-0.2, 0.3, 0.0, 0.5]

    out_left, out_right = widen(left, right, 1.0)

    assert out_left == _approx(left, abs_tol=1e-9)
    assert out_right == _approx(right, abs_tol=1e-9)


def test_mono_input_is_unchanged_by_any_width():
    """组合：左右完全相同的单声道内容，宽度参数不产生任何变化。"""
    left = [0.2, -0.5, 0.1]
    right = list(left)

    for width in (0.0, 1.0, 2.0):
        out_left, out_right = widen(left, right, width)
        assert out_left == _approx(left)
        assert out_right == _approx(right)


def test_length_mismatch_raises_width_error():
    """组合：左右长度不等必须抛 WidthError。"""
    left = [0.1, 0.2, 0.3]
    right = [0.1, 0.2]

    assert validate(left, right, 1.0)
    with pytest.raises(WidthError):
        widen(left, right, 1.0)


def test_empty_input_returns_empty_results():
    """组合：所有入口的空输入都返回空结果，不报错。"""
    assert mid_side([], []) == ([], [])
    assert from_mid_side([], []) == ([], [])
    assert widen([], [], 1.0) == ([], [])
    assert bass_mono([], [], 100.0, 48000) == ([], [])
    assert phase_guard([], [], 0.5) == ([], [])
    assert correlation([], []) == pytest.approx(0.0, abs=1e-6)
    assert validate([], [], 1.0) == []
    assert width_batch([], {"width": 1.0}) == {"pairs": [], "count": 0}


def test_width_batch_preserves_order_on_success():
    """组合：批量全部成功时输出顺序与输入一致。"""
    pairs = [
        ([0.1, 0.2, -0.1], [0.0, 0.1, 0.2]),
        ([-0.2, 0.0, 0.4], [0.1, -0.3, 0.2]),
        ([0.05, 0.05], [0.05, 0.05]),
    ]

    result = width_batch(pairs, {"width": 1.0})

    assert result["count"] == 3
    assert len(result["pairs"]) == 3
    for (got_left, got_right), (src_left, src_right) in zip(
        result["pairs"], pairs
    ):
        assert got_left == _approx(src_left)
        assert got_right == _approx(src_right)
