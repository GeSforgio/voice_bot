<#
.SYNOPSIS
    🧱 Пиздун 2.0 — запуск с живым логом
.DESCRIPTION
    Запускает бота, дублирует вывод в консоль и в лог-файл
    Логи хранятся в папке logs/ с датой в имени
#>

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$LogDir = Join-Path $ScriptDir "logs"
$MaxLogs = 20

# Создаём папку логов
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

# Имя лог-файла: pizdun_YYYYMMDD_HHmmss.log
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "pizdun_$Timestamp.log"

# Чистим старые логи
Get-ChildItem -Path $LogDir -Filter "pizdun_*.log" -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $MaxLogs |
    ForEach-Object { Remove-Item $_.FullName -Force }

# Заголовок
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  🧱  ПИЗДУН 2.0  —  Discord бот" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  Хост: $env:COMPUTERNAME" -ForegroundColor Gray
Write-Host "  Дата: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray
Write-Host "----------------------------------------------" -ForegroundColor Gray
Write-Host "  📝 Лог: $LogFile" -ForegroundColor Yellow
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""

# Активируем .venv
$Activate = Join-Path $ScriptDir ".venv\Scripts\Activate.ps1"
if (Test-Path $Activate) {
    . $Activate
    Write-Host "✅ Окружение активировано" -ForegroundColor Green
}
else {
    Write-Host "❌ .venv не найден! Запусти: python -m venv .venv" -ForegroundColor Red
    pause
    exit 1
}

Write-Host "🎭 Запускаю бота..." -ForegroundColor Green
Write-Host "----------------------------------------------" -ForegroundColor Gray
Write-Host ""

# Форматируем вывод: добавляем время к каждой строке
$scriptBlock = {
    param($LogPath)
    python main.py 2>&1 | ForEach-Object {
        $time = Get-Date -Format "HH:mm:ss"
        $line = "$time | $_"
        Write-Output $line
    }
}

# Запускаем и пишем одновременно в консоль и лог
$job = Start-Job -ScriptBlock $scriptBlock -ArgumentList $LogFile

# Читаем вывод job'а и дублируем
$stream = $null
try {
    $logStream = [System.IO.StreamWriter]::new($LogFile, $false, [System.Text.UTF8Encoding]::new($false))
    
    do {
        $line = Receive-Job -Job $job 2>&1
        if ($line) {
            foreach ($msg in $line) {
                $text = "$msg"
                $logStream.WriteLine($text)
                Write-Host $text
            }
        }
        Start-Sleep -Milliseconds 100
    } while ($job.State -eq 'Running')
    
    # Добираем остатки
    Start-Sleep -Milliseconds 500
    $remaining = Receive-Job -Job $job 2>&1
    if ($remaining) {
        foreach ($msg in $remaining) {
            $text = "$msg"
            $logStream.WriteLine($text)
            Write-Host $text
        }
    }
}
catch {
    Write-Host "❌ Ошибка: $_" -ForegroundColor Red
}
finally {
    if ($logStream) { $logStream.Close() }
    Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "----------------------------------------------" -ForegroundColor Gray
Write-Host "✅ Бот остановлен" -ForegroundColor Green
Write-Host "📝 Полный лог: $LogFile" -ForegroundColor Yellow

pause
