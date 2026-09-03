# sync-skills.ps1
# 同步 .trae/skills/ → .claude/skills/
# 用途：确保 Claude Code 和 Trae IDE 使用相同的 Skills

param(
    [switch]$CheckOnly  # 仅检查是否有差异，不执行同步
)

$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $PSScriptRoot
$TraeDir = Join-Path $RootDir ".trae\skills"
$ClaudeDir = Join-Path $RootDir ".claude\skills"

if (-not (Test-Path $TraeDir)) {
    Write-Host "[SKIP] .trae/skills/ 不存在，无需同步" -ForegroundColor Yellow
    exit 0
}

function Get-DirHash {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $null }
    $files = Get-ChildItem -Path $Path -Recurse -File | Sort-Object FullName
    $hashes = $files | ForEach-Object { (Get-FileHash $_.FullName -Algorithm SHA256).Hash }
    return ($hashes -join "") -replace '\s', ''
}

$traeHash = Get-DirHash $TraeDir
$claudeHash = Get-DirHash $ClaudeDir

if ($traeHash -eq $claudeHash) {
    Write-Host "[OK] .trae/skills/ 与 .claude/skills/ 已同步" -ForegroundColor Green
    exit 0
}

if ($CheckOnly) {
    Write-Host "[DIFF] .trae/skills/ 与 .claude/skills/ 不一致！请运行 scripts/sync-skills.ps1" -ForegroundColor Red
    exit 1
}

Write-Host "[SYNC] 正在同步 .trae/skills/ → .claude/skills/ ..." -ForegroundColor Cyan

# 清理旧内容
if (Test-Path $ClaudeDir) {
    Remove-Item -Path $ClaudeDir -Recurse -Force
}

# 复制
Copy-Item -Path $TraeDir -Destination $ClaudeDir -Recurse

Write-Host "[DONE] 同步完成" -ForegroundColor Green
Write-Host "  .trae/skills/  →  .claude/skills/" -ForegroundColor Gray