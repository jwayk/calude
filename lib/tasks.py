from __future__ import annotations
import typing as t
from functools import wraps

from rich.progress import (
    Progress,
    ProgressColumn,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    MofNCompleteColumn,
    TimeRemainingColumn,
)


class Spinner(Progress):
    @classmethod
    def get_default_columns(cls) -> t.Tuple[ProgressColumn, ...]:
        return (
            TextColumn("{task.description}"),
            SpinnerColumn("line", finished_text="done"),
        )


def track(task: t.Callable, sequence: t.Iterable, description: str) -> None:
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeRemainingColumn(elapsed_when_finished=True),
    ) as progress:
        for payload in progress.track(sequence, description=description):
            task(payload)


def spin(task_description: str):
    def decorator(function: t.Callable) -> t.Callable:
        @wraps(function)
        def wrapper(*args, **kwargs):
            with Spinner() as spinner:
                task_id = spinner.add_task(task_description, total=1)
                result = function(*args, **kwargs)
                spinner.update(task_id, completed=1)
            return result

        return wrapper

    return decorator
