# 陶喆专辑 FLAC 音乐库构建 — 设计文档

- 日期：2026-10-04
- 状态：已获用户批准（方案 A：Python + ffmpeg 脚本流水线）
- 项目目录：`E:\音乐库-工作区\`（与输出库同级，避免传输手机时误带）
  - `docs\` 设计文档 | `scripts\` 脚本 | `meta\` 元数据查证结果 | `temp\` 临时 WAV（每张专辑用后即删） | `logs\` 日志 | `reports\` 校验报告与曲目清单
- 输出目录：`E:\音乐库\陶喆\`

## 背景与目标

在安卓手机上自建本地音乐库，只接受 FLAC/WAV，按专辑归档。

源数据：`E:\陶喆`，8 张专辑（1997–2013），全部为「整轨单文件 + CUE + cover.jpg」：

- 7 张 APE（44.1kHz / 16bit / 双声道）+ 1 张 FLAC（同参数），共约 107 首，合计 2.6GB
- CUE 为标准 EAC 格式，**GB18030（GBK）编码**，含专辑名、REM DATE、曲目表和 INDEX 01

## 约束

1. **源目录正在做种** → `E:\陶喆` 全程只读：不写入、不移动、不重命名任何文件
2. 成品由用户自行用 LocalSend 传输到手机 → 本设计只负责产出成品到本地磁盘
3. 格式只接受 FLAC/WAV → 输出统一为 FLAC（无损，体积约为 WAV 一半），不产出 WAV 副本

## 要解决的问题

1. APE 不在接受格式内 → 无损转 FLAC
2. 整轨单文件在安卓播放器兼容性差（CUE 支持参差）→ 按 CUE 拆为单曲
3. GBK 编码的老 CUE → 正确解码，避免中文标签乱码
4. 播放器封面显示 → cover.jpg 内嵌进每轨 FLAC
5. 元数据丰富度 → 从 MusicBrainz / 公开资料补充发行信息与逐曲词曲作者，按标准标签写入

## 方案选型

选 A（Python + ffmpeg 脚本），理由：全自动、采样级精确、标签/封面精确可控、可逐轨 MD5 校验、可重复执行。B（CUETools）仅 AccurateRip 源质量校验为独有能力，与本次转换无关；C（foobar2000）配置繁琐易乱码。详见对话中的对比表。

## 处理流水线（每张专辑）

1. **解析 CUE**：按 gb18030 解码，提取专辑标题（TITLE）、日期（REM DATE）、风格（REM GENRE）、艺人（PERFORMER）、曲目表（TRACK / TITLE / INDEX 01）
   - 日期回退链：REM DATE → 源文件夹名的日期前缀（如 `1997.12.06`）→ 仅取文件夹年份
   - 曲目起点一律用 INDEX 01；INDEX 00→01 的间隙归入前一首（EAC 标准）
   - 最后一轨终点 = 音频文件末尾
2. **整轨解码**：ffmpeg 将整轨 APE/FLAC 解码为临时 WAV（保持 44.1k/16bit，不重采样、不处理增益）
3. **切轨**：按 INDEX 01 的采样点位置切分（帧 → 采样换算，采样级精确）
4. **编码**：逐轨 `ffmpeg -c:a flac -compression_level 8`
5. **标签**（mutagen 写 Vorbis comment）：基础字段见下表；查证类补充字段（发行信息/词曲作者）见「元数据补充」节
   | 字段 | 值 |
   |---|---|
   | ARTIST | 陶喆 |
   | ALBUMARTIST | 陶喆 |
   | ALBUM | CUE TITLE |
   | TITLE | CUE 曲名（保留中英对照原名） |
   | TRACKNUMBER | n |
   | TRACKTOTAL | 该专辑总轨数 |
   | DATE | 见日期回退链，如 2002-08-09 |
   | GENRE | REM GENRE（若有） |
6. **封面**：cover.jpg 内嵌为 PICTURE 块（type=3 front cover）；同时在专辑目录保留一份 cover.jpg

## 输出规范

```
E:\音乐库\陶喆\
├─ 1997 - David Tao\
│  ├─ 01 - Airport Take Off.flac
│  ├─ ...
│  └─ cover.jpg
├─ 2002 - 黑色柳丁\
│  ├─ 01 - 黑色柳丁(Black Tangerine).flac
│  └─ ...
└─ 2013 - 再见你好吗\
```

- 专辑目录名：`<年份> - <CUE 专辑名>`
- 文件名：`NN - <曲名>.flac`（NN 两位补零）
- 文件名净化：Windows 非法字符 `\ / : * ? " < > |` 替换为全角（`:` → `：`），去除首尾空格与结尾句点；**标签内容保持原样不净化**
- 每轨时长末端保留切点精度，不做淡入淡出等任何处理

## 元数据补充（查证类）

数据源与原则：

- 专辑发行信息：MusicBrainz（实测可查，但覆盖不均），优先匹配与 CUE 日期/地区一致的版本（如台湾原版）
- 逐曲词曲作者：MusicBrainz 实测无此数据 → 从中文百科/可信公开资料人工核对（双源交叉验证）
- **原则：只写可查证的，查不到留空，绝不编造**；所有补充字段的来源记录到 `reports\metadata-provenance.csv`
- 中间产物：每张专辑一份 `meta\<专辑>.json`（人工可审阅），转换脚本读取该文件写标签，使查证与转换分离

补充字段（Vorbis comment，MusicBrainz Picard 兼容命名）：

| 字段 | 值 | 来源 |
|---|---|---|
| MUSICBRAINZ_ALBUMID | 发行版 MBID | MusicBrainz |
| MUSICBRAINZ_ARTISTID | 陶喆 艺人 MBID | MusicBrainz |
| MUSICBRAINZ_RELEASEGROUPID | 发行组 MBID | MusicBrainz |
| LABEL | 厂牌（如 侠客唱片 / Shock Records） | MusicBrainz |
| RELEASECOUNTRY | 发行国家/地区 | MusicBrainz |
| CATALOGNUMBER / BARCODE | 目录号 / 条码（查得到才写） | MusicBrainz |
| COMPOSER | 作曲（逐曲） | 公开资料核对 |
| LYRICIST | 作词（逐曲） | 公开资料核对 |
| ARRANGER | 编曲（逐曲，查到才写） | 公开资料核对 |

冲突规则：DATE 以匹配到的 MusicBrainz 版本日期为准；无匹配则用 CUE REM DATE；再无则用文件夹日期。

## 校验（验收标准）

1. **逐轨无损证明**：每轨解码 PCM MD5 == 源 WAV 对应区段的 PCM MD5
2. **总长一致**：切轨总样本数 == 整轨总样本数
3. **ffprobe 全量检查**：每轨为 flac / 44100Hz / 16bit / 2ch，标签齐全，内嵌封面存在
4. **元数据一致性抽查**：写入的补充字段与 `meta\*.json`、`reports\metadata-provenance.csv` 三处一致
5. 生成全库曲目清单 CSV（专辑/轨号/曲名/时长/文件名），供人工核对

## 容错

- 单张专辑失败隔离，不阻塞其余专辑；结束时汇总报告（成功/失败/原因）
- 某专辑/某曲的补充元数据查不到 → 对应字段留空，不阻塞转换，并在来源记录中标注「未查到」
- 预处理：先对每张整轨做全量解码检查（`ffmpeg -f null -`），解码报错的专辑单独标记
- 若 ffmpeg 无法正确解码某 APE：备选安装 Monkey's Audio 官方命令行 `mac.exe` 解码为 WAV 后再走同一流水线
- 若 mutagen 无法安装：备选 ffmpeg 原生 `-metadata` + `-disposition:v attached_pic` 写标签与封面（能力略弱，作为兜底）

## 安全（做种保证）

- `E:\陶喆` 只读访问；处理前后各记录一次源目录清单（相对路径/大小/mtime）并比对，确认零变化
- 所有写入仅发生在 `E:\音乐库\` 与 `E:\音乐库-工作区\`

## 实施里程碑

1. **M1** 环境准备：`pip install mutagen`；确认 ffmpeg
2. **M2** 元数据调研：MusicBrainz 逐张匹配 + 逐曲词曲作者资料核对 → `meta\*.json` + 来源记录
3. **M3** 脚本编写：`convert.py`（解析 CUE / 切轨 / 读 meta JSON 写标签 / 校验一体）
4. **M4** 单专辑试跑：`2002.08.09 - 黑色柳丁`（13 轨），产出后由用户验收
5. **M5** 批量处理其余 7 张
6. **M6** 全量校验 + 生成曲目清单 CSV + 汇总报告

## 非目标（YAGNI）

- 不做 ReplayGain / 响度均衡 / 重采样 / 转 WAV 副本
- 不做手机端同步方案（用户用 LocalSend 自行传输）
- 不指定播放器（标准 Vorbis 标签 + 内嵌封面通用于所有主流安卓播放器）
- 不修改、不补全源目录任何内容
