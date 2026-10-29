# 工具 · 发布管家

`发布管家.py`（Python 3.8+，跨平台，无第三方依赖）是 cross-agent-dev-workflow-skill 的工具层兜底，对应协议里的阶段 3（整理发布）。`发布管家.ps1` 是 Windows 薄封装（转发到 Python）。

保留 3.8 兼容是为了兼容旧环境；Python 3.8 已结束上游支持，建议使用仍受支持的 Python 版本。[Python 3.8.20 发布说明](https://www.python.org/downloads/release/python-3820/)

| 命令 | 作用 | 对应协议 |
|---|---|---|
| `校验技能 <技能目录>` | 按 Agent Skills 规范校验 SKILL.md（name/description 规则、行数、相对链接在位） | 阶段 2 逐文件审查（机器可查的先机器查） |
| `三位一体 <套件根>` | 三技能互链对称校验（联动文档双向在位、SKILL.md 互提） | 阶段 3 口径同步 |
| `打包 <技能目录> [--out <zip>]` | 打发布 zip，自动排除 `__pycache__`/`.pyc`/`记忆第*层`/`记忆_通用`/`.git`/系统文件 | 阶段 3 发布打包 |
| `发布检查 <套件根>` | 要求三个 ZIP 全部存在；核对成员和内容与源文件逐字节一致、CRC、独立包 LICENSE、README 覆盖和入包文件 | 阶段 3 发布清单 |

退出码：`0` 全过，`1` 有 ✗（可直接接 CI / 脚本判断）。

> 工具不是必须的——没有 Python 时按 SKILL.md 协议手工执行完全成立。
