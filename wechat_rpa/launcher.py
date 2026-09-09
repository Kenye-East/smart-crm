"""微信 RPA - 双击启动引导入口

流程（每次启动都会走一次屏幕校准，不再询问）：
  1. 自动打开图形校准窗口
  2. 校准完成后进入检测主循环
  3. 若用户在校准里点了取消：
       已有校准文件 → 沿用旧配置继续
       没有校准文件 → 退出程序

用法：
    python -m wechat_rpa.launcher
"""
from __future__ import annotations

from dotenv import load_dotenv

from .calibrate_gui import has_calibration, run_calibration_gui


def main():
    load_dotenv()
    print("=" * 50)
    print("  微信 RPA 自动回复 启动器")
    print("=" * 50)

    if has_calibration():
        print("\n[1/2] 将打开校准窗口重新框选屏幕区域。")
        print("      想沿用上次的配置？在校准窗里点「取消」即可。\n")
    else:
        print("\n[1/2] 尚未校准屏幕区域，将打开校准窗口。")
        print("      先在引导窗里把微信调到最前、选好目标会话，再点「开始校准」。\n")

    ok = run_calibration_gui()
    if not ok:
        if has_calibration():
            print("\n已取消校准，沿用现有校准文件继续。")
        else:
            print("\n已取消校准，且无可用校准文件，程序退出。")
            print("      下次双击启动会重新进入校准。")
            return

    print("\n[2/2] 进入自动回复检测...")
    print("      （按 Ctrl+C 停止）\n")

    from .main import main as run_detect

    run_detect()


if __name__ == "__main__":
    main()
