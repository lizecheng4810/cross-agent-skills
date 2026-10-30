# 工具说明

## 临时脚本管家.py（主工具）

跨平台，Python 3.8+，无第三方依赖。命令一览：

| 命令 | 作用 |
|---|---|
| `配置 [--path <目录>] [--name <署名>]` | 查看/设置本机临时脚本根目录（写 `~/.agent-tsg/config.json`）并初始化 reusable/sessions/quarantine/manifests/reports 结构；`--name` 设置默认署名 `agent_name`（记忆管家/临时脚本管家共用） |
| `查 <关键词> [--lang py] [--project X]` | 检索索引找可复用脚本 |
| `登记 <文件> --purpose P [--reuse one-off\|reusable] [--project X] [--move]` | 收编脚本入库并登记元数据（`--by` 省略时自动取本机配置 `agent_name`） |
| `审计 <工作区>` | 启发式扫描疑似临时脚本（临时命名+未跟踪打分），写报告到 reports/ |
| `迁移 <文件> --to reusable\|sessions\|quarantine` | 移动脚本入库并更新索引（quarantine 保留 origin_path 供回迁） |
| `使用 <文件或id> [--note N]` | 标记脚本被复用过（使用次数+1，更新最后使用时间）——复用了就调一次 |
| `回迁 <文件或id>` | 把 quarantine 中经用户确认误伤的脚本移回工作区原路径 |
| `清理 [--project X] [--before 日期] [--quarantined] [--yes]` | 处置 one-off / 过期脚本；`--quarantined` 处置用户已确认的隔离项；默认只列清单，`--yes` 才执行 |
| `报告` | 库内摘要：各区数量、最常复用、待确认项 |

**并发安全（借鉴 cross-agent-memory 的指纹校验思想）**：`manifests/index.json` 保存前重读磁盘做指纹比对，检测到其他 Agent 的并发改动会拒绝写入并提示重读合并；所有 JSON 写入均为原子写入（临时文件+替换）。

审计的启发式只是初筛，**Agent 必须逐个深度判断后再按 SKILL.md 分级处置**，不能拿 score 直接删。

## 临时脚本管家.ps1（Windows 薄封装）

优先转发到 Python 实现；本机无 Python 时仅支持 `配置 -Path`（初始化目录+配置文件），其余功能需安装 Python。

## 无工具时的手工协议

工具是辅助，不是必须。任何 Agent 按目录结构直接读写 `manifests/index.json` 和各区文件夹，同样满足协议。
