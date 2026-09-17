#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易数据 → 月度 CSV + 账户总览 CSV。

输入: 一个 Python 数据文件 (data.py), 内含:
  - MONTHS: [("202601", [(date, weekday, type, desc, amount), ...]), ...]
  - 可选 ACCOUNT_OVERVIEW: [[账户名, 类型, 金额, 备注], ...]
输出: 每月 YYYYMM.csv + 账户总览.csv (UTF-8 BOM)

用法:
    python build_csv.py <data.py路径> <输出目录>
"""
import argparse
import csv
import os
import sys


# ==================== 分类规则 (与 categories.md 一致) ====================
# 按顺序匹配: 精确 → 包含。新描述落入"其它"。
DESC2CAT = {
    # 交通
    "打车": "交通", "地铁": "交通", "公交": "交通", "出租车": "交通",
    "单车": "交通", "骑行": "交通",
    # 出差 (长途/差旅住宿)
    "高铁": "出差", "火车": "出差", "机票": "出差", "飞机": "出差",
    "动车": "出差", "退票费": "出差", "酒店": "出差", "住宿": "出差",
    # 餐饮
    "外卖": "餐饮", "火锅": "餐饮", "烧烤": "餐饮", "奶茶": "餐饮",
    "咖啡": "餐饮", "食堂": "餐饮", "快餐": "餐饮", "寿司": "餐饮",
    "汉堡": "餐饮", "炸鸡": "餐饮", "小吃": "餐饮", "面": "餐饮",
    "饺子": "餐饮", "早餐": "餐饮", "晚餐": "餐饮", "聚餐": "餐饮",
    "蛋糕": "餐饮", "甜点": "餐饮", "饭": "餐饮", "菜": "餐饮",
    # 汽车
    "加油": "汽车", "高速费": "汽车", "洗车": "汽车", "保养": "汽车",
    "车险": "汽车", "违章": "汽车", "罚单": "汽车", "停车费": "汽车",
    "停车": "汽车",
    # 住房
    "房租": "住房", "电费": "住房", "水费": "住房", "燃气": "住房",
    "物业": "住房", "宽带": "住房", "家具": "住房", "床垫": "住房",
    "窗帘": "住房", "电视柜": "住房", "空调": "住房", "热水器": "住房",
    "维修": "住房", "装修": "住房", "插排": "住房", "灯具": "住房",
    # 医疗
    "医院": "医疗", "药": "医疗", "挂号": "医疗", "体检": "医疗",
    "针灸": "医疗", "中药": "医疗", "维生素": "医疗", "保健品": "医疗",
    "眼镜": "医疗", "牙": "医疗", "疫苗": "医疗",
    # 服饰
    "衣服": "服饰", "裤子": "服饰", "鞋": "服饰", "袜子": "服饰",
    "帽子": "服饰", "包": "服饰", "首饰": "服饰", "手表": "服饰",
    "外套": "服饰", "皮带": "服饰",
    # 礼物 / 礼金
    "礼物": "礼物", "送花": "礼物", "玩偶": "礼物", "手办": "礼物",
    "贺卡": "礼物", "红包": "礼金", "份子": "礼金", "随礼": "礼金",
    # 通讯
    "话费": "通讯", "流量": "通讯", "手机壳": "通讯", "会员": "通讯",
    "订阅": "通讯", "视频": "通讯", "音乐": "通讯",
    # 办公 / 娱乐 / 日用 / 水果 / 教育
    "打印": "办公", "文具": "办公", "纸": "办公", "笔": "办公",
    "电影": "娱乐", "KTV": "娱乐", "游戏": "娱乐", "剧本杀": "娱乐",
    "密室": "娱乐", "演出": "娱乐", "演唱会": "娱乐", "游乐园": "娱乐",
    "麻将": "娱乐", "桌游": "娱乐", "门票": "娱乐",
    "纸巾": "日用", "牙膏": "日用", "牙刷": "日用", "洗发水": "日用",
    "洗衣液": "日用", "垃圾袋": "日用", "清洁": "日用",
    "水果": "水果", "苹果": "水果", "香蕉": "水果", "西瓜": "水果",
    "榴莲": "水果", "草莓": "水果", "果切": "水果", "车厘子": "水果", "蓝莓": "水果",
    "学费": "教育", "课程": "教育", "培训": "教育", "书": "教育", "教材": "教育",
    # 工资 (收入聚合: 工资/绩效/补贴/退税)
    "工资": "工资", "绩效": "工资", "补贴": "工资", "奖金": "工资",
    "加班费": "工资", "退税": "工资", "补助": "工资",
    # 兼职 / 红包 / 理财
    "兼职": "兼职", "外快": "兼职", "稿费": "兼职", "佣金": "兼职",
    "红包": "红包", "转账": "红包",
    "理财": "理财", "基金": "理财", "股票": "理财", "余额宝": "理财",
    "零钱通": "理财", "定投": "理财", "利息": "理财", "收益": "理财",
}


def get_category(desc, date=None, default="其它"):
    """描述 → 分类。先精确后包含。"""
    if desc in DESC2CAT:
        return DESC2CAT[desc]
    for k, v in DESC2CAT.items():
        if k in desc:
            return v
    return default


def to_csv_rows(rows, header=("日期", "星期", "类型", "分类", "描述", "金额")):
    out = []
    for date, weekday, ttype, desc, amount in rows:
        out.append([date, weekday, ttype, get_category(desc), desc, amount])
    return out


def write_csv(filepath, header, rows):
    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_py", help="数据文件 data.py 路径")
    ap.add_argument("out_dir", help="CSV 输出目录")
    args = ap.parse_args()

    sys.path.insert(0, os.path.dirname(os.path.abspath(args.data_py)))
    ns = {}
    with open(args.data_py, encoding="utf-8") as f:
        exec(compile(f.read(), args.data_py, "exec"), ns)

    MONTHS = ns.get("MONTHS", [])
    ACCOUNTS = ns.get("ACCOUNT_OVERVIEW", [])

    os.makedirs(args.out_dir, exist_ok=True)
    for ym, rows in MONTHS:
        write_csv(os.path.join(args.out_dir, f"{ym}.csv"),
                  ("日期", "星期", "类型", "分类", "描述", "金额"), to_csv_rows(rows))

    if ACCOUNTS:
        write_csv(os.path.join(args.out_dir, "账户总览.csv"),
                  ("账户名", "类型", "金额", "备注"), ACCOUNTS)

    # 统计摘要
    for ym, rows in MONTHS:
        inc = sum(r[4] for r in rows if r[4] > 0)
        exp = -sum(r[4] for r in rows if r[4] < 0)
        print(f"{ym}: 收入 {inc:.2f}, 支出 {exp:.2f}, 净 {inc - exp:.2f} ({len(rows)} 笔)")
    print("Done")


if __name__ == "__main__":
    main()
