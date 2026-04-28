import hashlib
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
from pathlib import Path
from typing import Callable


class HashAlgorithm(Enum):
    """支持的哈希算法"""

    MD5 = "md5"
    SHA1 = "sha1"
    SHA256 = "sha256"

    @classmethod
    def from_string(cls, value: str) -> "HashAlgorithm":
        """根据字符串获取枚举成员，默认返回 MD5。"""
        mapping = {m.value: m for m in cls}
        return mapping.get(value.lower(), cls.MD5)


def get_recommended_workers() -> int:
    """
    根据当前设备的 CPU 逻辑核心数，推荐可同时计算哈希的文件数量。

    规则：
    - 逻辑核心数 <= 2  → 推荐 1 个（避免系统卡顿）
    - 逻辑核心数 <= 4  → 推荐 2 个
    - 逻辑核心数 <= 8  → 推荐 4 个
    - 逻辑核心数 > 8   → 推荐 6 个（避免过度占用 I/O）
    """
    cpu_count = os.cpu_count() or 1
    if cpu_count <= 2:
        return 1
    if cpu_count <= 4:
        return 2
    if cpu_count <= 8:
        return 4
    return 6


def get_cpu_info_text() -> str:
    """生成一段供 UI 展示的 CPU 与推荐并发数提示文本。"""
    cpu_count = os.cpu_count() or 1
    workers = get_recommended_workers()
    return f"检测到您的设备拥有 {cpu_count} 个逻辑核心，建议同时计算 {workers} 个文件以获得最佳性能。"


def calculate_file_hash(
    file_path: str | Path,
    algorithm: HashAlgorithm = HashAlgorithm.MD5,
    progress_callback: Callable[[int, int], None] | None = None,
    chunk_size: int = 8192,
) -> str:
    """
    计算单个文件的哈希值。

    Parameters
    ----------
    file_path : str | Path
        目标文件路径。
    algorithm : HashAlgorithm
        使用的哈希算法，默认 MD5。
    progress_callback : Callable[[int, int], None] | None
        进度回调函数，签名为 (已读取字节数, 文件总字节数)。
    chunk_size : int
        每次读取的块大小（字节），默认 8 KB。

    Returns
    -------
    str
        计算完成的十六进制哈希字符串。

    Raises
    ------
    FileNotFoundError
    PermissionError
    OSError
    """
    result = calculate_file_hashes(
        file_path,
        algorithms=[algorithm],
        progress_callback=progress_callback,
        chunk_size=chunk_size,
    )
    return result[algorithm.value]


def calculate_file_hashes(
    file_path: str | Path,
    algorithms: list[HashAlgorithm] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    chunk_size: int = 8192,
) -> dict[str, str]:
    """
    单次读取文件，同时计算多个哈希值。

    Parameters
    ----------
    file_path : str | Path
        目标文件路径。
    algorithms : list[HashAlgorithm] | None
        要计算的算法列表，默认 [MD5, SHA1, SHA256]。
    progress_callback : Callable[[int, int], None] | None
        进度回调函数，签名为 (已读取字节数, 文件总字节数)。
    chunk_size : int
        每次读取的块大小（字节），默认 8 KB。

    Returns
    -------
    dict[str, str]
        键为算法名称（小写），值为对应的十六进制哈希字符串。
    """
    if algorithms is None:
        algorithms = [HashAlgorithm.MD5, HashAlgorithm.SHA1, HashAlgorithm.SHA256]

    path = Path(file_path)
    hashers: dict[str, "hashlib._Hash"] = {
        algo.value: hashlib.new(algo.value) for algo in algorithms
    }
    total_size = path.stat().st_size
    read_size = 0

    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            for hasher in hashers.values():
                hasher.update(chunk)
            read_size += len(chunk)
            if progress_callback is not None:
                progress_callback(read_size, total_size)

    return {algo.value: hasher.hexdigest() for algo, hasher in zip(algorithms, hashers.values())}


def calculate_hashes_concurrent(
    file_paths: list[str | Path],
    algorithms: list[HashAlgorithm] | None = None,
    max_workers: int | None = None,
    on_progress: Callable[[str, int, int], None] | None = None,
    on_complete: Callable[[str, dict[str, str]], None] | None = None,
    on_error: Callable[[str, Exception], None] | None = None,
) -> dict[str, dict[str, str] | None]:
    """
    批量并发计算多个文件的多算法哈希值（单次读取，同时计算所有算法）。

    Parameters
    ----------
    file_paths : list[str | Path]
        待计算的文件路径列表。
    algorithms : list[HashAlgorithm] | None
        要计算的算法列表，默认 [MD5, SHA1, SHA256]。
    max_workers : int | None
        最大并发线程数，None 时自动根据 CPU 核心数决定。
    on_progress : Callable[[str, int, int], None] | None
        单个文件进度回调，签名为 (文件路径, 已读取字节数, 总字节数)。
    on_complete : Callable[[str, dict[str, str]], None] | None
        单个文件完成回调，签名为 (文件路径, {算法: 哈希值})。
    on_error : Callable[[str, Exception], None] | None
        单个文件错误回调，签名为 (文件路径, 异常对象)。

    Returns
    -------
    dict[str, dict[str, str] | None]
        键为文件路径，值为对应的所有哈希值字典；若计算失败则为 None。
    """
    if algorithms is None:
        algorithms = [HashAlgorithm.MD5, HashAlgorithm.SHA1, HashAlgorithm.SHA256]
    if max_workers is None:
        max_workers = get_recommended_workers()

    results: dict[str, dict[str, str] | None] = {}

    def _wrapped_progress(path_str: str) -> Callable[[int, int], None] | None:
        if on_progress is None:
            return None
        progress = on_progress
        return lambda read, total: progress(path_str, read, total)

    def _task(path_str: str) -> tuple[str, dict[str, str] | None]:
        try:
            hashes = calculate_file_hashes(
                path_str,
                algorithms=algorithms,
                progress_callback=_wrapped_progress(path_str),
            )
            return path_str, hashes
        except Exception as exc:
            if on_error is not None:
                on_error(path_str, exc)
            return path_str, None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_path = {
            executor.submit(_task, str(p)): str(p) for p in file_paths
        }
        for future in as_completed(future_to_path):
            path_str, hashes = future.result()
            results[path_str] = hashes
            if hashes is not None and on_complete is not None:
                on_complete(path_str, hashes)

    return results
