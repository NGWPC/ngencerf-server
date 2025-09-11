#!/usr/bin/env python3
import argparse
import ctypes
import ctypes.util
import os
import random
import shutil
import statistics
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import fsspec

#
# # Mount with caching disabled (as you did)
# s3fs ngwpc-forcing ~/s3/ngwpc-forcing -o enable_noobj_cache -o max_stat_cache_size=0
#
# python s3_benchmark.py   --fuse_dir ~/s3/ngwpc-forcing/aorc_2.2/CONUS/Gage_01031300   --s3_prefix s3://ngwpc-forcing/aorc_2.2/CONUS/Gage_01031300   --runs 3 --buf_mb 8 --shuffle


# ----- knobs -----
S3_WORKERS = 8  # number of parallel S3 file downloads


# -------------- small utils

def human_mb(nbytes): return nbytes / (1024.0 * 1024.0)


def warn(msg): print(f"WARNING: {msg}", file=sys.stderr)


# Try to load libc for posix_fadvise(DONTNEED)
def _get_libc():
    path = ctypes.util.find_library("c")
    return ctypes.CDLL(path, use_errno=True) if path else None


_LIBC = _get_libc()
_POSIX_FADV_DONTNEED = 4


def evict_file_cache(paths):
    """
    Best-effort: ask kernel to evict page cache for given files.
    No sudo; no remount. Safe if unsupported (no-op).
    """
    if not _LIBC or not hasattr(_LIBC, "posix_fadvise"):
        return
    posix_fadvise = _LIBC.posix_fadvise
    posix_fadvise.argtypes = [ctypes.c_int, ctypes.c_longlong, ctypes.c_longlong, ctypes.c_int]
    posix_fadvise.restype = ctypes.c_int
    for p in paths:
        try:
            fd = os.open(p, os.O_RDONLY)
            try:
                posix_fadvise(fd, 0, 0, _POSIX_FADV_DONTNEED)  # whole file
            finally:
                os.close(fd)
        except OSError:
            pass  # Ignore unreadable files


def list_fuse_files(root_dir):
    files = []
    for dirpath, _, filenames in os.walk(root_dir):
        for name in filenames:
            p = os.path.join(dirpath, name)
            try:
                sz = os.path.getsize(p)
            except OSError:
                continue
            files.append((p, sz))
    return files


def list_s3_files(fs, s3_prefix):
    # Try detail on find (fast), else fall back to info per key
    files = []
    # Prefer detail=True (newer fsspec); fall back to per-file info
    try:
        found = fs.find(s3_prefix, detail=True)
        # s3fs returns dict keyed by path
        if isinstance(found, dict):
            it = ((k, v) for k, v in found.items())
        else:
            it = ((m.get("name") or m.get("Key"), m) for m in found)
        for k, meta in it:
            if not k:
                continue
            if meta.get("type") == "directory":
                continue
            sz = int(meta.get("size", meta.get("Size", 0)))
            files.append((k, sz))
    except TypeError:
        # Older fsspec: no detail
        for p in fs.find(s3_prefix):
            try:
                info = fs.info(p)
                if info.get("type") == "directory":
                    continue
                sz = int(info.get("size", 0))
            except Exception:
                sz = 0
            files.append((p, sz))
    return files


def copy_fuse_tree(src_root, dst_root, buf_bytes, files_list=None):
    total = 0
    start = time.perf_counter()
    iterable = files_list or list_fuse_files(src_root)
    for src, sz in iterable:
        rel = os.path.relpath(src, src_root)
        dst = os.path.join(dst_root, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(src, "rb") as r, open(dst, "wb") as w:
            shutil.copyfileobj(r, w, length=buf_bytes)
        total += sz
    return time.perf_counter() - start, total


def copy_s3_tree_parallel(fs, s3_prefix, dst_root, buf_bytes, files_list=None, workers=S3_WORKERS):
    total = 0
    files = files_list or list_s3_files(fs, s3_prefix)

    def _copy_one(src_sz):
        src, sz = src_sz
        rel = src[len(s3_prefix):].lstrip("/") if src.startswith(s3_prefix) else os.path.basename(src)
        dst = os.path.join(dst_root, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with fs.open(src, "rb") as r, open(dst, "wb") as w:
            shutil.copyfileobj(r, w, length=buf_bytes)
        return sz

    start = time.perf_counter()
    # Threaded fan-out over files
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_copy_one, x) for x in files]
        for f in as_completed(futs):
            total += f.result()
    return time.perf_counter() - start, total, len(files)


def stats_line(times):
    mean = statistics.mean(times)
    med = statistics.median(times)
    p95 = sorted(times)[int(0.95 * (len(times) - 1))]
    return mean, med, p95


# -------------- main

def run(args):
    fuse_dir = os.path.abspath(os.path.expanduser(args.fuse_dir))
    assert os.path.isdir(fuse_dir), f"FUSE dir not found: {args.fuse_dir}"

    fs = fsspec.filesystem("s3")
    s3_prefix = args.s3_prefix.rstrip("/") + "/"

    # Build lists once
    fuse_files = list_fuse_files(fuse_dir)
    s3_files = list_s3_files(fs, s3_prefix)
    fuse_bytes = sum(sz for _, sz in fuse_files)
    s3_bytes = sum(sz for _, sz in s3_files)
    print(f"FUSE files: {len(fuse_files)}  total: {fuse_bytes} bytes ({human_mb(fuse_bytes):.2f} MiB)")
    print(f"S3   files: {len(s3_files)}  total: {s3_bytes} bytes ({human_mb(s3_bytes):.2f} MiB)")
    if len(fuse_files) == 0 or len(s3_files) == 0:
        raise SystemExit("No files found under one or both prefixes.")

    # Optional random order
    if args.shuffle:
        random.shuffle(fuse_files)
        random.shuffle(s3_files)

    buf_bytes = args.buf_mb * 1024 * 1024
    fuse_times, s3_times = [], []

    # Precompute plain list of FUSE source paths for eviction
    fuse_src_paths = [p for p, _ in fuse_files]

    # Use system temp and auto-clean
    with tempfile.TemporaryDirectory() as tmp_root:
        fuse_out = os.path.join(tmp_root, "bench_fuse")
        s3_out = os.path.join(tmp_root, "bench_s3")

        for i in range(args.runs):
            # Clean outputs each run
            shutil.rmtree(fuse_out, ignore_errors=True)
            shutil.rmtree(s3_out, ignore_errors=True)
            os.makedirs(fuse_out, exist_ok=True)
            os.makedirs(s3_out, exist_ok=True)

            # 1) fsspec first — parallel over files
            t, tot, n = copy_s3_tree_parallel(fs, s3_prefix, s3_out, buf_bytes, files_list=s3_files, workers=S3_WORKERS)
            s3_times.append(t)
            s3_mbps = human_mb(tot) / t if t > 0 else 0.0
            print(f"fsspec[{S3_WORKERS}] trial {i + 1}/{args.runs}: {t:.3f}s  ({s3_mbps:.2f} MiB/s)  {tot} bytes across {n} files")

            # 2) Evict cached pages for FUSE source files (no sudo)
            evict_file_cache(fuse_src_paths)

            # 3) FUSE read (single-threaded)
            t, tot = copy_fuse_tree(fuse_dir, fuse_out, buf_bytes, files_list=fuse_files)
            fuse_times.append(t)
            fuse_mbps = human_mb(tot) / t if t > 0 else 0.0
            print(f"FUSE       trial {i + 1}/{args.runs}: {t:.3f}s  ({fuse_mbps:.2f} MiB/s)  {tot} bytes")

        # temp dir auto-deletes here

    # Summary
    fm, fmed, f95 = stats_line(fuse_times)
    sm, smed, s95 = stats_line(s3_times)
    print("\n== Summary ==")
    print(f"FUSE        avg: {fm:.3f}s  median: {fmed:.3f}s  p95: {f95:.3f}s  throughput(avg): {human_mb(fuse_bytes) / fm:.2f} MiB/s")
    print(f"fsspec[{S3_WORKERS}] avg: {sm:.3f}s  median: {smed:.3f}s  p95: {s95:.3f}s  throughput(avg): {human_mb(s3_bytes) / sm:.2f} MiB/s")
    if fm > 0:
        print(f"Speedup (fsspec[{S3_WORKERS}] vs FUSE): {(human_mb(s3_bytes) / sm) / (human_mb(fuse_bytes) / fm):.2f}×")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Compare FUSE vs fsspec by copying all files under a directory/prefix.")
    ap.add_argument("--fuse_dir", required=True, help="Root of directory on FUSE mount (e.g., ~/s3/bucket/prefix)")
    ap.add_argument("--s3_prefix", required=True, help="S3 URL prefix (e.g., s3://bucket/prefix)")
    ap.add_argument("--runs", type=int, default=3, help="Number of timed trials")
    ap.add_argument("--buf_mb", type=int, default=8, help="Copy buffer size in MiB")
    ap.add_argument("--shuffle", action="store_true", help="Randomize file order each run")
    args = ap.parse_args()
    run(args)
