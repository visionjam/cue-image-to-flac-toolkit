# 陶喆全集分轨 FLAC 音乐库 — 最终交付报告

日期：**2026-10-04**　|　工作区：`E:\音乐库-工作区`　|　成品目录：`E:\音乐库\陶喆\`　|　源目录 `E:\陶喆` 全程只读

---

## 1. 成果概述

- **8 张专辑 / 107 轨**，全部为单轨 FLAC（无损）。
- **总时长 7:02:01**（25,321 秒；由 `reports/tracklist.csv` 逐轨 duration 求和）。
- **总大小 2.6 G**（`du -sh "E:/音乐库/陶喆"`；精确 2,764,248,392 字节 ≈ 2.57 GiB）。
- 共 115 个文件 = 107 个 `.flac` + 8 个 `cover.jpg`（每张专辑目录各 1 张封面）。
- 来源：源目录 8 张整轨（7 张 APE + 1 张 FLAC），GBK 编码 CUE 切轨 → FLAC 分轨，标签与封面全部内嵌。

## 2. 逐专辑统计

| 专辑目录 | 轨数 | 总时长 | 目录大小（du -sh） |
|---|---|---|---|
| 1997 - David Tao | 15 | 0:50:31 | 301M |
| 1999 - I'm OK | 13 | 0:52:21 | 336M |
| 2002 - 黑色柳丁 | 13 | 0:53:08 | 334M |
| 2003 - ULTRASOUND乐之路1997-2003 | 13 | 0:51:26 | 304M |
| 2005 - 太平盛世 | 13 | 0:49:29 | 300M |
| 2006 - 太美丽 | 13 | 0:49:46 | 325M |
| 2009 - 69乐章 | 14 | 1:02:16 | 401M |
| 2013 - 再见你好吗 | 13 | 0:53:04 | 339M |
| **合计** | **107** | **7:02:01** | **2.6G** |

数据来源：轨数与时长由 `reports/tracklist.csv`（107 数据行）按专辑聚合；目录大小来自 `du -sh`。每轨一并产出文件名 `NN - 曲名.flac`（见 tracklist.csv 的 `file` 列）。

## 3. 校验结论（全库终验，2026-10-04）

命令：`cd "E:/音乐库-工作区" && python scripts/verify.py --all`（退出码 **0**；全库重解码 8 个源整轨 + 107 个成品，含首张黑色柳丁）

```
[OK ] 1997.12.06 - DAVID.TAO (15 tracks)
[OK ] 1999.12.10 - I'm.OK (13 tracks)
[OK ] 2002.08.09 - 黑色柳丁 (13 tracks)
[OK ] 2003.08.08 - ULTRASOUND乐之路1997-2003 (13 tracks)
[OK ] 2005.01.21 - 太平盛世 (13 tracks)
[OK ] 2006.01.21 - 太美丽 (13 tracks)
[OK ] 2009.08.21 - 69乐章 (14 tracks)
[OK ] 2013.06.11 - 再见你好吗 (13 tracks)
tracklist -> E:\音乐库-工作区\reports\tracklist.csv
report    -> E:\音乐库-工作区\reports\verification-2026-10-04-2355.md
```

- **逐轨 PCM MD5：107/107 全通过**。方法：重解源整轨 → 按 CUE 采样点切段计算 PCM MD5，与成品 FLAC 解码 PCM MD5 逐轨比对，全部一致（`verification-2026-10-04-2355.md`：专辑 8，失败 0，无任何 problem 行）。
- **样本数一致性**：每轨成品解码帧数与 CUE 段长逐轨一致，且 8 张专辑总样本数与源整轨完全相等（校验脚本内建断言，8/8 通过）。
- **格式 44.1kHz / 16bit / 2ch**：verify 的 ffprobe 检查全部通过；另以 ffprobe 独立复扫 107 个成品（`codec_name=flac, sample_rate=44100, channels=2, bits_per_raw_sample=16`），**0 个不合格**。
- **标签/封面全过**：107 轨均含 ARTIST、ALBUMARTIST、ALBUM、TITLE、TRACKNUMBER、TRACKTOTAL 必需标签与内嵌封面图；8 个专辑目录均有 `cover.jpg`；`MUSICBRAINZ_ALBUMID` 及 COMPOSER/LYRICIST/ARRANGER 值与 `meta/*.json` 逐轨一致。
- 附带：107 轨 PCM MD5 **无重复**（无错切/重复轨）。

`reports/tracklist.csv`：`wc -l` = **108 行**（表头 1 + 数据 **107** 行）。

## 4. 元数据覆盖（107 轨口径）

| 字段 | 覆盖 | 覆盖率 |
|---|---|---|
| composer（作曲） | 100 / 107 | 93.5% |
| lyricist（作词） | 98 / 107 | 91.6% |
| arranger（编曲） | 80 / 107 | 74.8% |
| 专辑级 MusicBrainz 信息 | 8 / 8 专辑 | 100% |

- 合计 278 / 321 逐轨字段有值（未查到 43 处，见 §7）。
- 专辑级字段 10 项（release_id、release_group_id、artist_id、label、country、catalog_number、barcode、matched_title、date、year）在 `reports/metadata-provenance.csv` 中各 8 行、全部有值。
- 数字来源：`reports/metadata-provenance.csv`（共 401 数据行 = 逐轨 107×3 + 专辑级 10×8）实际行数统计；补齐过程见 `reports/metadata-fill-log-2026-10-04.md`（本轮 +59 处：composer +2、lyricist +5、arranger +52；另有 #9 作词更正 1 处）。

## 5. 做种安全（源目录零改动证明）

```
$ python scripts/source_manifest.py after "E:/陶喆" "E:/音乐库-工作区/reports/source-manifest-after.txt"
manifest -> E:\音乐库-工作区\reports\source-manifest-after.txt (24 files)      # 退出码 0

$ python scripts/source_manifest.py compare "E:/陶喆" "E:/音乐库-工作区/reports"
NO CHANGES: source untouched                                                   # 退出码 0
```

清单口径：源目录 24 个文件（8 专辑 × CUE + 整轨音频 + cover.jpg）的相对路径、字节大小、`mtime_ns`（纳秒）。开工前（`reports/source-manifest-before.txt`）与完工后逐条比对**完全一致**——源目录自始至终只读，做种种子未受任何影响。

## 6. 交付指引

1. 成品位置：**`E:\音乐库\陶喆\`**（8 个专辑子目录，命名 `年份 - 专辑名`）。
2. 传输：用 **LocalSend** 把 `E:\音乐库\陶喆\` 整个目录发送到手机（PC 与手机同一局域网；若手机端收到的是压缩包需先解压）。
3. 手机端建议存放路径：**`Music/陶喆/`**（保持 8 个专辑子目录结构），以便媒体扫描器归类。
4. 播放：任何标准播放器（Poweramp、Musicolet、foobar2000 等）直接扫描识别即可——单轨 FLAC 含完整标签与内嵌封面，**无需 CUE**。

## 7. 遗留与备注

- **未查到字段 43 处**（321 − 278）：composer 7、lyricist 9、arranger 27。集中在：1997 口白/纯音乐 4 轨（#1/#3/#11/#15，词曲未署名）、1999 首尾轨（#1 Doxology、#13 Amen）、2002 新闻剪辑轨 #2、2003 编曲（#1–#4/#6–#13，共 12 轨）、2013 编曲（#3–#13，共 11 轨）与 #1 作词、2005 #13 传统圣诗编曲、2009 #1 作词。这些位置**保留空值而未用专辑级「全碟声明」外推**（证据强度不足）；若日后查到逐轨署名，可单字段回补，属可逆操作。
- **来源级别说明（一句话）**：所有已填字段都在 `reports/metadata-provenance.csv` 中登记单一 canonical URL 并按证据强度分级（【逐轨】>【合并】>【全碟】，同强度取百度、无则维基），专辑级 MusicBrainz 信息单列 10 个专辑级字段（8/8 有值）——即「逐轨 + 专辑级」两级来源，全部可溯源，无自动推断值。
- 已知边界：元数据核对以中文维基/百度百科为主（详见 `reports/source-crosscheck-2026-10-04.md` §6 局限说明），未纳入 mojim/en.wikipedia；百度对脚本反爬，人工复核时可用 `wapbaike.baidu.com` 同 id 访问。
- 证据文件索引：`reports/tracklist.csv`（逐轨清单+MD5）、`reports/verification-2026-10-04-2355.md`（终验报告）、`reports/source-manifest-before.txt` / `source-manifest-after.txt`（源零改动）、`reports/metadata-provenance.csv`、`reports/metadata-fill-log-2026-10-04.md`、`reports/source-crosscheck-2026-10-04.md`。
