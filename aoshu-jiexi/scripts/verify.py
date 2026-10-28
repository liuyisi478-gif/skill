"""小学奥数解析验算工具箱（仅标准库，Python 3.8+）。

用途：写完解析后，针对可计算的题目写几行调用代码，用程序结论核对解析中的答案。
原则：凡能穷举、能模拟、能递推的题，一律交给程序算，不靠心算。

四类常用场景与写法
------------------
1) 数列第 n 项 / 末位数字（先找最短循环节）
    import verify as V
    gen = (x for x in V.fib_stream())
    cyc = V.find_cycle(V.take(gen, 200), key=lambda x: x % 10)
    print(V.nth_by_cycle(cyc, 2022))        # -> 末位数字

2) "求所有满足条件的数"（必须穷举，防漏解）
    sols = V.all_of(lambda x: x % 7 == 3 and x % 5 == 1, range(1, 1000))
    print(sols, len(sols))

3) 计数题（把所有情况列出来再数）
    cnt = V.brute_count(lambda t: t[0] + t[1] == 10 and t[0] > t[1],
                        V.product(range(0, 11), repeat=2))

4) 答案代回检验（方程、行程、混合题都适用）
    V.check("追及时间", 12, 180 / (25 - 10))

也可以直接命令行跑自检：python verify.py
"""

from fractions import Fraction
from itertools import product, count
import math

# ---------- 基础 ----------

def frac(x, y=None):
    """精确分数：frac(3, 4) -> 3/4，避免小数误差。"""
    return Fraction(x, y) if y is not None else Fraction(x)


def take(gen, n):
    """取生成器的前 n 项。"""
    out = []
    for v in gen:
        out.append(v)
        if len(out) >= n:
            break
    return out


def fib_stream(a=1, b=1):
    """斐波那契型递推流（可按题意改初值与规则）。"""
    while True:
        yield a
        a, b = b, a + b


def digits(n):
    return [int(c) for c in str(abs(n))]


def digit_sum(n):
    return sum(digits(n))


# ---------- 周期 ----------

def find_cycle(seq, key=None, max_len=None):
    """在有限序列中找最短循环节，返回该循环节列表。

    找不到返回 None。用于"第 n 项末位""第 n 次出现"类题，
    先实测周期长度，不凭直觉假定为 4 或 10。
    """
    k = key or (lambda x: x)
    v = [k(x) for x in seq]
    n = len(v)
    limit = max_len or n // 2
    for p in range(1, limit + 1):
        ok = True
        for i in range(n - p):
            if v[i] != v[i + p]:
                ok = False
                break
        if ok:
            return v[:p]
    return None


def nth_by_cycle(cycle, n):
    """按循环节取第 n 项（n 从 1 开始）。"""
    return cycle[(n - 1) % len(cycle)]


# ---------- 枚举 ----------

def all_of(pred, iterable, limit=100000):
    """穷举所有满足条件的元素（防漏解）。"""
    out = []
    for i, x in enumerate(iterable):
        if i > limit:
            break
        if pred(x):
            out.append(x)
    return out


def brute_count(pred, iterable, limit=100000):
    """穷举计数。"""
    return len(all_of(pred, iterable, limit))


def product_all(*pools):
    """笛卡尔积的全排列/组合枚举。"""
    return product(*pools)


def multi_loop(lo, hi, cond, dims=2):
    """多维整数穷举：multi_loop(1, 20, lambda t: ..., 2)。"""
    return [t for t in product(range(lo, hi + 1), repeat=dims) if cond(t)]


# ---------- 检验 ----------

_FAILS = []


def check(name, got, want, tol=None):
    """核对解析中的数值与程序结论是否一致，打印 PASS/FAIL。"""
    if tol is None:
        ok = got == want
    else:
        ok = abs(float(got) - float(want)) <= tol
    print(("PASS" if ok else "FAIL"), name, "| 解析值:", got, "| 程序值:", want)
    if not ok:
        _FAILS.append(name)
    return ok


def check_true(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), name, detail)
    if not cond:
        _FAILS.append(name)
    return cond


def summary():
    if _FAILS:
        print("未通过项：", _FAILS)
        return False
    print("全部通过")
    return True


# ---------- 常用模型 ----------

def meet_time(v1, v2, dist):
    """相向而行相遇时间。"""
    return Fraction(dist, v1 + v2)


def chase_time(v_fast, v_slow, gap):
    """同向追及时间。"""
    return Fraction(gap, v_fast - v_slow)


def work_together(t1, t2):
    """两人合作完成时间（工程问题）。"""
    return 1 / (frac(1, t1) + frac(1, t2))


def lcm(a, b):
    return a * b // math.gcd(a, b)


if __name__ == "__main__":
    print("== 自检：斐波那契末位周期 ==")
    seq = take(fib_stream(), 200)
    cyc = find_cycle(seq, key=lambda x: x % 10)
    print("周期长度:", len(cyc), "循环节:", cyc)
    check("第2022项末位", nth_by_cycle(cyc, 2022), 6)

    print("== 自检：穷举求所有解 ==")
    sols = all_of(lambda x: x % 7 == 3 and x % 5 == 1, range(1, 1000))
    print("解:", sols[:10], "共", len(sols), "个")
    check_true("第1个解为31", sols[0] == 31, str(sols[:3]))

    print("== 自检：答案代回 ==")
    check("追及时间(秒)", 12, chase_time(25, 10, 180))

    print("== 自检：分数精确计算 ==")
    check("合作完成天数", work_together(6, 12), 4)

    summary()
