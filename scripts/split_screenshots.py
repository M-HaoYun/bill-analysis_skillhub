#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
滚动截图切分工具（OCR 前置步骤）

把手机长截图（记账、豆瓣、微信等滚动截图）按固定高度切成 part，供逐片 OCR。
核心目标只有一个：**不让切分这一步引入任何可避免的信息损失**。

设计要点（每条都是踩过的坑，改动前先读完）
--------------------------------------------------------------------
1) 不做二次有损编码
   - JPEG 源：以 quality=95 + subsampling=0（4:4:4）保存。
     注意 Pillow 在 quality=95 时**默认仍是 4:2:0**（色度只有 1/4 分辨率），
     彩色小字、彩色图标、缩略图边缘会糊。必须显式 subsampling=0。
     实测同一张截图切片：默认 48.11dB / 4:2:0  →  subsampling=0 为 50.25dB / 4:4:4。
   - PNG 源：仍存 PNG（逐位无损）。PNG 截图（iOS/部分安卓）若被改存 JPEG，
     会凭空多一次有损编码（实测 PSNR 48.11dB 而非无损）。
2) 自然排序，而不是字典序
   sorted() 会得到 1,10,11,2,27,3 —— 时间线直接错乱。这里按数字段排序：
   1.jpg < 2.jpg < 10.jpg。哈希文件名（如 35edea778c.jpg）本身无序，
   排序只保证"稳定可复现"，真实顺序要靠图片内的日期字段。
3) 重叠步进防边界截断
   默认 chunk=2700 / step=2400（重叠 300px），避免某条记录正好被切在切口上
   而两片都残缺。重叠带来的重复条目由后续按业务唯一键去重。
4) 尾部碎片必须保留
   只要该片段**未被上一片覆盖**就必须保存。旧逻辑一律丢弃 <300px 的尾片，
   在 step==chunk（无重叠）时会静默丢数据 —— 实测尾部记录直接消失。
5) 切完做覆盖校验
   确认 [0, 原图高) 被切片完全覆盖；有缺口则大声报错并以退出码 2 结束。

用法
--------------------------------------------------------------------
    python split_screenshots.py <截图目录> <输出目录> [选项]

选项:
    --chunk 2700      每片高度（默认 2700）
    --step  2400      滑动步进，< chunk 即产生重叠（默认 2400）
    --quality 95      JPEG 质量（默认 95）
    --subsampling 0   JPEG 色度采样：0=4:4:4 文字安全（默认），2=4:2:0 体积小
    --format auto     输出格式 auto(跟随源格式) | jpg | png，默认 auto
    --only 12,13      只处理指定文件（文件名去扩展名，逗号分隔），用于补切
    --list            只列出将处理的文件与尺寸，不实际切分

输出:
    <输出目录>/<原文件名去扩展名>/p00.jpg(png), p01, ...
    每个原文件一个子目录，避免互相覆盖。
"""
import argparse
import os
import re
import sys

try:
    from PIL import Image, ImageOps

    # 超长滚动截图（高度可达 3 万+）会触发 DecompressionBomb 限制，显式放开
    Image.MAX_IMAGE_PIXELS = None
except ImportError:
    print("需要 Pillow: pip install pillow", file=sys.stderr)
    sys.exit(1)

SRC_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
MIN_TAIL = 300  # 小于此高度的尾片，仅在已被上一片完全覆盖时才丢弃


def natural_key(name):
    """自然排序键：1.jpg < 2.jpg < 10.jpg。纯数字/字母混排也安全（不会 TypeError）。"""
    stem = os.path.splitext(name)[0]
    key = []
    for part in re.split(r"(\d+)", stem):
        if part == "":
            continue
        if part.isdigit():
            key.append((1, int(part), ""))
        else:
            key.append((0, 0, part.lower()))
    return key


def plan_slices(h, chunk, step):
    """规划切片区间 [(top,bottom), ...]，保证完整覆盖 [0,h)。

    - 尾部碎片：只有在**已被上一片完全覆盖**时才丢弃（纯冗余）；
      未被覆盖的一律保留，无论多矮 —— 这是旧版丢数据的根因。
    """
    if step <= 0 or step > chunk:
        step = chunk
    spans = []
    top = 0
    while top < h:
        bottom = min(top + chunk, h)
        spans.append((top, bottom))
        if bottom >= h:
            break
        top += step
    # 纯冗余尾片（完全落在上一片内）才可丢弃
    if len(spans) > 1 and spans[-1][1] <= spans[-2][1]:
        spans.pop()
    return spans


def check_coverage(spans, h):
    """返回 (缺口列表, 重叠量列表)。缺口非空表示有像素没被任何切片覆盖。"""
    gaps, overlaps = [], []
    reach = 0
    for top, bottom in spans:
        if top > reach:
            gaps.append((reach, top))
        elif top < reach:
            overlaps.append(reach - top)
        reach = max(reach, bottom)
    if reach < h:
        gaps.append((reach, h))
    return gaps, overlaps


def pick_ext(src_name, fmt):
    if fmt == "jpg":
        return ".jpg"
    if fmt == "png":
        return ".png"
    return ".png" if src_name.lower().endswith((".png", ".webp", ".bmp")) else ".jpg"


def split_image(src_path, out_dir, chunk, step, quality, subsampling, fmt):
    img = Image.open(src_path)
    img = ImageOps.exif_transpose(img)  # 手机截图若带旋转标记，先摆正
    img = img.convert("RGB")
    w, h = img.size
    spans = plan_slices(h, chunk, step)
    os.makedirs(out_dir, exist_ok=True)
    ext = pick_ext(os.path.basename(src_path), fmt)
    for n, (top, bottom) in enumerate(spans):
        part = img.crop((0, top, w, bottom))
        out = os.path.join(out_dir, f"p{n:02d}{ext}")
        if ext == ".png":
            part.save(out, format="PNG", optimize=False)  # 逐位无损
        else:
            part.save(out, format="JPEG", quality=quality, subsampling=subsampling)
    gaps, overlaps = check_coverage(spans, h)
    return {"parts": len(spans), "w": w, "h": h, "ext": ext,
            "gaps": gaps, "overlaps": overlaps}


def main():
    ap = argparse.ArgumentParser(description="滚动截图切分工具（OCR 前置，避免二次有损编码）")
    ap.add_argument("src_dir", help="截图目录")
    ap.add_argument("out_dir", help="输出目录")
    ap.add_argument("--chunk", type=int, default=2700, help="每片高度（默认 2700）")
    ap.add_argument("--step", type=int, default=2400, help="滑动步进，< chunk 即重叠（默认 2400）")
    ap.add_argument("--quality", type=int, default=95,
                    help="JPEG 质量（默认 95；100 接近无损，体积约 +40%%）")
    ap.add_argument("--subsampling", type=int, default=0, choices=[0, 1, 2],
                    help="JPEG 色度采样，0=4:4:4 文字安全（默认），2=4:2:0")
    ap.add_argument("--format", default="auto", choices=["auto", "jpg", "png"],
                    help="输出格式，auto=跟随源格式（默认）")
    ap.add_argument("--only", default="", help="只处理指定文件（去扩展名，逗号分隔）")
    ap.add_argument("--list", action="store_true", help="只列出文件与尺寸，不切分")
    args = ap.parse_args()

    if not os.path.isdir(args.src_dir):
        print(f"目录不存在: {args.src_dir}", file=sys.stderr)
        return 1

    files = [f for f in os.listdir(args.src_dir) if f.lower().endswith(SRC_EXTS)]
    files.sort(key=natural_key)
    if args.only:
        want = {s.strip() for s in args.only.split(",") if s.strip()}
        files = [f for f in files if os.path.splitext(f)[0] in want]
        missing = want - {os.path.splitext(f)[0] for f in files}
        if missing:
            print(f"警告: --only 指定的文件未找到: {sorted(missing)}", file=sys.stderr)
    if not files:
        print(f"未找到图片: {args.src_dir}", file=sys.stderr)
        return 1

    if args.list:
        for f in files:
            with Image.open(os.path.join(args.src_dir, f)) as im:
                print(f"{f}  {im.size[0]}x{im.size[1]}  "
                      f"-> {len(plan_slices(im.size[1], args.chunk, args.step))} parts")
        return 0

    total, bad = 0, []
    for fname in files:
        stem = os.path.splitext(fname)[0]
        out = os.path.join(args.out_dir, stem)
        r = split_image(os.path.join(args.src_dir, fname), out, args.chunk,
                        args.step, args.quality, args.subsampling, args.format)
        total += r["parts"]
        ov = f"重叠 {sorted(set(r['overlaps']))}" if r["overlaps"] else "无重叠"
        print(f"{fname}: {r['w']}x{r['h']} -> {r['parts']} parts ({r['ext']}, {ov}) -> {out}")
        if r["gaps"]:
            bad.append((fname, r["gaps"]))
            print(f"  !! 覆盖缺口: {r['gaps']}  —— 有像素未被任何切片覆盖", file=sys.stderr)

    print(f"完成，共 {len(files)} 张图，{total} 个 part")
    if bad:
        print("存在覆盖缺口，请检查 --chunk/--step 参数", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
