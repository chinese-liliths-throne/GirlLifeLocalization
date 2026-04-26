import json
import re
from base64 import urlsafe_b64decode
from enum import IntEnum

from pydantic import BaseModel, Field, TypeAdapter


POS_PATTERN = re.compile(r"<<POS:(\d+)>>|&lt;&lt;POS:(\d+)&gt;&gt;")
RANGE_END_PATTERN = re.compile(r"<<RANGE_END:(\d+)>>|&lt;&lt;RANGE_END:(\d+)&gt;&gt;")
TEMPLATE_PATTERN = re.compile(r"<<TPL:([A-Za-z0-9_=-]+)>>|&lt;&lt;TPL:([A-Za-z0-9_=-]+)&gt;&gt;")


class StageEnum(IntEnum):
    未翻译 = 0
    已翻译 = 1
    有疑问 = 2
    已检查 = 3
    已审核 = 5
    已锁定 = 9
    已隐藏 = -1


class ParatranzData(BaseModel):
    key: str = Field(default="")
    original: str = Field(default="")
    translation: str = Field(default="")
    stage: StageEnum = Field(default=StageEnum.未翻译)
    context: str = Field(default="")

    def extract_pos_from_context(self) -> int | None:
        """从 ParaTranz context 中提取最后一个 POS 坐标。"""

        if not self.context:
            return None
        matches = [match[0] or match[1] for match in POS_PATTERN.findall(self.context)]
        if matches:
            value = int(matches[-1])
            return max(0, value - 1)
        return None

    def extract_range_end_from_context(self) -> int | None:
        if not self.context:
            return None
        matches = [match[0] or match[1] for match in RANGE_END_PATTERN.findall(self.context)]
        if matches:
            value = int(matches[-1])
            return max(0, value - 1)
        return None

    def extract_template_payload_from_context(self) -> dict | None:
        if not self.context:
            return None
        matches = [match[0] or match[1] for match in TEMPLATE_PATTERN.findall(self.context)]
        if not matches:
            return None
        try:
            raw = urlsafe_b64decode(matches[-1].encode("ascii"))
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None


paratranz_data_list_adapter = TypeAdapter(list[ParatranzData])


__all__ = ["StageEnum", "ParatranzData", "paratranz_data_list_adapter"]
