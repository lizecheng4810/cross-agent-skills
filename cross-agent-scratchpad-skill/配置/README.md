# 配置说明

本 skill 的实际本机配置文件不在 skill 目录里，而在：

```
~/.agent-tsg/config.json        （Windows: C:\Users\<用户>\.agent-tsg\config.json）
```

内容示例：

```json
{
  "temp_script_root": "D:\\AAA实习\\临时脚本库",
  "agent_name": "zcode",
  "configured_at": "2026-09-04T10:00:00"
}
```

> `agent_name` 是默认署名：由 `配置 --name <署名>` 设置，记忆管家与临时脚本管家两个工具共用（登记/迁移/指纹档案的留痕署名一致）。

设计原因：

- **路径是设备级事实**：跨设备不通用，放本机配置而不是项目记忆；
- **配置一次**：首次使用时 Agent 必须询问用户取得路径，之后读取并校验可达性，不再重复问；
- **失效不回退**：路径不可达时 Agent 必须停下来重新询问用户，绝不静默把临时脚本写回工作区。
