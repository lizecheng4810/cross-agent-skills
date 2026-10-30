# cross-agent-skills — 跨 Agent / 跨 Harness 三位一体技能套件

三个共生设计的 Agent Skills，**掌舵 · 记账 · 打扫**，密不可分：

> 📖 不想看技术文档？先读[《说人话版》](说人话版.md)，一页看懂三件套。

| 技能 | 角色 | 职责 |
|---|---|---|
| [cross-agent-dev-workflow-skill](cross-agent-dev-workflow-skill/) | 🚦 **总调度（掌舵）** | 项目全生命周期交付总流程：研发迭代 → 测试纠错 → 整理发布三阶段，证据制验收门 + 停止闸 + 阶段状态机（存 memory 的 `5_代办.md`，跨会话跨 Agent 续跑） |
| [cross-agent-memory-skill](cross-agent-memory-skill/) | 🧠 **大脑（记账）** | **就地记忆**：在真实工作区文件夹树里就地创建/维护分层记忆（`记忆第X层`，层号=记忆层级序数，层数 Agent 深研后自定），每层 0_索引 + 6 件，先读→合并→写回，sha256 指纹并发检测，主动补齐新增子工程的记忆层 |
| [cross-agent-scratchpad-skill](cross-agent-scratchpad-skill/) | 🧹 **清洁工（打扫）** | **临时脚本治理**：临时脚本一律存用户指定的外部库，先复用后创建，遗留物分级审计（复用→迁入 / 无价值→清理 / 来源不明→隔离等确认），真实工程文件绝不自动删 |

## 三位一体怎么协作

```
接手任务 ── 一键入口：python 记忆管家.py 接手 <工作区>（三技能共用）
   │  读记忆 0_索引/分层方案 → 读 5_代办「🚦 交付流程状态」定续跑点 → 遗留物审计（增量）
   ↓
阶段1 研发迭代   深度研究+GitHub/全网资产检索 → 方案（拍板线问用户）→ 多轮实现
   │            （决策/踩坑实时入 memory；临时脚本全走 scratchpad 外部库）
   ↓ 证据制验收门
阶段2 测试纠错   实际运行 → 逐文件审查 → 纠错循环（问题/根因/修复/验证+回归）
   ↓ 验收门：已知问题清单为空 + 清单全过
阶段3 整理发布   结构整合 → 遗留物分级处置（scratchpad 红线）→ 打包 → 发布清单
   ↓
报告「已达到可上线发布状态」→ 停止闸生效，不做多余的事
```

- **状态承载**：dev-workflow 的阶段状态机存在 memory 的 `5_代办.md`——换 Agent、换设备、换会话都能从断点续跑。
- **删除安全**：dev-workflow 的一切删除委托 scratchpad 分级协议；用户授权「全部权限」也不解除红线。
- **可单独用，整装最佳**：三技能各自独立可用；未装伙伴时 dev-workflow 按 SKILL.md §六 三条铁律降级。

## 设计亮点

- **跨 Agent / 跨 Harness**：标准 SKILL.md 格式（[agentskills.io](https://agentskills.io/specification)），ZCode / Codex CLI / Cursor / Claude Code 等任何支持 skills 的工具都能加载。
- **工具层兜底协议**：不只靠提示词纪律——`记忆管家.py`（接手/建层含 --通用/刷新通用/检索/索引/校验指纹）、`临时脚本管家.py`（配置/查/登记含查重/审计/迁移/原子索引）、`发布管家.py`（校验技能/三位一体互链检查/打包/发布检查）。
- **深度联动**：统一署名（`~/.agent-tsg/config.json` 的 `agent_name`，由记忆管家与临时脚本管家两工具共用）；`联动/` 文档两两互指成环；审计结论按约定写入记忆对应文件；memory 另有中央 `记忆_通用/`（跨项目通用知识，任何记忆层可引用）。
- **规模分档 + 停止闸**：轻量/标准/深度三档，小任务不套重流程；验收门一过即停，防过度打磨。
- **版本可追溯**：各技能 SKILL.md 带 `metadata.version`，套件变更见 [CHANGELOG.md](CHANGELOG.md)。

## 安装

各技能目录内有 `安装指引.md`；把对应文件夹拷入目标 harness 的 skills 目录即可（如 ZCode：`~/.zcode/skills/`，Claude Code：`~/.claude/skills/`）。**建议三件套整装**。

## 环境要求

- 无必须依赖（协议可纯手工执行）；推荐 Python 3.8+ 以使用辅助工具。

## License

[MIT](LICENSE) — 同行可自由安装、使用、修改、分发。
