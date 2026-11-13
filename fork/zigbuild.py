#!/usr/bin/env python3
"""Compile-and-link check of Main_MiSTer for the MiSTer (ARMv7 hard-float, glibc 2.31)
using zig as the cross compiler. The release binary is built by the fork's GitHub
Actions workflow with the official ARM GCC toolchain; this is for checking a patch.

usage: zigbuild.py <Main_MiSTer source dir> <build dir>
"""
import concurrent.futures as cf
import glob
import os
import subprocess
import sys

SRC, OUT = (os.path.abspath(a) for a in sys.argv[1:3])
ZIG = [sys.executable, "-m", "ziglang"]
TARGET = ["-target", "arm-linux-gnueabihf.2.31", "-mcpu=cortex_a9"]
INCLUDE = ["-I" + os.path.join(SRC, p) for p in (
    ".", "lib/libco", "lib/miniz", "lib/md5", "lib/lzma", "lib/zstd/lib",
    "lib/libchdr/include", "lib/bluetooth", "lib/serial_server/library")]
DEFS = ["-D_7ZIP_ST", '-DPACKAGE_VERSION="1.3.3"', "-DHAVE_LROUND", "-DHAVE_STDINT_H",
        "-DHAVE_STDLIB_H", "-DHAVE_SYS_PARAM_H", "-DENABLE_64_BIT_WORDS=0",
        "-D_FILE_OFFSET_BITS=64", "-D_LARGEFILE64_SOURCE", '-DVDATE="261113"']
WARN = ["-w"]   # upstream builds with gcc; clang's extra warnings are noise here

def rel(p):
    return os.path.relpath(p, SRC)

c_src = (glob.glob(SRC + "/*.c") + glob.glob(SRC + "/lib/miniz/*.c") + glob.glob(SRC + "/lib/md5/*.c")
         + glob.glob(SRC + "/lib/lzma/*.c") + glob.glob(SRC + "/lib/zstd/lib/common/*.c")
         + glob.glob(SRC + "/lib/zstd/lib/decompress/*.c") + glob.glob(SRC + "/lib/libchdr/*.c")
         + [SRC + "/lib/libco/arm.c"])
cpp_src = (glob.glob(SRC + "/*.cpp") + glob.glob(SRC + "/lib/serial_server/library/*.cpp")
           + glob.glob(SRC + "/support/*/*.cpp"))

GCC_ONLY = {  # gcc folds these at compile time, clang doesn't; compile a copy with const
    "support/n64/n64_joy_emu.cpp": ("static constexpr float MAX_DIST", "static const float MAX_DIST"),
}

def rel_name(copy):
    """support/n64/x.cpp.clang.cpp (in OUT) -> support/n64/x.cpp"""
    return os.path.relpath(copy, OUT)[:-len(".clang.cpp")]

def compile_one(path):
    obj = os.path.join(OUT, rel(path) + ".o")
    os.makedirs(os.path.dirname(obj), exist_ok=True)
    if rel(path) in GCC_ONLY:
        a, b = GCC_ONLY[rel(path)]
        copy = os.path.join(OUT, rel(path) + ".clang.cpp")
        with open(path) as f, open(copy, "w") as g:
            g.write('#line 1 "%s"\n' % path + f.read().replace(a, b))
        path = copy
        INCS = INCLUDE + ["-I" + os.path.dirname(os.path.join(SRC, rel_name(copy)))]
    else:
        INCS = INCLUDE
    if path.endswith(".c"):
        cmd = ZIG + ["cc"] + TARGET + ["-std=gnu99", "-O2"] + WARN + INCS + DEFS + ["-c", path, "-o", obj]
    else:
        cmd = ZIG + ["c++"] + TARGET + ["-std=gnu++14", "-O2"] + WARN + INCS + DEFS + ["-c", path, "-o", obj]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return path, obj, r.returncode, r.stderr

# logo.png is linked in as _binary_logo_png_start/_end (upstream uses ld -b binary)
asm = os.path.join(OUT, "logo_png.S")
os.makedirs(OUT, exist_ok=True)
with open(asm, "w") as f:
    f.write('.section .rodata\n.global _binary_logo_png_start\n.global _binary_logo_png_end\n'
            '_binary_logo_png_start:\n.incbin "%s"\n_binary_logo_png_end:\n' % os.path.join(SRC, "logo.png"))

objs, failed = [], []
with cf.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as ex:
    for path, obj, rc, err in ex.map(compile_one, c_src + cpp_src):
        if rc:
            failed.append((rel(path), err))
        else:
            objs.append(obj)
r = subprocess.run(ZIG + ["cc"] + TARGET + ["-c", asm, "-o", asm + ".o"], capture_output=True, text=True)
if r.returncode:
    failed.append(("logo_png.S", r.stderr))
objs.append(asm + ".o")

if failed:
    for name, err in failed:
        print("COMPILE FAILED:", name)
        print("\n".join(err.splitlines()[:15]))
    sys.exit(1)

binary = os.path.join(OUT, "MiSTer")
link = ZIG + ["c++"] + TARGET + ["-o", binary] + objs + [
    "-L" + SRC + "/lib/imlib2", "-lImlib2", "-lfreetype", "-lbz2", "-lpng16", "-lz",
    "-L" + SRC + "/lib/bluetooth", "-lbluetooth",
    "-lm", "-lrt", "-ldl", "-lpthread", "-Wl,--allow-shlib-undefined", "-s"]
r = subprocess.run(link, capture_output=True, text=True)
if r.returncode:
    print("LINK FAILED\n" + "\n".join(r.stderr.splitlines()[:40]))
    sys.exit(1)
print("built", binary, os.path.getsize(binary), "bytes from", len(objs), "objects")
