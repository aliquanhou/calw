$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$source = "D:\calw_v2.1"
$dest = "D:\calw_v2.1_backups\calw_$timestamp"
$maxBackups = 7

Write-Host "[Calw Backup] 开始备份..." -ForegroundColor Cyan

# 创建备份目录
if (-not (Test-Path "D:\calw_v2.1_backups")) {
    New-Item -ItemType Directory -Path "D:\calw_v2.1_backups" -Force | Out-Null
}

# 排除 __pycache__ 和 .pytest_cache
Copy-Item -Path $source -Destination $dest -Recurse -Force -Exclude @("__pycache__", ".pytest_cache", "*.pyc")

Write-Host "[Calw Backup] ✅ 备份完成: $dest" -ForegroundColor Green

# 清理旧备份（保留最近7个）
$backups = Get-ChildItem "D:\calw_v2.1_backups" -Directory | Sort-Object Name -Descending
if ($backups.Count -gt $maxBackups) {
    $backups[$maxBackups..($backups.Count-1)] | ForEach-Object {
        Remove-Item $_.FullName -Recurse -Force
        Write-Host "[Calw Backup] 🗑️ 删除旧备份: $($_.Name)" -ForegroundColor Yellow
    }
}

Write-Host "[Calw Backup] ✅ 完成 (保留 $maxBackups 个备份)" -ForegroundColor Green
