import itertools
import threading
import time
import sys
class Spinner:
    def __init__(self, text="Thinking..."):
        self.text = text
        self.running = False
    def start(self):
        self.running = True
        def animate():
            for c in itertools.cycle(["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]):
                if not self.running:
                    break
                sys.stdout.write(f"\r{c} {self.text}")
                sys.stdout.flush()
                time.sleep(0.08)
        self.thread = threading.Thread(target=animate)
        self.thread.start()

    def stop(self):
        self.running = False
        self.thread.join()
        sys.stdout.write("\r" + " " * 60 + "\r")

    def update_message(self, message):
        self.message = message

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


class RecordingTimer:
    def __init__(self, seconds):
        self.seconds = seconds
        self.running = False

    def start(self):
        self.running = True
        def animate():
            start = time.time()
            while self.running:
                elapsed = int(time.time() - start)
                if elapsed > self.seconds:
                    break
                sys.stdout.write(
                    f"\r🎤 Recording... {elapsed:02}/{self.seconds:02} sec"
                )
                sys.stdout.flush()
                time.sleep(0.2)
        self.thread = threading.Thread(target=animate)
        self.thread.start()

    def stop(self):
        self.running = False
        self.thread.join()
        sys.stdout.write("\r" + " " * 80 + "\r")
        sys.stdout.flush()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()