"""Per-user IM retrieval preferences and their accepted ranges."""
from dataclasses import asdict, dataclass
import math


@dataclass(frozen=True)
class RetrievalSettings:
    limit: int = 6
    token_budget: int = 4000
    k1: float = 1.5
    b: float = 0.75

    def __post_init__(self):
        if type(self.limit) is not int or not 1 <= self.limit <= 50:
            raise ValueError("最大召回块数必须为 1–50 的整数")
        if type(self.token_budget) is not int or not 128 <= self.token_budget <= 32000:
            raise ValueError("token 预算必须为 128–32000 的整数")
        if not math.isfinite(self.k1) or not 0 < self.k1 <= 5:
            raise ValueError("k1 必须大于 0 且不超过 5")
        if not math.isfinite(self.b) or not 0 <= self.b <= 1:
            raise ValueError("b 必须为 0–1")

    def to_dict(self) -> dict:
        return asdict(self)
