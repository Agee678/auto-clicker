import tkinter as tk
from tkinter import messagebox
import pyautogui
import time
import threading
import keyboard
import pytesseract
from PIL import ImageGrab
from pynput.mouse import Controller
import os
import sys

# 挂机模式：关闭 pyautogui 的角落 fail-safe，避免鼠标移到屏幕角落触发异常
pyautogui.FAILSAFE = False


def setup_tesseract():
    """自动探测 Tesseract 可执行文件，优先使用随包带来的，其次系统默认路径"""
    # 1. 打包后随包带来的目录（sys._MEIPASS）
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
        cand = os.path.join(base, 'tesseract', 'tesseract.exe')
        if os.path.exists(cand):
            pytesseract.pytesseract.tesseract_cmd = cand
            os.environ['TESSDATA_PREFIX'] = os.path.join(base, 'tesseract')
            return True

    # 2. exe 同级目录下的 tesseract 文件夹（方便手动分发）
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.join(base, 'tesseract', 'tesseract.exe')
    if os.path.exists(cand):
        pytesseract.pytesseract.tesseract_cmd = cand
        os.environ['TESSDATA_PREFIX'] = os.path.join(base, 'tesseract')
        return True

    # 3. 系统常见安装路径
    for p in [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
    ]:
        if os.path.exists(p):
            pytesseract.pytesseract.tesseract_cmd = p
            return True

    return False


# 探测一次，结果缓存
OCR_READY = setup_tesseract()


# ==================== 全局状态 ====================
AD_TRIGGER_POS = None     # 广告触发位置
CLOSE_POS = None          # 关闭按钮位置
COUNTDOWN_REGION = None   # 倒计时区域 (left, top, right, bottom)
WAIT_SECONDS = 30         # OCR 不可用时的固定等待秒数
WAIT_AFTER_ZERO = 1       # 倒计时归零后再等多少秒点关闭
VERIFY_BEFORE_END = 5     # 剩余多少秒开始验证同步

running = False
stop_event = threading.Event()
emergency_stop = False
ocr_current_text = "未启动"

mouse = Controller()


def log(msg):
    log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    log_text.see(tk.END)
    root.update_idletasks()


def show_tip(msg):
    status_var.set(msg)
    root.after(1200, lambda: status_var.set("就绪"))


def capture_position(label):
    """3秒后记录鼠标位置"""
    log(f"[捕获] 3秒后记录 {label}，请把鼠标移到目标位置……")
    root.attributes('-topmost', False)
    root.iconify()
    time.sleep(3)
    pos = mouse.position
    root.deiconify()
    root.attributes('-topmost', True)
    log(f"[已记录] {label}: {pos}")
    show_tip(f"{label} 记录成功")
    return pos


def capture_region_from_pos(center_pos, width=120, height=50):
    """以中心点截取矩形区域，供 OCR 识别"""
    x, y = center_pos
    left = max(0, x - width // 2)
    top = max(0, y - height // 2)
    right = left + width
    bottom = top + height
    return (left, top, right, bottom)


def click_position(x, y):
    pyautogui.click(x, y)
    log(f"[点击] ({x}, {y})")


def record_ad_pos():
    global AD_TRIGGER_POS
    AD_TRIGGER_POS = capture_position("广告触发位置")
    log(f"广告位置已保存: {AD_TRIGGER_POS}")


def record_close_pos():
    global CLOSE_POS
    CLOSE_POS = capture_position("关闭按钮位置")
    log(f"关闭位置已保存: {CLOSE_POS}")


def record_countdown_region():
    """记录倒计时数字区域中心点"""
    global COUNTDOWN_REGION
    pos = capture_position("倒计时数字区域中心")
    if pos:
        COUNTDOWN_REGION = capture_region_from_pos(pos)
        log(f"倒计时区域已保存: {COUNTDOWN_REGION}")
        show_tip("倒计时区域记录成功")


def ocr_read(region):
    """OCR 识别倒计时区域，返回纯数字字符串或 None"""
    if not OCR_READY or region is None:
        return None
    try:
        img = ImageGrab.grab(bbox=region)
        text = pytesseract.image_to_string(img, lang='chi_sim+eng', config='--psm 7 digits')
        digits = ''.join(filter(str.isdigit, text))
        return digits if digits else None
    except Exception as e:
        log(f"[OCR错误] {e}")
        return None


def toggle_cycle():
    global running
    if AD_TRIGGER_POS is None or CLOSE_POS is None:
        messagebox.showwarning("提示", "请先记录广告位置和关闭按钮位置！")
        return

    try:
        wait_sec = int(wait_var.get())
    except ValueError:
        wait_sec = 30

    running = not running
    if running:
        stop_event.clear()
        btn_toggle.config(text="暂停循环")
        status_var.set("运行中")
        mode = "OCR倒计时" if (OCR_READY and COUNTDOWN_REGION) else "固定等待"
        log(f"[循环] 开始自动点击，模式：{mode}")
        threading.Thread(target=auto_loop, args=(wait_sec,), daemon=True).start()
    else:
        stop_event.set()
        btn_toggle.config(text="开始循环")
        status_var.set("已暂停")
        log("[循环] 已暂停")


def auto_loop(wait_sec):
    global running, emergency_stop, ocr_current_text
    emergency_stop = False

    while running and not stop_event.is_set() and not emergency_stop:
        total_seconds = None      # 首次识别到的总时长
        detected_seconds = None   # 当前识别到的剩余秒数
        zero_confirmed_time = None

        # 1. 点击广告
        log(f"[循环] 点击广告: {AD_TRIGGER_POS}")
        click_position(*AD_TRIGGER_POS)

        start_time = time.time()

        while running and not stop_event.is_set() and not emergency_stop:
            elapsed = time.time() - start_time

            # OCR 识别
            text = ocr_read(COUNTDOWN_REGION) if COUNTDOWN_REGION else None
            if text:
                ocr_current_text = text
                try:
                    val = int(text)
                    if total_seconds is None:
                        total_seconds = val
                        log(f"[检测] 首次识别倒计时总时长: {total_seconds}秒")
                    detected_seconds = val
                except ValueError:
                    pass
            else:
                ocr_current_text = "--"

            # 界面实时显示 OCR 数字
            root.after(0, lambda t=ocr_current_text: ocr_var.set(f"OCR倒计时: {t}"))

            # 进入“结束前 5 秒”验证期
            if total_seconds is not None and detected_seconds is not None:
                if detected_seconds <= VERIFY_BEFORE_END:
                    log(f"[验证] 剩余{detected_seconds}秒，进入同步验证期")

                # 倒计时归零 或 数字消失（广告结束）
                is_zero = text and int(text) == 0
                is_disappeared = (text is None and detected_seconds is not None and detected_seconds > 0)

                if is_zero or is_disappeared:
                    if zero_confirmed_time is None:
                        zero_confirmed_time = time.time()
                        if is_zero:
                            log(f"[检测] 识别到倒计时归零(0)，{WAIT_AFTER_ZERO}秒后点击关闭")
                        else:
                            log(f"[检测] 倒计时数字消失，{WAIT_AFTER_ZERO}秒后点击关闭")

                    if zero_confirmed_time and time.time() - zero_confirmed_time >= WAIT_AFTER_ZERO:
                        log(f"[动作] 倒计时结束{WAIT_AFTER_ZERO}秒后，点击关闭: {CLOSE_POS}")
                        click_position(*CLOSE_POS)
                        break

            # OCR 不可用时，回退到固定等待
            if not OCR_READY or COUNTDOWN_REGION is None:
                if elapsed >= wait_sec:
                    log(f"[固定等待] 已等待{wait_sec}秒，点击关闭")
                    click_position(*CLOSE_POS)
                    break

            time.sleep(0.5)

        if emergency_stop or not running or stop_event.is_set():
            break

        time.sleep(2)  # 轮次间隔

    if not emergency_stop and running:
        btn_toggle.config(text="开始循环")
        status_var.set("已停止")
        log("[循环] 已结束")
    elif emergency_stop:
        btn_toggle.config(text="开始循环")
        status_var.set("紧急停止")
        log("[紧急停止] 循环已强制终止")
        running = False


def emergency_stop_listener():
    """F4 紧急停止热键，后台监听"""
    while True:
        try:
            if keyboard.is_pressed('f4'):
                global running, emergency_stop
                if running:
                    emergency_stop = True
                    running = False
                    stop_event.set()
                    root.after(0, lambda: log("[紧急停止] 检测到 F4，已强制停止"))
                    root.after(0, lambda: btn_toggle.config(text="开始循环"))
                    root.after(0, lambda: status_var.set("紧急停止"))
                    root.after(0, lambda: ocr_var.set("OCR倒计时: --"))
                    time.sleep(1)  # 防抖
        except Exception:
            pass
        time.sleep(0.1)


def on_close():
    global running
    running = False
    stop_event.set()
    root.destroy()


# ==================== GUI 界面 ====================
root = tk.Tk()
root.title("微信小程序广告自动点击助手（OCR 倒计时版）")
root.geometry("560x540")
root.attributes('-topmost', True)

title_label = tk.Label(root, text="OCR 倒计时自动点击助手", font=("微软雅黑", 14, "bold"))
title_label.pack(pady=10)

status_var = tk.StringVar(value="就绪")
status_label = tk.Label(root, textvariable=status_var, fg="blue", font=("微软雅黑", 10))
status_label.pack()

ocr_var = tk.StringVar(value="OCR倒计时: --")
ocr_label = tk.Label(root, textvariable=ocr_var, fg="green", font=("微软雅黑", 11, "bold"))
ocr_label.pack()

# 配置区
cfg_frame = tk.LabelFrame(root, text="参数设置", padx=5, pady=5)
cfg_frame.pack(pady=5, fill=tk.X, padx=10)

tk.Label(cfg_frame, text="固定等待(秒):", font=("微软雅黑", 9)).grid(row=0, column=0, sticky=tk.W)
wait_var = tk.StringVar(value="30")
tk.Entry(cfg_frame, textvariable=wait_var, width=6).grid(row=0, column=1, padx=5)

tk.Label(cfg_frame, text="归零后再等(秒):", font=("微软雅黑", 9)).grid(row=0, column=2, sticky=tk.W, padx=(10, 0))
zero_var = tk.StringVar(value="1")
tk.Entry(cfg_frame, textvariable=zero_var, width=6).grid(row=0, column=3, padx=5)

tk.Label(cfg_frame, text="提前验证(秒):", font=("微软雅黑", 9)).grid(row=1, column=0, sticky=tk.W)
verify_var = tk.StringVar(value="5")
tk.Entry(cfg_frame, textvariable=verify_var, width=6).grid(row=1, column=1, padx=5)


def load_config():
    global WAIT_SECONDS, WAIT_AFTER_ZERO, VERIFY_BEFORE_END
    try:
        WAIT_SECONDS = int(wait_var.get())
    except Exception:
        pass
    try:
        WAIT_AFTER_ZERO = int(zero_var.get())
    except Exception:
        pass
    try:
        VERIFY_BEFORE_END = int(verify_var.get())
    except Exception:
        pass


# 按钮区
btn_frame = tk.Frame(root)
btn_frame.pack(pady=15)

btn_ad = tk.Button(btn_frame, text="记录广告位置", command=record_ad_pos, width=16, bg="#e1f5fe")
btn_ad.grid(row=0, column=0, padx=8, pady=5)

btn_close = tk.Button(btn_frame, text="记录关闭位置", command=record_close_pos, width=16, bg="#fff3e0")
btn_close.grid(row=0, column=1, padx=8, pady=5)

btn_count = tk.Button(btn_frame, text="记录倒计时区域", command=record_countdown_region, width=16, bg="#e8f5e9")
btn_count.grid(row=1, column=0, columnspan=2, pady=5)

btn_toggle = tk.Button(btn_frame, text="开始循环",
                       command=lambda: [load_config(), toggle_cycle()], width=16, bg="#c8e6c9")
btn_toggle.grid(row=2, column=0, columnspan=2, pady=10)

btn_exit = tk.Button(root, text="退出程序", command=on_close, width=12, bg="#ffcdd2")
btn_exit.pack(pady=5)

tip_label = tk.Label(root,
                     text="提示：OCR 需随包携带 Tesseract（tesseract.exe + tessdata）；不可用时自动回退固定等待；循环中按 F4 紧急停止",
                     fg="gray", font=("微软雅黑", 9), wraplength=520)
tip_label.pack()

# 日志区
log_frame = tk.LabelFrame(root, text="运行日志", padx=5, pady=5)
log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

log_text = tk.Text(log_frame, height=10, font=("Consolas", 9))
log_text.pack(fill=tk.BOTH, expand=True)

root.protocol("WM_DELETE_WINDOW", on_close)
log("程序已启动。请先记录广告位置、关闭位置、倒计时区域，再点【开始循环】。")

# 启动热键监听线程
threading.Thread(target=emergency_stop_listener, daemon=True).start()

root.mainloop()