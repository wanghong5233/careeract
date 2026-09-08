from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ActorContext:
    user_id: str
    request_id: str
