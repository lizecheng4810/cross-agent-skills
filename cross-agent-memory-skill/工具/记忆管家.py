#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
记忆管家 —— cross-agent-memory 的主工具（跨平台，需 Python 3.8+）

说明：判断该分几层（1~N 层，不设上限）、深度阅读并填写记忆文件，由 Agent 按 SKILL.md 自主完成。
本脚本只做机械操作。**层号约定 = 记忆层级序数**：工作区根 = 第一层；某文件夹的层号 =
根到它的路径上拥有记忆层的祖先数 + 1（分组文件夹如 platforms 不建层就不占层号）。
文件夹名形如 记忆第X层（X 为中文数字，一~九十九）。
  建层   就地创建 记忆第X层 文件夹（默认 0_索引 + 5_代办）；--完整模板 创建旧版全部主题文件
         加 --通用 则在目标文件夹下建中央 记忆_通用/（0_通用索引 + 4 件，任何层都能引用）
  扫描   列出工作区里已有的 记忆第X层 文件夹（任意层数，含 记忆_通用）
  检查   层级完整性检查：按记忆层级序数推断每处应有的 记忆第X层，找出缺失的候选子模块/子工程
  索引   为当前存在的标准记忆文件生成/更新指纹，并清除已删除标准文件的旧指纹
  校验   对比当前文件与指纹档案，报告被其他 Agent/Harness 改过的文件（并发检测）
  刷新通用 重建所有 记忆第X层/0_索引.md 的「🔗 通用知识」段（保留已有摘要，补新文件、删失效引用）
  检索   在指定范围的记忆文档中词面检索，可多关键词、限范围和结果数
  接手   默认快速检查根层或 --scope 目标路径；--full-audit 显式完整盘点
  帮助   显示本说明

记忆索引.json 存放于各 记忆第X层 文件夹内，随工作区走。
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys
from pathlib import Path

INDEX_NAME = "记忆索引.json"
UNIVERSAL_DIR = "记忆_通用"  # 中央跨层通用知识（不在任何 记忆第X层 内，与它们平级）
UNIVERSAL_FILES = [
    "0_通用索引.md",
    "1_通用偏好.md",
    "2_通用配方.md",
    "3_通用工具.md",
    "4_通用踩坑.md",
]
UNIVERSAL_LABELS = {  # 「🔗 通用知识」段里每个文件的展示名
    "1_通用偏好.md": "通用偏好",
    "2_通用配方.md": "通用配方",
    "3_通用工具.md": "通用工具",
    "4_通用踩坑.md": "通用踩坑",
}
# 「🔗 通用知识」段定位：标题行到下一个二级标题之间
UNIVERSAL_SECTION_RE = re.compile(r"(## 🔗 通用知识[^\n]*\n)(.*?)(?=\n## |\Z)", re.S)
# 本机配置（与 cross-agent-scratchpad-skill 共享同一份，设备级事实不放工作区记忆）
LOCAL_CONFIG = Path.home() / ".agent-tsg" / "config.json"
CORE_FILES = [
    "0_索引.md",
    "1_项目架构.md",
    "2_踩坑日志.md",
    "3_个性化需求.md",
    "4_提示词配方.md",
    "5_代办.md",
    "6_需要我配合.txt",
]
# 新层默认只建导航与当前交接；主题文件在有真实内容时再创建。
DEFAULT_LAYER_FILES = ("0_索引.md", "5_代办.md")
# 支持一~九十九层（任意层数，由 Agent 深度研究项目后自主决定）
CN_DIGITS = "一二三四五六七八九"
LAYER_RE = re.compile(r"^记忆第([一二三四五六七八九十]{1,3})层$")
LAYER_NAME_RE = re.compile(r"^记忆第[一二三四五六七八九十]{1,3}层$")
# 跳过可再生的依赖/构建/缓存目录；源码/文档/测试目录可能包含独立模块，不按名称忽略。
SKIP_NAMES = re.compile(
    r"^(node_modules|\.git|__pycache__|\.venv|venv|dist|build|target|out|obj|coverage|release|"
    r"\.idea|\.vscode|\.pytest_cache|\.mypy_cache|\.ruff_cache|\.tox|\.cache|\.next|\.nuxt|vendor)$"
)
# 判定「独立模块/子工程」的项目标志文件（有其一即视为候选）
PROJECT_MARKERS = (
    "README.md", "readme.md", "README.txt", "package.json", "pyproject.toml",
    "setup.py", "requirements.txt", "Cargo.toml", "pom.xml", "build.gradle",
    "pubspec.yaml", "CMakeLists.txt", "go.mod", ".git", "composer.json", "*.csproj",
)
def configure_console() -> None:
    """避免 Windows 代码页无法编码提示符时让只读检查意外崩溃。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def to_cn(n: int) -> str:
    """1~99 → 中文数字（一/十/十四/二十/九十九）。"""
    if not 1 <= n <= 99:
        raise ValueError(f"层号超范围（1~99）：{n}")
    if n < 10:
        return CN_DIGITS[n - 1]
    if n == 10:
        return "十"
    ten, ones = divmod(n, 10)
    return (CN_DIGITS[ten - 1] + "十" if ten > 1 else "十") + (CN_DIGITS[ones - 1] if ones else "")


def cn_to_int(s: str):
    """中文数字（一~九十九）→ int；解析失败返回 None。"""
    if not s:
        return None
    if s == "十":
        return 10
    ten = ones = 0
    if "十" in s:
        head, _, tail = s.partition("十")
        if head:
            i = CN_DIGITS.find(head)
            if i < 0:
                return None
            ten = i + 1
        if tail:
            i = CN_DIGITS.find(tail)
            if i < 0:
                return None
            ones = i + 1
        return ten * 10 + ones
    i = CN_DIGITS.find(s)
    return i + 1 if i >= 0 else None


def parse_layer(s: str):
    """--层 参数：中文数字（四）或阿拉伯数字（4）→ int。"""
    s = str(s).strip()
    if s.isdigit():
        return int(s)
    return cn_to_int(s)


def layer_name(n: int) -> str:
    return f"记忆第{to_cn(n)}层"


def expected_layer_depth(dirpath: Path, root: Path, errors=None) -> int:
    """层号 = 记忆层级序数：根=第一层；某文件夹的层号 = 根到它的路径上
    （含根、不含自身）拥有记忆层的祖先数 + 1。分组文件夹（如 platforms、
    AI_NEWS_MARKETS）自己不建记忆层就不占层号，避免模块层号被分组层级虚增。"""
    rel = dirpath.relative_to(root)
    if not rel.parts:
        return 1  # 根 = 第一层
    n = 0
    ancestor = root
    for part in rel.parts[:-1]:  # 严格祖先（不含自身）
        ancestor = ancestor / part
        if has_layer(ancestor, errors):
            n += 1
    return n + 2  # 1（根层）+ 祖先已占层数 + 1（本层）


def _record_scan_error(errors, path, error) -> None:
    if errors is None:
        return
    item = (str(path), str(error))
    if item not in errors:
        errors.append(item)


def _report_scan_errors(errors) -> None:
    if not errors:
        return
    print(f"  ⚠ 有 {len(errors)} 个位置无法读取，扫描结果不完整：")
    for path, message in errors[:20]:
        print(f"    ! {path}: {message}")
    if len(errors) > 20:
        print(f"    … 另有 {len(errors) - 20} 个读取错误未展开。")


def tpl_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "_模板" / "记忆"


def tpl_universal_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "_模板" / "记忆_通用"


def tool_command() -> str:
    """Return a runnable command path without assuming the caller's working directory."""
    return f'python "{Path(__file__).resolve()}"'


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def local_agent_name() -> str:
    """从本机配置读默认署名（scratchpad 的 配置 --name 写入）。"""
    try:
        cfg = json.loads(LOCAL_CONFIG.read_text(encoding="utf-8-sig"))
        return cfg.get("agent_name", "") or ""
    except Exception:
        return ""


def write_text(p: Path, s: str) -> None:
    # Path.write_text(newline=...) 仅 Python 3.10+ 支持；工具承诺兼容 3.8+。
    with p.open("w", encoding="utf-8", newline="\n") as f:
        f.write(s)


def atomic_write_text(p: Path, s: str) -> None:
    """原子写入：先写临时文件再 os.replace，避免并发写把文件截断成半截 JSON。"""
    tmp = p.with_suffix(p.suffix + f".tmp{os.getpid()}")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        f.write(s)
    os.replace(tmp, p)


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint_of(p: Path) -> dict:
    return {
        "sha256": sha256_of(p),
        "mtime": datetime.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
        "bytes": p.stat().st_size,
    }


def load_index(mem_dir: Path) -> dict:
    idx = mem_dir / INDEX_NAME
    if idx.exists():
        try:
            return json.loads(read_text(idx))
        except Exception as e:
            print(f"⚠ {idx} 解析失败（{e}），将重建。", file=sys.stderr)
    return {"_说明": "本层记忆文件指纹档案（sha256+更新记录），供并发校验用；由 记忆管家.py 索引/校验 维护。", "files": {}}


def save_index(mem_dir: Path, data: dict) -> None:
    data["files"] = dict(sorted(data.get("files", {}).items()))
    data["_updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    atomic_write_text(mem_dir / INDEX_NAME, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


# ---------- 建层（普通层 或 通用层） ----------
def cmd_build(args) -> None:
    target = Path(args.target).resolve()
    if not target.is_dir():
        sys.exit(f"目标文件夹不存在：{target}")
    if bool(getattr(args, "通用", False)) and getattr(args, "层", None):
        sys.exit("--层 和 --通用 不能同时使用；要建普通层只传 --层；要建中央通用只传 --通用。")
    if not getattr(args, "通用", False) and not getattr(args, "层", None):
        sys.exit("必须指定 --层 <一/二/…/99> 或 --通用")

    # ===== 分支 A：建中央 记忆_通用 文件夹 =====
    if getattr(args, "通用", False):
        mem_dir = target / UNIVERSAL_DIR
        if mem_dir.exists():
            sys.exit(f"该文件夹下已有通用文件夹：{mem_dir}（如需更新，直接编辑里面的文件）")
        mem_dir.mkdir(parents=True)
        for name in UNIVERSAL_FILES:
            src = tpl_universal_dir() / name
            write_text(mem_dir / name, read_text(src) if src.exists() else f"# {name}\n")
        data = load_index(mem_dir)
        files = data.setdefault("files", {})
        for name in UNIVERSAL_FILES:
            p = mem_dir / name
            if p.is_file():
                files[name] = {
                    "sha256": sha256_of(p),
                    "mtime": datetime.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
                    "bytes": p.stat().st_size,
                }
        save_index(mem_dir, data)
        print(f"✔ 已就地创建通用记忆文件夹：{mem_dir}\\")
        print(f"  含：{' + '.join(UNIVERSAL_FILES)} + {INDEX_NAME}")
        print(f"  ⚠ 这是中央跨层通用知识，**任何** 记忆第X层 都能通过 0_索引.md 的「🔗 通用知识」段引用。")
        print(f"  ⚠ 用户说\"这是通用的\"时，Agent 应写入这里并刷新所有 记忆第X层 的 0_索引。")
        print(f"  ⚠ 路径用 <工作区>/xxx 占位，不要写死机器专属绝对路径。")
        return

    # ===== 分支 B：建普通的 记忆第X 层 =====
    n = parse_layer(getattr(args, "层"))
    if not n:
        sys.exit("层号非法（用中文数字 一/二/三/四…九十九，或阿拉伯数字 1/2/3/4…99）")
    if n > 99:
        sys.exit("层号超范围（最多九十九层；如需更深请与用户讨论是否结构该拆分）")
    mem_dir = target / layer_name(n)
    if mem_dir.exists():
        sys.exit(f"该文件夹下已有记忆文件夹：{mem_dir}（如需更新，直接编辑里面的文件）")
    mem_dir.mkdir(parents=True)
    template_files = CORE_FILES if getattr(args, "完整模板", False) else DEFAULT_LAYER_FILES
    for name in template_files:
        src = tpl_dir() / name
        write_text(mem_dir / name, read_text(src) if src.exists() else f"# {name}\n")
    # 真正生成初始指纹档案（对模板原样文件逐个记录 sha256），否则 校验 会误报"尚无指纹档案"
    data = load_index(mem_dir)
    files = data.setdefault("files", {})
    for name in template_files:
        p = mem_dir / name
        if p.is_file():
            files[name] = {
                "sha256": sha256_of(p),
                "mtime": datetime.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
                "bytes": p.stat().st_size,
            }
    save_index(mem_dir, data)
    files_label = "0_索引 + 6 件格式参考" if getattr(args, "完整模板", False) else "0_索引 + 5_代办 + 指纹档案"
    print(f"✔ 已就地创建：{mem_dir}\\（含 {files_label} + {INDEX_NAME}）")
    print("  ⚠ 只补充本层有长期价值的内容；其他主题文件需要时再从 _模板 复制。")
    print("  ⚠ 层号应与记忆层级序数一致（根=一；分组文件夹不建层就不占层号）；层数与各层职责请记入根记忆层 0_索引 的「分层方案」。")
    # 顺手提示：如工作区已有 记忆_通用，0_索引 模板已含「🔗 通用知识」段可自动引用
    uni = target / UNIVERSAL_DIR if (target / UNIVERSAL_DIR).is_dir() else None
    if uni is None:
        for ancestor in target.parents:
            if (ancestor / UNIVERSAL_DIR).is_dir():
                uni = ancestor / UNIVERSAL_DIR
                break
    if uni is None:
        print(f"  💡 工作区尚未建 {UNIVERSAL_DIR}（跨层通用知识），用户首次提到「通用」时跑：")
        print(f'     {tool_command()} 建层 "<工作区>" --通用')


# ---------- 扫描 ----------
def cmd_scan(args) -> None:
    root = Path(args.workspace).resolve()
    if not root.is_dir():
        sys.exit(f"工作区不存在：{root}")
    errors = []
    hits = sorted(iter_memory_layers(root, errors))
    try:
        universal_hits = sorted(p for p in root.iterdir()
                                if p.is_dir() and not p.is_symlink() and p.name == UNIVERSAL_DIR)
    except OSError as e:
        universal_hits = []
        _record_scan_error(errors, root, e)
    print(f"扫描 {root} 下的记忆文件夹（共 {len(hits)} 层，另 记忆_通用 {len(universal_hits)} 个）：")
    if not hits and not universal_hits:
        print("  （未找到 记忆第X层 或 记忆_通用，可用 建层 命令就地创建）")
    for u in universal_hits:
        print(f"  ✓ 通用  {u}")
    for h in hits:
        exp = expected_layer_depth(h.parent, root)
        mark = "✓" if to_cn(exp) == LAYER_RE.match(h.name).group(1) else "⚠层号与深度不符"
        print(f"  {mark} {h}")
    _report_scan_errors(errors)


# ---------- 层级完整性检查 ----------
def has_layer(d: Path, errors=None) -> bool:
    try:
        return any(p.is_dir() and not p.is_symlink() and LAYER_NAME_RE.match(p.name) for p in d.iterdir())
    except OSError as e:
        _record_scan_error(errors, d, e)
        return False


def declared_exclusions(root: Path, errors=None):
    """读取根索引「例外目录」段里的反引号相对路径。"""
    index_path = root / layer_name(1) / "0_索引.md"
    try:
        if index_path.parent.is_symlink() or index_path.is_symlink() or not index_path.is_file():
            return []
        text = read_text(index_path)
    except (OSError, UnicodeDecodeError) as e:
        _record_scan_error(errors, index_path, e)
        return []
    match = re.search(r"^## 例外目录[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not match:
        return []
    result = []
    for line in match.group(1).splitlines():
        for value in re.findall(r"`([^`]+)`", line):
            value = value.strip().replace("\\", "/")
            if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
                continue
            value = value.rstrip("/")
            parts = value.split("/")
            if (value and "<" not in value and ":" not in value
                    and all(part not in ("", ".", "..") for part in parts)):
                result.append(value.casefold())
    return result


def is_declared_exclusion(root: Path, directory: Path, excluded=None, errors=None) -> bool:
    excluded = declared_exclusions(root, errors) if excluded is None else excluded
    try:
        relative = directory.resolve().relative_to(root.resolve()).as_posix().casefold()
    except ValueError:
        return True
    except (OSError, RuntimeError) as e:
        _record_scan_error(errors, directory, e)
        return True
    return any(relative == item or relative.startswith(item + "/") for item in excluded)


def iter_memory_layers(root: Path, errors=None):
    """遍历记忆层；忽略依赖/生成目录、符号链接和根索引显式声明的例外路径。"""
    excluded = declared_exclusions(root, errors)

    def onerror(error):
        _record_scan_error(errors, getattr(error, "filename", root), error)

    for current, dirnames, _ in os.walk(root, topdown=True, followlinks=False, onerror=onerror):
        base = Path(current)
        kept = []
        for name in dirnames:
            child = base / name
            if child.is_symlink() or SKIP_NAMES.match(name) or is_declared_exclusion(root, child, excluded, errors):
                continue
            if LAYER_NAME_RE.match(name):
                yield child
                continue
            kept.append(name)
        dirnames[:] = kept


def iter_memory_files(root: Path, start=None, errors=None):
    """遍历记忆文档，跳过依赖/生成目录、符号链接和已声明的例外路径。"""
    excluded = declared_exclusions(root, errors)

    def onerror(error):
        _record_scan_error(errors, getattr(error, "filename", start or root), error)

    for current, dirnames, filenames in os.walk(start or root, topdown=True, followlinks=False, onerror=onerror):
        base = Path(current)
        dirnames[:] = [
            name for name in dirnames
            if not (base / name).is_symlink()
            and not SKIP_NAMES.match(name)
            and not is_declared_exclusion(root, base / name, excluded, errors)
        ]
        for name in filenames:
            path = base / name
            if name == INDEX_NAME or path.is_symlink() or path.suffix.lower() not in (".md", ".txt"):
                continue
            try:
                rel = path.relative_to(root)
            except ValueError:
                continue
            if rel.parts[0] == UNIVERSAL_DIR or any(LAYER_NAME_RE.match(part) for part in rel.parts):
                yield path


def is_project_candidate(d: Path, errors=None) -> bool:
    try:
        names = {p.name for p in d.iterdir()}
    except OSError as e:
        _record_scan_error(errors, d, e)
        return False
    for marker in PROJECT_MARKERS:
        if marker.startswith("*."):
            if any(n.endswith(marker[1:]) for n in names):
                return True
        elif marker in names:
            return True
    return False


def resolve_scope(root: Path, raw_scope: str) -> Path:
    """解析工作区内的范围路径；拒绝越出工作区的绝对/相对路径。"""
    if not raw_scope:
        return root
    candidate = Path(raw_scope)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        sys.exit(f"范围路径必须位于工作区内：{candidate}")
    if not candidate.exists():
        sys.exit(f"范围路径不存在：{candidate}")
    return candidate


def cmd_check(args) -> None:
    root = Path(args.workspace).resolve()
    if not root.is_dir():
        sys.exit(f"工作区不存在：{root}")
    scope = resolve_scope(root, getattr(args, "scope", ""))
    if scope.is_file():
        scope = scope.parent
    max_depth = getattr(args, "max_depth", 0)
    if max_depth < 0:
        sys.exit("--max-depth 必须为 0（不限深度）或正整数。")
    label = "完整审计" if not max_depth else f"限深审计（最多 {max_depth} 层）"
    print(f"层级完整性检查：{scope}（{label}；符号链接目录不跟随）")
    errors = []
    excluded = declared_exclusions(root, errors)
    if scope != root and is_declared_exclusion(root, scope, excluded, errors):
        print("  已跳过：指定范围位于根索引声明的例外目录内，不参与完整性审计。")
        _report_scan_errors(errors)
        return
    checked, missing = 0, []

    def walk(d: Path, depth: int, forced: bool):
        nonlocal checked
        if max_depth and depth > max_depth:
            return
        checked += 1
        exp = expected_layer_depth(d, root, errors)
        if not has_layer(d, errors) and (forced or d == root or is_project_candidate(d, errors)):
            missing.append((d, exp))
        if max_depth and depth >= max_depth:
            return
        try:
            children = sorted(d.iterdir())
        except OSError as e:
            _record_scan_error(errors, d, e)
            return
        for child in children:
            if (not child.is_dir() or child.is_symlink() or SKIP_NAMES.match(child.name)
                    or LAYER_NAME_RE.match(child.name) or child.name == UNIVERSAL_DIR
                    or is_declared_exclusion(root, child, excluded, errors)):
                continue
            walk(child, depth + 1, forced=(child.parent.name == "platforms"))

    walk(scope, 0, forced=(scope.parent.name == "platforms"))
    root_missing = scope == root and not has_layer(root, errors)
    print(f"  已检查 {checked} 个目录。")
    if root_missing:
        print("  ⚠ 工作区根缺少 记忆第一层。")
    if missing:
        print("  候选目录（请对照根层分层方案判断；候选不等于必须建层）：")
        for d, exp in missing:
            print(f"    ? {d}  ← 若确有独立上下文，可建 {layer_name(exp)}")
    else:
        print("  ✓ 未发现缺记忆层的候选子模块文件夹。")
    if excluded:
        print(f"  已遵从根索引声明的 {len(excluded)} 个例外路径。")
    print("  候选判定基于目录结构和项目标志文件；工具不自动创建记忆层。")
    _report_scan_errors(errors)


def _files_of(mem_dir: Path):
    """该记忆文件夹应维护指纹的文件清单：普通层 = 0_索引+6件；通用层 = 5 件通用模板。"""
    return UNIVERSAL_FILES if mem_dir.name == UNIVERSAL_DIR else CORE_FILES


# ---------- 索引（生成/更新指纹档案） ----------
def cmd_index(args) -> None:
    mem_dir = _resolve_mem_dir(args.workspace, args.layer_dir)
    data = load_index(mem_dir)
    files = data.setdefault("files", {})
    removed = []
    for name in _files_of(mem_dir):
        if not (mem_dir / name).is_file() and name in files:
            files.pop(name, None)
            removed.append(name)
    n = 0
    for name in _files_of(mem_dir) + [INDEX_NAME]:
        p = mem_dir / name
        if not p.is_file():
            continue
        files[name] = {
            "sha256": sha256_of(p),
            "mtime": datetime.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
            "bytes": p.stat().st_size,
        }
        n += 1
    if not args.by:
        args.by = local_agent_name()
    if args.by:
        data["_last_updated_by"] = args.by
    save_index(mem_dir, data)
    print(f"✔ 已记录 {mem_dir.name} 内 {n} 个文件的指纹 → {mem_dir / INDEX_NAME}")
    if removed:
        print(f"  已清除已删除标准记忆文件的旧指纹：{', '.join(removed)}")


# ---------- 校验（并发检测：谁在我上次记录之后改过文件） ----------
def cmd_verify(args) -> None:
    mem_dir = _resolve_mem_dir(args.workspace, args.layer_dir)
    data = load_index(mem_dir)
    files = data.get("files", {})
    if not files:
        print(f"（{mem_dir} 尚无指纹档案，请先执行 索引）")
        return
    changed, new, gone = [], [], []
    for name in _files_of(mem_dir):
        p = mem_dir / name
        rec = files.get(name)
        if not p.is_file():
            if rec:
                gone.append(name)
            continue
        if rec is None:
            new.append(name)
        elif sha256_of(p) != rec.get("sha256"):
            changed.append(name)
    if not (changed or new or gone):
        print(f"✓ {mem_dir.name}：自上次记录后无外部改动。")
        return
    print(f"⚠ {mem_dir.name} 检测到外部改动（可能是其他 Agent/Harness 刚写入）：")
    for name in changed:
        print(f"  ~ 已被修改：{name}  ← 更新前必须先深读，在原基础上合并，绝不覆盖")
    for name in new:
        print(f"  + 新增文件：{name}")
    for name in gone:
        print(f"  - 已被删除：{name}")
    print("  处理：先深读被改文件 → 把自己的更新合并进去 → 再执行 索引 刷新指纹。")
    if args.refresh:
        cmd_index(argparse.Namespace(workspace=str(mem_dir.parent), layer_dir=mem_dir.name, by=args.by))
        print("  ✔ 指纹档案已刷新（--refresh）。")


# ---------- 刷新通用（重建所有层的「🔗 通用知识」段） ----------
def _build_universal_section(old_body: str) -> str:
    """按当前 记忆_通用/ 重建段落；旧段落里已填写的摘要尽量保留。"""
    keep = {}
    for line in (old_body or "").splitlines():
        m = re.match(r"^- (.+?)：(.+?) → ", line.strip())
        if m:
            keep[m.group(1)] = m.group(2)
    lines = [
        "## 🔗 通用知识（来自 `<工作区>/记忆_通用/`，任何层都能调用）",
        "> **路径约定**：用 `<工作区>` 占位，不写死机器专属绝对路径（换电脑复制 AI 文件夹时路径会变）。",
    ]
    for fn, label in UNIVERSAL_LABELS.items():
        summary = keep.get(label, "[摘要]")
        lines.append(f"- {label}：{summary} → `<工作区>/记忆_通用/{fn}`")
    lines.append("- 完整索引 → `<工作区>/记忆_通用/0_通用索引.md`")
    lines.append('- （用户说"这是通用的"时，Agent 写到 `<工作区>/记忆_通用/` 并刷新所有层本段；可跑 `刷新通用` 一键完成）')
    return "\n".join(lines) + "\n"


def cmd_refresh_universal(args) -> None:
    root = Path(args.workspace).resolve()
    if not root.is_dir():
        sys.exit(f"工作区不存在：{root}")
    if not (root / UNIVERSAL_DIR).is_dir() or (root / UNIVERSAL_DIR).is_symlink():
        sys.exit(f'工作区还没有 {UNIVERSAL_DIR}（先跑：{tool_command()} 建层 "<工作区>" --通用）')
    hits = sorted(iter_memory_layers(root))
    if not hits:
        print("（工作区没有任何 记忆第X层，无需刷新）")
        return
    by = args.by or local_agent_name()
    changed = 0
    for layer_dir in hits:
        idx_file = layer_dir / "0_索引.md"
        if not idx_file.is_file():
            print(f"  ⚠ {layer_dir.name} 缺 0_索引.md，跳过")
            continue
        text = read_text(idx_file)
        m = UNIVERSAL_SECTION_RE.search(text)
        new_sec = _build_universal_section(m.group(2) if m else "")
        if m:
            new_text = UNIVERSAL_SECTION_RE.sub(lambda _: new_sec, text, count=1)
        elif re.search(r"^## 更新日志", text, re.M):
            new_text = text.replace("## 更新日志", new_sec + "\n## 更新日志", 1)
        else:
            new_text = text.rstrip("\n") + "\n\n" + new_sec
        if new_text == text:
            print(f"  = 已一致 {idx_file}")
            continue
        write_text(idx_file, new_text)
        data = load_index(layer_dir)
        data.setdefault("files", {})[idx_file.name] = fingerprint_of(idx_file)
        if by:
            data["_last_updated_by"] = by
        save_index(layer_dir, data)
        changed += 1
        print(f"  ✔ 已刷新 {idx_file}")
    print(f"完成：{changed}/{len(hits)} 层的「🔗 通用知识」段已对齐当前 记忆_通用/（其余已一致）。")


# ---------- 检索（默认词面匹配；命中后只读相关文档） ----------
def cmd_search(args) -> None:
    root = Path(args.workspace).resolve()
    if not root.is_dir():
        sys.exit(f"工作区不存在：{root}")
    start = resolve_scope(root, getattr(args, "scope", ""))
    errors = []
    excluded = declared_exclusions(root, errors)
    if is_declared_exclusion(root, start, excluded, errors):
        print("检索范围位于根索引声明的例外目录内，已跳过。")
        _report_scan_errors(errors)
        return
    terms = [args.keyword] + list(getattr(args, "term", []) or [])
    terms = list(dict.fromkeys(term.casefold() for term in terms if term.strip()))
    if not terms:
        sys.exit("至少提供一个非空关键词。")
    limit = int(getattr(args, "top", 20))
    if limit < 1:
        sys.exit("--top 必须为正整数。")
    files = [start] if start.is_file() else iter_memory_files(root, start, errors)
    matches = []
    for p in files:
        if not p.is_file() or p.name == INDEX_NAME:
            continue
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        in_memory = rel.parts[0] == UNIVERSAL_DIR or any(LAYER_NAME_RE.match(part) for part in rel.parts)
        if not in_memory or p.suffix.lower() not in (".md", ".txt"):
            continue
        try:
            lines = read_text(p).splitlines()
        except (OSError, UnicodeDecodeError) as e:
            _record_scan_error(errors, p, e)
            continue
        file_hits = []
        for i, line in enumerate(lines, 1):
            normalized = line.casefold()
            found = [term for term in terms if term in normalized]
            if found:
                file_hits.append((i, line.strip()[:160], found))
        if file_hits:
            score = sum(len(found) for _, _, found in file_hits)
            matches.append((score, rel.as_posix(), file_hits))
    matches.sort(key=lambda item: (-item[0], item[1]))
    total = 0
    for score, rel, file_hits in matches:
        for line_no, excerpt, found in file_hits:
            if total >= limit:
                break
            print(f"[{score}] {rel}:{line_no}: {excerpt}  (命中：{', '.join(found)})")
            total += 1
        if total >= limit:
            break
    print(f"检索完成：返回 {total} 行，扫描 {len(matches)} 个命中文件；词面搜索不做语义推断。")
    _report_scan_errors(errors)


def _layers_on_scope_chain(root: Path, scope: Path, errors=None):
    """返回工作区根至目标路径上的记忆层，不扫描兄弟目录。"""
    target_layer = scope if LAYER_RE.match(scope.name) else None
    target = scope.parent if target_layer else (scope.parent if scope.is_file() else scope)
    rel = target.relative_to(root)
    dirs = [root]
    current = root
    for part in rel.parts:
        current = current / part
        dirs.append(current)
    selected = []
    excluded = declared_exclusions(root, errors)
    for directory in dirs:
        if is_declared_exclusion(root, directory, excluded, errors):
            continue
        try:
            layers = sorted(p for p in directory.iterdir()
                            if p.is_dir() and not p.is_symlink() and LAYER_RE.match(p.name))
        except OSError as e:
            _record_scan_error(errors, directory, e)
            continue
        if not layers:
            continue
        expected = to_cn(expected_layer_depth(directory, root, errors))
        selected.append(next((p for p in layers if LAYER_RE.match(p.name).group(1) == expected), layers[0]))
    if target_layer and not is_declared_exclusion(root, target_layer, excluded, errors) and target_layer not in selected:
        selected.append(target_layer)
    # 同一路径下重复层名/异常布局不应导致重复校验。
    return list(dict.fromkeys(selected))


def _print_workflow_status(root: Path, layers, errors=None) -> None:
    statuses = []
    for layer in layers:
        todo = layer / "5_代办.md"
        if not todo.is_file():
            continue
        try:
            text = read_text(todo)
        except (OSError, UnicodeDecodeError) as e:
            _record_scan_error(errors, todo, e)
            continue
        match = re.search(r"## 🚦[^\n]*\n(.*?)(?=\n## |\Z)", text, re.S)
        if match:
            statuses.append((layer, match.group(1)))
    if not statuses:
        print("  （相关层没有 🚦 交付状态段）")
        return
    for layer, block in statuses:
        label = layer.relative_to(root).as_posix()
        print(f"  [{label}/5_代办.md]")
        for line in block.strip("\n").splitlines():
            if line.strip():
                print(f"    {line.rstrip()}")


# ---------- 全量接手审计（显式调用；快速接手不遍历兄弟层） ----------
def cmd_takeover_full(args) -> None:
    """完整盘点记忆层、按需范围检查并校验记忆指纹。"""
    root = Path(args.workspace).resolve()
    if not root.is_dir():
        sys.exit(f"工作区不存在：{root}")
    by = args.by or local_agent_name()
    errors = []
    print(f"=== 接手检查 {root} ===")

    # 0) 通用记忆文件夹（记忆_通用）
    print("\n[0] 通用记忆文件夹（记忆_通用）：")
    try:
        universal_hits = sorted(p for p in root.iterdir()
                                if p.is_dir() and not p.is_symlink() and p.name == UNIVERSAL_DIR)
    except OSError as e:
        universal_hits = []
        _record_scan_error(errors, root, e)
    if universal_hits:
        for u in universal_hits:
            print(f"  ✓ 已建：{u}")
    else:
        print(f"  ⚠ 工作区尚未建 {UNIVERSAL_DIR}（跨层通用知识）")
        print(f'     用户首次说「这是通用的」时跑：{tool_command()} 建层 "{root}" --通用')

    # 1) 已有哪些记忆层（任意层数）
    hits = sorted(iter_memory_layers(root, errors))
    print(f"\n[1] 已有记忆层 {len(hits)} 个：")
    for h in hits:
        exp = expected_layer_depth(h.parent, root, errors)
        mark = "✓" if to_cn(exp) == LAYER_RE.match(h.name).group(1) else "⚠层号与深度不符"
        print(f"  {mark} {h}")

    # 2) 层级完整性检查（候选只作提示，按分层方案判断，不自动建层）
    print("\n[2] 层级完整性检查：")
    cmd_check(argparse.Namespace(workspace=str(root), scope=getattr(args, "scope", ""), max_depth=0))

    # 3) 每个记忆层做并发校验（检测其他 Agent/Harness 的改动）
    print("\n[3] 各层并发校验：")
    for h in hits:
        cmd_verify(argparse.Namespace(workspace=str(h.parent), layer_dir=h.name,
                                      refresh=False, by=by))

    # 4) 联动提示：临时脚本库配置状态（scratchpad 节点0）
    print("\n[4] 联动检查（cross-agent-scratchpad）：")
    try:
        cfg = json.loads(LOCAL_CONFIG.read_text(encoding="utf-8-sig"))
        tsg_root = cfg.get("temp_script_root", "")
        ok = bool(tsg_root) and os.path.isdir(tsg_root)
        print(f"  本机临时脚本库：{tsg_root or '（未配置）'}  可达：{'是' if ok else '否/未配置'}")
        if not ok:
            print("  ⚠ 按协议必须先询问用户库路径，绝不擅自选路径、绝不静默回退到工作区。")
    except Exception:
        print("  本机配置不可读（未配置）。按协议先询问用户临时脚本库路径。")
    # 5) 交付流程状态（cross-agent-dev-workflow 的阶段状态机存在 5_代办.md）
    print("\n[5] 交付流程状态（cross-agent-dev-workflow）：")
    status_layers = []
    for h in hits:
        todo = h / "5_代办.md"
        if not todo.is_file():
            continue
        try:
            text = read_text(todo)
        except (OSError, UnicodeDecodeError) as e:
            _record_scan_error(errors, todo, e)
            continue
        m = re.search(r"## 🚦[^\n]*\n(.*?)(?=\n## |\Z)", text, re.S)
        if m:
            status_layers.append((h, m.group(1)))
    if status_layers:
        h, block = status_layers[0]
        print(f"  （{h.relative_to(root).as_posix() if h.parent != root else '根层'}/5_代办.md）")
        for line in block.strip("\n").splitlines():
            if line.strip():
                print(f"    {line.rstrip()}")
        if len(status_layers) > 1:
            print(f"  （另有 {len(status_layers) - 1} 层也有 🚦 状态段：{', '.join(x[0].name for x in status_layers[1:])}）")
    else:
        print("  （无 🚦 状态段：未使用 cross-agent-dev-workflow，或尚未建立状态段）")
    print("\n后续：按当前任务路径选择记忆层，只读相关索引和主题文件；首次接手或信息不足时再扩大读取范围。")
    _report_scan_errors(errors)


# ---------- 快速接手（默认）：根索引 + 目标路径上的层 ----------
def cmd_takeover(args) -> None:
    """读取/校验当前任务范围；--full-audit 才遍历整个记忆树。"""
    if getattr(args, "full_audit", False):
        return cmd_takeover_full(args)
    root = Path(args.workspace).resolve()
    if not root.is_dir():
        sys.exit(f"工作区不存在：{root}")
    by = args.by or local_agent_name()
    scope = resolve_scope(root, getattr(args, "scope", ""))
    errors = []
    excluded = declared_exclusions(root, errors)
    scope_excluded = is_declared_exclusion(root, scope, excluded, errors)
    layers = [] if scope_excluded else _layers_on_scope_chain(root, scope, errors)
    print(f"=== 快速接手 {root} ===")
    print(f"任务范围：{scope}")
    universal = root / UNIVERSAL_DIR
    print(f"通用记忆：{'已存在' if universal.is_dir() else '未建立'}")
    print("相关记忆层：")
    if scope_excluded:
        print("  （任务范围位于根索引声明的例外目录内；不读取该目录中的记忆层。）")
    elif not layers:
        print("  （范围路径上未发现记忆层；若这是首次接手，请按项目结构做一次初始化研究。）")
    for layer in layers:
        expected = to_cn(expected_layer_depth(layer.parent, root))
        mark = "" if LAYER_RE.match(layer.name).group(1) == expected else "（层号与路径深度不一致，请核实分层方案）"
        print(f"  - {layer.relative_to(root).as_posix()}{mark}")
        index_path = layer / "0_索引.md"
        if index_path.is_file():
            print(f"    路由索引：{index_path}")
        cmd_verify(argparse.Namespace(workspace=str(layer.parent), layer_dir=layer.name,
                                      refresh=False, by=by))
    print("交付状态：")
    _print_workflow_status(root, layers, errors)
    print("临时脚本库：")
    try:
        cfg = json.loads(LOCAL_CONFIG.read_text(encoding="utf-8-sig"))
        tsg_root = cfg.get("temp_script_root", "")
        ok = bool(tsg_root) and os.path.isdir(tsg_root)
        print(f"  {tsg_root or '（未配置）'}  可达：{'是' if ok else '否/未配置'}")
        if not ok:
            print("  按 cross-agent-scratchpad-skill 规则，使用/新建临时脚本前先确认库路径。")
    except Exception:
        print("  配置不可读；使用/新建临时脚本前先按 scratchpad 规则处理。")
    print("快速模式不扫描兄弟模块，也不做层级完整性审计。需要时运行：检查 <工作区> 或 接手 <工作区> --full-audit。")
    print("读取建议：先读相关 0_索引.md 与 5_代办.md；其他主题文件按本次任务再打开。")
    _report_scan_errors(errors)


def _resolve_mem_dir(workspace: str, layer_dir: str) -> Path:
    if layer_dir:
        base = Path(workspace).resolve() if workspace else Path.cwd()
        mem = base / layer_dir
    else:
        mem = Path(workspace).resolve() if workspace else None
        if mem is None:
            sys.exit("请用 --层 <记忆第X层> 或直接给 <记忆文件夹路径>")
    if not mem.is_dir() or not (LAYER_NAME_RE.match(mem.name) or mem.name == UNIVERSAL_DIR):
        sys.exit(f"不是合法的 记忆第X层 / {UNIVERSAL_DIR} 文件夹：{mem}")
    return mem


def main() -> None:
    configure_console()
    ap = argparse.ArgumentParser(description="记忆管家（cross-agent-memory 辅助工具；层号=记忆层级序数，层数 1~99 不限）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("建层", help="就地创建 记忆第X层（默认仅 0_索引+5_代办）；--完整模板 创建全部六类文档；--通用 建中央 记忆_通用")
    p.add_argument("target", help="要在哪个文件夹里建（就地嵌入）")
    p.add_argument("--层", required=False, default="", help="层号：中文数字（一/二/三/四…）或阿拉伯数字（1/2/3/4…）；应等于记忆层级序数（根=一）")
    p.add_argument("--通用", action="store_true", help="建中央 记忆_通用/（与 --层 互斥）")
    p.add_argument("--完整模板", action="store_true", help="兼容旧版：同时创建架构/踩坑/偏好/配方/待办/配合六类文档")
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("扫描", help="列出工作区里已有的 记忆第X层（任意层数）")
    p.add_argument("workspace")
    p.set_defaults(fn=cmd_scan)

    p = sub.add_parser("检查", help="完整层级审计：按分层规则列出候选；不自动创建记忆层")
    p.add_argument("workspace")
    p.add_argument("--scope", default="", help="只审计工作区内指定目录（默认完整工作区）")
    p.add_argument("--max-depth", type=int, default=0, help="可选深度上限；默认 0 表示不设上限")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("索引", help="更新当前标准记忆文件指纹，并清理已删除文件的旧指纹")
    p.add_argument("workspace", nargs="?", default="", help="所在工作区/父文件夹")
    p.add_argument("--层", dest="layer_dir", default="", help="记忆第X层（如 记忆第四层）")
    p.add_argument("--by", default="", help="更新者署名（agent/harness 名）")
    p.set_defaults(fn=cmd_index)

    p = sub.add_parser("校验", help="并发检测：报告上次记录后被外部改动的记忆文件")
    p.add_argument("workspace", nargs="?", default="")
    p.add_argument("--层", dest="layer_dir", default="")
    p.add_argument("--refresh", action="store_true", help="检测后合并完成时刷新指纹档案")
    p.add_argument("--by", default="")
    p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("刷新通用", help="重建所有 记忆第X层/0_索引.md 的「🔗 通用知识」段（保留摘要/补新/删失效）并刷新指纹")
    p.add_argument("workspace")
    p.add_argument("--by", default="", help="更新者署名（默认取本机配置 agent_name）")
    p.set_defaults(fn=cmd_refresh_universal)

    p = sub.add_parser("检索", help="词面检索记忆；支持按范围和结果数缩小读取")
    p.add_argument("workspace")
    p.add_argument("keyword", help="主关键词或短语（大小写不敏感、词面匹配）")
    p.add_argument("--term", action="append", default=[], help="追加关键词；可多次传入")
    p.add_argument("--scope", default="", help="只搜索工作区内指定目录")
    p.add_argument("--top", type=int, default=20, help="最多返回的命中行数（默认 20）")
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("接手", help="默认快速接手：校验任务路径上的记忆层；--full-audit 才扫描整个工作区")
    p.add_argument("workspace")
    p.add_argument("--scope", default="", help="任务目标目录/文件；仅读取目标路径上的记忆层，不扫兄弟模块")
    p.add_argument("--full-audit", action="store_true", help="显式执行完整记忆层扫描、层级审计和全层指纹校验")
    p.add_argument("--by", default="", help="署名（默认取本机配置 agent_name）")
    p.set_defaults(fn=cmd_takeover)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
