import pyautogui
import time
import keyboard
from pynput.mouse import Controller

# ==================== 配置区 ====================
AD_TRIGGER_POS = None    # 广告触发位置，按 F1 记录
CLOSE_POS = None         # 关闭按钮位置，按 F2 记录
AD_WAIT_SECONDS = 30     # 单次广告等待秒数（可根据实际倒计时修改）
POST_CLICK_DELAY = 2.0   # 点击关闭后休眠（秒）
# ================================================

mouse = Controller()


def capture_position(label: str):
    print(f"[捕获] 将鼠标移动到 {label}，按 F 确认，ESC 取消……")
    while True:
        if keyboard.is_pressed('f'):
            pos = mouse.position
            time.sleep(0.2)
            print(f"[已记录] {label}: {pos}")
            return pos
        if keyboard.is_pressed('esc'):
            print("[已取消]")
            return None
        time.sleep(0.05)


def click_position(x: int, y: int):
    pyautogui.click(x, y)
    print(f"[点击] ({x}, {y})")


def run_cycle() -> bool:
    global AD_TRIGGER_POS, CLOSE_POS

    if AD_TRIGGER_POS is None or CLOSE_POS is None:
        print("[错误] 请先按 F1 和 F2 分别记录广告位置和关闭位置。")
        return True

    print(f"[循环] 点击广告: {AD_TRIGGER_POS}")
    click_position(*AD_TRIGGER_POS)

    print(f"[等待] {AD_WAIT_SECONDS} 秒（广告倒计时）……")
    time.sleep(AD_WAIT_SECONDS)

    print(f"[循环] 点击关闭: {CLOSE_POS}")
    click_position(*CLOSE_POS)

    time.sleep(POST_CLICK_DELAY)
    return True


def main():
    global AD_TRIGGER_POS, CLOSE_POS
    print("=== 简化版自动点击助手 ===")
    print("F1: 记录广告触发位置")
    print("F2: 记录关闭按钮位置")
    print("F3: 开始/暂停自动循环")
    print("ESC: 退出程序")
    print("----------------------------------------")

    running = False
    while True:
        if keyboard.is_pressed('f1'):
            AD_TRIGGER_POS = capture_position("广告触发位置")
            time.sleep(0.4)

        elif keyboard.is_pressed('f2'):
            CLOSE_POS = capture_position("关闭按钮位置")
            time.sleep(0.4)

        elif keyboard.is_pressed('f3'):
            running = not running
            print(f"[状态] {'运行中' if running else '已暂停'}")
            time.sleep(0.4)

            if running:
                while running:
                    if not run_cycle():
                        running = False
                    if keyboard.is_pressed('f3'):
                        running = False
                        print("[状态] 已暂停")
                        time.sleep(0.4)

        elif keyboard.is_pressed('esc'):
            print("[退出]")
            break

        time.sleep(0.1)


if __name__ == "__main__":
    main()