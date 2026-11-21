# audio-stereo-width

## 题面

给母带加立体声扩展后，低频整体消失、单声道播放还发虚：mid_side 把 M/S 都算成 (L+R)，S 永远为 0；from_mid_side 还原时没有按半增益定义处理 S，幅度翻倍；widen 直接乘左右声道，整体变响；bass_mono 不合并低频，单声道兼容时低频抵消；phase_guard 用固定阈值，慢歌也被收窄；correlation 用归一化点积却不减均值，直流偏置被误判；静音段相关除零；宽度为 2 时不钳制，超过后失真；width_batch 共用侧信号缓冲，对与对之间串；width<0 不校验，导致反相。width/stereo.py 是核心，tests/test_stereo.py 15个红。要修的是：按 M=(L+R)/2、S=(L-R)/2 实现 8 个函数，宽度限制在 0..2 并钳制输出到 -1..1，低频用相位安全方式合并，相位保护尊重调用方阈值，相关先减均值且静音返回 0，批量先整体校验、失败回滚、成功保序，使 15 个测试全部转绿。

## 运行方式

在仓库根目录执行：

```bash
python -m pytest tests -q
```

初始（未实现）状态下应恰好输出 `15 failed`，且没有 collection error、import error 或 syntax error：

```text
15 failed
```

15 个测试全部直接调用 `width/stereo.py` 的桩函数，因此当前失败原因是 `NotImplementedError`。实现完成后目标为 `15 passed`。

## 字段表

| 字段 | 取值 |
| --- | --- |
| 所属领域 | 游戏、图形与多媒体 |
| 子方向 | 音视频处理 |
| 任务类型 | Bugfix |
| 语言/框架 | Python 3, pytest |
| 环境可复现等级 | 无外部依赖 |

## 目录结构

```text
audio-stereo-width/
├── README.md
├── conftest.py
├── .gitignore
├── width/
│   ├── __init__.py
│   └── stereo.py
└── tests/
    └── test_stereo.py
```

`conftest.py` 将仓库根加入 `sys.path`，因此无需安装包即可导入 `width`。实现只使用 Python 标准库 `math` 与 pytest，离线运行、不使用随机数、不 `sleep`、不联网。

## 约束

- 立体声统一表示为 `(left, right)` 两个等长的 `list[float]`，样本范围 `-1.0 .. 1.0`。
- M/S 定义为 `M=(L+R)/2`、`S=(L-R)/2`；宽度合法范围 `0.0 .. 2.0`。
- 浮点比较容差为 `1e-6`；`width == 1.0` 时要求逐样本原样返回（容差 `1e-9`）。
- 参数、宽度或批量输入非法时统一抛出 `width.stereo.WidthError`。
- `tests/test_stereo.py` 是验收规格，**不可修改**；修复只发生在 `width/stereo.py`（`width/__init__.py` 仅做导出）。
