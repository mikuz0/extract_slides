#!/usr/bin/env python3
import cv2
import os
import sys
import argparse
import numpy as np


def analyze_video(video_path, pixel_diff=30, sample_interval_sec=1.0,
                  collect_samples=False):
    """
    Проходит по видео, беря кадр раз в sample_interval_sec секунд.

    Если collect_samples=True — возвращает список (time_sec, gray_frame).
    Если collect_samples=False — только печатает статистику и возвращает None.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Ошибка: не удалось открыть видео '{video_path}'")
        return None

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0
    print(f"Видео: {fps:.2f} FPS, {total_frames} кадров, длительность {duration:.2f} сек")

    if fps <= 0:
        print("Ошибка: не удалось определить FPS.")
        cap.release()
        return None

    frame_step = max(1, int(round(fps * sample_interval_sec)))
    print(f"Шаг между сэмплами: {frame_step} кадров ({sample_interval_sec} сек)")

    RESIZE = (640, 360)

    def to_gray(frame):
        small = cv2.resize(frame, RESIZE)
        return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

    samples = []
    frame_idx = 0
    next_sample_idx = 0

    while True:
        ret = cap.grab()
        if not ret:
            break

        if frame_idx == next_sample_idx:
            ret, frame = cap.retrieve()
            if not ret:
                break
            t_sec = frame_idx / fps
            samples.append((t_sec, to_gray(frame)))
            next_sample_idx += frame_step

        frame_idx += 1

    cap.release()
    print(f"Проанализировано сэмплов: {len(samples)}")

    if collect_samples:
        return samples

    # Считаем статистику по changed_ratio
    ratios = []
    for i in range(1, len(samples)):
        _, gray_curr = samples[i]
        _, gray_prev = samples[i - 1]
        diff_map = cv2.absdiff(gray_prev, gray_curr)
        ratio = float(np.count_nonzero(diff_map > pixel_diff)) / diff_map.size
        ratios.append(ratio)

    return ratios


def print_threshold_recommendations(ratios):
    """Печатает статистику и рекомендации по порогу."""
    if not ratios:
        print("Нет данных для анализа.")
        return

    ratios_arr = np.array(ratios)
    print("\n" + "=" * 60)
    print("СТАТИСТИКА РАЗЛИЧИЙ МЕЖДУ СОСЕДНИМИ СЭМПЛАМИ")
    print("=" * 60)
    print(f"  min      = {ratios_arr.min():.4f}")
    print(f"  max      = {ratios_arr.max():.4f}")
    print(f"  mean     = {ratios_arr.mean():.4f}")
    print(f"  median   = {np.median(ratios_arr):.4f}")
    print(f"  90%-ль   = {np.percentile(ratios_arr, 90):.4f}")
    print(f"  95%-ль   = {np.percentile(ratios_arr, 95):.4f}")
    print(f"  99%-ль   = {np.percentile(ratios_arr, 99):.4f}")

    # Гистограмма: сколько сэмплов попало в диапазоны
    print("\nРаспределение по диапазонам:")
    bins = [0, 0.005, 0.01, 0.02, 0.05, 0.10, 0.20, 1.0]
    for j in range(len(bins) - 1):
        lo, hi = bins[j], bins[j + 1]
        count = int(np.sum((ratios_arr >= lo) & (ratios_arr < hi)))
        bar = "█" * min(count, 60)
        print(f"  [{lo:.3f} .. {hi:.3f}) : {count:4d}  {bar}")

    # Рекомендации
    print("\n" + "-" * 60)
    print("РЕКОМЕНДАЦИИ")
    print("-" * 60)

    p99 = np.percentile(ratios_arr, 99)
    p95 = np.percentile(ratios_arr, 95)
    p90 = np.percentile(ratios_arr, 90)

    median = np.median(ratios_arr)
    mx = ratios_arr.max()

    if mx < 0.01:
        print("⚠  Все различия очень малы (< 0.01).")
        print("   Возможно, видео действительно статично, или нужно")
        print("   уменьшить pixel_diff (например, до 20).")
        print(f"   Текущий pixel_diff = 30, попробуйте 20.")
    elif mx > median * 5:
        print(f"✔  Наблюдается чёткое разделение шума и смен слайдов.")
        print(f"   Медиана (шум)          ~ {median:.4f}")
        print(f"  90-й перцентиль        ~ {p90:.4f}")
        print(f"  95-й перцентиль        ~ {p95:.4f}")
        print(f"  99-й перцентиль        ~ {p99:.4f}")
        print(f"  Максимум               ~ {mx:.4f}")
        print()
        print(f"   Рекомендуемый changed_ratio: между {p95:.4f} и {p99:.4f},")
        print(f"   чтобы отсечь шум и поймать смены. Например:")
        rec = max(p95, min(p99, mx * 0.6))
        print(f"       --changed-ratio {rec:.4f}")
    else:
        print("⚠  Смены слайдов плохо отделяются от шума.")
        print(f"   Медиана = {median:.4f}, максимум = {mx:.4f}")
        print("   Попробуйте:")
        print(f"     - увеличить pixel_diff (например, до 50), чтобы")
        print(f"       отсечь мелкий шум от сжатия и курсора;")
        print(f"     - или уменьшить sample_interval до 0.5 сек для")
        print(f"       более точного попадания в момент смены.")
        print(f"     - changed_ratio можно оставить около {max(0.01, p90):.4f}")


def get_scene_changes(samples, changed_ratio=0.05, min_gap_sec=2.0,
                      pixel_diff=30):
    """
    По готовым сэмплам (time_sec, gray) находит моменты смены слайдов.
    """
    if len(samples) < 2:
        return []

    scene_times = []
    stable_idx = 0

    for i in range(1, len(samples)):
        t_curr, gray_curr = samples[i]
        _, gray_stable = samples[stable_idx]

        diff_map = cv2.absdiff(gray_stable, gray_curr)
        ratio = float(np.count_nonzero(diff_map > pixel_diff)) / diff_map.size

        if ratio > changed_ratio:
            if not scene_times or (t_curr - scene_times[-1]) > min_gap_sec:
                scene_times.append(t_curr)
                stable_idx = i

    return scene_times


def format_timestamp(seconds):
    """HH-MM-SS для имени файла (часы-минуты-секунды)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}-{minutes:02d}-{secs:02d}"


def format_timestamp_human(seconds):
    """ЧЧ:ММ:СС для вывода в консоль."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_timestamp_labeled(seconds):
    """
    Метка с явными обозначениями: HH:.. MM:.. SS:..
    Например: 'HH:00 MM:03 SS:29'
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"HH:{hours:02d} MM:{minutes:02d} SS:{secs:02d}"


def extract_frame(video_path, timestamp, output_dir, label_height=50):
    """
    Извлекает кадр, добавляет снизу белую полосу высотой label_height px
    и пишет на ней временну́ю метку с явными обозначениями HH / MM / SS.

    Параметры:
    - label_height: высота белой полосы (px).
    """
    os.makedirs(output_dir, exist_ok=True)
    ts_str = format_timestamp(timestamp)  # HH-MM-SS
    output_filename = os.path.join(
        output_dir,
        f"slide_HH{ts_str[0:2]}-MM{ts_str[3:5]}-SS{ts_str[6:8]}.png"
    )

    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
    ret, frame = cap.read()
    cap.release()

    if not ret:
        print(f"  Ошибка: не удалось извлечь кадр на {format_timestamp_human(timestamp)}")
        return

    # --- Добавляем белую полосу снизу ---
    h, w = frame.shape[:2]
    label = np.full((label_height, w, 3), 255, dtype=np.uint8)
    frame_with_label = np.vstack([frame, label])

    # --- Пишем временну́ю метку с явными обозначениями ---
    text = format_timestamp_labeled(timestamp)  # HH:00 MM:03 SS:29
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.9
    thickness = 2
    color = (0, 0, 0)  # чёрный текст

    (text_w, text_h), baseline = cv2.getTextSize(text, font, font_scale, thickness)

    # По горизонтали — по центру, по вертикали — по центру полосы.
    x = (w - text_w) // 2
    y = h + (label_height + text_h) // 2

    cv2.putText(frame_with_label, text, (x, y), font,
                font_scale, color, thickness, cv2.LINE_AA)

    cv2.imwrite(output_filename, frame_with_label)
    print(f"  Сохранён: {output_filename}")


def main():
    parser = argparse.ArgumentParser(
        description="Извлечение скриншотов слайдов из видео.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  # Только проверка порога (без сохранения кадров)
  python extract_slides.py 05.mp4 --check-only

  # Проверка с другим pixel_diff
  python extract_slides.py 05.mp4 --check-only --pixel-diff 50

  # Извлечение с явно заданными порогами
  python extract_slides.py 05.mp4 slides --changed-ratio 0.03 --pixel-diff 30

  # Извлечение с другим интервалом сэмплирования
  python extract_slides.py 05.mp4 slides --sample-interval 0.5

  # Извлечение с более высокой белой полосой снизу
  python extract_slides.py 05.mp4 slides --label-height 80
        """
    )
    parser.add_argument("video", help="Путь к видеофайлу")
    parser.add_argument("output_dir", nargs="?", default="slides",
                        help="Папка для сохранения (по умолчанию: slides)")
    parser.add_argument("--check-only", action="store_true",
                        help="Только анализ порога, без сохранения кадров")
    parser.add_argument("--pixel-diff", type=int, default=30,
                        help="Порог разницы яркости одного пикселя (0-255, по умолчанию 30)")
    parser.add_argument("--changed-ratio", type=float, default=0.05,
                        help="Доля изменившихся пикселей (0.0-1.0, по умолчанию 0.05)")
    parser.add_argument("--sample-interval", type=float, default=1.0,
                        help="Интервал между сэмплами в секундах (по умолчанию 1.0)")
    parser.add_argument("--min-gap", type=float, default=2.0,
                        help="Минимум секунд между сменами слайдов (по умолчанию 2.0)")
    parser.add_argument("--capture-delay", type=float, default=1.0,
                        help="Задержка после смены слайда в секундах (по умолчанию 1.0)")
    parser.add_argument("--label-height", type=int, default=50,
                        help="Высота белой полосы снизу в px (по умолчанию 50)")

    args = parser.parse_args()

    if not os.path.exists(args.video):
        print(f"Ошибка: файл '{args.video}' не найден.")
        sys.exit(1)

    # === Режим 1: только проверка порога ===
    if args.check_only:
        print("Режим: только проверка порога (без сохранения кадров)")
        ratios = analyze_video(
            args.video,
            pixel_diff=args.pixel_diff,
            sample_interval_sec=args.sample_interval,
            collect_samples=False
        )
        if ratios:
            print_threshold_recommendations(ratios)
        return

    # === Режим 2: извлечение кадров ===
    print("Режим: извлечение кадров")
    print(f"Параметры: pixel_diff={args.pixel_diff}, "
          f"changed_ratio={args.changed_ratio}, "
          f"sample_interval={args.sample_interval}, "
          f"min_gap={args.min_gap}, "
          f"capture_delay={args.capture_delay}, "
          f"label_height={args.label_height}")

    samples = analyze_video(
        args.video,
        pixel_diff=args.pixel_diff,
        sample_interval_sec=args.sample_interval,
        collect_samples=True
    )

    if not samples:
        print("Не удалось собрать сэмплы.")
        return

    scene_times = get_scene_changes(
        samples,
        changed_ratio=args.changed_ratio,
        min_gap_sec=args.min_gap,
        pixel_diff=args.pixel_diff
    )

    print(f"\nНайдено смен слайдов: {len(scene_times)}")
    for t in scene_times:
        print(f"  {t:7.2f} сек  ({format_timestamp_human(t)})")

    if not scene_times:
        print("\nСмены слайдов не обнаружены. Запустите с --check-only,")
        print("чтобы получить рекомендации по порогу.")
        return

    print(f"\nИзвлечение кадров с задержкой {args.capture_delay} сек "
          f"в папку '{args.output_dir}'...")
    for scene_time in scene_times:
        capture_time = scene_time + args.capture_delay
        extract_frame(args.video, capture_time, args.output_dir,
                      label_height=args.label_height)


if __name__ == "__main__":
    main()
