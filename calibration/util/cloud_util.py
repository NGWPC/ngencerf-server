import json
import hashlib
import logging
import os
import re
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from typing import Iterator, Tuple
from urllib.parse import urlparse

import fsspec

from calibration.views.called_from import called_from

logger = logging.getLogger(__name__)

# Where to persist cached copies of remote objects.
# Default to /var/tmp so cache survives reboots (per FHS).
# Override with FSSPEC_CACHE_DIR if you want a different location (e.g., /tmp for ephemeral).
CACHEDIR_DEFAULT = os.environ.get("FSSPEC_CACHE_DIR", "/var/tmp/fsspec-cache")


# You can pass auth via env (AWS_*, GOOGLE_APPLICATION_CREDENTIALS, AZURE_*),
# or via storage_options in get_filesystem(). Keep it simple here.

def get_filesystem(url: str) -> tuple[fsspec.AbstractFileSystem, str]:
    """
    Return an fsspec filesystem for the given URL and the normalized URL.

    - If passed a bare local path, we normalize to file://... so fsspec is happy.
    - The returned fs is created from the URL's scheme (s3, file, gs, az, ...).

    :param url: Full URL string for a resource (cloud or local).
    :return: (filesystem, normalized_url) tuple
    """
    url = normalize_url(url)
    parsed = urlparse(url)
    scheme = parsed.scheme or "file"
    # fsspec auto-picks backend by scheme
    fs = fsspec.filesystem(scheme)
    return fs, url


def _norm_prefix(url: str) -> tuple[str, str]:
    """
    Split a URL into (base, path) without trailing slashes in base.

    Example:
        s3://my-bucket/path/to/stuff -> ("s3://my-bucket", "path/to/stuff")

    :param url: Full URL string.
    :return: (base, path) where base includes scheme+netloc, and path is the remainder.
    """
    url = normalize_url(url)
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}".rstrip("/")
    path = p.path.lstrip("/")
    return base, path


def _same_provider(fs_a: fsspec.AbstractFileSystem,
                   fs_b: fsspec.AbstractFileSystem) -> bool:
    """
    Return True if both filesystem objects are of the same backend type.
    This is important because server-side copy is only possible when
    source and destination are managed by the same provider.
    """
    return type(fs_a) is type(fs_b)


def _server_side_cp_supported(fs: fsspec.AbstractFileSystem) -> bool:
    """
    Check if a filesystem supports a provider-native server-side copy.
    For example: S3, GCS, Azure may expose a 'cp_file' or 'copy' method.
    """
    return hasattr(fs, "cp_file") or hasattr(fs, "copy") or hasattr(fs, "cp")


def _cp_file_server_side(fs: fsspec.AbstractFileSystem,
                         src: str,
                         dst: str) -> None:
    """
    Attempt to perform a server-side copy using whichever method the
    backend exposes. Raises NotImplementedError if not supported.

    :param fs: The fsspec filesystem object.
    :param src: Source file URL.
    :param dst: Destination file URL.
    """
    if hasattr(fs, "cp_file"):
        return fs.cp_file(src, dst)
    if hasattr(fs, "copy"):
        return fs.copy(src, dst)
    if hasattr(fs, "cp"):
        return fs.cp(src, dst)
    raise NotImplementedError("No server-side copy method available for this backend")


# Regexes for detecting Windows local paths
_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_UNC_RE = re.compile(r"^\\\\")  # UNC paths like \\server\share


def is_probably_local_path(p: str) -> bool:
    """
    Heuristic to decide if a path is local rather than a URL.

    - If it has a URL scheme (e.g. s3://), return False.
    - Windows drive letters (C:/...) or UNC paths (\\\\server\\share) return True.
    - Any other relative or absolute POSIX path returns True.
    """
    parsed = urlparse(p)
    if parsed.scheme:  # already looks like a URL
        return False
    # Windows drive or UNC counts as local
    if _DRIVE_RE.match(p) or _UNC_RE.match(p):
        return True
    # Plain relative/absolute posix path -> local
    return True  # default: assume local


def normalize_url(p: str) -> str:
    """
    Ensure a path is expressed as a proper URL.

    - If it looks like a local path, expand and absolutize it,
      then prefix with file:// (POSIX) or file:///C:/... (Windows).
    - If it's already a URL (has a scheme), return unchanged.
    """
    if is_probably_local_path(p):
        # Expand ~ and make absolute; fsspec file:// likes absolute paths
        ap = os.path.abspath(os.path.expanduser(p))
        # On Windows, file URLs need forward slashes and an extra slash before drive
        if os.name == "nt":
            ap = ap.replace("\\", "/")
            return f"file:///{ap}"  # Windows: file:///C:/path
        return f"file://{ap if ap.startswith('/') else '/' + ap}"  # POSIX
    return p


def copy_tree(src_url: str,
              dst_url: str,
              workers: int = 16,
              buffer_size: int = 8 * 1024 * 1024) -> int:
    """
    Recursively copy all files under src_url into dst_url.

    - If source and destination are the same provider and support
      server-side copy, use that (fast, no local I/O).
    - Otherwise stream through this process with multiple threads.


    :param src_url: Source prefix URL (e.g. s3://bucket/prefix or file:///dir).
    :param dst_url: Destination prefix URL (e.g. file:///localdir or s3://otherbucket/target).
    :param workers: Number of parallel threads to use.
    :param buffer_size: Buffer size for streamed copies (default 8 MiB).
    :return: Number of files successfully copied.
    """
    logger.info(called_from())

    fs_src, _ = get_filesystem(src_url)
    fs_dst, _ = get_filesystem(dst_url)

    src_base, src_prefix = _norm_prefix(src_url)
    dst_base, dst_prefix = _norm_prefix(dst_url)

    # Find all source files
    # fs.find may return scheme-less paths for some backends,
    # so rebuild full URLs explicitly
    src_root = f"{src_base}/{src_prefix}".rstrip("/")
    files = [p for p in fs_src.find(src_root) if not p.endswith("/")]

    if not files:
        logger.warning(f"No files found at {src_url}")
        return 0

    logger.info(f"Copying {len(files)} files from {src_url} to {dst_url} using {workers} workers")

    # Decide if we can use provider-native server-side copy
    use_server_side = _same_provider(fs_src, fs_dst) and _server_side_cp_supported(fs_src)

    def _dst_path(src_path: str) -> str:
        """
        Compute destination path by replacing src_root with dst_base/prefix.
        """
        rel = src_path[len(src_root):].lstrip("/")
        return f"{dst_base}/{dst_prefix}/{rel}".replace("//", "/")

    def _copy_one(src_path: str) -> tuple[str, float, int]:
        """
        Copy one file:
        - Try server-side copy if possible.
        - Otherwise stream through this process with buffer_size.

        Returns: (dst_path, seconds, size_bytes)
        """
        t0 = time.perf_counter()
        dst_path = _dst_path(src_path)

        # Ensure parent exists (some fs backends require explicit directory creation)
        parent = os.path.dirname(urlparse(dst_path).path).lstrip("/")
        try:
            fs_dst.mkdirs(f"{dst_base}/{parent}", exist_ok=True)
        except Exception:
            pass

        # Attempt to get size for throughput reporting (best-effort)
        size_bytes = -1
        try:
            info = fs_src.info(src_path)
            size_bytes = int(info.get("size", -1))
        except Exception:
            pass

        if use_server_side:
            # Server-side copy within the same provider (fast, no data over your machine)
            _cp_file_server_side(fs_src, src_path, dst_path)
        else:
            # Stream through memory with a large buffer; threads handle parallelism
            with fs_src.open(src_path, "rb") as r, fs_dst.open(dst_path, "wb") as w:
                shutil.copyfileobj(r, w, length=buffer_size)

        dt = time.perf_counter() - t0

        # Per-file timing/throughput log
        if size_bytes and size_bytes > 0:
            mb = size_bytes / (1024 * 1024)
            mbps = mb / dt if dt > 0 else 0.0
            logger.info(f"Finished copying {src_path} -> {dst_path} in {dt:.3f}s "
                        f"({mb:.2f} MiB @ {mbps:.2f} MiB/s)")
        else:
            logger.info(f"Finished copying {src_path} -> {dst_path} in {dt:.3f}s")

        return dst_path, dt, max(size_bytes, 0)

    # Threaded fan-out over files
    start_wall = time.perf_counter()
    completed = 0
    total_bytes = 0
    total_cpu_time = 0.0  # sum of per-file times (not equal to wall time with parallelism)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_copy_one, p) for p in files]
        for fut in as_completed(futs):
            dst_path, dt, nbytes = fut.result()  # will raise if error
            completed += 1
            total_bytes += nbytes
            total_cpu_time += dt

    wall_dt = time.perf_counter() - start_wall

    logger.info(f"Successfully copied {completed}/{len(files)} files from {src_url} to {dst_url}")

    # Summary timing/throughput (added)
    if total_bytes > 0:
        mb = total_bytes / (1024 * 1024)
        wall_mbps = mb / wall_dt if wall_dt > 0 else 0.0
        avg_per_file = wall_dt / completed if completed else 0.0
        logger.info(
            f"Copy summary: {mb:.2f} MiB in {wall_dt:.3f}s "
            f"({wall_mbps:.2f} MiB/s, avg per file {avg_per_file:.3f}s, workers={workers}, "
            f"{'server-side' if use_server_side else 'streamed'})"
        )
    else:
        logger.info(
            f"Copy summary: duration {wall_dt:.3f}s (workers={workers}, "
            f"{'server-side' if use_server_side else 'streamed'})"
        )

    return completed


def path_exists(path: str) -> bool:
    """
    Cloud/local agnostic exists() check.
    Works for file://, s3://, gcs://, az://, etc.

    :param path: URL or local filesystem path.
    :return: True if path exists, False otherwise.
    """
    if not path:
        return False

    parsed = urlparse(path)
    scheme = parsed.scheme or "file"

    if scheme == "file":
        return os.path.exists(parsed.path or path)

    try:
        fs = fsspec.filesystem(scheme)
        return fs.exists(path)
    except Exception:
        return False


# ----------------------------
# Caching + localization
# ----------------------------

_REMOTE_SCHEMES = {"s3", "gs", "gcs", "az", "abfs", "abfss"}


def _is_remote(url_or_path: str) -> bool:
    p = urlparse(url_or_path)
    return bool(p.scheme) and p.scheme.lower() in _REMOTE_SCHEMES


def _cache_key(url: str) -> str:
    # Stable filename from URL
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _meta_path(cache_dir: str, key: str) -> str:
    return os.path.join(cache_dir, f"{key}.meta.json")


def _data_path(cache_dir: str, key: str, suffix=".gpkg") -> str:
    return os.path.join(cache_dir, f"{key}{suffix}")


def _read_meta(path: str) -> dict:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_meta(path: str, meta: dict) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(meta, f)
    os.replace(tmp, path)


def _info_for(fs, url: str) -> dict:
    try:
        return fs.info(url)
    except Exception:
        return {}


@contextmanager
def localize_to_path(
    url_or_path: str,
    *,
    enable_cache: bool = True,
    cache_dir: str = CACHEDIR_DEFAULT,
    suffix: str = ".gpkg"
) -> Iterator[Tuple[str, str]]:
    """
    Yield (original_path, local_path) for local or remote resources.

    Local paths:
      - Yields (p, p) without copying or caching.

    Remote URLs (s3/gs/az/abfs):
      - If enable_cache=True (default): persist under `cache_dir` and REUSE across runs.
        Cache validation uses provider metadata:
          - If both local file exists AND (ETag matches AND size matches) => cache hit.
          - Otherwise download to <file>.downloading and atomically promote it.
        We store sidecar JSON with {etag, size, mtime, url, t}.
      - If enable_cache=False: we download to a NamedTemporaryFile and delete on exit.
        (Use this for truly one-shot reads.)

    Note: This is separate from copy_tree(); copy_tree does not populate or read
    this cache. If you want copy_tree to reuse the same artifacts across runs,
    refactor it to localize each source file via this function first.
    """
    orig = url_or_path
    if not _is_remote(orig):
        # Local path: no caching layer involved
        yield orig, orig
        return

    os.makedirs(cache_dir, exist_ok=True)
    p = urlparse(orig)
    scheme = p.scheme.lower()
    fs = fsspec.filesystem(scheme)

    # Remote metadata to validate cache freshness
    meta_remote = _info_for(fs, orig)
    etag = str(meta_remote.get("ETag") or meta_remote.get("etag") or "")
    size = int(meta_remote.get("Size") or meta_remote.get("size") or -1)
    mtime = int(meta_remote.get("LastModified") or meta_remote.get("last_modified") or 0)

    if enable_cache:
        key = _cache_key(orig)
        data_path = _data_path(cache_dir, key, suffix=suffix)
        meta_path = _meta_path(cache_dir, key)

        meta_local = _read_meta(meta_path)
        ok = (
            os.path.exists(data_path)
            and meta_local.get("etag") == etag
            and meta_local.get("size") == size
        )

        if ok:
            # Cache hit
            yield orig, data_path
            return

        # Cache miss → download then promote
        tmp = data_path + ".downloading"
        logger.info(f"Downloading remote file to cache: original '{orig}' (local cache: {data_path})")
        try:
            # Use fs.get to persist efficiently; same-bucket copies may be server-side
            fs.get(orig, tmp)
            os.replace(tmp, data_path)
            _write_meta(meta_path, {"etag": etag, "size": size, "mtime": mtime, "url": orig, "t": time.time()})
            yield orig, data_path
            return
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass

    # No persistent cache requested → one-shot temp file
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmpf:
        tmp_path = tmpf.name
    try:
        logger.info(f"Downloading remote file to temp: original '{orig}' (local copy: {tmp_path})")
        fs.get(orig, tmp_path)
        yield orig, tmp_path
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
