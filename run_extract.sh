#!/usr/bin/env bash
#
# Пакетная обработка всех видео из указанного каталога.
# Для каждого видео создаётся подкаталог в slides/ по имени файла,
# куда складываются скриншоты слайдов.
#
# Использование:
#   ./run_extract.sh                # обработать все видео из VIDEO_DIR
#   ./run_extract.sh --check-only   # только анализ порога, без сохранения
#   ./run_extract.sh --help         # справка

set -euo pipefail

# ============================================================
# НАСТРОЙКИ — меняйте здесь
# ============================================================

# Каталог с видеофайлами
VIDEO_DIR="/home/mikuz/Downloads/Системное моделирование/"

# Каталог для результатов (относительно текущей директории)
OUTPUT_DIR="slides"

# Параметры извлечения слайдов (передаются в extract_slides.py)
CHANGED_RATIO="0.03"
PIXEL_DIFF="30"
SAMPLE_INTERVAL="0.10"
MIN_GAP="1.0"
CAPTURE_DELAY="1.0"
LABEL_HEIGHT="50"

# Путь к Python-скрипту (относительно этого скрипта)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTRACT_PY="${SCRIPT_DIR}/extract_slides.py"

# Виртуальное окружение (если используете)
VENV_ACTIVATE="${SCRIPT_DIR}/myenv/bin/activate"

# ============================================================
# Вспомогательные функции
# ============================================================

usage() {
    cat <<EOF
Использование: $0 [опции]

Опции:
  --check-only        Только анализ порога, без сохранения кадров
  --changed-ratio N   Порог доли изменившихся пикселей (по умолчанию: $CHANGED_RATIO)
  --pixel-diff N      Порог разницы яркости пикселя (по умолчанию: $PIXEL_DIFF)
  --help              Показать эту справку

Переменные (правьте в начале скрипта):
  VIDEO_DIR = $VIDEO_DIR
  OUTPUT_DIR = $OUTPUT_DIR
  EXTRACT_PY = $EXTRACT_PY
EOF
}

# ============================================================
# Разбор аргументов
# ============================================================

CHECK_ONLY=0
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --check-only)
            CHECK_ONLY=1
            shift
            ;;
        --changed-ratio)
            CHANGED_RATIO="$2"
            shift 2
            ;;
        --pixel-diff)
            PIXEL_DIFF="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "Неизвестный аргумент: $1" >&2
            usage
            exit 1
            ;;
    esac
done

# ============================================================
# Проверки
# ============================================================

if [[ ! -f "$EXTRACT_PY" ]]; then
    echo "Ошибка: не найден $EXTRACT_PY" >&2
    exit 1
fi

if [[ ! -d "$VIDEO_DIR" ]]; then
    echo "Ошибка: каталог '$VIDEO_DIR' не существует." >&2
    exit 1
fi

if [[ ! -d "$OUTPUT_DIR" ]]; then
    echo "Создаю каталог '$OUTPUT_DIR'..."
    mkdir -p "$OUTPUT_DIR"
fi

# Активируем venv, если он есть
if [[ -f "$VENV_ACTIVATE" ]]; then
    # shellcheck disable=SC1090
    source "$VENV_ACTIVATE"
    echo "Активировано виртуальное окружение: $VENV_ACTIVATE"
fi

# Определяем Python (если venv — python, иначе python3)
PYTHON_BIN="python3"
if [[ -f "$VENV_ACTIVATE" ]]; then
    PYTHON_BIN="python"
fi

# ============================================================
# Основная обработка
# ============================================================

# Собираем список видеофайлов
shopt -s nullglob nocaseglob
VIDEO_FILES=(
    "$VIDEO_DIR"/*.mp4
    "$VIDEO_DIR"/*.mkv
    "$VIDEO_DIR"/*.avi
    "$VIDEO_DIR"/*.mov
    "$VIDEO_DIR"/*.webm
)
shopt -u nullglob nocaseglob

if [[ ${#VIDEO_FILES[@]} -eq 0 ]]; then
    echo "В каталоге '$VIDEO_DIR' не найдено видеофайлов."
    exit 0
fi

echo "============================================================"
echo "Каталог с видео : $VIDEO_DIR"
echo "Каталог вывода  : $OUTPUT_DIR"
echo "Найдено видео   : ${#VIDEO_FILES[@]}"
echo "Режим           : $([[ $CHECK_ONLY -eq 1 ]] && echo 'только проверка порога' || echo 'извлечение кадров')"
echo "============================================================"

TOTAL=0
PROCESSED=0
FAILED=0

for video in "${VIDEO_FILES[@]}"; do
    TOTAL=$((TOTAL + 1))
    filename="$(basename "$video")"
    # Имя без расширения — используется как имя подкаталога
    name="${filename%.*}"
    target_dir="${OUTPUT_DIR}/${name}"

    echo
    echo "------------------------------------------------------------"
    echo "[$TOTAL/${#VIDEO_FILES[@]}] $filename"
    echo "------------------------------------------------------------"

    if [[ $CHECK_ONLY -eq 1 ]]; then
        # В режиме проверки каталог не нужен, но для единообразия создадим
        if "$PYTHON_BIN" "$EXTRACT_PY" "$video" --check-only \
                --changed-ratio "$CHANGED_RATIO" \
                --pixel-diff "$PIXEL_DIFF" \
                --sample-interval "$SAMPLE_INTERVAL"; then
            PROCESSED=$((PROCESSED + 1))
        else
            echo "Ошибка при обработке '$filename'" >&2
            FAILED=$((FAILED + 1))
        fi
    else
        mkdir -p "$target_dir"
        if "$PYTHON_BIN" "$EXTRACT_PY" "$video" "$target_dir" \
                --changed-ratio "$CHANGED_RATIO" \
                --pixel-diff "$PIXEL_DIFF" \
                --sample-interval "$SAMPLE_INTERVAL" \
                --min-gap "$MIN_GAP" \
                --capture-delay "$CAPTURE_DELAY" \
                --label-height "$LABEL_HEIGHT"; then
            count=$(find "$target_dir" -maxdepth 1 -name '*.png' | wc -l)
            echo "  ✔ Сохранено слайдов: $count"
            PROCESSED=$((PROCESSED + 1))
        else
            echo "Ошибка при обработке '$filename'" >&2
            FAILED=$((FAILED + 1))
        fi
    fi
done

echo
echo "============================================================"
echo "ГОТОВО"
echo "  Всего видео    : $TOTAL"
echo "  Обработано     : $PROCESSED"
echo "  С ошибками     : $FAILED"
echo "============================================================"
