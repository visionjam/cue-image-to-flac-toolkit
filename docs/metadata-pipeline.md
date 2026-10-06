# 元数据完善管道（下载/组装库 → 完整标签）

面向 CUE 转换之后的专辑目录，或来自其他合法渠道音频：把音轨补齐为可长期使用的完整元数据
（词曲编曲、发行信息、MusicBrainz 标识、内嵌封面），并留下逐值可查的来源账。

四段式：**MB 对标 → 双源交叉核对 → 封面 → 带证明的写入**。

## 铁律

- **查到才写、查不到留空并注明**；绝不编造、不推断（人名尤其）。留空 ≠ 已处理——留空必须有一条
  「未查到/未核对」的来源行说明原因。
- **每值有据**：meta JSON 的每个非空补充值，都必须在 `reports/metadata-provenance.csv` 有一行
  带 URL 的来源；`check_meta.py` 强制该规则（无来源不落盘）。
- **双源交叉**：中文维基 + 百科类词条逐项比对词/曲/编曲；分歧**如实记录、按证据裁定**并写入注记，
  不得静默择优。
- **合并单元格陷阱**：百科曲目表的 rowspan 会让部分行"只显示一半署名"——先经
  `baike_tracklist.py parse` 展开再核对（该工具会把继承值填回每一行）。
- **写入可证明**：`tag_write.py` 对每个文件做四重核对——音频区逐字节不变、STREAMINFO MD5 不变、
  完整解码 PCM MD5 == STREAMINFO（16/24bit）、标签回读一致；任一失败即 [FAIL]。

## 流程

### 1. MusicBrainz 对标

```bash
python scripts/mb_lookup.py --artist "<艺术家>" --album "<专辑名>"     # 候选发行版
python scripts/mb_lookup.py --detail <release-mbid> --detail-out <path.json>   # 发行版详情
```

选版规则（写入 spec 的 note 留痕）：轨数与库内一致优先；CD+VCD 等多 medium 时取曲目所在
medium；同轨数时优先数据完整（厂牌/条码）与目标市场版本；库内文件时长与某版逐毫秒吻合可作判据。

### 2. 双源交叉核对

- 维基：读专辑条目（信息框 + 曲目表），提取作词/作曲/编曲与发行信息。
- 百科：`python scripts/baike_tracklist.py fetch <词条URL> <out.html>`（默认直连，需要时 `--proxy`），
  再 `parse <out.html>` 得到展开合并单元格后的曲目表。
- 逐项比对；**异体字/别名/大陆改名/日期多口径/署名分歧** 全部写进 spec 的 `note`/`date_note` 等字段。

### 3. 封面（双来源 + 目检）

```bash
python scripts/cover_fetch.py caa-rg <release-group-id> <base> --out-dir covers
python scripts/cover_fetch.py netease-search "<专辑名> <艺术家>" --out-dir covers
python scripts/cover_fetch.py img <picUrl> <base>-netease-orig.jpg --out-dir covers
```

两来源都抓 → 量尺寸 → **人工目检**（确认是该专辑官方封面，而非宣传照/翻唱）→ 取方形大图 →
必要时 `ffmpeg -i <orig> -q:v 2 <base>-<宽>.jpg` 转码为 JPEG。

### 4. 编译 + 写入 + 审计

```bash
python scripts/meta_build.py --spec <spec.json> --meta-dir meta \
       --prov-csv reports/metadata-provenance.csv --library-root <专辑父目录>
python scripts/tag_write.py album --dir <专辑目录> --meta meta/<专辑>.json \
       --cover covers/<base>-<宽>.jpg --artist "<艺术家>" --dry-run     # 先空转
python scripts/tag_write.py album ...                                        # 正式写入
python scripts/check_meta.py --all                                           # 无来源不落盘
```

- spec 结构与字段含义见 `scripts/meta_build.py` 头部注释；`medium` 用于多 medium 发行版。
- `tag_write.py` 支持 `files` 模式（逐文件 spec，适用于单曲/混合目录：无轨号文件按文件名匹配）。
- 尾部残留清理（下载截断类）用可选 `--trim-manifest`（CSV：relpath,tail_junk_bytes,junk_sha1，幂等）。

## 实战案例

`reports/周杰伦/`：21 个单元 / 191 个文件 的完整批次记录——

- `00-调研报告.md`：来源与可得性侦察
- `03-元数据进度.md`：逐单元台账（绑定发行版/封面/核对结果/分歧判例）
- `04-终版元数据报告.md`：终版报告（含伪 24bit 实锤、全部分歧判例、留白清单）

其来源账 `metadata-provenance.csv` 共 788 行：每个值一行、0 重复，可直接作为本管道输出的模板参考。

`reports/草东没有派对/`：3 个单元 / 24 个文件（2026-10-06，下载组装库全流程：取回 → 核验 → 元数据）——

- `00-调研报告.md`：来源与可得性侦察
- `01-取回与核验.md`：逐字节传输对照、金标准解码（含无内嵌签名与伪 24bit 两个特例的处理方式）
- `02-元数据终版报告.md`：绑定发行版 / 双源交叉 / 留白清单
- 该批次同时修正本管道两处口径缺口：`check_meta.py` 顶层键白名单补 `genre`；`meta_build.py` 为 `matched_title` 增补来源行（此前有值无行）
