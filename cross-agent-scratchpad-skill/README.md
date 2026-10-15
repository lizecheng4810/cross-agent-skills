# cross-agent-scratchpad-skill

跨 Agent / 跨 Harness 的**临时脚本全生命周期治理**技能。

## 解决什么问题

1. 临时脚本越积越多，从不清理，占用存储；
2. 临时脚本被建在项目工作区里，污染源代码工程环境；
3. 分不清哪些脚本可复用该留、哪些一次性该删；
4. 多个 Agent/Harness 各自为政，重复造脚本、重复扫描、决策不延续。

## 核心设计

- **外部统一库存放**：用户每台设备指定一个工作区外的临时脚本库（`~/.agent-tsg/config.json` 记录，未配置必问用户）；
- **先复用后创建**：建脚本前必查 `manifests/index.json` 索引（用途/语言/哈希/使用次数）；
- **分级处置**：自己的脚本自动治理；历史遗留按复用价值迁移或删除；来源不明只隔离（quarantine/）+ 报告 + 等用户确认；真实工程文件绝不自动删；
- **深度联动（三位一体）**：与 `cross-agent-memory`（就地记忆）、`cross-agent-dev-workflow-skill`（项目交付总流程）共生——判断、偏好、审计结论、待办全部入分层记忆，跨 Agent 延续；dev-workflow 的删除操作全部委托本技能分级红线。

## 目录结构

```
SKILL.md                          # 操作协议（Agent 读这个）
README.md                         # 本文件
安装指引.md
配置/                             # 本机配置说明（实际配置在 ~/.agent-tsg/config.json）
工具/临时脚本管家.py               # 主工具（Python，跨平台）
工具/临时脚本管家.ps1              # Windows 薄封装（无 Python 时降级支持初始化）
工具/README.md                    # 工具命令说明
模板/                             # 审计报告、清理决策清单模板
联动/cross-agent-memory.md        # 与记忆技能的联动约定
联动/cross-agent-dev-workflow.md  # 与交付总流程技能的联动约定（三位一体）
```

## 快速上手

```powershell
# 1. 配置本机临时脚本库（首次）
python 工具\临时脚本管家.py 配置 --path D:\临时脚本库

# 2. 建脚本前查复用
python 工具\临时脚本管家.py 查 编码

# 3. 审计某工作区的遗留临时脚本
python 工具\临时脚本管家.py 审计 D:\某项目

# 4. 收编/迁移脚本入库
python 工具\临时脚本管家.py 迁移 D:\某项目\tmp_fetch.py --to reusable --purpose 抓取数据

# 5. 查看现状
python 工具\临时脚本管家.py 报告
```

日常使用不需要记命令——装好 skill 后，Agent 会按 SKILL.md 协议在接手任务、创建脚本、结束任务三个节点自动执行。
