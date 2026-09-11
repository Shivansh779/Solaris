from datetime import datetime


def current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def system_log(category, level, message):
    with open("System_Logs.txt", "a") as f:
        f.write(f"[{level}] [{category}] [{current_time()}]: {message}\n")
