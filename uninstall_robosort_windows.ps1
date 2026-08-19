<#
.SYNOPSIS
    Деинсталляция RoboSort на Windows 10.
    Запускайте от имени администратора.
.DESCRIPTION
    - Останавливает и удаляет задачу из планировщика.
    - Удаляет все файлы программы, логи, конфигурацию, виртуальное окружение.
    - (Опционально) удаляет папку установки.
#>

#Requires -RunAsAdministrator

# -----------------------------------------------------------------------------
# 1. Определение путей (должны совпадать с установочным скриптом)
# -----------------------------------------------------------------------------
$InstallDir = "C:\Program Files\RoboSort"
$LogDir = "C:\ProgramData\RoboSort\logs"
$ConfigDir = "$InstallDir\config"
$TaskName = "RoboSort"

# -----------------------------------------------------------------------------
# 2. Подтверждение удаления
# -----------------------------------------------------------------------------
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "          Деинсталляция RoboSort" -ForegroundColor Yellow
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Будут удалены:"
Write-Host "  - Задача планировщика '$TaskName'"
Write-Host "  - Папка установки: $InstallDir"
Write-Host "  - Логи: $LogDir"
Write-Host ""
$confirm = Read-Host "Вы уверены, что хотите удалить RoboSort? (y/n) [n]"
if ($confirm -ne "y" -and $confirm -ne "Y") {
    Write-Host "Удаление отменено." -ForegroundColor Green
    exit 0
}

# -----------------------------------------------------------------------------
# 3. Остановка и удаление задачи из планировщика
# -----------------------------------------------------------------------------
Write-Host "Остановка и удаление задачи планировщика..." -ForegroundColor Yellow
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task) {
    try {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Задача '$TaskName' удалена." -ForegroundColor Green
    } catch {
        Write-Warning "Не удалось удалить задачу: $_"
    }
} else {
    Write-Host "Задача не найдена." -ForegroundColor Gray
}

# -----------------------------------------------------------------------------
# 4. Завершение запущенных процессов RoboSort
# -----------------------------------------------------------------------------
Write-Host "Проверка запущенных процессов..." -ForegroundColor Yellow
$processes = Get-Process | Where-Object { $_.ProcessName -like "*python*" -and $_.Path -like "*RoboSort*" }
if ($processes) {
    Write-Host "Найдены процессы RoboSort. Завершаем..." -ForegroundColor Yellow
    $processes | ForEach-Object {
        try {
            Stop-Process -Id $_.Id -Force
            Write-Host "Остановлен процесс PID $($_.Id)" -ForegroundColor Gray
        } catch {
            Write-Warning "Не удалось остановить процесс $($_.Id): $_"
        }
    }
} else {
    Write-Host "Запущенных процессов RoboSort не найдено." -ForegroundColor Gray
}

# -----------------------------------------------------------------------------
# 5. Удаление файлов и папок
# -----------------------------------------------------------------------------
Write-Host "Удаление файлов..." -ForegroundColor Yellow

# Папка установки
if (Test-Path $InstallDir) {
    try {
        # Сначала даём права на удаление, если нужно
        Takeown /F $InstallDir /R /D Y 2>$null
        Icacls $InstallDir /grant Administrators:F /T 2>$null
        Remove-Item -Path $InstallDir -Recurse -Force -ErrorAction Stop
        Write-Host "Папка установки удалена: $InstallDir" -ForegroundColor Green
    } catch {
        Write-Warning "Не удалось удалить папку $InstallDir : $_"
    }
} else {
    Write-Host "Папка установки не найдена." -ForegroundColor Gray
}

# Логи
if (Test-Path $LogDir) {
    try {
        Remove-Item -Path $LogDir -Recurse -Force -ErrorAction Stop
        Write-Host "Папка логов удалена: $LogDir" -ForegroundColor Green
    } catch {
        Write-Warning "Не удалось удалить папку логов: $_"
    }
} else {
    Write-Host "Папка логов не найдена." -ForegroundColor Gray
}

# -----------------------------------------------------------------------------
# 6. Очистка переменных окружения (если были добавлены)
# (В установочном скрипте мы не добавляли, но если добавите – можно убрать)

# -----------------------------------------------------------------------------
# 7. Завершение
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "Деинсталляция RoboSort завершена." -ForegroundColor Green
Write-Host "Все файлы удалены." -ForegroundColor Gray