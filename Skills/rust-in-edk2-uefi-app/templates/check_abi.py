#!/usr/bin/env python3
"""RpShim.h <-> ffi.rs 符号一致性校验。

背景：RpShim.h 与 rust/src/ffi.rs 是一对必须同步的手写声明。CLAUDE.md 只立了
"改一边必须改另一边" 的纪律，但没有任何工具保障 —— 加一个 rp_* 函数或 RP_*
常量而忘了改 ffi.rs，编译期未必报错（函数漏声明要等到链接期，常量漏声明则
根本不报错，只是值悄悄错位）。这个脚本把纪律变成可执行的检查。

约定（当前工程的映射规则）：
  - 函数：同名，rp_foo -> fn rp_foo
  - 常量：C 侧 RP_EV_PRESSED -> Rust 侧 EV_PRESSED（剥掉 RP_ 前缀），数值必须相等

用法：
    python tools/check_abi.py                    # 自动定位，有漂移则非零退出
    python tools/check_abi.py --verbose          # 连一致的符号也列出来
    python tools/check_abi.py --header X.h --ffi Y.rs --prefix MY_

默认布局（脚本放在 <repo>/tools/ 下时自动命中）：
    <repo>/RustPaintPkg/Application/RustPaint/RpShim.h
    <repo>/rust/src/ffi.rs

换项目时用 --header/--ffi 指定，用 --prefix 改常量前缀（C 侧 RP_FOO 对应
Rust 侧 FOO；若两侧同名，传 --prefix ''）。--fn-prefix 同理，默认 rp_。

退出码：0 = 一致；1 = 有漂移；2 = 文件找不到。
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_HEADER = os.path.join(ROOT, "RustPaintPkg", "Application", "RustPaint", "RpShim.h")
DEFAULT_FFI = os.path.join(ROOT, "rust", "src", "ffi.rs")

# C 侧不需要在 Rust 侧有对应物的宏（include guard 之类）
IGNORE_DEFINES = {"RP_SHIM_H_"}


def strip_c_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    return text


def strip_rs_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    return text


def parse_int(raw):
    """把 C/Rust 侧的字面量解析成 int；解析不了返回 None（跳过比较）。"""
    s = raw.strip().strip("()").strip()
    s = s.replace("U", "").replace("u", "").replace("L", "")
    s = s.rstrip("uUiIlL")
    try:
        return int(s, 0)
    except ValueError:
        return None


RE_C_DEFINE = re.compile(r"^#define\s+([A-Z][A-Z0-9_]*)\s+(.+?)\s*$", re.M)
RE_RS_CONST = re.compile(r"^pub const ([A-Z][A-Z0-9_]*)\s*:\s*(\w+)\s*=\s*([^;]+);", re.M)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Check that a C shim header and its Rust extern declarations agree.")
    ap.add_argument("--header", default=DEFAULT_HEADER, help="C header (the ABI contract)")
    ap.add_argument("--ffi", default=DEFAULT_FFI, help="Rust extern declaration file")
    ap.add_argument("--prefix", default="RP_",
                    help="constant prefix on the C side (stripped on the Rust side); "
                         "pass '' when both sides use the same names")
    ap.add_argument("--fn-prefix", default="rp_", help="function prefix, identical on both sides")
    ap.add_argument("--verbose", action="store_true", help="list every symbol, not just the summary")
    args = ap.parse_args(argv)

    header, ffi, prefix, fn_prefix = args.header, args.ffi, args.prefix, args.fn_prefix
    for path in (header, ffi):
        if not os.path.exists(path):
            print("missing: %s" % path)
            return 2

    with open(header, encoding="utf-8", errors="replace") as f:
        c_text = strip_c_comments(f.read())
    with open(ffi, encoding="utf-8", errors="replace") as f:
        rs_text = strip_rs_comments(f.read())

    # --- 函数：两侧同名 ---
    re_c_fn = re.compile(r"\b(%s[a-z0-9_]+)\s*\(" % re.escape(fn_prefix))
    re_rs_fn = re.compile(r"\bfn\s+(%s[a-z0-9_]+)\s*\(" % re.escape(fn_prefix))
    c_fns = set(re_c_fn.findall(c_text))
    rs_fns = set(re_rs_fn.findall(rs_text))

    # --- 常量：C 侧带 prefix，Rust 侧剥掉 prefix ---
    c_consts = {}
    for name, raw in RE_C_DEFINE.findall(c_text):
        if name in IGNORE_DEFINES:
            continue
        if prefix and not name.startswith(prefix):
            continue
        c_consts[name] = parse_int(raw)
    rs_consts = {}
    for name, _ty, raw in RE_RS_CONST.findall(rs_text):
        rs_consts[name] = parse_int(raw)

    def to_rust_name(name):
        return name[len(prefix):] if prefix and name.startswith(prefix) else name

    problems = []

    fn_only_c = sorted(c_fns - rs_fns)
    fn_only_rs = sorted(rs_fns - c_fns)
    if fn_only_c:
        problems.append("fn: declared in C but not Rust -> %s" % ", ".join(fn_only_c))
    if fn_only_rs:
        problems.append("fn: declared in Rust but not C -> %s" % ", ".join(fn_only_rs))

    const_missing = []
    const_mismatch = []
    for name, val in sorted(c_consts.items()):
        rs_name = to_rust_name(name)
        if rs_name not in rs_consts:
            const_missing.append("%s (expected %s on the Rust side)" % (name, rs_name))
            continue
        if val is None or rs_consts[rs_name] is None:
            continue
        if val != rs_consts[rs_name]:
            const_mismatch.append("%s = %s vs %s = %s" % (name, val, rs_name, rs_consts[rs_name]))
    if const_missing:
        problems.append("const: missing on Rust side -> %s" % ", ".join(const_missing))
    if const_mismatch:
        problems.append("const: value mismatch -> %s" % "; ".join(const_mismatch))

    rs_extra = sorted(n for n in rs_consts
                      if (prefix + n) not in c_consts and n not in c_consts)
    if rs_extra:
        problems.append("const: on Rust side only -> %s" % ", ".join(rs_extra))

    print("header      : %s" % header)
    print("ffi         : %s" % ffi)
    print("functions   : %d in C, %d in Rust, %d matched"
          % (len(c_fns), len(rs_fns), len(c_fns & rs_fns)))
    print("constants   : %d compared" % sum(1 for n in c_consts if to_rust_name(n) in rs_consts))
    print()
    if problems:
        for p in problems:
            print("[DRIFT] %s" % p)
        return 1
    print("OK: %s and %s agree" % (os.path.basename(header), os.path.basename(ffi)))
    if args.verbose:
        print("\n--- functions ---")
        for n in sorted(c_fns):
            print("  %s" % n)
        print("\n--- constants ---")
        for n in sorted(c_consts):
            print("  %-24s -> %-20s = %s" % (n, to_rust_name(n), c_consts[n]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
