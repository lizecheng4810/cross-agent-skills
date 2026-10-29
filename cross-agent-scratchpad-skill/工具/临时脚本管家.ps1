# 临时脚本管家 —— Windows 薄封装
# 优先转发到同目录的 Python 实现；无 Python 时对「配置」提供原生降级。
# 用法示例：
#   .\临时脚本管家.ps1 配置 -Path D:\临时脚本库 -Name zcode
#   .\临时脚本管家.ps1 查 关键词
#   .\临时脚本管家.ps1 审计 D:\某工作区
#   .\临时脚本管家.ps1 迁移 D:\某项目\tmp.py -To quarantine -Project 某项目
param(
    [Parameter(Position = 0)][string]$Cmd = "报告",
    [Parameter(Position = 1)][string]$Target,
    [string]$Path,
    [string]$Name,
    [string]$Lang,
    [string]$Purpose,
    [ValidateSet("reusable", "sessions", "quarantine", "")][string]$To,
    [ValidateSet("one-off", "reusable", "")][string]$Reuse,
    [string]$Project,
    [string]$Before,
    [string]$Note,
    [switch]$Quarantined,
    [switch]$Yes
)

$ErrorActionPreference = "Stop"
$pyScript = Join-Path $PSScriptRoot "临时脚本管家.py"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Resolve-Python {
    foreach ($candidate in @("python", "py")) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $command) { continue }
        try {
            if ($candidate -eq "py") {
                & $command.Source -3 --version 2>$null | Out-Null
            } else {
                & $command.Source --version 2>$null | Out-Null
            }
            if ($LASTEXITCODE -eq 0) {
                return [pscustomobject]@{ Source = $command.Source; Launcher = ($candidate -eq "py") }
            }
        } catch {}
    }
    return $null
}

$pythonCommand = Resolve-Python
if ($pythonCommand) {
    # 每个命令只追加它支持的参数，避免 argparse 报错
    $argList = @($pyScript, $Cmd)
    switch -Regex ($Cmd) {
        '^(配置)$' {
            if ($Path) { $argList += @("--path", $Path) }
            if ($Name) { $argList += @("--name", $Name) }
        }
        '^(查)$' {
            if (-not $Target) { Write-Host "用法：查 <关键词> [-Lang py] [-Project X]"; exit 1 }
            $argList += $Target
            if ($Lang) { $argList += @("--lang", $Lang) }
            if ($Project) { $argList += @("--project", $Project) }
        }
        '^(登记)$' {
            if (-not ($Target -and $Purpose)) { Write-Host "用法：登记 <文件> -Purpose 用途 [-Reuse one-off|reusable] [-Project X]"; exit 1 }
            $argList += @($Target, "--purpose", $Purpose)
            if ($Reuse) { $argList += @("--reuse", $Reuse) }
            if ($Project) { $argList += @("--project", $Project) }
            if ($Yes) { $argList += "--move" }   # 登记 -Yes = 移动而非复制
        }
        '^(迁移|回迁|使用)$' {
            if (-not $Target) { Write-Host "用法：$Cmd <文件或id>"; exit 1 }
            $argList += $Target
            if ($Cmd -eq '迁移') {
                if (-not $To) { Write-Host "用法：迁移 <文件> -To reusable|sessions|quarantine"; exit 1 }
                $argList += @("--to", $To)
                if ($Purpose) { $argList += @("--purpose", $Purpose) }
                if ($Project) { $argList += @("--project", $Project) }
            }
            if ($Cmd -eq '使用' -and $Note) { $argList += @("--note", $Note) }
        }
        '^(审计)$' {
            if (-not $Target) { Write-Host "用法：审计 <工作区路径>"; exit 1 }
            $argList += $Target
        }
        '^(清理)$' {
            if ($Project) { $argList += @("--project", $Project) }
            if ($Before) { $argList += @("--before", $Before) }
            if ($Quarantined) { $argList += "--quarantined" }
            if ($Yes) { $argList += "--yes" }
        }
    }
    if ($pythonCommand.Launcher) {
        & $pythonCommand.Source -3 @argList
    } else {
        & $pythonCommand.Source @argList
    }
    exit $LASTEXITCODE
}

# —— 无 Python 的降级实现：仅支持 配置 ——
$configPath = Join-Path $env:USERPROFILE ".agent-tsg\config.json"
if ($Cmd -eq "配置") {
    if (-not $Path) { Write-Host "未配置或未给 -Path。请先询问用户临时脚本存放位置。"; exit 1 }
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
    foreach ($d in "reusable", "sessions", "quarantine", "manifests", "reports") {
        New-Item -ItemType Directory -Force -Path (Join-Path $Path $d) | Out-Null
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $configPath) | Out-Null
    # -Encoding utf8 在 PS5 下带 BOM，Python 侧用 utf-8-sig 读取，二者兼容
    $cfg = @{ temp_script_root = (Resolve-Path $Path).Path; configured_at = (Get-Date -Format s) }
    if ($Name) { $cfg["agent_name"] = $Name }   # 与 Python 版 配置 --name 一致：两工具共用默认署名
    $cfg | ConvertTo-Json | Set-Content -Encoding UTF8 $configPath
    Write-Host "[配置] 根目录：$Path（结构已初始化，配置写入 $configPath）"
} else {
    Write-Host "本机没有 Python，PS 封装仅支持『配置』。请安装 Python 3.8+ 以获得完整功能。"
    exit 1
}
