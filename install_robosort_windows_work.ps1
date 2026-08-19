<#
.SYNOPSIS
    Установка RoboSort на Windows 10.
    Запускайте от имени администратора.
.DESCRIPTION
    - Проверяет наличие Python 3.9+, если нет — скачивает и устанавливает.
    - Создаёт виртуальное окружение.
    - Устанавливает зависимости.
    - Создаёт конфигурационный файл.
    - Добавляет задачу в планировщик для автозапуска.
#>

#Requires -RunAsAdministrator

# -----------------------------------------------------------------------------
# 1. Настройки Python
# -----------------------------------------------------------------------------
$PythonVersion = "3.12.1"
$PythonInstallerUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe"
$PythonInstaller = "$env:TEMP\python-installer.exe"

# -----------------------------------------------------------------------------
# 2. Проверка наличия Python 3.9+
# -----------------------------------------------------------------------------
function Test-PythonVersion {
    try {
        $py = Get-Command python -ErrorAction Stop
        $ver = & $py.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        $verParts = $ver -split '\.'
        if ([int]$verParts[0] -ge 3 -and [int]$verParts[1] -ge 9) {
            return $true
        }
    } catch {}
    return $false
}

if (-not (Test-PythonVersion)) {
    Write-Host "Python 3.9+ не найден. Будет выполнена автоматическая установка." -ForegroundColor Yellow
    Write-Host "Скачивание установщика Python $PythonVersion ..." -ForegroundColor Cyan
    try {
        Invoke-WebRequest -Uri $PythonInstallerUrl -OutFile $PythonInstaller
    } catch {
        Write-Error "Не удалось скачать Python: $_"
        exit 1
    }

    Write-Host "Запуск установки Python (тихо, с добавлением в PATH)..." -ForegroundColor Cyan
    Start-Process -Wait -FilePath $PythonInstaller -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0 Include_pip=1 Include_tcltk=0"
    Remove-Item $PythonInstaller -Force

    # Обновляем переменную PATH для текущей сессии
    Write-Host "Обновление переменной PATH..." -ForegroundColor Cyan
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

    # Проверяем, что теперь python доступен
    if (-not (Test-PythonVersion)) {
        Write-Error "Python установлен, но не обнаружен в PATH. Перезапустите скрипт после перезагрузки."
        exit 1
    }
    Write-Host "Python успешно установлен!" -ForegroundColor Green
} else {
    Write-Host "Python уже установлен." -ForegroundColor Green
}

# -----------------------------------------------------------------------------
# 3. Определение путей
# -----------------------------------------------------------------------------
$InstallDir = "C:\Program Files\RoboSort"
$VenvDir = "$InstallDir\venv"
$ConfigDir = "$InstallDir\config"
$LogDir = "C:\ProgramData\RoboSort\logs"
$ModelDir = "$InstallDir\models"
$PythonExe = "$VenvDir\Scripts\python.exe"
$PipExe = "$VenvDir\Scripts\pip.exe"

# -----------------------------------------------------------------------------
# 4. Создание директорий
# -----------------------------------------------------------------------------
Write-Host "Создание директорий..." -ForegroundColor Green
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path $ModelDir | Out-Null

# Копирование файлов проекта (предполагается, что скрипт запускается из корня репозитория)
$SourceDir = (Get-Location).Path
Write-Host "Копирование исходного кода из $SourceDir в $InstallDir ..." -ForegroundColor Green
Copy-Item -Recurse -Force "$SourceDir\src" "$InstallDir\"
Copy-Item -Force "$SourceDir\main.py" "$InstallDir\"
Copy-Item -Force "$SourceDir\__init__.py" "$InstallDir\" 2>$null
Copy-Item -Recurse -Force "$SourceDir\src" "$InstallDir\"
Copy-Item -Force "$SourceDir\main.py" "$InstallDir\"
Copy-Item -Force "$SourceDir\__init__.py" "$InstallDir\" 2>$null
Copy-Item -Force "$SourceDir\scripts\calibrate.py" "$InstallDir\"  # <-- добавлено
Copy-Item -Recurse -Force "$SourceDir\tests" "$InstallDir\" 2>$null  # если есть
Copy-Item -Force "$SourceDir\README.md" "$InstallDir\" 2>$null
Copy-Item -Force "$SourceDir\REPORT.md" "$InstallDir\" 2>$null
# Копируем cad_models.yaml, если есть
if (Test-Path "$SourceDir\config\cad_models.yaml") {
    Copy-Item -Force "$SourceDir\config\cad_models.yaml" "$ConfigDir\"
}


# -----------------------------------------------------------------------------
# 5. Создание виртуального окружения
# -----------------------------------------------------------------------------
Write-Host "Создание виртуального окружения..." -ForegroundColor Green
python -m venv $VenvDir
if (-not (Test-Path $PythonExe)) {
    Write-Error "Не удалось создать виртуальное окружение."
    exit 1
}

# -----------------------------------------------------------------------------
# 6. Установка зависимостей
# -----------------------------------------------------------------------------
Write-Host "Обновление pip и установка зависимостей..." -ForegroundColor Green
& $PipExe install --upgrade pip setuptools wheel

$Requirements = @"
numpy>=1.21
opencv-python>=4.5
pyserial>=3.5
ultralytics>=8.0.0
torch>=1.10
pydantic>=2.0
pydantic-settings>=2.0
pyyaml>=6.0
tqdm>=4.64
pytest>=7.0
fastapi==0.111.1
uvicorn==0.30.1
python-multipart==0.0.9
pillow==10.4.0
python-dotenv==1.0.1
jinja2==3.1.4
aiofiles==24.1.0
trimesh==4.2.0
pyrender==0.1.45
numpy-stl==3.1.0

"@
$ReqFile = "$InstallDir\requirements.txt"
$Requirements | Out-File -FilePath $ReqFile -Encoding utf8

& $PipExe install -r $ReqFile
if ($LASTEXITCODE -ne 0) {
    Write-Error "Ошибка установки зависимостей."
    exit 1
}

# -----------------------------------------------------------------------------
# 7. Создание конфигурационного файла (интерактивно)
# -----------------------------------------------------------------------------
Write-Host "Настройка конфигурации..." -ForegroundColor Green
$ConfigFile = "$ConfigDir\config.yaml"

if (-not (Test-Path $ConfigFile)) {
    Write-Host "Создание нового конфигурационного файла." -ForegroundColor Yellow
    $defaultCam = 0
    $defaultPort = "COM3"
    $defaultBaud = 115200
    $defaultModel = "models/yolov8n.pt"
    $defaultPixelsPerMm = 0.5

    Write-Host "Введите параметры (оставьте пустым для значения по умолчанию):"
    $camIndex = Read-Host "Индекс камеры [0]"
    if ($camIndex -eq "") { $camIndex = $defaultCam }
    $serialPort = Read-Host "Порт Arduino [COM3]"
    if ($serialPort -eq "") { $serialPort = $defaultPort }
    $baudRate = Read-Host "Скорость порта [115200]"
    if ($baudRate -eq "") { $baudRate = $defaultBaud }
    $modelPath = Read-Host "Путь к модели YOLO [models/yolov8n.pt]"
    if ($modelPath -eq "") { $modelPath = $defaultModel }
    $pixelsPerMm = Read-Host "Калибровочный коэффициент (пикселей на мм) [0.5]"
    if ($pixelsPerMm -eq "") { $pixelsPerMm = $defaultPixelsPerMm }

    $ConfigContent = @"
camera:
  camera_index: $camIndex
  width: 640
  height: 480

serial:
  port: "$serialPort"
  baud_rate: $baudRate
  timeout: 2.0
  retry_attempts: 3
  retry_delay: 0.5

model:
  yolo_model_path: "$modelPath"
  confidence_threshold: 0.5
  device: auto

classification:
  min_dimensions: [10, 10, 2]
  max_dimensions: [450, 320, 320]
  circle_ratio_threshold: 0.8
  confidence_low_threshold: 0.6   # <-- добавлено

system:
  conveyor_speed: 1.0
  cycle_timeout: 2.0
  log_level: INFO
  metrics_interval: 5.0
  memory_log_interval: 100

pixels_per_mm: $pixelsPerMm
"@
    $ConfigContent | Out-File -FilePath $ConfigFile -Encoding utf8
    Write-Host "Конфигурация сохранена в $ConfigFile" -ForegroundColor Green
} else {
    Write-Host "Конфигурационный файл уже существует: $ConfigFile" -ForegroundColor Yellow
}

# -----------------------------------------------------------------------------
# 8. Создание bat-файла для запуска
# -----------------------------------------------------------------------------
$BatFile = "$InstallDir\run_robosort.bat"
$BatContent = @"
@echo off
cd /d "$InstallDir"
set PYTHONPATH=$InstallDir
"$PythonExe" main.py --config "$ConfigFile"
pause
"@
$BatContent | Out-File -FilePath $BatFile -Encoding ascii
Write-Host "Создан bat-файл для запуска: $BatFile" -ForegroundColor Green

# -----------------------------------------------------------------------------
# 9. Добавление задачи в планировщик Windows (автозапуск при входе)
# -----------------------------------------------------------------------------
$TaskName = "RoboSort"
$TaskDescription = "Автоматический запуск системы сортировки RoboSort"
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Action = New-ScheduledTaskAction -Execute "$PythonExe" -Argument "main.py --config $ConfigFile" -WorkingDirectory $InstallDir
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

$Ask = Read-Host "Добавить задачу в планировщик для автозапуска при входе? (y/n) [y]"
if ($Ask -eq "" -or $Ask -eq "y") {
    try {
        Register-ScheduledTask -TaskName $TaskName -Description $TaskDescription -Trigger $Trigger -Action $Action -Principal $Principal -Settings $Settings -Force
        Write-Host "Задача '$TaskName' успешно создана." -ForegroundColor Green
    } catch {
        Write-Warning "Не удалось создать задачу: $_"
    }
} else {
    Write-Host "Задача не создана." -ForegroundColor Yellow
}

# -----------------------------------------------------------------------------
# 10. Завершение
# -----------------------------------------------------------------------------
Write-Host "Установка завершена!" -ForegroundColor Green
Write-Host ""
Write-Host "Для запуска вручную используйте: $BatFile"
Write-Host "Или выполните: $PythonExe main.py --config $ConfigFile"
Write-Host "Логи будут сохраняться в: $LogDir"
Write-Host ""
Write-Host "Не забудьте загрузить модель YOLO (если отсутствует) – при первом запуске она скачается автоматически."
Write-Host "При необходимости отредактируйте конфиг: $ConfigFile"

#-------------------------------------------------------------------------------
# 11. Создание ярлыка на рабочем столе (добавить в конец)
$WshShell = New-Object -comObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\RoboSort.lnk")
$Shortcut.TargetPath = "$BatFile"
$Shortcut.WorkingDirectory = "$InstallDir"
$Shortcut.Save()
Write-Host "Ярлык создан на рабочем столе." -ForegroundColor Green
