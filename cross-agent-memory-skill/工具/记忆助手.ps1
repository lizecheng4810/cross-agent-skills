# ============================================================
#  记忆助手 —— cross-agent-memory 的 Windows 薄封装
#  转发到同目录的 记忆管家.py（Python 3.8+，跨平台主工具）。
#  无 Python 时：按 SKILL.md 协议手工操作（脚本仅为可选辅助）。
#  用法见 工具/README.md
# ============================================================
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("接手", "建层", "建记忆", "扫描", "检查", "索引", "校验", "刷新通用", "检索", "帮助")]
    [string]$命令 = "帮助",
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$参数 = @()
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$py = Join-Path $PSScriptRoot "记忆管家.py"

function Invoke-Python {
    param([string[]]$ForwardArgs)
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
    if (-not $python) { return $null }
    # 注意：PS 函数会把内部 stdout 捕获为返回值，必须 Out-Host 直通，否则 python 的正常输出被吞进 $rc
    if ($python.Name -eq "py.exe") {
        & $python.Source -3 $py @ForwardArgs | Out-Host
    } else {
        & $python.Source $py @ForwardArgs | Out-Host
    }
    return $LASTEXITCODE
}

switch ($命令) {
    { $_ -in "接手", "建层", "建记忆", "扫描", "检查", "索引", "校验", "刷新通用", "检索" } {
        $forward = @()
        if ($命令 -eq "建记忆") { $命令 = "建层" }
        $forward += $命令
        if ($参数.Count -gt 0) { $forward += $参数 }
        $rc = Invoke-Python $forward
        if ($null -eq $rc) {
            Write-Warning "Python 不可用。请按 SKILL.md 协议手工操作（本脚本仅为可选辅助）。"
            exit 1
        }
        # Python 已打印过协议错误信息；此处仅透传退出码（0=成功，非0=协议性报错）
        exit $rc
    }
    default {
        Write-Host "记忆助手（cross-agent-memory · 转发到 记忆管家.py）"
        Write-Host "  接手 <工作区>                          一键接手入口：扫描+完整性检查+并发校验+联动检查"
        Write-Host "  建层 <文件夹> --层 1|2|3|4…（或 一/二/三/四…）  就地建 记忆第X层（层号=记忆层级序数，1~99 不限）；建层 <工作区> --通用 建中央 记忆_通用"
        Write-Host "  扫描 <工作区>                          列出已有的 记忆第X层 文件夹"
        Write-Host "  检查 <工作区>                          层级完整性检查：按记忆层级序数找缺记忆层的子模块"
        Write-Host "  索引 [<工作区>] --层 记忆第X层 --by 署名   生成/更新该层指纹档案（记忆索引.json）"
        Write-Host "  校验 [<工作区>] --层 记忆第X层 [--refresh]  并发检测：报告被其他 Agent 改过的文件"
        Write-Host "  刷新通用 <工作区>                     重建所有层 0_索引 的「🔗 通用知识」段并刷新指纹"
        Write-Host "  检索 <工作区> <关键词>                 跨全部记忆层与 记忆_通用 全文检索"
        Write-Host "提示：判断层级、深度阅读并填写记忆由 Agent 按 SKILL.md 自主完成，本脚本仅辅助。"
    }
}
