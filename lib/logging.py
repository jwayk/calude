import logging
from logging import FileHandler, Formatter


class Logger(logging.Logger):
    def __init__(self, name, level=logging.DEBUG):
        super().__init__(name, level)
        file_handler = FileHandler(filename=f"./logs/calendar.log")
        file_handler.setFormatter(
            Formatter(
                "%(asctime)s - %(levelname)s - %(message)s", "[%Y-%m-%d %H:%M:%S]"
            )
        )
        self.addHandler(file_handler)
