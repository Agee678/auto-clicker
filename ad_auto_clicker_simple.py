import tkinter as tk
from tkinter import ttk, messagebox
import pyautogui
import time
import threading
import numpy as np
from PIL import ImageGrab
from pynput.mouse import Controller

# ==================== 配置区 ====================
AD_TRIGGER_POS = None     # 广告触发位置
CLOSE_POS = None          # 关闭按钮位置
CLOSE_REF_IMG = None      # 关闭按钮参考图
CHECK_RADIUS = 20         # 检测半径
DIFF_THRESHOLD = 300      # 差异阈值
MAX_WAIT_SECONDS = 60     # 最大等待秒数
POLL_INTERVAL = 1.0       # 检查间隔
POST_CLICK_DELAY = 2.0    # 点击关闭后休眠
# ================================================

mouse = Controller()
running = False
stop_event = threading.Event()


def log(msg):
    """在日志框输出"""
    log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    log_text.see(tk.END)
    root.update_idletasks()


def show_tip(msg):
    status_var.set(msg)
    root.after(1000, lambda: status_var.set("就绪"))


def capture_position(label):
    """用 tkinter 窗口提示，3秒后自动读取鼠标位置"""
    log(f"[捕获] 3秒后记录 {label}，请把鼠标移到目标位置……")
    root.attributes('-topmost', False)
    root.iconify()  # 最小化主窗口，方便用户移动鼠标
    time.sleep(3)
    pos = mouse.position
    root.deiconify()  # 恢复窗口
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
        log("[循环] 开始自动点击")
        threading.Thread(target=auto_loop, daemon=True).start()
    else:
        stop_event.set()
        btn_toggle.config(text="开始循环")
        status_var.set("已暂停")
        log("[循环] 已暂停")


def auto_loop():
    global CLOSE_REF_IMG
    while running and not stop_event.is_set():
        if CLOSE_REF_IMG is None:
            CLOSE_REF_IMG = capture_region(CLOSE_POS, CHECK_RADIUS)
            log("[提示] 已自动记录关闭按钮参考图")

        log(f"[循环] 点击广告: {AD_TRIGGER_POS}")
        click_position(*AD_TRIGGER_POS)

        log(f"[等待] 监测广告结束（最长 {MAX_WAIT_SECONDS} 秒）……")
        start_time = time.time()
        closed = False

        while running and not stop_event.is_set() and (time.time() - start_time) < MAX_WAIT_SECONDS:
            current_img = capture_region(CLOSE_POS, CHECK_RADIUS)
            diff = images_diff(CLOSE_REF_IMG, current_img)

            if diff > DIFF_THRESHOLD:
                log(f"[检测] 关闭按钮状态变化（差异值 {diff}），广告可能已结束。")
                click_position(*CLOSE_POS)
                closed = True
                break

            time.sleep(POLL_INTERVAL)

        if not closed and running and not stop_event.is_set():
            log(f"[超时] 强制点击关闭。")
            click_position(*CLOSE_POS)

        if running and not stop_event.is_set():
            time.sleep(POST_CLICK_DELAY)

    if not stop_event.is_set():
        btn_toggle.config(text="开始循环")
        status_var.set("已停止")
        log("[循环] 已结束")


def on_close():
    global running
    running = False
    stop_event.set()
    root.destroy()


# ==================== GUI 界面 ====================
root = tk.Tk()
root.title("微信小程序广告自动点击助手")
root.geometry("520x420")
root.attributes('-topmost', True)

# 标题
title_label = tk.Label(root, text="智能倒计时自动点击助手", font=("微软雅黑", 14, "bold"))
title_label.pack(pady=10)

# 状态栏
status_var = tk.StringVar(value="就绪")
status_label = tk.Label(root, textvariable=status_var, fg="blue")
status_label.pack()

# 按钮区
btn_frame = tk.Frame(root)
btn_frame.pack(pady=15)

btn_ad = tk.Button(btn_frame, text="F1 记录广告位置", command=record_ad_pos, width=18, bg="#e1f5fe")
btn_ad.grid(row=0, column=0, padx=8, pady=5)

btn_close = tk.Button(btn_frame, text="F2 记录关闭位置", command=record_close_pos, width=18, bg="#fff3e0")
btn_close.grid(row=0, column=1, padx=8, pady=5)

btn_toggle = tk.Button(btn_frame, text="开始循环", command=toggle_cycle, width=18, bg="#c8e6c9")
btn_toggle.grid(row=1, column=0, columnspan=2, pady=10)

btn_exit = tk.Button(root, text="退出程序", command=on_close, width=12, bg="#ffcdd2")
btn_exit.pack(pady=5)

# 日志区
log_frame = tk.LabelFrame(root, text="运行日志", padx=5, pady=5)
log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

log_text = tk.Text(log_frame, height=10, font=("Consolas", 9))
log_text.pack(fill=tk.BOTH, expand=True)

root.protocol("WM_DELETE_WINDOW", on_close)
log("程序已启动。请先点击【记录广告位置】和【记录关闭位置】。")

root.mainloop()