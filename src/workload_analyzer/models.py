from dataclasses import dataclass
from enum import Enum
from typing import Optional


class EntrySource(str, Enum):
    MANUAL = "manual"
    AUTO_OUTLOOK = "auto_outlook"
    AUTO_MEETING = "auto_meeting"
    MANUAL_OVERRIDE = "manual_override"
    SCREEN_LOCK_RECOVERY = "screen_lock_recovery"
    IDLE_RECOVERY = "idle_recovery"


@dataclass
class Role:
    id: Optional[int]
    name: str


@dataclass
class Category:
    id: Optional[int]
    name: str
    color: str
    role_id: int
    active: bool = True
    outlook_category_name: Optional[str] = None


@dataclass
class TimeEntry:
    id: Optional[int]
    category_id: int
    start_ts: int
    end_ts: Optional[int]
    source: EntrySource
    comment: Optional[str] = None

    def is_active(self) -> bool:
        return self.end_ts is None

    def duration_seconds(self) -> int:
        if self.end_ts is None:
            return 0
        return self.end_ts - self.start_ts


@dataclass
class RejectedSuggestion:
    id: Optional[int]
    outlook_category_name: str
    app_category_id: int
    rejection_count: int
    silenced: bool
    last_rejected_at: str
