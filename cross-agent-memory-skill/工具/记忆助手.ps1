# ============================================================
#  记忆助手 —— cross-agent-memory 的 Windows 薄封装
#  转发到同目录的 记忆管家.py（Python 3.8+，跨平台主工具）。
#  无 Python 时：按 SKILL.md 协议手工操作（脚本仅为可选辅助）。
#  用法见 工具/README.md
# ============================================================
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("接手", "建层", "建记忆", "扫描", "检查", "索引", "校验", "帮助")]
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
    if (-not $python) { return $false }
    if ($python.Name -eq "py.exe") {
        & $python.Source -3 $py @ForwardArgs
    } else {
        & $python.Source $py @ForwardArgs
    }
    return ($LASTEXITCODE -eq 0)
}

switch ($命令) {
    { $_ -in "接手", "建层", "建记忆", "扫描", "检查", "索引", "校验" } {
        $forward = @()
        if ($命令 -eq "建记忆") { $命令 = "建层" }
        $forward += $命令
        if ($参数.Count -gt 0) { $forward += $参数 }
        if (-not (Invoke-Python $forward)) {
            Write-Warning "Python 不可用或执行失败。请按 SKILL.md 协议手工操作（本脚本仅为可选辅助）。"
        }
    }
    default {
        Write-Host "记忆助手（cross-agent-memory · 转发到 记忆管家.py）"
        Write-Host "  接手 <工作区>                          一键接手入口：扫描+完整性检查+并发校验+联动检查"
        Write-Host "  建层 <文件夹> --层 1|2|3|4…（或 一/二/三/四…）  就地建 记忆第X层（层号=目录深度，1~99 不限）"
        Write-Host "  扫描 <工作区>                          列出已有的 记忆第X层 文件夹"
        Write-Host "  检查 <工作区>                          层级完整性检查：按目录深度找缺记忆层的子模块"
        Write-Host "  索引 [<工作区>] --层 记忆第X层 --by 署名   生成/更新该层指纹档案（记忆索引.json）"
        Write-Host "  校验 [<工作区>] --层 记忆第X层 [--refresh]  并发检测：报告被其他 Agent 改过的文件"
        Write-Host "提示：判断层级、深度阅读并填写记忆由 Agent 按 SKILL.md 自主完成，本脚本仅辅助。"
    }
}
