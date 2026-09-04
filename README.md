# cross-agent-skills — 跨 Agent / 跨 Harness 配套技能包

两个共生设计的 Agent Skills，共享同一个「接手任务入口」，一次深度阅读同时服务两者：

| 技能 | 职责 |
|---|---|
| [cross-agent-memory-skill](cross-agent-memory-skill/) | **就地记忆**：在真实工作区文件夹树里就地创建/维护分层记忆（记忆第一/二/三层，每层 0_索引 + 6 件），先读→合并→写回，sha256 指纹并发检测，主动补齐新增子工程的记忆层 |
| [cross-agent-scratchpad-skill](cross-agent-scratchpad-skill/) | **临时脚本治理**：临时脚本一律存用户指定的外部库，先复用后创建，遗留物分级审计（复用→迁入 / 无价值→清理 / 来源不明→隔离等确认），真实工程文件绝不自动删 |

## 设计亮点

- **跨 Agent / 跨 Harness**：标准 SKILL.md 格式，ZCode / Codex CLI / Cursor / Claude Code 等任何支持 skills 的工具都能加载。
- **工具层兜底协议**：两个 Python 主工具提供 `接手` 一键入口、原子 JSON 写入、索引指纹并发检测、库外文件清理守卫——不是只靠提示词纪律。
- **深度联动**：统一署名（`~/.agent-tsg/config.json` 的 `agent_name` 两工具共用）；审计结论按约定写入记忆对应文件；memory 的指纹思想与 scratchpad 的外部库思想互相借鉴。

## 安装

各技能目录内有 `安装指引.md`；把对应文件夹拷入目标 harness 的 skills 目录即可（如 ZCode：`~/.zcode/skills/`，Claude Code：`~/.claude/skills/`）。

## 环境要求

- 无必须依赖（协议可纯手工执行）；推荐 Python 3.8+ 以使用辅助工具。
