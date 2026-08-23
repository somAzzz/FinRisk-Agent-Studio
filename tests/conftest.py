"""Global safety gates for the test suite."""

from pydantic_ai import models

# TestModel and FunctionModel remain usable; accidental live provider requests fail.
models.ALLOW_MODEL_REQUESTS = False
