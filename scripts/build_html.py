#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易数据 → 单文件 HTML 收支分析工作台。

输入: 一个 Python 数据文件 (data.py), 内含:
  - MONTHS: [("202601", [(date, weekday, type, desc, amount), ...]), ...]
  - 可选 ACCOUNT_OVERVIEW: [[账户名, 类型, 金额, 备注], ...]
  - 可选 DB_IDS: {"transactions": "...", "accounts": "..."} (资料库联动用)
模板: assets/workspace_template.html (含 __EMBEDDED_DATA__ / __DB_IDS__ / __DATA_VERSION__ 占位符)

用法:
    python build_html.py <data.py路径> <输出HTML路径> [--template assets/workspace_template.html]
"""
import argparse
import json
import os
import sys
import time

from build_csv import get_category  # 复用分类逻辑


def to_tx_list(rows, prefix):
    out = []
    for i, (date, weekday, ttype, desc, amount) in enumerate(rows):
        out.append({
            "id": f"{prefix}_{i:04d}",
            "date": date,
            "weekday": weekday,
            "type": ttype,
            "category": get_category(desc, date=date),
            "desc": desc,
            "amount": amount,
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_py", help="数据文件 data.py 路径")
    ap.add_argument("out_html", help="输出 HTML 路径")
    ap.add_argument("--template", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                       "..", "assets", "workspace_template.html"))
    args = ap.parse_args()

    sys.path.insert(0, os.path.dirname(os.path.abspath(args.data_py)))
    ns = {}
    with open(args.data_py, encoding="utf-8") as f:
        exec(compile(f.read(), args.data_py, "exec"), ns)

    MONTHS = ns.get("MONTHS", [])
    ACCOUNTS = ns.get("ACCOUNT_OVERVIEW", [])
    DB_IDS = ns.get("DB_IDS", {})

    all_tx = []
    for ym, rows in MONTHS:
        all_tx.extend(to_tx_list(rows, "t" + ym))
    all_tx.sort(key=lambda x: (x["date"], -x["amount"]))

    with open(args.template, encoding="utf-8") as f:
        template = f.read()

    final = template.replace("__EMBEDDED_DATA__", json.dumps(all_tx, ensure_ascii=False))
    final = final.replace("__DB_IDS__", json.dumps(DB_IDS, ensure_ascii=False))
    final = final.replace("__DATA_VERSION__", json.dumps(time.strftime("%Y%m%d%H%M%S")))
    # 账户数据可注入模板 (模板若支持)
    if "__ACCOUNT_OVERVIEW__" in final:
        final = final.replace("__ACCOUNT_OVERVIEW__", json.dumps(ACCOUNTS, ensure_ascii=False))

    with open(args.out_html, "w", encoding="utf-8") as f:
        f.write(final)

    print(f"生成 {args.out_html}, 共 {len(all_tx)} 笔交易, 版本 {time.strftime('%Y%m%d%H%M%S')}")


if __name__ == "__main__":
    main()
