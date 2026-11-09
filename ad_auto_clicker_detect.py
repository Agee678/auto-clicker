import tkinter as tk
from tkinter import messagebox
import pyautogui
import time
import threading
import keyboard
import numpy as np
from PIL import ImageGrab
from pynput.mouse import Controller

# ==================== 配置区 ====================
AD_TRIGGER_POS = None     # 广告触发位置
CLOSE_POS = None          # 关闭按钮位置
CLOSE_REF_IMG = None      # 关闭按钮参考图（F2 记录时捕获）

CHECK_RADIUS = 20         # 关闭按钮周围检测半径（像素）
DIFF_THRESHOLD = 1000     # 差异阈值，越大越不容易误触（原 300 太低）
CONFIRM_COUNT = 3         # 连续多少次检测到变化才确认点击关闭
STABILIZE_SECONDS = 5     # 点击广告后，前多少秒不检测（让广告界面稳定）
MAX_WAIT_SECONDS = 60     # 最长等待秒数
POLL_INTERVAL = 1.0       # 检查间隔（秒）
POST_CLICK_DELAY = 2.0    # 点击关闭后休眠（秒）
# ================================================

mouse = Controller()
running = False
stop_event = threading.Event()
emergency_stop = False


def log(msg):
    log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    log_text.see(tk.END)
    root.update_idletasks()


def show_tip(msg):
    status_var.set(msg)
    root.after(1200, lambda: status_var.set("就绪"))


def capture_position(label):
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


def capture_region(center_pos, radius=20):
    x, y = center_pos
    left = max(0, x - radius)
    top = max(0, y - radius)
    right = x + radius
    bottom = y + radius
    return np.array(ImageGrab.grab(bbox=(left, top, right, bottom)))


def click_position(x, y):
    pyautogui.click(x, y)
    log(f"[点击] ({x}, {y})")


def images_diff(img1, img2):
    if img1.shape != img2.shape:
        return float('inf')
    return int(np.abs(img1.astype(int) - img2.astype(int)).sum())


def record_ad_pos():
    global AD_TRIGGER_POS
    AD_TRIGGER_POS = capture_position("广告触发位置")
    log(f"广告位置已保存: {AD_TRIGGER_POS}")


def record_close_pos():
    global CLOSE_POS, CLOSE_REF_IMG
    CLOSE_POS = capture_position("关闭按钮位置")
    CLOSE_REF_IMG = capture_region(CLOSE_POS, CHECK_RADIUS)
    log(f"关闭位置已保存: {CLOSE_POS}")
    log("[提示] 参考图已记录，请确保此时关闭按钮处于广告未结束时的状态。")


def toggle_cycle():
    global running
    if AD_TRIGGER_POS is None or CLOSE_POS is None:
        messagebox.showwarning("提示", "请先记录广告位置和关闭按钮位置！")
        return

    running = not running
    if running:
        stop_event.clear()
        btn_toggle.config(text="暂停循环")
        status_var.set("运行中")
        log("[循环] 开始自动点击（带图像检测）")
        threading.Thread(target=auto_loop, daemon=True).start()
    else:
        stop_event.set()
        btn_toggle.config(text="开始循环")
        status_var.set("已暂停")
        log("[循环] 已暂停")


def auto_loop():
    global CLOSE_REF_IMG, emergency_stop, running
    emergency_stop = False

    while running and not stop_event.is_set() and not emergency_stop:
        # 参考图为空时自动补记录
        if CLOSE_REF_IMG is None:
            CLOSE_REF_IMG = capture_region(CLOSE_POS, CHECK_RADIUS)
            log("[提示] 已自动记录关闭按钮参考图")

        # 1. 点击广告
        log(f"[循环] 点击广告: {AD_TRIGGER_POS}")
        click_position(*AD_TRIGGER_POS)

        # 2. 稳定期：前 STABILIZE_SECONDS 秒不检测，只等待
        log(f"[稳定] 广告播放中，前 {STABILIZE_SECONDS} 秒不检测关闭按钮……")
        for i in range(STABILIZE_SECONDS, 0, -1):
            if not running or stop_event.is_set() or emergency_stop:
                break
            status_var.set(f"稳定中 {i} 秒")
            root.update_idletasks()
            time.sleep(1)

        if emergency_stop or not running or stop_event.is_set():
            break

        # 3. 检测期：开始监测关闭按钮状态变化
        log("[检测] 开始监测关闭按钮状态变化……")
        start_time = time.time()
        consecutive_diff = 0
        closed = False

        while running and not stop_event.is_set() and not emergency_stop:
            if time.time() - start_time > MAX_WAIT_SECONDS:
                log(f"[超时] {MAX_WAIT_SECONDS} 秒内未检测到稳定变化，强制点击关闭。")
                click_position(*CLOSE_POS)
                closed = True
                break

            current_img = capture_region(CLOSE_POS, CHECK_RADIUS)
            diff = images_diff(CLOSE_REF_IMG, current_img)

            if diff > DIFF_THRESHOLD:
                consecutive_diff += 1
                log(f"[检测] 差异值 {diff}，连续 {consecutive_diff}/{CONFIRM_COUNT}")
                if consecutive_diff >= CONFIRM_COUNT:
                    log(f"[确认] 连续 {CONFIRM_COUNT} 次检测到变化，广告可能已结束。")
                    click_position(*CLOSE_POS)
                    closed = True
                    break
            else:
                consecutive_diff = 0  # 差异不足，重置计数

            time.sleep(POLL_INTERVAL)

        if not closed and not emergency_stop and running and not stop_event.is_set():
            time.sleep(POST_CLICK_DELAY)

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
                    time.sleep(1)
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
root.title("微信小程序广告自动点击助手（检测版）")
root.geometry("560x480")
root.attributes('-topmost', True)

title_label = tk.Label(root, text="图像检测版自动点击助手", font=("微软雅黑", 14, "bold"))
title_label.pack(pady=10)

status_var = tk.StringVar(value="就绪")
status_label = tk.Label(root, textvariable=status_var, fg="blue", font=("微软雅黑", 10))
status_label.pack()

# 配置区
cfg_frame = tk.LabelFrame(root, text="检测参数", padx=5, pady=5)
cfg_frame.pack(pady=5, fill=tk.X, padx=10)

tk.Label(cfg_frame, text="稳定等待(秒):", font=("微软雅黑", 9)).grid(row=0, column=0, sticky=tk.W)
stab_var = tk.StringVar(value=str(STABILIZE_SECONDS))
tk.Entry(cfg_frame, textvariable=stab_var, width=6).grid(row=0, column=1, padx=5)

tk.Label(cfg_frame, text="差异阈值:", font=("微软雅黑", 9)).grid(row=0, column=2, sticky=tk.W, padx=(10,0))
diff_var = tk.StringVar(value=str(DIFF_THRESHOLD))
tk.Entry(cfg_frame, textvariable=diff_var, width=8).grid(row=0, column=3, padx=5)

tk.Label(cfg_frame, text="连续确认次数:", font=("微软雅黑", 9)).grid(row=1, column=0, sticky=tk.W)
confirm_var = tk.StringVar(value=str(CONFIRM_COUNT))
tk.Entry(cfg_frame, textvariable=confirm_var, width=6).grid(row=1, column=1, padx=5)

# 按钮区
btn_frame = tk.Frame(root)
btn_frame.pack(pady=15)

btn_ad = tk.Button(btn_frame, text="记录广告位置", command=record_ad_pos, width=16, bg="#e1f5fe")
btn_ad.grid(row=0, column=0, padx=8, pady=5)

btn_close = tk.Button(btn_frame, text="记录关闭位置", command=record_close_pos, width=16, bg="#fff3e0")
btn_close.grid(row=0, column=1, padx=8, pady=5)

btn_toggle = tk.Button(btn_frame, text="开始循环", command=toggle_cycle, width=16, bg="#c8e6c9")
btn_toggle.grid(row=1, column=0, columnspan=2, pady=10)

btn_exit = tk.Button(root, text="退出程序", command=on_close, width=12, bg="#ffcdd2")
btn_exit.pack(pady=5)

tip_label = tk.Label(root, text="提示：记录关闭位置时，请确保广告尚未弹出；循环中按 F4 可紧急停止",
                     fg="gray", font=("微软雅黑", 9))
tip_label.pack()

# 日志区
log_frame = tk.LabelFrame(root, text="运行日志", padx=5, pady=5)
log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

log_text = tk.Text(log_frame, height=10, font=("Consolas", 9))
log_text.pack(fill=tk.BOTH, expand=True)

root.protocol("WM_DELETE_WINDOW", on_close)
log("程序已启动。请先记录广告位置和关闭位置（广告未出现时记录关闭位置），再点【开始循环】。")

# 启动热键监听线程
threading.Thread(target=emergency_stop_listener, daemon=True).start()

root.mainloop()