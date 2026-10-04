# 老专辑封面处理经验（clean cover handling）

处理老旧数字音乐资源（尤其华语 CD 时代的整轨 + CUE 资源）时，封面常常是质量最差的一环：资源包里自带的 `cover.jpg` 多是当年从百科/商城随手扒的图——**带水印、带贴纸、缩略图级分辨率**。本文是这套工具链在处理首個数据集时踩出来的完整经验，供遇到同类问题的人参考。

## 第一步：先判断「原始文件里有没有封面」

**不要假设音频文件内嵌了封面。** 老资源里很常见的情况是：整轨 APE 只带了播放器（如 foobar2000）写入的播放统计标签，封面根本不在文件里。

```python
# APE（APEv2 标签）
import mutagen.apev2
tag = mutagen.apev2.APEv2("album.ape")
print([str(k) for k in tag.keys()])   # 常见结果：只有 First_played / Last_played / Play_counter

# FLAC（PICTURE 块）
import mutagen.flac
f = mutagen.flac.FLAC("album.flac")
print(len(f.pictures))                # 0 = 没有内嵌封面
```

`ffprobe album.ape` 只输出一条 `ape` 音频流（无 `attached_pic`）同样说明没有内嵌图。

## 第二步：干净封面的来源优先级

按「首选中位质量 + 无水印」排序的实践经验：

### 1. Cover Art Archive（官方关联，首选之一）

- 入口：`https://coverartarchive.org/release/<MusicBrainz-Release-ID>`（返回 JSON）
- 取图：JSON 里 `images[].front == true` 的条目，`thumbnails.large`（通常 1200px 内）或 `image` 原图
- 注意：
  - 该站托管在 archive.org 体系，部分网络环境需通过常规代理访问；
  - 个别发行版服务端会持续返回 500——**试试同发行组（release-group）下的其他版本**，常有姐妹版带图；
  - 社区上传图质量参差：偶见「商品图水印（如 yesasia）」或带实体贴纸的扫描，**必须目检**。

### 2. 网易云音乐公开检索接口（华语资源命中率很高）

- 搜索：`https://music.163.com/api/search/get/web?s=<关键词>&type=10&limit=10`（type=10 = 专辑）
- 取图：结果里 `picUrl + "?param=800y800"` 可请求放大版
- 优点：老华语专辑覆盖好、图多无水印、常见 800×800 或更大
- 注意：
  - **必须核对结果**：按 `album.name` + `artist.name` + 曲目数三重确认，搜索可能返回翻唱/现场/合辑；
  - 返回内容可能与扩展名不符（实测遇到过 PNG；必要时按魔数判断并转码，见下文）。

### 3. Discogs（结构化好、免鉴权可读，但质量看运气）

- 入口：`https://api.discogs.com/releases/<Release-ID>`（公开数据无需 token，带 User-Agent 即可），`images[]` 里 `type == "primary"` 为主图
- 特点：分辨率常 600px 上下；**扫描图比例高**——常见问题：实拍塑料盒（反光、盒边）、光盘条形码/价格贴纸、扫描边缘色带
- 定位：保底来源；其 `secondary` 图里偶尔能找到更好的正面扫描

## 第三步：识图检查清单（逐张肉眼过）

拿到候选后按顺序检查：

1. **水印**：边角找「Baidu 百科」「yesasia」「豆瓣」等字样
2. **贴纸**：宣传贴纸、价格签、条码（在印刷层外的都算）
3. **实体痕迹**：塑料盒反光、扫描边缘、裁切是否与官方构图一致（有的源会过度裁切）
4. **分辨率**：<500px 的缩略图级别不建议用于内嵌（手机播放时明显发虚）

## 第四步：应用替换（目录图 + 内嵌图都要换）

```python
from pathlib import Path
from mutagen.flac import FLAC, Picture
import pathlib

data = Path("new_cover.jpg").read_bytes()
assert data[:3] == b"\xff\xd8\xff", "先确认是 JPEG（PNG/WebP 需先转码）"
# PNG/WebP → JPEG（q2 视觉无损）：
#   ffmpeg -v error -y -i in.png -q:v 2 out.jpg

for f in sorted(Path("专辑目录").glob("*.flac")):
    a = FLAC(str(f))
    a.clear_pictures()
    p = Picture(); p.type = 3; p.mime = "image/jpeg"; p.desc = "Cover"; p.data = data
    a.add_picture(p)
    a.save()
```

同时把同一张图覆盖到专辑目录的 `cover.jpg`（有的播放器/管理软件读目录图）。

## 第五步：证明「只换了图，没碰音频」

mutagen 重写 FLAC 的元数据块不触碰音频帧，但**要证明而不是假设**：

- 替换前后对比任一轨的解码 PCM MD5（本项目的 `tracklist.csv` 就存了全部逐轨值）；
- 或直接重跑本工具链的 `verify.py --all`——它以「重新解码源文件逐轨比对」为口径，8 张专辑/107 轨全绿即证明音频逐字节未变。

## 合规提醒

以上操作仅应用于**你自行合法获取**的音频文件，用于个人库的整理与显示；封面图片版权归各权利人，请勿再分发图片本身。抓取公开接口时保持基本礼节（请求间隔 ≥1s、不批量轰炸）。
