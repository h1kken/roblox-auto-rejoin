import colorama
colorama.init()


class ANSI:
    # color
    RED    = '\033[31m'
    GREEN  = '\033[32m'
    YELLOW = '\033[33m'
    BLUE   = '\033[34m'
    PURPLE = '\033[35m'
    CYAN   = '\033[36m'
    WHITE  = '\033[37m'
    GRAY   = '\033[90m'
    PINK   = '\033[95m'
    # decor
    BOLD   = '\033[1m'
    # other
    CLEAR  = '\033[0m'