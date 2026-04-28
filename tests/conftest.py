from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass
class FakeExecuteResult:
    items: list[Any]

    def scalars(self) -> "FakeExecuteResult":
        return self

    def all(self) -> list[Any]:
        return self.items

    def scalar_one_or_none(self) -> Any:
        return self.items[0] if self.items else None

    def scalar(self) -> Any:
        return self.items[0] if self.items else None


def result(items: Iterable[Any]) -> FakeExecuteResult:
    return FakeExecuteResult(list(items))
