from time import time

start_time = None

def update(cpu):
    global start_time
    if cpu > 70:
        if not start_time:
            start_time = time()
    else:
        start_time = None

def get_duration():
    if start_time:
        return time() - start_time
    return 0
