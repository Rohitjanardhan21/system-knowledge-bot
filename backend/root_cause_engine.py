import psutil


def get_top_processes():
    processes = []

    for p in psutil.process_iter(['pid', 'name', 'cpu_percent']):
        try:
            processes.append(p.info)
        except:
            continue

    processes = sorted(processes, key=lambda x: x['cpu_percent'], reverse=True)

    return processes[:5]


def detect_root_cause():
    top = get_top_processes()

    if not top:
        return None

    main = top[0]

    return {
        "process": main["name"],
        "pid": main["pid"],
        "cpu_usage": main["cpu_percent"],
    }
