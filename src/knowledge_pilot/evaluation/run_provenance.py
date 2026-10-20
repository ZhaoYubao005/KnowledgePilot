"""Run provenance types and learner-owned file hashing placeholder."""

from collections.abc import Sequence
import json
from pathlib import Path
import platform
from typing import Any, Mapping, TypedDict
import hashlib
import subprocess
class FileIdentity(TypedDict):
    """Identity of actual file bytes; path is repository-relative POSIX text."""

    path: str
    sha256: str
    bytes: int


class CorpusFileIdentity(FileIdentity):
    document_id: str


class RunProvenance(TypedDict):
    """Caller-supplied observations; None means unavailable, never a guessed value.

    Dataset/manifest/corpus/code identities must describe actual supplied files.
    code_files includes the relevant uncommitted code, not only files at HEAD.
    Missing observations are explained in observation_errors (empty if none).
    No model identifier is collected or inferred in this schema step.
    """

    git_commit: str | None
    git_worktree_dirty: bool | None
    dataset: FileIdentity
    manifest: FileIdentity
    corpus_files: list[CorpusFileIdentity]
    code_files: list[FileIdentity]
    python_version: str | None
    observation_errors: list[str]


def sha256_file(path: Path) -> str:

    hasher = hashlib.sha256()

    with path.open("rb") as file:

        while True:
            chunk = file.read(8192)

            if not chunk:
                break

            # TODO 1：将 chunk 输入哈希计算器
            hasher.update(chunk)

    # TODO 2：返回最终 SHA-256 十六进制摘要
    return hasher.hexdigest()


def build_file_identity(
    file_path: Path,
    project_root: Path,
) -> FileIdentity:
    """Build an identity using a repository-relative POSIX path and raw bytes."""
    # TODO(user): Resolve and validate both paths, reject files outside the
    # project root, then return relative path, sha256_file(), and byte size.
    resolved_path = file_path.resolve()
    resolved_root = project_root.resolve()

    relative_path = resolved_path.relative_to(
        resolved_root
    ).as_posix()

    identity: FileIdentity = {
        "path": relative_path,
        "sha256": sha256_file(resolved_path),
        "bytes": resolved_path.stat().st_size,
    }

    return identity


def collect_corpus_identities(
    manifest: Mapping[str, Any],
    project_root: Path,
) -> list[CorpusFileIdentity]:

    records: list[CorpusFileIdentity] = []

    # 记录已经出现的 document_id 和文件路径
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()

    # 遍历 Manifest 中的 Corpus 文件
    for entry in manifest["corpus_files"]:

        document_id = entry["document_id"]

        # 1. 检查 document_id 是否重复
        if document_id in seen_ids:
            raise ValueError(
                f"Duplicate document_id: {document_id}"
            )

        # 2. 获取文件身份
        file_path = project_root / entry["path"]

        identity = build_file_identity(
            file_path,
            project_root,
        )

        relative_path = identity["path"]

        # 3. 检查文件路径是否重复
        if relative_path in seen_paths:
            raise ValueError(
                f"Duplicate corpus path: {relative_path}"
            )

        # 4. 记录已出现的 ID 和路径
        seen_ids.add(document_id)
        seen_paths.add(relative_path)

        # 5. 组装 CorpusFileIdentity
        record: CorpusFileIdentity = {
            "path": relative_path,
            "document_id": document_id,
            "sha256": identity["sha256"],
            "bytes": identity["bytes"],
        }

        records.append(record)

    # 6. 按仓库相对路径确定性排序
    records.sort(key=lambda record: record["path"])

    return records


def collect_run_provenance(
    *,
    project_root: Path,
    dataset_path: Path,
    manifest_path: Path,
    code_paths: Sequence[Path],
) -> RunProvenance:
    """Collect one run's file, Git, and Python observations without mutation.

    Dataset, Manifest, Corpus, and code files are required evidence: missing or
    outside-root files must fail. Git is an optional observation: if unavailable,
    record None fields plus an explicit observation error. Git dirty detection
    must include untracked files. Code identities must be independently built
    for every caller-supplied path and sorted by repository-relative POSIX path.
    This function must not initialize Chroma/Ollama or write any file.
    """
    # TODO(user): Read the Manifest JSON, reuse build_file_identity() and
    # collect_corpus_identities(), collect deterministic code identities, query
    # Git HEAD/status (including untracked files), record platform.python_version(),
    # and assemble RunProvenance with explicit Git observation failures.
    root = project_root.resolve()

    # 兼容调用方传入相对路径或绝对路径
    dataset_file = (
        dataset_path
        if dataset_path.is_absolute()
        else root / dataset_path
    )

    manifest_file = (
        manifest_path
        if manifest_path.is_absolute()
        else root / manifest_path
    )

    # 1. Dataset 身份
    dataset_identity = build_file_identity(
        dataset_file,
        root,
    )

    # 2. Manifest 身份
    manifest_identity = build_file_identity(
        manifest_file,
        root,
    )

    # 3. 读取真实 Manifest
    with manifest_file.open("r", encoding="utf-8") as file:
        manifest_data = json.load(file)

    # 4. Corpus 文件身份
    corpus_files = collect_corpus_identities(
        manifest_data,
        root,
    )
    code_files: list[FileIdentity] = []

    for path in code_paths:
        code_path = path if path.is_absolute() else root / path

        identity = build_file_identity(
            code_path,
            root,
        )

        code_files.append(identity)

    code_files.sort(key=lambda item: item["path"])
    # Git 观测
    git_commit: str | None = None
    git_worktree_dirty: bool | None = None
    observation_errors: list[str] = []

    try:
        # 获取当前 Git Commit
        commit_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )

        git_commit = commit_result.stdout.strip()

        # 检查 Git 工作区状态
        status_result = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )

        git_worktree_dirty = bool(status_result.stdout.strip())

    except (OSError, subprocess.CalledProcessError) as exc:
        git_commit = None
        git_worktree_dirty = None
        observation_errors.append(f"Git observation failed: {exc}")
    # 获取 Python 版本
    python_version = platform.python_version()

    # 组装完整运行溯源记录
    provenance: RunProvenance = {
        "git_commit": git_commit,
        "git_worktree_dirty": git_worktree_dirty,
        "dataset": dataset_identity,
        "manifest": manifest_identity,
        "corpus_files": corpus_files,
        "code_files": code_files,
        "python_version": python_version,
        "observation_errors": observation_errors,
    }

    return provenance
