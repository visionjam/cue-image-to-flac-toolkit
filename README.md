# cue-image-to-flac-toolkit

整轨 CUE（EAC 风格、GBK 编码）→ **分轨 FLAC** 的转换与校验工具链：采样级精确切轨、标签与内嵌封面写入、**逐轨 PCM MD5 无损证明**、元数据查证与来源审计。

首个数据集：陶喆 1997–2013 八张专辑（8 albums / 107 tracks / 7:02:01），全库校验 8/8 通过。

## 特性

- **采样级精确切轨**：CUE 的 CD 帧（1/75s）整数换算为采样（×588），无时间漂移、无爆音
- **GBK 老资源友好**：直接解析 EAC 风格 CUE（含 INDEX 00/01、中文曲名），文件名非法字符全角净化
- **逐轨无损证明**：每轨输出 FLAC 解码 PCM 的 MD5 与源整轨对应区段的 PCM MD5 **逐字节比对**，不一致即整张失败
- **元数据体系**：基础标签来自 CUE；补充发行信息（MusicBrainz MBID/厂牌/国家）与逐曲词曲作者经公开来源查证，遵循「查到才写、查不到留空、绝不编造」，每个值附来源 URL（见 `reports/metadata-provenance.csv`）
- **全库独立校验**：`verify.py` 重新解码源文件独立复核（不复用转换中间产物），并生成曲目清单
- **源目录只读保障**：`source_manifest.py` 处理前后目录清单比对，证明源文件零改动（为做种场景设计）

## 依赖

- **Python ≥ 3.10** — 官网下载：https://www.python.org/downloads/
- **ffmpeg / ffprobe**（需支持 APE 解码与 FLAC 编码，官方 full build 即可）— 下载：https://ffmpeg.org/download.html
  - Windows 推荐构建：[gyan.dev ffmpeg builds](https://www.gyan.dev/ffmpeg/builds/) 或 [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds/releases)（解压后将 `bin` 目录加入 PATH）
  - macOS：`brew install ffmpeg` ｜ Linux：发行版包管理器或 [官方静态构建](https://johnvansickle.com/ffmpeg/)
- **mutagen** — https://pypi.org/project/mutagen/ （`pip install mutagen`）
- **pytest**（仅运行测试需要）— https://pypi.org/project/pytest/ （`pip install pytest`）

## 用法

```bash
# 转换（单张或全部）：解析 CUE → 解码 → 切轨 → 编码 → 写标签/封面 → 逐轨 MD5 校验
python scripts/convert.py --album "<源文件夹名>"        # 重复 --album 或 --all
python scripts/convert.py --all --source-root <源目录> --output-root <输出目录>

# 全库独立校验 + 生成曲目清单 CSV
python scripts/verify.py --all

# 元数据来源审计（每个非空值必须能在 provenance CSV 找到带 URL 的来源行）
python scripts/check_meta.py --all

# 源目录清单：before / after / compare
python scripts/source_manifest.py before <源目录> <清单文件>
```

各脚本 `--help` 有完整参数；`--source-root` / `--output-root` / `--work-root` 均可覆盖（默认值按本项目数据集设置）。

## 目录结构

```
scripts/    工具链代码与测试（pytest，全部用例在真实 ffmpeg/mutagen 上运行）
meta/       经查证并审计的专辑元数据（JSON；_ 前缀为原始查询证据）
reports/    校验报告、曲目清单、元数据来源账、交叉复核报告
docs/       设计文档与实施计划
```

## 无损校验的口径

「无损」不是听起来对——是每轨都能证明：输出 FLAC 解码出的 PCM 字节流（音频流，`-map 0:a:0`）与源整轨对应区段**逐字节一致**；全库 107/107 通过且所有 PCM MD5 互不重复。封面等附加流不参与音频哈希。

## 元数据与版权说明

- 本仓库**不包含任何音频、封面图或歌词**，仅包含：代码、流程文档、以及**事实性元数据**（曲名、词曲作者、发行日期、厂牌等）与**公开来源引用**。
- 元数据查证流程：多来源交叉核对（MusicBrainz / Discogs / 中文维基 / 百科类公开页面），逐值记录来源 URL；查不到的字段留空并标注「未查到」，不做推断。
- 本工具用于处理**你自行合法获取**的整轨 + CUE 音频文件；请勿借此分发受版权保护的音频内容。

## 已知限制

- 输入为 44.1kHz/16bit/立体声（CD 规格）；其他规格会被拒绝并报错
- 单 FILE 单碟 CUE（多碟 CUE 会作为错误处理）
- APE 解码依赖 ffmpeg 内置解码器；个别损坏文件需外部解码器兜底

## 许可证

本项目以 [MIT 许可证](LICENSE) 开源。
