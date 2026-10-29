# cross-agent-skills

面向跨 Agent / 跨 Harness 工作的三件套技能：交付流程、工作区记忆和临时脚本治理。

| 技能 | 职责 |
|---|---|
| [cross-agent-dev-workflow-skill](cross-agent-dev-workflow-skill/) | 从研发、验证到整理发布的阶段协议，含验收门和停止闸 |
| [cross-agent-memory-skill](cross-agent-memory-skill/) | 将可复用上下文保存在工作区，以精简索引和范围化读取支持快速续接 |
| [cross-agent-scratchpad-skill](cross-agent-scratchpad-skill/) | 临时脚本外置、复用、审计和分级处置 |

## 接手方式

常规接手按任务路径读取记忆：根层 `0_索引.md` 与当前 `5_代办.md`，然后是范围层索引、交接和本任务相关主题。不会默认读取所有层和所有主题；只有首次初始化、记忆冲突、结构变化、跨模块范围或用户要求时才扩大审查。

可选工具的快速入口：

```powershell
python "cross-agent-memory-skill\工具\记忆管家.py" 接手 "<工作区>" --scope "<任务路径>"
```

未给范围时只检查根层。完整记忆审计需显式使用 `--full-audit`。根索引明确列出的例外目录会从完整性候选扫描中排除；候选只用于提示，不会自动建层。

```text
阶段0 接手与续跑
  ↓
阶段1 研发迭代 → 阶段验收
  ↓
阶段2 实际验证、审查、纠错 → 验收门
  ↓
阶段3 整理和发布准备 → 达标后停止
```

## 安装

各技能目录包含独立的 `安装指引.md`。把完整技能文件夹放进目标 Harness 的 skills 目录。工具为可选组件，无 Python 时仍可按技能文件手工执行。

工具保持 Python 3.8+ 兼容；Python 3.8 已于 2024-10-07 结束支持，建议日常使用仍受支持的 Python 版本。[Python 3.8.20 发布说明](https://www.python.org/downloads/release/python-3820/)

## 研究与版本

- [Agent Skills 规范](https://agentskills.io/specification)
- 套件历史见 [CHANGELOG.md](CHANGELOG.md)。

## 本地验证

在套件根目录执行回归测试：

```powershell
python -m unittest discover -s tests -v
```

技能结构、三方联动和最终 ZIP 由 `cross-agent-dev-workflow-skill/工具/发布管家.py` 提供检查命令；发布检查要求三个 ZIP 已先完成打包。

## License

[MIT](LICENSE)。
