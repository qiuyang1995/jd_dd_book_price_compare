from dataclasses import dataclass
from enum import Enum


class JDQueryStatus(str, Enum):
    SUCCESS = "success"
    LOGIN_REQUIRED = "login_required"
    ACCESS_RESTRICTED = "access_restricted"
    NO_SELF_OPERATED = "no_self_operated"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass(frozen=True)
class JDPriceResult:
    status: JDQueryStatus
    price: str = ""
    message: str = ""

    @property
    def is_success(self) -> bool:
        return self.status == JDQueryStatus.SUCCESS and bool(self.price)

    @property
    def display_value(self) -> str:
        if self.is_success:
            return self.price
        return self.message


@dataclass(frozen=True)
class DDPriceResult:
    price: str = ""
    discount: str = ""


@dataclass(frozen=True)
class WorkbookColumns:
    isbn: int
    jd_price: int
    dd_price: int
    dd_discount: int


@dataclass(frozen=True)
class WorkbookRow:
    row_index: int
    isbn: str


@dataclass(frozen=True)
class RunSummary:
    processed_rows: int
    total_rows: int
    elapsed_seconds: float
