#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
记忆管家 —— cross-agent-memory 的主工具（跨平台，需 Python 3.8+）

说明：判断该分几层（1~N 层，不设上限）、深度阅读并填写记忆文件，由 Agent 按 SKILL.md 自主完成。
本脚本只做机械操作。**层号约定 = 记忆层级序数**：工作区根 = 第一层；某文件夹的层号 =
根到它的路径上拥有记忆层的祖先数 + 1（分组文件夹如 platforms 不建层就不占层号）。
文件夹名形如 记忆第X层（X 为中文数字，一~九十九）。
  建层   就地创建 记忆第X层 文件夹（0_索引 + 6 件格式参考）；--层 接受中文数字（一/二/三/四…）或阿拉伯数字（1/2/3/4…）
         加 --通用 则在目标文件夹下建中央 记忆_通用/（0_通用索引 + 4 件，任何层都能引用）
  扫描   列出工作区里已有的 记忆第X层 文件夹（任意层数，含 记忆_通用）
  检查   层级完整性检查：按记忆层级序数推断每处应有的 记忆第X层，找出缺失的候选子模块/子工程
  索引   为某层的记忆文件生成/更新指纹档案（记忆索引.json：sha256 + mtime + 更新者）
  校验   对比当前文件与指纹档案，报告被其他 Agent/Harness 改过的文件（并发检测）
  刷新通用 重建所有 记忆第X层/0_索引.md 的「🔗 通用知识」段（保留已有摘要，补新文件、删失效引用）
  检索   跨全部记忆层与 记忆_通用 全文检索关键词，输出 文件:行号:内容
  接手   一键接手入口：记忆_通用 检查 + 扫描 + 层级完整性检查 + 各层并发校验 + 交付流程状态 + 临时脚本库配置联动检查
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
# 支持一~九十九层（任意层数，由 Agent 深度研究项目后自主决定）
CN_DIGITS = "一二三四五六七八九"
LAYER_RE = re.compile(r"^记忆第([一二三四五六七八九十]{1,3})层$")
LAYER_NAME_RE = re.compile(r"^记忆第[一二三四五六七八九十]{1,3}层$")
# 检查时跳过的系统/依赖/产物/记忆/通用源码目录（平台名不排除，让它们能作为候选）
SKIP_NAMES = re.compile(
    r"^(node_modules|\.git|__pycache__|\.venv|venv|dist|build|\.idea|\.vscode|release|"
    r"public|src|server|desktop|docs|scripts|assets|test|tests|TMP_|文件备份|已生成|"
    r"记忆第[一二三四五六七八九十]{1,3}层|记忆_通用)$"
)
# 判定「独立模块/子工程」的项目标志文件（有其一即视为候选）
PROJECT_MARKERS = (
    "README.md", "readme.md", "README.txt", "package.json", "pyproject.toml",
    "setup.py", "requirements.txt", "Cargo.toml", "pom.xml", "build.gradle",
    "pubspec.yaml", "CMakeLists.txt", "go.mod", ".git", "composer.json", "*.csproj",
)
MAX_CHECK_DEPTH = 3  # 检查时向下递归的层数（相对工作区根）；更深处对其单独执行 检查


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


def expected_layer_depth(dirpath: Path, root: Path) -> int:
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
        if any(p.is_dir() and LAYER_NAME_RE.match(p.name) for p in ancestor.iterdir()):
            n += 1
    return n + 2  # 1（根层）+ 祖先已占层数 + 1（本层）


def tpl_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "_模板" / "记忆"


def tpl_universal_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "_模板" / "记忆_通用"


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
    p.write_text(s, encoding="utf-8", newline="\n")


def atomic_write_text(p: Path, s: str) -> None:
    """原子写入：先写临时文件再 os.replace，避免并发写把文件截断成半截 JSON。"""
    tmp = p.with_suffix(p.suffix + f".tmp{os.getpid()}")
    tmp.write_text(s, encoding="utf-8", newline="\n")
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
    for name in CORE_FILES:
        src = tpl_dir() / name
        write_text(mem_dir / name, read_text(src) if src.exists() else f"# {name}\n")
    # 真正生成初始指纹档案（对模板原样文件逐个记录 sha256），否则 校验 会误报"尚无指纹档案"
    data = load_index(mem_dir)
    files = data.setdefault("files", {})
    for name in CORE_FILES:
        p = mem_dir / name
        if p.is_file():
            files[name] = {
                "sha256": sha256_of(p),
                "mtime": datetime.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
                "bytes": p.stat().st_size,
            }
    save_index(mem_dir, data)
    print(f"✔ 已就地创建：{mem_dir}\\（含 0_索引 + 6 件格式参考 + {INDEX_NAME}）")
    print("  ⚠ 请按 SKILL.md 深度理解该层内容 + 融合对话经验后填写，不是留空。")
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
        print(f"     python 工具\\记忆管家.py 建层 <工作区> --通用")


# ---------- 扫描 ----------
def cmd_scan(args) -> None:
    root = Path(args.workspace).resolve()
    if not root.is_dir():
        sys.exit(f"工作区不存在：{root}")
    hits = sorted(p for p in root.rglob("*") if p.is_dir() and LAYER_NAME_RE.match(p.name))
    universal_hits = sorted(p for p in root.iterdir() if p.is_dir() and p.name == UNIVERSAL_DIR)
    print(f"扫描 {root} 下的记忆文件夹（共 {len(hits)} 层，另 记忆_通用 {len(universal_hits)} 个）：")
    if not hits and not universal_hits:
        print("  （未找到 记忆第X层 或 记忆_通用，可用 建层 命令就地创建）")
    for u in universal_hits:
        print(f"  ✓ 通用  {u}")
    for h in hits:
        exp = expected_layer_depth(h.parent, root)
        mark = "✓" if to_cn(exp) == LAYER_RE.match(h.name).group(1) else "⚠层号与深度不符"
        print(f"  {mark} {h}")


# ---------- 层级完整性检查 ----------
def has_layer(d: Path) -> bool:
    return any(p.is_dir() and LAYER_NAME_RE.match(p.name) for p in d.iterdir())


def is_project_candidate(d: Path) -> bool:
    names = {p.name for p in d.iterdir()}
    for marker in PROJECT_MARKERS:
        if marker.startswith("*."):
            if any(n.endswith(marker[1:]) for n in names):
                return True
        elif marker in names:
            return True
    return False


def cmd_check(args) -> None:
    root = Path(args.workspace).resolve()
    if not root.is_dir():
        sys.exit(f"工作区不存在：{root}")
    print(f"层级完整性检查 {root} ...（%s）" % "层号=记忆层级序数（根=一；分组文件夹不建层就不占层号）")
    checked, missing = 0, []
    platforms = root / "platforms"

    def walk(d: Path, depth: int, forced: bool):
        nonlocal checked
        if depth > MAX_CHECK_DEPTH:
            return
        checked += 1
        exp = expected_layer_depth(d, root)
        if has_layer(d):
            pass  # 本层已建记忆，继续看下层
        elif forced or depth == 1 or is_project_candidate(d):
            missing.append((d, exp))
        # 向下递归：跳过系统/依赖/产物目录；platforms 的直接子目录视为强制候选
        if depth < MAX_CHECK_DEPTH:
            for child in sorted(d.iterdir()):
                if not child.is_dir():
                    continue
                if SKIP_NAMES.match(child.name):
                    continue
                walk(child, depth + 1, forced=(child.parent.name == "platforms"))

    walk(root, 0, forced=True)
    # 根自身（第一层）单独提示
    root_missing = not has_layer(root)
    print(f"  已检查 {checked} 个目录（含根，向下最多 {MAX_CHECK_DEPTH} 级；platforms 下各平台强制候选）。")
    if root_missing:
        print("  ⚠ 工作区根缺少 记忆第一层。")
    if missing:
        print("  ⚠ 以下候选文件夹缺少对应层号的记忆文件夹（应主动补齐，不等用户提醒）：")
        for d, exp in missing:
            print(f"    ✗ {d}  ← 应建 {layer_name(exp)}")
    else:
        print("  ✓ 未发现缺记忆层的候选子模块文件夹。")
    print("  说明：候选判定 = 一级子目录，或有项目标志文件（README/package.json/.git 等）的目录，或 platforms 下各平台。")
    print("        更深处模块请对其单独执行 检查；层号是否合适最终由 Agent 按分层方案判断。")


def _files_of(mem_dir: Path):
    """该记忆文件夹应维护指纹的文件清单：普通层 = 0_索引+6件；通用层 = 5 件通用模板。"""
    return UNIVERSAL_FILES if mem_dir.name == UNIVERSAL_DIR else CORE_FILES


# ---------- 索引（生成/更新指纹档案） ----------
def cmd_index(args) -> None:
    mem_dir = _resolve_mem_dir(args.workspace, args.layer_dir)
    data = load_index(mem_dir)
    files = data.setdefault("files", {})
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
    if not (root / UNIVERSAL_DIR).is_dir():
        sys.exit(f"工作区还没有 {UNIVERSAL_DIR}（先跑：python 工具\\记忆管家.py 建层 <工作区> --通用）")
    hits = sorted(p for p in root.rglob("*") if p.is_dir() and LAYER_NAME_RE.match(p.name))
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


# ---------- 检索（跨全部记忆层 + 记忆_通用 全文检索） ----------
def cmd_search(args) -> None:
    root = Path(args.workspace).resolve()
    if not root.is_dir():
        sys.exit(f"工作区不存在：{root}")
    kw = args.keyword
    total = 0
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.name == INDEX_NAME:
            continue
        rel = p.relative_to(root)
        in_memory = rel.parts[0] == UNIVERSAL_DIR or any(LAYER_NAME_RE.match(part) for part in rel.parts)
        if not in_memory or p.suffix.lower() not in (".md", ".txt"):
            continue
        try:
            lines = read_text(p).splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        shown = 0
        for i, line in enumerate(lines, 1):
            if kw in line:
                print(f"{rel.as_posix()}:{i}: {line.strip()[:80]}")
                total += 1
                shown += 1
                if shown >= 5:
                    break
    print(f"检索完成：命中 {total} 行（每文件最多显示 5 行；细节请打开对应记忆文件）。")


# ---------- 接手（一键入口：扫描 + 层级完整性检查 + 各层并发校验） ----------
def cmd_takeover(args) -> None:
    """把两技能共用的「接手任务第一步」工具化：一次跑完 扫描/检查/校验，
    并提示本机临时脚本库配置状态（联动 cross-agent-scratchpad-skill）。"""
    root = Path(args.workspace).resolve()
    if not root.is_dir():
        sys.exit(f"工作区不存在：{root}")
    by = args.by or local_agent_name()
    print(f"=== 接手检查 {root} ===")

    # 0) 通用记忆文件夹（记忆_通用）
    print("\n[0] 通用记忆文件夹（记忆_通用）：")
    universal_hits = sorted(p for p in root.iterdir() if p.is_dir() and p.name == UNIVERSAL_DIR)
    if universal_hits:
        for u in universal_hits:
            print(f"  ✓ 已建：{u}")
    else:
        print(f"  ⚠ 工作区尚未建 {UNIVERSAL_DIR}（跨层通用知识）")
        print(f"     用户首次说「这是通用的」时跑：python 工具\\记忆管家.py 建层 {root} --通用")

    # 1) 已有哪些记忆层（任意层数）
    hits = sorted(p for p in root.rglob("*") if p.is_dir() and LAYER_RE.match(p.name))
    print(f"\n[1] 已有记忆层 {len(hits)} 个：")
    for h in hits:
        exp = expected_layer_depth(h.parent, root)
        mark = "✓" if to_cn(exp) == LAYER_RE.match(h.name).group(1) else "⚠层号与深度不符"
        print(f"  {mark} {h}")

    # 2) 层级完整性检查（缺对应层号记忆层的候选子模块）
    print("\n[2] 层级完整性检查：")
    cmd_check(argparse.Namespace(workspace=str(root)))

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
        except (OSError, UnicodeDecodeError):
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
    print("\n后续：有记忆→深读各件再动手（先看根记忆层 0_索引 的「分层方案」）；缺层→建层+深度填写；无记忆→深读整个项目后自主定层数（1~N 层，不设上限）。")


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
    ap = argparse.ArgumentParser(description="记忆管家（cross-agent-memory 辅助工具；层号=记忆层级序数，层数 1~99 不限）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("建层", help="就地创建 记忆第X层（0_索引+6件格式参考）；--通用 建中央 记忆_通用")
    p.add_argument("target", help="要在哪个文件夹里建（就地嵌入）")
    p.add_argument("--层", required=False, default="", help="层号：中文数字（一/二/三/四…）或阿拉伯数字（1/2/3/4…）；应等于记忆层级序数（根=一）")
    p.add_argument("--通用", action="store_true", help="建中央 记忆_通用/（与 --层 互斥）")
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("扫描", help="列出工作区里已有的 记忆第X层（任意层数）")
    p.add_argument("workspace")
    p.set_defaults(fn=cmd_scan)

    p = sub.add_parser("检查", help="层级完整性检查：按记忆层级序数找缺记忆层的候选子模块")
    p.add_argument("workspace")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("索引", help="为某层记忆文件生成/更新指纹档案（记忆索引.json）")
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

    p = sub.add_parser("检索", help="跨全部记忆层与 记忆_通用 全文检索关键词（文件:行号:内容）")
    p.add_argument("workspace")
    p.add_argument("keyword")
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("接手", help="一键接手入口：记忆_通用检查 + 扫描记忆层 + 层级完整性检查 + 各层并发校验 + 交付流程状态 + 联动配置检查")
    p.add_argument("workspace")
    p.add_argument("--by", default="", help="署名（默认取本机配置 agent_name）")
    p.set_defaults(fn=cmd_takeover)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
