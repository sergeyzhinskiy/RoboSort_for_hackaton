#!/bin/bash
# Установка RoboSort на Linux (Ubuntu/Debian)
# Требует прав root

set -e

echo "======================================================================"
echo "                Установка RoboSort для Linux"
echo "======================================================================"

# Проверка прав
if [ "$EUID" -ne 0 ]; then
    echo "Пожалуйста, запустите скрипт с правами root: sudo $0"
    exit 1
fi

# -----------------------------------------------------------------------------
# 1. Параметры установки
# -----------------------------------------------------------------------------
INSTALL_DIR="/opt/robosort"
CONFIG_DIR="/etc/robosort"
LOG_DIR="/var/log/robosort"
LIB_DIR="/var/lib/robosort"
MODEL_DIR="$LIB_DIR/models"
VENV_DIR="$INSTALL_DIR/venv"
PYTHON_BIN="$VENV_DIR/bin/python"
PIP_BIN="$VENV_DIR/bin/pip"

# -----------------------------------------------------------------------------
# 2. Создание пользователя и групп (опционально)
# -----------------------------------------------------------------------------
echo "Создание системного пользователя robosort..."
id -u robosort &>/dev/null || useradd -r -s /bin/false robosort

# -----------------------------------------------------------------------------
# 3. Создание директорий
# -----------------------------------------------------------------------------
echo "Создание директорий..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$CONFIG_DIR"
mkdir -p "$LOG_DIR"
mkdir -p "$MODEL_DIR"
mkdir -p "$INSTALL_DIR/src"

# -----------------------------------------------------------------------------
# 4. Установка системных зависимостей
# -----------------------------------------------------------------------------
echo "Установка системных зависимостей..."
apt-get update
apt-get install -y python3 python3-pip python3-venv python3-dev build-essential \
    libssl-dev libffi-dev iptables iproute2 net-tools tzdata curl wget git \
    screen tmux htop uml-utilities netcat-openbsd

# Дополнительно для OpenCV
apt-get install -y libopencv-dev python3-opencv 2>/dev/null || true

# -----------------------------------------------------------------------------
# 5. Копирование исходного кода (если запускаем из корня репозитория)
# -----------------------------------------------------------------------------
echo "Копирование исходных файлов..."
if [ -d "./src" ] && [ -f "./main.py" ]; then
    cp -r ./src "$INSTALL_DIR/"
    cp ./main.py "$INSTALL_DIR/"
    cp ./__init__.py "$INSTALL_DIR/" 2>/dev/null || true
else
    echo "Ошибка: не найдены src/ и main.py. Запустите скрипт из корня репозитория."
    exit 1
fi

# -----------------------------------------------------------------------------
# 6. Создание виртуального окружения
# -----------------------------------------------------------------------------
echo "Создание виртуального окружения..."
python3 -m venv "$VENV_DIR"
if [ ! -f "$PYTHON_BIN" ]; then
    echo "Ошибка создания виртуального окружения."
    exit 1
fi

# -----------------------------------------------------------------------------
# 7. Установка Python-зависимостей
# -----------------------------------------------------------------------------
echo "Установка Python-зависимостей..."
$PIP_BIN install --upgrade pip setuptools wheel

cat > "$INSTALL_DIR/requirements.txt" << 'EOF'
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
EOF

$PIP_BIN install -r "$INSTALL_DIR/requirements.txt"

# -----------------------------------------------------------------------------
# 8. Создание конфигурационного файла
# -----------------------------------------------------------------------------
echo "Настройка конфигурации..."
CONFIG_FILE="$CONFIG_DIR/config.yaml"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Введите параметры (оставьте пустым для значения по умолчанию):"
    read -p "Индекс камеры [0]: " CAM_INDEX
    CAM_INDEX=${CAM_INDEX:-0}
    read -p "Порт Arduino (например, /dev/ttyUSB0) [/dev/ttyUSB0]: " SERIAL_PORT
    SERIAL_PORT=${SERIAL_PORT:-/dev/ttyUSB0}
    read -p "Скорость порта [115200]: " BAUD_RATE
    BAUD_RATE=${BAUD_RATE:-115200}
    read -p "Путь к модели YOLO (относительно $INSTALL_DIR) [models/yolov8n.pt]: " MODEL_PATH
    MODEL_PATH=${MODEL_PATH:-models/yolov8n.pt}
    read -p "Калибровочный коэффициент (пикселей на мм) [0.5]: " PIXELS_PER_MM
    PIXELS_PER_MM=${PIXELS_PER_MM:-0.5}

    cat > "$CONFIG_FILE" << EOF
camera:
  camera_index: $CAM_INDEX
  width: 640
  height: 480

serial:
  port: "$SERIAL_PORT"
  baud_rate: $BAUD_RATE
  timeout: 2.0

model:
  yolo_model_path: "$MODEL_PATH"
  confidence_threshold: 0.5
  device: auto

classification:
  min_dimensions: [10, 10, 2]
  max_dimensions: [450, 320, 320]
  circle_ratio_threshold: 0.7

system:
  conveyor_speed: 1.0
  cycle_timeout: 2.0
  log_level: INFO

pixels_per_mm: $PIXELS_PER_MM
EOF
    echo "Конфигурация сохранена в $CONFIG_FILE"
else
    echo "Конфигурация уже существует: $CONFIG_FILE"
fi

# -----------------------------------------------------------------------------
# 9. Создание скрипта запуска
# -----------------------------------------------------------------------------
echo "Создание скрипта управления..."
cat > /usr/local/bin/robosort-ctl << 'EOF'
#!/bin/bash
case "$1" in
    start)
        cd /opt/robosort
        /opt/robosort/venv/bin/python main.py --config /etc/robosort/config.yaml &
        echo $! > /var/run/robosort.pid
        ;;
    stop)
        if [ -f /var/run/robosort.pid ]; then
            kill $(cat /var/run/robosort.pid) && rm -f /var/run/robosort.pid
        else
            pkill -f "python main.py"
        fi
        ;;
    status)
        if pgrep -f "python main.py" > /dev/null; then
            echo "RoboSort запущен"
        else
            echo "RoboSort не запущен"
        fi
        ;;
    *)
        echo "Использование: robosort-ctl {start|stop|status}"
        exit 1
        ;;
esac
exit 0
EOF
chmod +x /usr/local/bin/robosort-ctl

# -----------------------------------------------------------------------------
# 10. Создание systemd-сервиса
# -----------------------------------------------------------------------------
echo "Создание systemd-сервиса..."
cat > /etc/systemd/system/robosort.service << EOF
[Unit]
Description=RoboSort - система сортировки объектов
After=network.target

[Service]
Type=simple
User=robosort
WorkingDirectory=$INSTALL_DIR
ExecStart=$PYTHON_BIN main.py --config $CONFIG_FILE
Restart=on-failure
RestartSec=5
StandardOutput=append:$LOG_DIR/out.log
StandardError=append:$LOG_DIR/err.log
Environment=PYTHONPATH=$INSTALL_DIR

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable robosort.service
echo "Сервис robosort создан и включён в автозагрузку."

# -----------------------------------------------------------------------------
# 11. Настройка прав
# -----------------------------------------------------------------------------
echo "Установка прав доступа..."
chown -R robosort:robosort "$INSTALL_DIR" "$LOG_DIR" "$LIB_DIR"
chown -R root:root "$CONFIG_DIR"
chmod 755 "$INSTALL_DIR"
chmod 644 "$CONFIG_FILE"

# -----------------------------------------------------------------------------
# 12. Проверка сети (опционально – если нужен IP Forwarding)
# -----------------------------------------------------------------------------
# (Для RoboSort не требуется, но оставлено для расширяемости)

# -----------------------------------------------------------------------------
# 13. Завершение
# -----------------------------------------------------------------------------
echo "======================================================================"
echo "Установка RoboSort завершена!"
echo ""
echo "Конфигурация: $CONFIG_FILE"
echo "Логи: $LOG_DIR"
echo ""
echo "Управление:"
echo "  Запуск вручную:   robosort-ctl start"
echo "  Остановка:        robosort-ctl stop"
echo "  Статус:           robosort-ctl status"
echo ""
echo "  Или используйте systemctl:"
echo "    systemctl start robosort"
echo "    systemctl stop robosort"
echo "    journalctl -u robosort -f  # просмотр логов"
echo ""
echo "Для запуска от имени пользователя robosort можно также выполнить:"
echo "  sudo -u robosort $PYTHON_BIN $INSTALL_DIR/main.py --config $CONFIG_FILE"
echo ""
echo "При первом запуске модель YOLO будет автоматически скачана в $MODEL_DIR"
echo "======================================================================"