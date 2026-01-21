watching = {
    "memory": False,
    "disk": False
}

def enable_watch(component):
    if component in watching:
        watching[component] = True

def is_watching(component):
    return watching.get(component, False)
