#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布管家 —— cross-agent-dev-workflow-skill 的工具层兜底。

命令：
  校验技能 <技能目录>          按 Agent Skills 规范校验 SKILL.md
  三位一体 <套件根目录>         校验三技能互链对称（联动文档双向在位、SKILL.md 互提）
  打包 <技能目录> [--out <zip>] 打发布 zip（排除缓存/记忆/系统文件）
  发布检查 <套件根目录>         zip 新鲜度 / README 覆盖 / LICENSE / ship 清单总检

Python 3.8+，无第三方依赖。退出码：0=全过，1=有 ✗。
"""

import hashlib
import os
import re
import sys
import time
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

# 打包/发布时绝不入 zip 的东西（缓存、记忆、系统文件、版本库）
EXCLUDE_DIRS = {"__pycache__", ".git", ".idea", ".vscode", "记忆_通用", "node_modules"}
EXCLUDE_DIR_RE = re.compile(r"^记忆第.+层$")
EXCLUDE_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}
EXCLUDE_SUFFIX = (".pyc", ".pyo", ".log", ".tmp")

SUITE_SKILLS = [
    "cross-agent-memory-skill",
    "cross-agent-scratchpad-skill",
    "cross-agent-dev-workflow-skill",
]

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
FRONT_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n", re.S)
KEY_RE = re.compile(r"^([A-Za-z][\w-]*):[ \t]*(.*)$", re.M)
LINK_RE = re.compile(r"\]\(([^)#\s]+)\)")


def ok(msg):
    print(f"  ✔ {msg}")


def warn(msg):
    print(f"  ⚠ {msg}")


def fail(msg):
    print(f"  ✗ {msg}")


def read_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def parse_frontmatter(text):
    """极简 YAML 解析：只取顶层 key: value（本套件 frontmatter 均为单行值）。"""
    m = FRONT_RE.match(text)
    if not m:
        return None, None
    raw, body = m.group(1), text[m.end():]
    meta = {}
    for km in KEY_RE.finditer(raw):
        key, val = km.group(1), km.group(2).strip().strip('"').strip("'")
        if key not in meta and val:
            meta[key] = val
    return meta, body


def load_skill(skill_dir):
    skill_md = os.path.join(skill_dir, "SKILL.md")
    if not os.path.isfile(skill_md):
        return None
    try:
        text = read_text(skill_md)
    except UnicodeDecodeError:
        fail(f"SKILL.md 不是合法 UTF-8：{skill_dir}")
        return None
    meta, body = parse_frontmatter(text)
    return {"dir": skill_dir, "dirname": os.path.basename(os.path.normpath(skill_dir)),
            "meta": meta or {}, "body": body or "", "text": text}


def cmd_validate_skill(skill_dir):
    """校验技能 <技能目录>：SKILL.md 规范 + 引用文件在位。"""
    print(f"=== 校验技能 {skill_dir} ===")
    errors = 0
    sk = load_skill(skill_dir)
    if sk is None:
        fail("缺少 SKILL.md（或编码错误）")
        return 1
    ok("SKILL.md 存在且为 UTF-8")

    name = sk["meta"].get("name")
    desc = sk["meta"].get("description")
    if not name:
        fail("frontmatter 缺少 name"); errors += 1
    else:
        if len(name) > 64 or not NAME_RE.match(name):
            fail(f"name 不合规：{name!r}（≤64 字符，仅小写字母/数字/连字符，不连续连字符）"); errors += 1
        elif name != sk["dirname"] and sk["dirname"] != name + "-skill":
            warn(f"name={name} 与目录名 {sk['dirname']} 不一致（套件容忍 name 或 name-skill 两种）")
        else:
            ok(f"name 合规：{name}")
    if not desc:
        fail("frontmatter 缺少 description"); errors += 1
    elif len(desc) > 1024:
        fail(f"description 超长：{len(desc)} > 1024 字符"); errors += 1
    else:
        ok(f"description 合规（{len(desc)} 字符）")

    lines = sk["text"].count("\n") + 1
    if lines >= 500:
        warn(f"SKILL.md 共 {lines} 行 ≥500，建议细则移入 references/（渐进式披露）")
    else:
        ok(f"SKILL.md {lines} 行（<500）")

    missing = []
    for lm in LINK_RE.finditer(sk["body"]):
        target = lm.group(1)
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith(("#", "/", "http")):
            continue
        target = target.split("#")[0]
        if target and not os.path.exists(os.path.join(sk["dir"], target)):
            missing.append(target)
    if missing:
        fail(f"正文引用了不存在的文件：{', '.join(sorted(set(missing)))}"); errors += 1
    else:
        ok("正文相对链接全部在位")

    print(f"结论：{'✗ 未通过' if errors else '✔ 通过'}")
    return 1 if errors else 0


def _linkage_doc_name(other_name):
    """联动文档命名：对方 name.md、name-skill.md 或去掉 -skill 的短名.md。"""
    cands = [f"{other_name}.md"]
    if other_name.endswith("-skill"):
        cands.append(f"{other_name[:-6]}.md")
    else:
        cands.append(f"{other_name}-skill.md")
    return cands


def cmd_trinity(root):
    """三位一体 <套件根>：三技能互链对称校验。"""
    print(f"=== 三位一体检查 {root} ===")
    errors = 0
    skills = {}
    for d in SUITE_SKILLS:
        p = os.path.join(root, d)
        sk = load_skill(p)
        if sk is None:
            fail(f"缺少技能目录/SKILL.md：{d}"); errors += 1
        else:
            skills[d] = sk
            ok(f"{d}（name={sk['meta'].get('name', '?')}）")
    dirs = list(skills.values())
    for a in dirs:
        for b in dirs:
            if a is b:
                continue
            b_name = b["meta"].get("name") or b["dirname"]
            link_dir = os.path.join(a["dir"], "联动")
            found = None
            if os.path.isdir(link_dir):
                for fn in os.listdir(link_dir):
                    if fn in _linkage_doc_name(b_name) or fn[:-3] in [b_name, b["dirname"]]:
                        found = os.path.join(link_dir, fn); break
            if not found and os.path.isdir(link_dir):
                for fn in os.listdir(link_dir):
                    try:
                        if b_name in read_text(os.path.join(link_dir, fn)):
                            found = os.path.join(link_dir, fn); break
                    except (UnicodeDecodeError, OSError):
                        pass
            if found:
                ok(f"{a['dirname']}/联动 → {os.path.basename(found)}（指向 {b_name}）")
            else:
                fail(f"{a['dirname']}/联动/ 缺少指向 {b_name} 的文档"); errors += 1
            if b_name in a["text"] or b["dirname"] in a["text"]:
                pass
            else:
                fail(f"{a['dirname']}/SKILL.md 未提及 {b_name}"); errors += 1
    ok("互提检查完成（上表无 ✗ 即对称）") if errors == 0 else None
    print(f"结论：{'✗ 互链不完整' if errors else '✔ 三位一体互链完整对称'}")
    return 1 if errors else 0


def _ship_files(skill_dir):
    """返回应进 zip 的相对路径列表（应用排除规则后）。

    排除运行时记忆（记忆第N层/记忆_通用）与缓存/系统文件；但 `_模板/` 下的
    同名目录是制品模板（skill 的一部分），必须入包。"""
    out = []
    for base, dirs, files in os.walk(skill_dir):
        rel = os.path.relpath(base, skill_dir)
        in_tpl = rel != "." and "_模板" in rel.split(os.sep)
        if not in_tpl:
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not EXCLUDE_DIR_RE.match(d)]
        for fn in files:
            if fn in EXCLUDE_FILES or fn.endswith(EXCLUDE_SUFFIX):
                continue
            out.append(os.path.relpath(os.path.join(base, fn), skill_dir).replace(os.sep, "/"))
    return sorted(out)


def _fmt_time(mtime):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))


def cmd_pack(skill_dir, out_zip=None):
    """打包 <技能目录> [--out <zip>]。"""
    if not os.path.isfile(os.path.join(skill_dir, "SKILL.md")):
        fail(f"不是技能目录（缺 SKILL.md）：{skill_dir}")
        return 1
    if out_zip is None:
        out_zip = os.path.join(os.path.dirname(os.path.abspath(skill_dir)),
                               os.path.basename(os.path.normpath(skill_dir)) + ".zip")
    files = _ship_files(skill_dir)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in files:
            zf.write(os.path.join(skill_dir, rel), rel)
    h = hashlib.sha256(open(out_zip, "rb").read()).hexdigest()[:16]
    size = os.path.getsize(out_zip)
    print(f"✔ 已打包 {len(files)} 个文件 → {out_zip}")
    print(f"  大小 {size:,} 字节 · sha256:{h} · {_fmt_time(os.path.getmtime(out_zip))}")
    return 0


def cmd_release_check(root):
    """发布检查 <套件根>：zip 新鲜度 / README 覆盖 / LICENSE / ship 清单。"""
    print(f"=== 发布检查 {root} ===")
    errors = warns = 0
    if not os.path.isfile(os.path.join(root, "LICENSE")):
        fail("套件根缺少 LICENSE"); errors += 1
    else:
        ok("LICENSE 在位")
    try:
        readme = read_text(os.path.join(root, "README.md"))
    except OSError:
        readme = ""
        fail("套件根缺少 README.md"); errors += 1

    for d in SUITE_SKILLS:
        p = os.path.join(root, d)
        if not os.path.isdir(p):
            fail(f"缺少技能目录：{d}"); errors += 1
            continue
        name = (load_skill(p) or {}).get("meta", {}).get("name", d)
        if name in readme or d in readme:
            ok(f"README 已覆盖 {d}")
        else:
            fail(f"README 未提及 {d}"); errors += 1
        zip_path = os.path.join(root, d + ".zip")
        ship = _ship_files(p)
        newest = max((os.path.getmtime(os.path.join(p, rel)) for rel in ship), default=0)
        if not os.path.isfile(zip_path):
            warn(f"{d}.zip 不存在（如需分发请先 打包）"); warns += 1
            continue
        zip_mtime = os.path.getmtime(zip_path)
        if newest > zip_mtime + 2:
            fail(f"{d}.zip 已过期：最新源文件 {_fmt_time(newest)} 晚于 zip {_fmt_time(zip_mtime)}，请重新打包")
            errors += 1
        else:
            ok(f"{d}.zip 新鲜（{len(ship)} 个文件入包）")

    print(f"结论：{'✗ 存在必须修复项' if errors else '✔ 可发布'}（⚠ {warns} 项提醒）")
    return 1 if errors else 0


USAGE = __doc__


def main(argv):
    if len(argv) < 2:
        print(USAGE)
        return 0 if len(argv) < 1 else 1
    cmd, args = argv[1], argv[2:]
    if cmd == "校验技能" and len(args) >= 1:
        return cmd_validate_skill(args[0])
    if cmd == "三位一体" and len(args) >= 1:
        return cmd_trinity(args[0])
    if cmd == "打包" and len(args) >= 1:
        out = None
        if "--out" in args:
            i = args.index("--out")
            if i + 1 < len(args):
                out = args[i + 1]
                args = args[:i] + args[i + 2:]
        return cmd_pack(args[0], out)
    if cmd == "发布检查" and len(args) >= 1:
        return cmd_release_check(args[0])
    print(USAGE)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
