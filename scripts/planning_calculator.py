# -*- coding: utf-8 -*-
"""
家庭财务规划通用测算脚本 — 资产配比 + 公积金/房贷还贷策略。

纯标准库，无第三方依赖。所有参数通过命令行输入，脚本本身不含任何个人数据。

子命令:
  loan      等额本金还款计划(月供/总利息/还清时间)
  prepay    提前还本两方式对比(年限不变减月供 vs 月还本不变缩年限)
  allocate  四笔钱资产分层建议(应急金/生育金/还贷池/权益仓)
  cashflow  月度现金流情景模拟(降薪/停发压测)

示例:
  # 贷款80万 30年 年利率2.6% 已还12期, 输出还款概要
  python planning_calculator.py loan --principal 800000 --years 30 --rate 0.026 --paid-months 12

  # 提前还15万: 对比"减月供"vs"缩年限"  (--monthly-gf 公积金月缴存, 用于看自付)
  python planning_calculator.py prepay --principal 800000 --years 30 --rate 0.026 --paid-months 12 --prepay 150000 --monthly-gf 2500

  # 资产分层: 总现金32万, 月支出1.2万, 应急8个月, 生育金4万, 股票1.5万, 房贷利率2.6%
  python planning_calculator.py allocate --cash 320000 --monthly-expense 12000 --emergency-months 8 --baby-fund 40000 --stock 15000 --loan-rate 0.026

  # 情景压测: 一组命名情景对比 (字段可缺省, 默认0)
  python planning_calculator.py cashflow --scenarios '{"现状":{"wage":9000,"perf":5000,"expense":12000,"mortgage":800},"绩效停发":{"wage":9000,"expense":12000,"mortgage":800}}'

作者: 通用工具 (无个人信息)
"""
import argparse
import json
import math
import sys


def monthly_rate(annual_rate: float) -> float:
    return annual_rate / 12.0


def equal_principal_total_interest(P: float, N: int, r_annual: float) -> float:
    """等额本金总利息 = r*(N*P - (P/N)*N*(N-1)/2)"""
    r = monthly_rate(r_annual)
    m = P / N
    return r * (N * P - m * N * (N - 1) / 2)


def monthly_schedule(P: float, N: int, r_annual: float, k: int) -> float:
    """第 k 期(1-based)月供"""
    r = monthly_rate(r_annual)
    m = P / N
    remain = P - m * (k - 1)
    return m + remain * r


def fmt(v: float) -> str:
    return f"{v:,.0f}"


def cmd_loan(args):
    P = args.principal
    N = args.years * 12
    r = args.rate
    m = P / N
    paid = min(args.paid_months, N)
    remain = P - m * paid
    remain_n = N - paid
    total_i = equal_principal_total_interest(P, N, r)
    remain_i = equal_principal_total_interest(remain, remain_n, r) if remain_n > 0 else 0.0
    print(f"贷款 {fmt(P)} 元 | {args.years} 年 | 年利率 {r*100:.2f}% | 等额本金")
    print(f"月还本金: {fmt(m)} 元 | 首月供: {fmt(monthly_schedule(P,N,r,1))} | 末月供: {fmt(monthly_schedule(P,N,r,N))}")
    print(f"总利息: {fmt(total_i)} 元 (本息合计 {fmt(P+total_i)})")
    if paid > 0:
        print(f"已还 {paid} 期 | 剩余本金: {fmt(remain)} | 剩余 {remain_n} 期 ({remain_n/12:.1f} 年)")
        print(f"剩余利息: {fmt(remain_i)} 元")
    # 前12期明细
    print("\n前12期月供(每月递减):")
    row = "  ".join(fmt(monthly_schedule(P, N, r, k)) for k in range(1, min(13, N + 1)))
    print(" " + row)
    # 可选: 输出每一年末剩余
    if args.detail:
        print("\n每12期末节点:")
        for k in range(12, N + 1, 12):
            print(f"  第{k:>3}期后 剩余本金 {fmt(P - m*k):>10}")


def cmd_prepay(args):
    P = args.principal
    N = args.years * 12
    r = args.rate
    m = P / N
    paid = min(args.paid_months, N)
    remain = P - m * paid
    remain_n = N - paid
    gf = getattr(args, "monthly_gf", 0.0) or 0.0

    print(f"基准(不还): 剩余本金 {fmt(remain)} | 剩余 {remain_n} 期 | "
          f"剩余利息 {fmt(equal_principal_total_interest(remain, remain_n, r))}")
    if gf:
        print(f"  首月供 {fmt(monthly_schedule(remain, remain_n, r, 1))} - 公积金{fmt(gf)} = "
              f"自付 {fmt(monthly_schedule(remain, remain_n, r, 1) - gf)}")
    print()

    A = args.prepay
    P2 = remain - A
    if P2 <= 0:
        print(f"提前还 {fmt(A)} ≥ 剩余本金, 直接结清.")
        return

    # 方式一: 年限不变, 月供降低
    m1 = P2 / remain_n
    i1 = equal_principal_total_interest(P2, remain_n, r)
    f1 = m1 + P2 * monthly_rate(r)
    # 方式二: 月还本不变, 缩短年限
    n2 = math.ceil(P2 / m)
    m2 = P2 / n2
    i2 = equal_principal_total_interest(P2, n2, r)
    f2 = m2 + P2 * monthly_rate(r)

    print(f"提前还本 {fmt(A)} 元后 剩余本金 {fmt(P2)}")
    print("=" * 64)
    print("方式一: 年限不变, 月供降低")
    print(f"  剩余 {remain_n} 期 ({remain_n/12:.1f}年) | 首月供 {fmt(f1)} (递减 {fmt(m1*r)}/月)")
    print(f"  剩余总利息: {fmt(i1)}")
    if gf:
        print(f"  公积金覆盖后自付(首月): {fmt(f1 - gf)}")
    print("=" * 64)
    print("方式二: 月还本不变, 缩短年限")
    print(f"  剩余 {n2} 期 ({n2/12:.1f}年, 提前 {(remain_n-n2)/12:.1f} 年还清) | 首月供 {fmt(f2)}")
    print(f"  剩余总利息: {fmt(i2)}")
    if gf:
        print(f"  公积金覆盖后自付(首月): {fmt(f2 - gf)}")
    print("=" * 64)
    print(f"对比: 缩年限比减月供多省利息 {fmt(i1 - i2)} 元")
    print(f"      代价: 首月供多 {fmt(f2 - f1)} 元/月")
    if gf and gf >= f2:
        print(f"      结论: 公积金月缴存 {fmt(gf)} 可完全覆盖缩年限月供 -> 选缩短年限(零现金压力)")
    else:
        print(f"      结论: 缩年限月供高于公积金, 若现金流紧则选减月供; 扛得住则缩年限更省")


def cmd_allocate(args):
    cash = args.cash
    exp = args.monthly_expense
    em = args.emergency_months
    baby = args.baby_fund
    stock = args.stock
    loan_r = args.loan_rate
    dep_r = args.deposit_rate

    total = cash + stock
    emergency = exp * em
    safety = emergency + baby
    excess = cash - safety
    if excess < 0:
        excess = 0.0

    print(f"总资产: 现金 {fmt(cash)} + 权益 {fmt(stock)} = {fmt(total)}")
    print(f"月现金支出 {fmt(exp)} x {em} 个月 -> 应急金 {fmt(emergency)}")
    print(f"安全线(应急+生育金) = {fmt(safety)}")
    print(f"可动现金 {fmt(cash)} - 安全线 {fmt(safety)} = 超额 {fmt(excess)}")
    print()
    print("四笔钱分层:")
    print(f"  ① 应急金    {fmt(emergency):>10}  ({emergency/total*100:.1f}%)  货基/活期, 绝对不动")
    print(f"  ② 生育/计划 {fmt(baby):>10}  ({baby/total*100:.1f}%)  定存/国债, 到期对齐用钱时点")
    repay = min(excess, cash - safety)
    print(f"  ③ 还贷池    {fmt(repay):>10}  ({repay/total*100:.1f}%)  超额优先还贷 = 锁 {loan_r*100:.2f}% 无风险")
    print(f"  ④ 权益仓    {fmt(stock):>10}  ({stock/total*100:.1f}%)  只放闲钱, 设上限")
    print()
    if excess <= 0:
        print(f"提示: 超额为 0, 现金流偏紧 -> 先保流动性, 暂缓还贷/投资, 考虑压缩支出")
    elif loan_r > dep_r:
        print(f"提示: 贷款利率 {loan_r*100:.2f}% > 存款 {dep_r*100:.2f}% -> 超额现金还贷优于存银行")
        print(f"      可还金额约 {fmt(excess)} (需自留一定机动, 不必一次还满)")
    else:
        print(f"提示: 存款利率 {dep_r*100:.2f}% >= 贷款利率 {loan_r*100:.2f}% -> 不必急于还贷")
    print(f"权益占比 {stock/total*100:.1f}% | 参考: 生命周期法则(100-年龄)需前提成立才可用, 现金流脆弱期 0-10% 合理")


def cmd_cashflow(args):
    scenarios = json.loads(args.scenarios)
    print(f"{'情景':<16}{'收入':>10}{'支出':>10}{'月净':>10}  年化")
    print("-" * 66)
    for name, p in scenarios.items():
        inc = (p.get("wage", 0) + p.get("perf", 0) + p.get("subsidy", 0)
               + p.get("finance", 0) + p.get("extra_inc", 0))
        exp = (p.get("expense", 0) + p.get("mortgage", 0)
               + p.get("extra_exp", 0))
        net = inc - exp
        flag = "  <-- 转负!" if net < 0 else ""
        print(f"{name:<16}{fmt(inc):>10}{fmt(exp):>10}{fmt(net):>10}  {fmt(net*12):>9}{flag}")
    print("-" * 66)
    print("字段: wage工资 perf绩效/奖金 subsidy补贴 finance理财 extra_inc其它收入")
    print("      expense日常支出 mortgage房贷自付 extra_exp其它支出 (单位: 元/月)")


def main():
    ap = argparse.ArgumentParser(description="家庭财务规划测算(资产配比+还贷策略), 纯标准库")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_loan = sub.add_parser("loan", help="等额本金还款计划")
    p_loan.add_argument("--principal", type=float, required=True)
    p_loan.add_argument("--years", type=int, default=30)
    p_loan.add_argument("--rate", type=float, default=0.026)
    p_loan.add_argument("--paid-months", type=int, default=0)
    p_loan.add_argument("--detail", action="store_true")
    p_loan.set_defaults(func=cmd_loan)

    p_pre = sub.add_parser("prepay", help="提前还本两方式对比")
    p_pre.add_argument("--principal", type=float, required=True)
    p_pre.add_argument("--years", type=int, default=30)
    p_pre.add_argument("--rate", type=float, default=0.026)
    p_pre.add_argument("--paid-months", type=int, default=0)
    p_pre.add_argument("--prepay", type=float, required=True)
    p_pre.add_argument("--monthly-gf", type=float, default=0.0, help="公积金月缴存(看自付)")
    p_pre.set_defaults(func=cmd_prepay)

    p_al = sub.add_parser("allocate", help="四笔钱资产分层")
    p_al.add_argument("--cash", type=float, required=True, help="可动现金总额")
    p_al.add_argument("--monthly-expense", type=float, required=True)
    p_al.add_argument("--emergency-months", type=int, default=6)
    p_al.add_argument("--baby-fund", type=float, default=0.0)
    p_al.add_argument("--stock", type=float, default=0.0)
    p_al.add_argument("--loan-rate", type=float, default=0.026)
    p_al.add_argument("--deposit-rate", type=float, default=0.01)
    p_al.set_defaults(func=cmd_allocate)

    p_cf = sub.add_parser("cashflow", help="情景现金流压测")
    p_cf.add_argument("--scenarios", type=str, required=True, help='JSON: {"名":{"wage":..,"expense":..,...}}')
    p_cf.set_defaults(func=cmd_cashflow)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
