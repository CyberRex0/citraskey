from typing import TypedDict

class FlaskConfigT(TypedDict):
    session_secret: str
    enable_profiler: bool

class ConfigT(TypedDict):
    flask: FlaskConfigT