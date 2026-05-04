#!/usr/bin/env python3
"""监听 ~/ai/blog/posts/ 目录，.md 文件变化后自动发布。
用法: python3 watch.py       # 前台运行，Ctrl+C 停止
      python3 watch.py &     # 后台运行
"""

import os
import subprocess
import sys
import time

WATCH_DIR = os.path.expanduser("~/ai/blog/posts")
PUBLISH_SCRIPT = os.path.expanduser("~/ai/blog/publish.py")
POLL_INTERVAL = 3  # 秒

def get_state():
    """返回 {文件名: mtime}"""
    state = {}
    if os.path.exists(WATCH_DIR):
        for f in os.listdir(WATCH_DIR):
            if f.endswith(".md"):
                state[f] = os.path.getmtime(os.path.join(WATCH_DIR, f))
    return state

def main():
    print(f"👀 监听 {WATCH_DIR}/")
    print("   编辑任意 .md 文件后自动发布到 hehan.tech")
    print("   Ctrl+C 停止\n")

    last_state = get_state()
    last_publish = 0  # 防抖：至少间隔 5 秒

    while True:
        time.sleep(POLL_INTERVAL)
        current = get_state()
        if current != last_state and time.time() - last_publish > 5:
            changed = [f for f in current if f not in last_state or current[f] != last_state[f]]
            new_files = [f for f in current if f not in last_state]
            if new_files:
                print(f"\n📝 新文件: {', '.join(new_files)}")
            elif changed:
                print(f"\n✏️ 修改: {', '.join(changed)}")
            subprocess.run([sys.executable, PUBLISH_SCRIPT])
            last_publish = time.time()
            last_publish_printed = True
        last_state = current

if __name__ == "__main__":
    main()
