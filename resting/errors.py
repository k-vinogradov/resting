from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from resting.script import Step, Script
    from resting.tests import Test


class RestingError(Exception):
    message = "unknown error"

    def __str__(self):
        if self.__cause__:
            cause = "\n".join(f"  {line}" for line in str(self.__cause__).splitlines())
            return f"{self.message}:\n{cause}"
        return self.message


class InvalidPath(RestingError):
    def __init__(self, path, item: Optional[str] = None):
        message = f"invalid path {path!r}"
        self.message = f"{message}: unknown item {item}" if item else message


class FailedStepError(RestingError):
    def __init__(self, step: Step, script: Script):
        self.message = "abort on step {label!r} ({number} of {total})".format(
            label=step.label,
            number=script.steps.index(step) + 1,
            total=len(script.steps),
        )


class EmptyEnvironment(InvalidPath):
    message = "empty environment"


class TestError(RestingError):
    def __init__(self, test: Test, step: Step):
        self.message = (
            "test {test!r} ({number} of {total}) from step {step!r} failed".format(
                test=test.name,
                number=step.tests.index(test) + 1,
                total=len(step.tests),
                step=step.label,
            )
        )
