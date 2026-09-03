$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$SyncScript = Join-Path $RootDir "scripts\sync-skills.ps1"

if (Test-Path $SyncScript) {
    & $SyncScript -CheckOnly
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "[WARN] Skills 不同步，自动修复中..." -ForegroundColor Yellow
        & $SyncScript
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] 同步失败，push 已阻止" -ForegroundColor Red
            exit 1
        }
        Write-Host "[INFO] 已自动同步，请重新 commit 变更后再 push" -ForegroundColor Yellow
        Write-Host "  git add .claude/skills/ && git commit --amend --no-edit" -ForegroundColor Gray
        exit 1
    }
}

exit 0