#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
记忆管家 —— cross-agent-memory 的主工具（跨平台，需 Python 3.8+）

说明：判断该分几层（1~N 层，不设上限）、深度阅读并填写记忆文件，由 Agent 按 SKILL.md 自主完成。
本脚本只做机械操作。**层号约定 = 目录深度**：工作区根 = 第一层，向下一级 = 第二层……以此类推，
文件夹名形如 记忆第X层（X 为中文数字，一~九十九）。
  建层   就地创建 记忆第X层 文件夹（0_索引 + 6 件格式参考）；--层 接受中文数字（一/二/三/四…）或阿拉伯数字（1/2/3/4…）
  扫描   列出工作区里已有的 记忆第X层 文件夹（任意层数）
  检查   层级完整性检查：按目录深度推断每层应有的 记忆第X层，找出缺失的候选子模块/子工程
  索引   为某层的记忆文件生成/更新指纹档案（记忆索引.json：sha256 + mtime + 更新者）
  校验   对比当前文件与指纹档案，报告被其他 Agent/Harness 改过的文件（并发检测）
  接手   一键接手入口：扫描 + 层级完整性检查 + 各层并发校验 + 临时脚本库配置联动检查
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
    r"记忆第[一二三四五六七八九十]{1,3}层)$"
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
    """目录深度 → 应建层号：根=第一层，向下一级=第二层……"""
    return len(dirpath.relative_to(root).parts) + 1


def tpl_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "_模板" / "记忆"


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


# ---------- 建层 ----------
def cmd_build(args) -> None:
    target = Path(args.target).resolve()
    n = parse_layer(getattr(args, "层"))
    if not n:
        sys.exit("层号非法（用中文数字 一/二/三/四…九十九，或阿拉伯数字 1/2/3/4…99）")
    if not target.is_dir():
        sys.exit(f"目标文件夹不存在：{target}")
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
    print("  ⚠ 层号应与目录深度一致（根=一，向下一级+1）；层数与各层职责请记入根记忆层 0_索引 的「分层方案」。")


# ---------- 扫描 ----------
def cmd_scan(args) -> None:
    root = Path(args.workspace).resolve()
    if not root.is_dir():
        sys.exit(f"工作区不存在：{root}")
    hits = sorted(p for p in root.rglob("*") if p.is_dir() and LAYER_NAME_RE.match(p.name))
    print(f"扫描 {root} 下的记忆文件夹（共 {len(hits)} 个）：")
    if not hits:
        print("  （未找到 记忆第X层，可用 建层 命令就地创建）")
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
    print(f"层级完整性检查 {root} ...（层号=目录深度：根=记忆第一层，向下一级+1）")
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


# ---------- 索引（生成/更新指纹档案） ----------
def cmd_index(args) -> None:
    mem_dir = _resolve_mem_dir(args.workspace, args.layer_dir)
    data = load_index(mem_dir)
    files = data.setdefault("files", {})
    n = 0
    for name in CORE_FILES + [INDEX_NAME]:
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
    for name in CORE_FILES:
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


# ---------- 接手（一键入口：扫描 + 层级完整性检查 + 各层并发校验） ----------
def cmd_takeover(args) -> None:
    """把两技能共用的「接手任务第一步」工具化：一次跑完 扫描/检查/校验，
    并提示本机临时脚本库配置状态（联动 cross-agent-scratchpad-skill）。"""
    root = Path(args.workspace).resolve()
    if not root.is_dir():
        sys.exit(f"工作区不存在：{root}")
    by = args.by or local_agent_name()
    print(f"=== 接手检查 {root} ===")

    # 1) 已有哪些记忆层（任意层数）
    hits = sorted(p for p in root.rglob("*") if p.is_dir() and LAYER_NAME_RE.match(p.name))
    print(f"\n[1] 已有记忆层 {len(hits)} 个：")
    for h in hits:
        exp = expected_layer_depth(h.parent, root)
        mark = "✓" if to_cn(exp) == LAYER_RE.match(h.name).group(1) else "⚠层号与深度不符"
        print(f"  {mark} {h}")

    # 2) 层级完整性检查（缺对应层号记忆层的候选子模块）
    print()
    cmd_check(argparse.Namespace(workspace=str(root)))

    # 3) 每个记忆层做并发校验（检测其他 Agent/Harness 的改动）
    print()
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
    print("\n后续：有记忆→深读各件再动手（先看根记忆层 0_索引 的「分层方案」）；缺层→建层+深度填写；无记忆→深读整个项目后自主定层数（1~N 层，不设上限）。")


def _resolve_mem_dir(workspace: str, layer_dir: str) -> Path:
    if layer_dir:
        base = Path(workspace).resolve() if workspace else Path.cwd()
        mem = base / layer_dir
    else:
        mem = Path(workspace).resolve() if workspace else None
        if mem is None:
            sys.exit("请用 --层 <记忆第X层> 或直接给 <记忆文件夹路径>")
    if not mem.is_dir() or not LAYER_NAME_RE.match(mem.name):
        sys.exit(f"不是合法的 记忆第X层 文件夹：{mem}")
    return mem


def main() -> None:
    ap = argparse.ArgumentParser(description="记忆管家（cross-agent-memory 辅助工具；层号=目录深度，层数 1~99 不限）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("建层", help="就地创建 记忆第X层（0_索引+6件格式参考）")
    p.add_argument("target", help="要在哪个文件夹里建（就地嵌入）")
    p.add_argument("--层", required=True, help="层号：中文数字（一/二/三/四…）或阿拉伯数字（1/2/3/4…）；应等于目录深度（根=一）")
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("扫描", help="列出工作区里已有的 记忆第X层（任意层数）")
    p.add_argument("workspace")
    p.set_defaults(fn=cmd_scan)

    p = sub.add_parser("检查", help="层级完整性检查：按目录深度找缺记忆层的候选子模块")
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

    p = sub.add_parser("接手", help="一键接手入口：扫描记忆层 + 层级完整性检查 + 各层并发校验 + 联动配置检查")
    p.add_argument("workspace")
    p.add_argument("--by", default="", help="署名（默认取本机配置 agent_name）")
    p.set_defaults(fn=cmd_takeover)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
