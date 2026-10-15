# 发布管家.ps1 - Windows 薄封装：转发到 发布管家.py
# 用法：.\发布管家.ps1 校验技能 <技能目录> / 三位一体 <套件根> / 打包 <技能目录> / 发布检查 <套件根>
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
if ($py) {
    & $py.Source (Join-Path $PSScriptRoot "发布管家.py") @args
    exit $LASTEXITCODE
}
Write-Host "未找到 python。请安装 Python 3.8+，或按 SKILL.md 协议手工执行。"
exit 1
