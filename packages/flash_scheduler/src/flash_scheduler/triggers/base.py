from abc import ABC, abstractmethod
from datetime import datetime


class Trigger(ABC):
    """
    Abstract base class for job triggers.

    Triggers determine when a job should next be executed.
    """

    @abstractmethod
    def next_fire_time(
        self, prev_fire_time: datetime | None, now: datetime
    ) -> datetime | None: ...

    def __eq__(self, other: object) -> bool:
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        return False

    def __hash__(self) -> int:
        return hash((self.__class__.__name__, tuple(sorted(self.__dict__.items()))))

    def __repr__(self) -> str:
        params = ", ".join(f"{k}={v!r}" for k, v in self.__dict__.items())
        return f"{self.__class__.__name__}({params})"
