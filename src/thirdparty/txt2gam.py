#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TXT2GAM 转换工具 (Python API & CLI)

# 元数据声明
- 原版版本: v0.4.0-b3
- 核心逻辑: 从原始的 C 语言版本逆向并转换为 Python
- 脚本说明: Python 3.11 单文件转换与 QSP 语法检查工具
- 原项目库:https://github.com/QSPFoundation/txt2gam
功能描述:
本脚本用于在纯文本格式 (TXT) 和 QSP 游戏二进制格式 (GAM) 之间进行双向转换。
同时提供 QSP 脚本源码的打包前语法检查，适合检查 .qsrc、.txt 合并文本。

最简单的库调用:
    from src.thirdparty.txt2gam import analyze_qsp_file, build_txt_to_gam

    result = analyze_qsp_file("glife.txt")
    if result.ok:
        build_txt_to_gam("glife.txt", "glife.qsp")

项目式打包:
    from src.thirdparty.txt2gam import build_qproj_to_gam

    ok = build_qproj_to_gam(
        input_dir="locations",
        qproj_file="glife.qproj",
        output_txt="glife.txt",
        output_game="glife.qsp",
    )

命令行示例:
    python src/thirdparty/txt2gam.py
    python txt2gam.py --check glife.txt
    python txt2gam.py --check-dir locations --pattern *.qsrc
    python txt2gam.py -m --qproj glife.qproj --idir locations glife.txt
    python txt2gam.py glife.txt glife.qsp
"""

import argparse
import json
import os
import re
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 允许直接用 python src/thirdparty/txt2gam.py 从项目根目录或任意目录运行。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 引入项目日志；脱离项目单独使用时回退到 loguru。
try:
    from src.config.error_reporting import ErrorReporter
    from src.config.logging import logger
except ModuleNotFoundError:
    ErrorReporter = Any
    from loguru import logger
    logger.add(sys.stderr, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan><b>{message}</b></cyan>")
# 项目日志格式可能依赖 extra["project_name"]，这里给脚本日志绑定默认值，避免 Loguru KeyError。
logger = logger.bind(project_name="txt2gam")

# ==========================================
# 常量定义 (Constants)
# ==========================================
QSP_VER = "0.4.0-b3"
QSP_APPNAME = "TXT2GAM"
QSP_GAMEID = "QSPGAME"
QSP_PASSWD = "No"
QSP_MAXACTIONS = 50
QSP_CODREMOV = 5  # 用于简单的加密/解密混淆

QSP_STARTLOC = "#"
QSP_ENDLOC = "--"
QSP_STRSDELIM = "\r\n"
QSP_BASESECTION_HEADER = "! BASE"
QSP_BASESECTION_FOOTER = "! END BASE"
QSP_BASEDESC_PRINT = "*P"
QSP_BASEDESC_PRINTLINE = "*PL"
QSP_BASEACTS_ACT_HEADER = "ACT"
QSP_BASEACTS_ACT_FOOTER = "END"
QSP_BASEACTS_LINE_PREFIX = "\t"

TXT2GAM_UCS2BOM = b'\xFF\xFE'
TXT2GAM_UTF8BOM = b'\xEF\xBB\xBF'

__all__ = [
    "QSPCheckResult",
    "QSPLocAct",
    "QSPLocation",
    "QSPWorld",
    "QSPSyntaxChecker",
    "analyze_qsp_text",
    "analyze_qsp_file",
    "analyze_qsp_directory",
    "check_qsp_text_file",
    "check_qsp_text_directory",
    "convert_txt_to_gam",
    "convert_gam_to_txt",
    "merge_qsrc_to_txt",
    "build_txt_to_gam",
    "build_qproj_to_gam",
    "run_project_test_build",
    "dump_qsp_syntax_metadata",
]

# ==========================================
# QSP 语法元数据 (来自 qsp/ 与 txt2gam/ 源码)
# ==========================================
# 错误码顺序来自 qsp/qsp.h，英文描述来自 qsp/errors.c。
QSP_ERROR_DESCRIPTIONS: Dict[str, str] = {
    "QSP_ERR_DIVBYZERO": "Division by zero!",
    "QSP_ERR_TYPEMISMATCH": "Type mismatch!",
    "QSP_ERR_STACKOVERFLOW": "Stack overflow!",
    "QSP_ERR_TOOMANYITEMS": "Too many items in expression!",
    "QSP_ERR_FILENOTFOUND": "File not found!",
    "QSP_ERR_CANTLOADFILE": "Can't load file!",
    "QSP_ERR_GAMENOTLOADED": "Game not loaded!",
    "QSP_ERR_COLONNOTFOUND": "Sign [:] not found!",
    "QSP_ERR_CANTINCFILE": "Can't add file!",
    "QSP_ERR_CANTADDACTION": "Can't add action!",
    "QSP_ERR_EQNOTFOUND": "Sign [=] not found!",
    "QSP_ERR_LOCNOTFOUND": "Location not found!",
    "QSP_ERR_ENDNOTFOUND": "[end] not found!",
    "QSP_ERR_LABELNOTFOUND": "Label not found!",
    "QSP_ERR_NOTCORRECTNAME": "Incorrect variable's name!",
    "QSP_ERR_QUOTNOTFOUND": "Quote not found!",
    "QSP_ERR_BRACKNOTFOUND": "Bracket not found!",
    "QSP_ERR_BRACKSNOTFOUND": "Brackets not found!",
    "QSP_ERR_SYNTAX": "Syntax error!",
    "QSP_ERR_UNKNOWNACTION": "Unknown action!",
    "QSP_ERR_ARGSCOUNT": "Incorrect arguments' count!",
    "QSP_ERR_CANTADDOBJECT": "Can't add object!",
    "QSP_ERR_CANTADDMENUITEM": "Can't add menu's item!",
    "QSP_ERR_TOOMANYVARS": "Too many variables!",
    "QSP_ERR_INCORRECTREGEXP": "Regular expression's error!",
    "QSP_ERR_CODENOTFOUND": "Code not found!",
    "QSP_ERR_TONOTFOUND": "[to] not found!",
}

QSP_ERROR_HINTS: Dict[str, str] = {
    "QSP_ERR_COLONNOTFOUND": "通常是 ACT / IF / ELSEIF / FOR 这类语句缺少 ':'。",
    "QSP_ERR_EQNOTFOUND": "通常是赋值语句缺少 '='，或 SET/LET 后面不是合法赋值。",
    "QSP_ERR_ENDNOTFOUND": "通常是 IF / ACT / FOR 多行块没有对应 END。",
    "QSP_ERR_LABELNOTFOUND": "JUMP 找不到 ':label' 标签。",
    "QSP_ERR_NOTCORRECTNAME": "变量名或数组名不符合 QSP 变量规则。",
    "QSP_ERR_QUOTNOTFOUND": "字符串引号没有闭合，QSP 用两个连续引号表示转义。",
    "QSP_ERR_BRACKNOTFOUND": "表达式里的 '('、')'、'['、']' 没有配对。",
    "QSP_ERR_BRACKSNOTFOUND": "函数调用或变量索引缺少必需括号。",
    "QSP_ERR_SYNTAX": "通用语法错误，优先检查操作符、逗号、冒号、括号和字符串。",
    "QSP_ERR_ARGSCOUNT": "命令或函数参数数量不符合 qsp/statements.c 注册表。",
    "QSP_ERR_TONOTFOUND": "FOR 语句缺少 TO。",
}

# 语句注册表来自 qsp/statements.c 的 qspAddStatement/qspAddStatName。
# args_type: 0=任意, 1=字符串, 2=数字。
QSP_STATEMENT_SPECS: Dict[str, Dict[str, Any]] = {
    "ADDOBJ": {"min": 1, "max": 3, "types": [1, 1, 2]},
    "CLA": {"min": 0, "max": 0, "types": []},
    "CLOSE ALL": {"min": 0, "max": 0, "types": []},
    "CLOSE": {"min": 0, "max": 1, "types": [1]},
    "CLS": {"min": 0, "max": 0, "types": []},
    "CMDCLEAR": {"min": 0, "max": 0, "types": []},
    "COPYARR": {"min": 2, "max": 4, "types": [1, 1, 2, 2]},
    "DELACT": {"min": 1, "max": 1, "types": [1]},
    "DELOBJ": {"min": 1, "max": 1, "types": [1]},
    "DYNAMIC": {"min": 1, "max": 10, "types": [1, 0, 0, 0, 0, 0, 0, 0, 0, 0]},
    "EXEC": {"min": 1, "max": 1, "types": [1]},
    "EXIT": {"min": 0, "max": 0, "types": []},
    "FREELIB": {"min": 0, "max": 0, "types": []},
    "GOSUB": {"min": 1, "max": 10, "types": [1, 0, 0, 0, 0, 0, 0, 0, 0, 0]},
    "GOTO": {"min": 1, "max": 10, "types": [1, 0, 0, 0, 0, 0, 0, 0, 0, 0]},
    "INCLIB": {"min": 1, "max": 1, "types": [1]},
    "JUMP": {"min": 1, "max": 1, "types": [1]},
    "KILLALL": {"min": 0, "max": 0, "types": []},
    "KILLOBJ": {"min": 0, "max": 1, "types": [2]},
    "KILLVAR": {"min": 0, "max": 2, "types": [1, 2]},
    "MENU": {"min": 1, "max": 3, "types": [1, 2, 2]},
    "*CLEAR": {"min": 0, "max": 0, "types": []},
    "*NL": {"min": 0, "max": 1, "types": [1]},
    "*PL": {"min": 0, "max": 1, "types": [1]},
    "*P": {"min": 1, "max": 1, "types": [1]},
    "CLEAR": {"min": 0, "max": 0, "types": []},
    "NL": {"min": 0, "max": 1, "types": [1]},
    "PL": {"min": 0, "max": 1, "types": [1]},
    "P": {"min": 1, "max": 1, "types": [1]},
    "MSG": {"min": 1, "max": 1, "types": [1]},
    "OPENGAME": {"min": 0, "max": 1, "types": [1]},
    "OPENQST": {"min": 1, "max": 1, "types": [1]},
    "PLAY": {"min": 1, "max": 2, "types": [1, 2]},
    "REFINT": {"min": 0, "max": 0, "types": []},
    "SAVEGAME": {"min": 0, "max": 1, "types": [1]},
    "SETTIMER": {"min": 1, "max": 1, "types": [2]},
    "SHOWACTS": {"min": 1, "max": 1, "types": [2]},
    "SHOWINPUT": {"min": 1, "max": 1, "types": [2]},
    "SHOWOBJS": {"min": 1, "max": 1, "types": [2]},
    "SHOWSTAT": {"min": 1, "max": 1, "types": [2]},
    "UNSELECT": {"min": 0, "max": 0, "types": []},
    "VIEW": {"min": 0, "max": 1, "types": [1]},
    "WAIT": {"min": 1, "max": 1, "types": [2]},
    "XGOTO": {"min": 1, "max": 10, "types": [1, 0, 0, 0, 0, 0, 0, 0, 0, 0]},
}

QSP_STAT_ALIASES: Dict[str, str] = {
    "ADD OBJ": "ADDOBJ", "CMDCLR": "CMDCLEAR", "DEL ACT": "DELACT", "DEL OBJ": "DELOBJ",
    "DELLIB": "FREELIB", "KILLQST": "FREELIB", "GS": "GOSUB", "GT": "GOTO",
    "ADDLIB": "INCLIB", "ADDQST": "INCLIB", "*CLR": "*CLEAR", "CLR": "CLEAR",
    "UNSEL": "UNSELECT", "XGT": "XGOTO", "LET": "SET",
}

QSP_BLOCK_STARTERS = {"IF", "ACT", "FOR"}
QSP_BLOCK_MIDDLES = {"ELSE", "ELSEIF"}
QSP_BLOCK_ENDERS = {"END"}
QSP_KNOWN_STATEMENTS = set(QSP_STATEMENT_SPECS) | set(QSP_STAT_ALIASES) | {
    "IF", "ELSE", "ELSEIF", "END", "LOCAL", "SET", "LET", "ACT", "FOR"
}

# CP1251 (西里尔字母) 到 UCS2LE 的硬编码转换表，继承自原版 C 代码 (coding.c)
qspCP1251ToUCS2LETable = [
    0x0402, 0x0403, 0x201A, 0x0453, 0x201E, 0x2026, 0x2020, 0x2021,
    0x20AC, 0x2030, 0x0409, 0x2039, 0x040A, 0x040C, 0x040B, 0x040F,
    0x0452, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2013, 0x2014,
    0x0020, 0x2122, 0x0459, 0x203A, 0x045A, 0x045C, 0x045B, 0x045F,
    0x00A0, 0x040E, 0x045E, 0x0408, 0x00A4, 0x0490, 0x00A6, 0x00A7,
    0x0401, 0x00A9, 0x0404, 0x00AB, 0x00AC, 0x00AD, 0x00AE, 0x0407,
    0x00B0, 0x00B1, 0x0406, 0x0456, 0x0491, 0x00B5, 0x00B6, 0x00B7,
    0x0451, 0x2116, 0x0454, 0x00BB, 0x0458, 0x0405, 0x0455, 0x0457,
    0x0410, 0x0411, 0x0412, 0x0413, 0x0414, 0x0415, 0x0416, 0x0417,
    0x0418, 0x0419, 0x041A, 0x041B, 0x041C, 0x041D, 0x041E, 0x041F,
    0x0420, 0x0421, 0x0422, 0x0423, 0x0424, 0x0425, 0x0426, 0x0427,
    0x0428, 0x0429, 0x042A, 0x042B, 0x042C, 0x042D, 0x042E, 0x042F,
    0x0430, 0x0431, 0x0432, 0x0433, 0x0434, 0x0435, 0x0436, 0x0437,
    0x0438, 0x0439, 0x043A, 0x043B, 0x043C, 0x043D, 0x043E, 0x043F,
    0x0440, 0x0441, 0x0442, 0x0443, 0x0444, 0x0445, 0x0446, 0x0447,
    0x0448, 0x0449, 0x044A, 0x044B, 0x044C, 0x044D, 0x044E, 0x044F
]

def qspDirectConvertUC(ch: int) -> int:
    """直接转换: CP1251 -> UCS2LE"""
    if ch >= 0x80 and ch - 0x80 < len(qspCP1251ToUCS2LETable):
        return qspCP1251ToUCS2LETable[ch - 0x80]
    return ch

def qspReverseConvertUC(ch: int) -> int:
    """逆向转换: UCS2LE -> CP1251"""
    if ch < 0x80:
        return ch
    try:
        idx = qspCP1251ToUCS2LETable.index(ch)
        return idx + 0x80
    except ValueError:
        return 0x20

def encode_qsp_string(s: str, is_ucs2: bool, is_code: bool) -> bytes:
    """
    将 Python 字符串编码为 QSP 二进制格式
    is_code: 是否需要执行简单的减法混淆 (QSP_CODREMOV)
    """
    if s is None:
        s = ""
    if is_ucs2:
        encoded = bytearray()
        for char in s:
            uCh = ord(char)
            if is_code:
                if uCh == QSP_CODREMOV:
                    uCh = (-QSP_CODREMOV) & 0xFFFF
                else:
                    uCh = (uCh - QSP_CODREMOV) & 0xFFFF
            encoded.extend(struct.pack('<H', uCh))
        return bytes(encoded)
    else:
        encoded = bytearray()
        for char in s:
            ch = qspReverseConvertUC(ord(char))
            if is_code:
                if ch == QSP_CODREMOV:
                    ch = (-QSP_CODREMOV) & 0xFF
                else:
                    ch = (ch - QSP_CODREMOV) & 0xFF
            encoded.append(ch)
        return bytes(encoded)

def decode_qsp_string(b: bytes, is_ucs2: bool, is_coded: bool) -> str:
    """
    将 QSP 二进制数据解码为 Python 字符串
    is_coded: 是否需要执行简单的加法去混淆 (QSP_CODREMOV)
    """
    if is_ucs2:
        decoded = []
        for i in range(0, len(b), 2):
            if i + 1 >= len(b):
                break
            uCh = struct.unpack('<H', b[i:i + 2])[0]
            if is_coded:
                if uCh == ((-QSP_CODREMOV) & 0xFFFF):
                    uCh = QSP_CODREMOV
                else:
                    uCh = (uCh + QSP_CODREMOV) & 0xFFFF
            decoded.append(chr(uCh))
        return "".join(decoded)
    else:
        decoded = []
        for ch in b:
            if is_coded:
                if ch == ((-QSP_CODREMOV) & 0xFF):
                    ch = QSP_CODREMOV
                else:
                    ch = (ch + QSP_CODREMOV) & 0xFF
            decoded.append(chr(qspDirectConvertUC(ch)))
        return "".join(decoded)

# ==========================================
# 数据模型定义 (Data Models)
# ==========================================
@dataclass
class QSPLocAct:
    """描述一个地点内的动作 (Action)"""
    image: str = ""
    desc: str = ""
    code: str = ""

@dataclass
class QSPCheckResult:
    """库调用时返回的语法检查结果。"""
    ok: bool
    error_count: int = 0
    file_count: int = 0
    files: List[str] = field(default_factory=list)


@dataclass
class QSPLocation:
    """描述游戏中的一个地点 (Location)"""
    name: str = ""
    desc: str = ""
    on_visit: str = ""
    actions: List[QSPLocAct] = field(default_factory=list)

class QSPWorld:
    """代表整个 QSP 游戏世界，包含多个地点"""
    def __init__(self):
        self.locations: List[QSPLocation] = []

    def load_from_text(self, text: str, loc_start: str, loc_end: str):
        """从纯文本格式解析游戏地点 (复杂的状态机逻辑)"""
        lines = text.splitlines()
        current_loc = None
        in_loc, in_base, in_action = False, False, False
        current_action = None
        loc_code_lines = []

        i = 0
        while i < len(lines):
            line = lines[i]
            if not in_loc:
                if line.startswith(loc_start):
                    name = line[len(loc_start):].strip()
                    current_loc = QSPLocation(name=name)
                    self.locations.append(current_loc)
                    in_loc = True
                    loc_code_lines = []
            else:
                if line.startswith(loc_end):
                    if current_loc:
                        if in_action and current_action:
                            current_action.code = "\r\n".join(loc_code_lines)
                        elif not in_base:
                            current_loc.on_visit = "\r\n".join(loc_code_lines)
                    in_loc, in_base, in_action = False, False, False
                    current_loc = None
                elif in_base:
                    if in_action:
                        if line.startswith(QSP_BASEACTS_ACT_FOOTER):
                            if current_action:
                                current_action.code = "\r\n".join(loc_code_lines)
                            in_action = False
                            loc_code_lines = []
                        else:
                            if line.startswith(QSP_BASEACTS_LINE_PREFIX):
                                loc_code_lines.append(line[len(QSP_BASEACTS_LINE_PREFIX):])
                            else:
                                loc_code_lines.append(line)
                    elif line.startswith(QSP_BASESECTION_FOOTER):
                        in_base = False
                        loc_code_lines = []
                    elif line.startswith(QSP_BASEACTS_ACT_HEADER):
                        # 解析动作头部: ACT 'Desc', 'Image':
                        parts = line[len(QSP_BASEACTS_ACT_HEADER):].strip().split(":", 1)[0]
                        desc, image = "", ""
                        if "'" in parts:
                            splits = parts.split("'")
                            if len(splits) >= 3: desc = splits[1]
                            if len(splits) >= 5: image = splits[3]
                        current_action = QSPLocAct(desc=desc, image=image)
                        current_loc.actions.append(current_action)
                        in_action = True
                        loc_code_lines = []
                    elif line.startswith(QSP_BASEDESC_PRINTLINE) or line.startswith(QSP_BASEDESC_PRINT):
                        # 解析基础描述
                        prefix_len = len(QSP_BASEDESC_PRINTLINE) if line.startswith(QSP_BASEDESC_PRINTLINE) else len(QSP_BASEDESC_PRINT)
                        desc_part = line[prefix_len:].strip()
                        if desc_part.startswith("'") and desc_part.endswith("'"):
                            desc_part = desc_part[1:-1].replace("''", "'")
                        if current_loc.desc:
                            current_loc.desc += "\r\n" + desc_part
                        else:
                            current_loc.desc = desc_part
                elif line.startswith(QSP_BASESECTION_HEADER):
                    in_base = True
                    in_action = False
                    loc_code_lines = []
                else:
                    loc_code_lines.append(line)
            i += 1

    def save_to_text(self, loc_start: str, loc_end: str) -> str:
        """将世界数据序列化为纯文本格式"""
        out = []
        for loc in self.locations:
            out.append(f"{loc_start} {loc.name}\r\n")

            has_base_desc = bool(loc.desc)
            base_acts_count = len([a for a in loc.actions if a.desc])

            if has_base_desc or base_acts_count > 0:
                out.append(f"{QSP_BASESECTION_HEADER}\r\n")
                if has_base_desc:
                    desc_escaped = loc.desc.replace("'", "''")
                    out.append(f"{QSP_BASEDESC_PRINT} '{desc_escaped}'\r\n")

                for act in loc.actions:
                    if not act.desc: continue
                    desc_escaped = act.desc.replace("'", "''")
                    header = f"{QSP_BASEACTS_ACT_HEADER} '{desc_escaped}'"
                    if act.image:
                        img_escaped = act.image.replace("'", "''")
                        header += f", '{img_escaped}'"
                    header += ":\r\n"
                    out.append(header)

                    if act.code:
                        for line in act.code.splitlines():
                            out.append(f"{QSP_BASEACTS_LINE_PREFIX}{line}\r\n")

                    out.append(f"{QSP_BASEACTS_ACT_FOOTER}\r\n")

                out.append(f"{QSP_BASESECTION_FOOTER}\r\n")

            if loc.on_visit:
                out.append(f"{loc.on_visit}\r\n")

            out.append(f"{loc_end} {loc.name} ---------------------------------\r\n\r\n")

        return "".join(out)

    def load_from_game(self, data: bytes, password: str) -> bool:
        """从二进制 GAM 文件中反序列化加载数据"""
        is_ucs2 = data[1] == 0
        delim = encode_qsp_string(QSP_STRSDELIM, is_ucs2, False)
        parts = data.split(delim)

        if len(parts) < 2:
            logger.error("数据片段过少，不是有效的 QSP 游戏文件。")
            return False

        header = decode_qsp_string(parts[0], is_ucs2, False)
        is_old_format = header != QSP_GAMEID

        if is_old_format:
            pass_str = decode_qsp_string(parts[1], is_ucs2, True)
            locs_count_str = decode_qsp_string(parts[0], is_ucs2, False)
            ind = 30
        else:
            pass_str = decode_qsp_string(parts[2], is_ucs2, True)
            locs_count_str = decode_qsp_string(parts[3], is_ucs2, True)
            ind = 4

        if pass_str != password:
            logger.error(f"密码无效! 提供密码: '{password}'")
            return False

        try:
            locs_count = int(locs_count_str)
        except ValueError:
            logger.error("无法解析地点数量，文件可能已损坏。")
            return False

        for _ in range(locs_count):
            if ind >= len(parts): break
            loc = QSPLocation()
            loc.name = decode_qsp_string(parts[ind], is_ucs2, True); ind += 1
            loc.desc = decode_qsp_string(parts[ind], is_ucs2, True); ind += 1
            loc.on_visit = decode_qsp_string(parts[ind], is_ucs2, True); ind += 1

            if is_old_format:
                acts_count = 20
            else:
                acts_count = int(decode_qsp_string(parts[ind], is_ucs2, True) or "0"); ind += 1

            for _ in range(acts_count):
                act = QSPLocAct()
                if not is_old_format:
                    act.image = decode_qsp_string(parts[ind], is_ucs2, True); ind += 1
                act.desc = decode_qsp_string(parts[ind], is_ucs2, True); ind += 1
                act.code = decode_qsp_string(parts[ind], is_ucs2, True); ind += 1
                if act.desc:
                    loc.actions.append(act)
            self.locations.append(loc)
        return True

    def save_to_game(self, is_old_format: bool, is_ucs2: bool, password: str) -> bytes:
        """序列化为 QSP 二进制 GAM 格式"""
        import datetime
        ver_info = datetime.datetime.now().strftime(f"%Y-%m-%d ({QSP_APPNAME} {QSP_VER})")

        out = bytearray()
        delim = encode_qsp_string(QSP_STRSDELIM, is_ucs2, False)

        def write_val(val: str, is_code: bool):
            out.extend(encode_qsp_string(val, is_ucs2, is_code))
            out.extend(delim)

        if is_old_format:
            write_val(str(len(self.locations)), False)
            write_val(password, True)
            write_val(ver_info, False)
            for _ in range(27): write_val("0", False)
        else:
            write_val(QSP_GAMEID, False)
            write_val(ver_info, False)
            write_val(password, True)
            write_val(str(len(self.locations)), True)

        for loc in self.locations:
            write_val(loc.name, True)
            write_val(loc.desc, True)
            write_val(loc.on_visit, True)

            if is_old_format:
                for j in range(20):
                    if j < len(loc.actions):
                        write_val(loc.actions[j].desc, True)
                        write_val(loc.actions[j].code, True)
                    else:
                        write_val("", True)
                        write_val("", True)
            else:
                acts_count = len([a for a in loc.actions if a.desc])
                write_val(str(acts_count), True)
                for act in loc.actions:
                    if not act.desc: continue
                    write_val(act.image, True)
                    write_val(act.desc, True)
                    write_val(act.code, True)

        return bytes(out)


class QSPSyntaxChecker:
    """
    QSP 静态语法检查器
    用于在编译前扫描并拦截常见的语法、标点和结构错误。
    """

    def __init__(
        self,
        text: str,
        filename: str,
        check_blocks: bool = False,
        check_control_syntax: bool = False,
        error_reporter: Optional["ErrorReporter"] = None,
        error_category: str = "build-syntax",
        source_root: Optional[str] = None,
        verbose: bool = True,
    ):
        self.text = text
        self.lines = text.splitlines()
        self.filename = filename
        self.error_count = 0
        self.check_blocks = check_blocks
        self.check_control_syntax = check_control_syntax
        self.error_reporter = error_reporter
        self.error_category = error_category
        self.source_root = Path(source_root).resolve() if source_root else None
        self.verbose = verbose

    def report_error(self, line_idx: int, col_idx: int, msg: str):
        """格式化输出带有上下文和波浪号的错误信息"""
        self.error_count += 1
        line_num = line_idx + 1

        # 获取上下文 (前后各1行)
        start_line = max(0, line_idx - 1)
        end_line = min(len(self.lines), line_idx + 2)

        rendered_lines = [f"[{self.filename} : 行 {line_num}] 语法拦截: {msg}", "=" * 60]
        if self.verbose:
            logger.error(rendered_lines[0])
            logger.error(rendered_lines[1])
        for i in range(start_line, end_line):
            prefix = f"{i + 1:5d} | "
            # 打印代码行，全部走 loguru，方便统一收集日志。
            rendered_lines.append(f"{prefix}{self.lines[i]}")
            if self.verbose:
                logger.error(rendered_lines[-1])
            # 如果是报错的当前行，打印波浪号指示器
            if i == line_idx:
                indent = len(prefix) + col_idx
                rendered_lines.append(" " * indent + "^" + "~" * (max(5, len(msg) - 5)) + f" {msg}")
                if self.verbose:
                    logger.error(rendered_lines[-1])
        rendered_lines.append("=" * 60)
        if self.verbose:
            logger.error(rendered_lines[-1])
        if self.error_reporter:
            self.error_reporter.report(
                self.error_category,
                self.filename,
                f"语法错误，第 {line_num} 行: {msg}",
                details=rendered_lines[1:],
                source_root=self.source_root,
            )

    def run_checks(self) -> bool:
        """执行全套规则扫描：包含字符串、注释、块结构和常见语句参数检查。"""
        if self.verbose:
            logger.info("启动 QSP 静态语法扫描器：基于 qsp/statements.c 与 txt2gam/locations.c 的常见规则。")

        in_location = False

        # 多行注释允许跨行；双引号字符串允许跨行拼接；
        # 单引号字符串只在“文本输出续行”语境里允许跨行，避免误吞 ACT/赋值类真错误。
        in_block_comment = False
        block_comment_line = -1
        block_comment_pos = -1
        current_quote: Optional[str] = None
        last_quote_line = -1
        last_quote_pos = -1

        for i, line in enumerate(self.lines):
            stripped_line = line.lstrip()
            previous_quote = current_quote
            if current_quote is None and not in_block_comment and self._is_plain_text_line(stripped_line):
                continue
            if not in_block_comment and current_quote is None:
                # 检查 1: 地点标记
                if line.startswith(QSP_STARTLOC):
                    in_location = True
                elif line.startswith(QSP_ENDLOC):
                    # 遇到 `--` 开头的视觉分割线或结束符，不再报错！
                    # 只是静默地将地点状态重置，这是原版编译器的真实行为。
                    in_location = False

                # 检查 2: ACT 冒号
                if self.check_control_syntax and stripped_line.startswith("ACT ") and ":" not in stripped_line:
                    self.report_error(i, len(line) - 1, "ACT 语句尾部似乎缺失了冒号 ':'")

            code_positions, in_block_comment, current_quote, unclosed_quote, block_start = self._scan_code_positions(
                line,
                in_block_comment,
                current_quote,
            )
            if block_start is not None:
                block_comment_line = i
                block_comment_pos = block_start
            elif not in_block_comment:
                block_comment_line = -1
                block_comment_pos = -1

            quote_pos = next((pos for pos, ch in code_positions if ch in ("‘", "’")), -1)
            if quote_pos != -1:
                self.report_error(i, quote_pos, "代码区检测到中文全角单引号！QSP引擎无法识别。")

            colon_pos = next((pos for pos, ch in code_positions if ch == "："), -1)
            if colon_pos != -1:
                self.report_error(i, colon_pos, "代码区检测到中文全角冒号！请替换为英文半角冒号。")

            if unclosed_quote is not None:
                quote_start, quote_char = unclosed_quote
                if quote_char == "'":
                    if self._can_continue_multiline_quote(i, line, quote_start, quote_char):
                        if previous_quote is None:
                            last_quote_line = i
                            last_quote_pos = quote_start
                    else:
                        self.report_error(i, quote_start, f"【致命错误】字符串没有闭合：找不到对应的 {quote_char}。")
                        current_quote = None
                elif previous_quote is None:
                    last_quote_line = i
                    last_quote_pos = quote_start
            elif previous_quote is not None and current_quote is None:
                last_quote_line = -1
                last_quote_pos = -1

        # --- 阶段 3：文件级终极清算 ---
        if in_block_comment:
            self.report_error(block_comment_line, block_comment_pos,
                              "【致命错误】多行注释 '{!' 没有闭合 (找不到对应的 '}')！")
        if current_quote is not None:
            self.report_error(last_quote_line, last_quote_pos, f"【致命错误】字符串没有闭合：找不到对应的 {current_quote}。")

        # 阶段 4：根据 qsp/statements.c 的语句注册表做轻量结构检查。
        # 默认关闭块匹配，GirlLife 这类大项目里有大量裸文本与动态片段，过严会误报。
        self._check_statement_blocks_and_args(check_blocks=self.check_blocks)

        if self.error_count > 0:
            if self.verbose:
                logger.error(f"扫描完成。共发现 {self.error_count} 个真实的语法错误。")
            return False

        if self.verbose:
            logger.success("语法扫描通过：未发现会阻断打包的常见 QSP 语法问题。")
        return True

    def _scan_code_positions(
        self,
        line: str,
        in_block_comment: bool,
        active_quote: Optional[str] = None,
    ) -> Tuple[List[Tuple[int, str]], bool, Optional[str], Optional[Tuple[int, str]], Optional[int]]:
        """提取当前行真正属于代码区的字符位置，避开字符串和注释。"""
        code_positions: List[Tuple[int, str]] = []
        quote = active_quote
        quote_start = -1
        block_start: Optional[int] = None
        idx = 0

        while idx < len(line):
            char = line[idx]

            if in_block_comment:
                if char == "!" and idx + 1 < len(line) and line[idx + 1] == "}":
                    in_block_comment = False
                    idx += 2
                    continue
                idx += 1
                continue

            if quote:
                if char == quote:
                    if idx + 1 < len(line) and line[idx + 1] == quote:
                        idx += 2
                        continue
                    quote = None
                idx += 1
                continue

            if char == "!":
                if idx + 1 < len(line) and line[idx + 1] == "!":
                    break
                if not (idx + 1 < len(line) and line[idx + 1] in ("=", "}")):
                    prefix = line[:idx].strip()
                    if not prefix or prefix[-1] in (":", "&"):
                        break

            if char == "{" and idx + 1 < len(line) and line[idx + 1] == "!":
                in_block_comment = True
                block_start = idx
                idx += 2
                continue

            if char in ("'", '"'):
                quote = char
                quote_start = idx
                idx += 1
                continue

            code_positions.append((idx, char))
            idx += 1

        if quote is not None:
            unresolved_start = 0 if active_quote is not None and quote_start == -1 else quote_start
            return code_positions, in_block_comment, quote, (unresolved_start, quote), block_start
        return code_positions, in_block_comment, None, None, block_start

    def _can_continue_multiline_quote(self, line_idx: int, line: str, quote_start: int, quote_char: str) -> bool:
        """判断未闭合字符串是否像合法的多行文本输出，而不是把下一行代码误吞进去。"""
        if quote_char != "'":
            return True
        if not self._is_multiline_text_quote_context(line[:quote_start]):
            return False
        next_line = self._peek_next_meaningful_line(line_idx)
        if next_line is None:
            return False
        return self._looks_like_text_continuation(next_line)

    def _is_multiline_text_quote_context(self, prefix: str) -> bool:
        """仅允许文本输出语境中的单引号字符串跨行。"""
        prefix = prefix.rstrip()
        if not prefix:
            return True
        if prefix.endswith((":", "&", "+", ",", "(")):
            return True
        return False

    def _peek_next_meaningful_line(self, line_idx: int) -> Optional[str]:
        """取下一条有内容的源码行，用来判断多行字符串是否真在续写文本。"""
        for next_idx in range(line_idx + 1, len(self.lines)):
            candidate = self.lines[next_idx]
            if candidate.strip():
                return candidate
        return None

    def _looks_like_text_continuation(self, line: str) -> bool:
        """判断下一行更像文本续行，而不是新的 QSP 语句。"""
        stripped = line.lstrip()
        if not stripped:
            return False
        if self._is_plain_text_line(stripped):
            return True
        if stripped.startswith(("'", '"', "<", "<<")):
            return True
        upper = stripped.upper()
        for name in sorted(QSP_KNOWN_STATEMENTS, key=len, reverse=True):
            if upper == name or upper.startswith(name + " "):
                return False
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*(\[.*\])?\s*(=|\+=|-=)", stripped):
            return False
        if stripped.startswith(("$", ":", "!", QSP_STARTLOC, QSP_ENDLOC)):
            return False
        return True

    def _is_plain_text_line(self, stripped_line: str) -> bool:
        """识别 QSP 中常见的裸文本/HTML 输出行，这类行不按命令语法解析。"""
        if not stripped_line:
            return False
        if stripped_line in ("'", '"'):
            return True
        upper = stripped_line.upper()
        for name in sorted(QSP_KNOWN_STATEMENTS, key=len, reverse=True):
            if upper == name or upper.startswith(name + " "):
                return False
        if stripped_line.startswith(("'", '"', "$", ":", "!", QSP_STARTLOC, QSP_ENDLOC)):
            return False
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*(\[.*\])?\s*(=|\+=|-=)", stripped_line):
            return False
        if stripped_line.startswith("<<"):
            return True
        if stripped_line.startswith("<") and not stripped_line.upper().startswith(("<=", "<>")):
            return True
        if "=" not in stripped_line and ":" not in stripped_line:
            return True
        return False

    def _strip_inline_comment(self, line: str) -> str:
        """去掉 QSP 行内注释；会避开字符串内的 !。"""
        quote: Optional[str] = None
        idx = 0
        while idx < len(line):
            char = line[idx]
            if quote:
                if char == quote:
                    if idx + 1 < len(line) and line[idx + 1] == quote:
                        idx += 2
                        continue
                    quote = None
                idx += 1
                continue
            if char in ("'", '"'):
                quote = char
                idx += 1
                continue
            if char == "!":
                if idx + 1 < len(line) and line[idx + 1] in ("=", "}"):
                    idx += 1
                    continue
                prefix = line[:idx].strip()
                if not prefix or prefix[-1] in (":", "&"):
                    return line[:idx]
            idx += 1
        return line

    def _split_statements(self, line: str) -> List[Tuple[str, int]]:
        """按 & 拆分单行多语句，避开字符串、括号和 HTML 实体/文本。"""
        result: List[Tuple[str, int]] = []
        quote: Optional[str] = None
        round_depth = 0
        square_depth = 0
        curly_depth = 0
        start = 0
        idx = 0
        while idx < len(line):
            char = line[idx]
            if quote:
                if char == quote:
                    if idx + 1 < len(line) and line[idx + 1] == quote:
                        idx += 2
                        continue
                    quote = None
                idx += 1
                continue
            if char in ("'", '"'):
                quote = char
            elif char == "(":
                round_depth += 1
            elif char == ")" and round_depth:
                round_depth -= 1
            elif char == "[":
                square_depth += 1
            elif char == "]" and square_depth:
                square_depth -= 1
            elif char == "{":
                curly_depth += 1
            elif char == "}" and curly_depth:
                curly_depth -= 1
            elif char == "&" and not round_depth and not square_depth and not curly_depth:
                prev_ch = line[idx - 1] if idx > 0 else ""
                next_ch = line[idx + 1] if idx + 1 < len(line) else ""
                if prev_ch.strip() and next_ch.strip():
                    idx += 1
                    continue
                part = line[start:idx].strip()
                if part:
                    result.append((part, start + len(line[start:idx]) - len(line[start:idx].lstrip())))
                start = idx + 1
            idx += 1
        part = line[start:].strip()
        if part:
            result.append((part, start + len(line[start:]) - len(line[start:].lstrip())))
        return result

    def _split_args(self, args: str) -> List[str]:
        """按逗号拆参数，避开字符串和函数/数组括号。"""
        if not args.strip():
            return []
        result: List[str] = []
        quote: Optional[str] = None
        round_depth = 0
        square_depth = 0
        curly_depth = 0
        start = 0
        idx = 0
        while idx < len(args):
            char = args[idx]
            if quote:
                if char == quote:
                    if idx + 1 < len(args) and args[idx + 1] == quote:
                        idx += 2
                        continue
                    quote = None
                idx += 1
                continue
            if char in ("'", '"'):
                quote = char
            elif char == "(":
                round_depth += 1
            elif char == ")" and round_depth:
                round_depth -= 1
            elif char == "[":
                square_depth += 1
            elif char == "]" and square_depth:
                square_depth -= 1
            elif char == "{":
                curly_depth += 1
            elif char == "}" and curly_depth:
                curly_depth -= 1
            elif char == "," and not round_depth and not square_depth and not curly_depth:
                result.append(args[start:idx].strip())
                start = idx + 1
            idx += 1
        result.append(args[start:].strip())
        return result

    def _iter_logical_lines(self) -> List[Tuple[int, str]]:
        """把行尾 _ 续行合并成逻辑行，返回原始起始行号和合并后的文本。"""
        logical_lines: List[Tuple[int, str]] = []
        buf = ""
        start_idx = 0
        for idx, raw_line in enumerate(self.lines):
            line = raw_line.rstrip()
            if not buf:
                start_idx = idx
            if line.endswith("_"):
                buf += line[:-1] + " "
                continue
            buf += line
            logical_lines.append((start_idx, buf))
            buf = ""
        if buf:
            logical_lines.append((start_idx, buf))
        return logical_lines

    def _match_statement_name(self, statement: str) -> Tuple[str, str]:
        """识别语句名，优先匹配带空格或星号的长命令。"""
        upper = statement.upper().strip()
        for name in sorted(QSP_KNOWN_STATEMENTS, key=len, reverse=True):
            if upper == name or upper.startswith(name + " "):
                canonical = QSP_STAT_ALIASES.get(name, name)
                return canonical, statement[len(name):].strip()
        return "", statement

    def _check_statement_blocks_and_args(self, check_blocks: bool = False):
        """检查 IF/ACT/FOR/END 配对、冒号和命令参数数量。"""
        block_stack: List[Tuple[str, int, int]] = []
        labels = set()
        jumps: List[Tuple[str, int, int]] = []

        for line_idx, raw_line in self._iter_logical_lines():
            if raw_line.startswith(QSP_STARTLOC) or raw_line.startswith(QSP_ENDLOC):
                continue
            if self._is_plain_text_line(raw_line.lstrip()):
                continue
            line = self._strip_inline_comment(raw_line)
            for statement, col in self._split_statements(line):
                if not statement:
                    continue
                if statement.startswith(":"):
                    labels.add(statement[1:].strip().upper())
                    continue

                name, arg_text = self._match_statement_name(statement)
                if not name:
                    # QSP 允许裸文本输出、动态表达式和项目自定义写法；未知命令只跳过，不作为致命错误。
                    continue

                if name in QSP_BLOCK_STARTERS:
                    if self.check_control_syntax and ":" not in statement:
                        self.report_error(line_idx, col + len(statement) - 1, f"{name} 多行/单行语句缺少冒号 ':'")
                    # qsp/statements.c 同时支持单行块和多行块：
                    # 冒号后还有代码时视为单行，不要求 END；冒号在末尾时才入栈等待 END。
                    colon_pos = statement.find(":")
                    trailing_code = statement[colon_pos + 1:].strip() if colon_pos >= 0 else ""
                    if check_blocks and not trailing_code:
                        block_stack.append((name, line_idx, col))
                    if self.check_control_syntax and name == "FOR" and not re.search(r"\bTO\b", statement, flags=re.IGNORECASE):
                        self.report_error(line_idx, col, "FOR 语句缺少 TO，对应原版 QSP_ERR_TONOTFOUND。")
                    continue

                if name in QSP_BLOCK_MIDDLES:
                    if check_blocks and (not block_stack or block_stack[-1][0] != "IF"):
                        self.report_error(line_idx, col, f"{name} 没有匹配的 IF。")
                    if self.check_control_syntax and name == "ELSEIF" and ":" not in statement:
                        self.report_error(line_idx, col + len(statement) - 1, f"{name} 缺少冒号 ':'")
                    continue

                if name in QSP_BLOCK_ENDERS:
                    if not check_blocks:
                        continue
                    if not block_stack:
                        self.report_error(line_idx, col, "END 没有匹配的 IF / ACT / FOR。")
                    else:
                        block_stack.pop()
                    continue

                spec = QSP_STATEMENT_SPECS.get(name)
                if spec:
                    args = self._split_args(arg_text)
                    min_args, max_args = spec["min"], spec["max"]
                    if len(args) < min_args or len(args) > max_args:
                        self.report_error(
                            line_idx,
                            col,
                            f"{name} 参数数量不对：当前 {len(args)} 个，要求 {min_args} 到 {max_args} 个。"
                        )
                    if name == "JUMP" and args:
                        jumps.append((args[0].strip("'\"").upper(), line_idx, col))

        if check_blocks:
            for block_name, line_idx, col in block_stack:
                self.report_error(line_idx, col, f"{block_name} 没有匹配的 END，对应原版 QSP_ERR_ENDNOTFOUND。")

        for label, line_idx, col in jumps:
            if label and label not in labels:
                self.report_error(line_idx, col, f"JUMP 目标标签不存在: {label}")


# ==========================================
# 集中式语法检查 / 源码审计工具
# ==========================================
def read_qsp_text_file(file_path: str, is_unicode: bool = True) -> str:
    """读取 QSP/TXT/QSRC 文本，兼容 UTF-8 BOM、UTF-16LE BOM 和 ANSI(cp1251)。"""
    path = Path(file_path)
    raw_data = path.read_bytes()
    if raw_data.startswith(TXT2GAM_UTF8BOM):
        return raw_data[3:].decode("utf-8")
    if raw_data.startswith(TXT2GAM_UCS2BOM):
        return raw_data[2:].decode("utf-16-le")
    encoding = "utf-8" if is_unicode else "cp1251"
    return raw_data.decode(encoding, errors="replace")


def check_qsp_text_file(file_path: str, is_unicode: bool = True) -> bool:
    """打包前语法检查入口：返回 True 才允许继续生成 qsp/gam。"""
    return analyze_qsp_file(file_path, is_unicode=is_unicode).ok


def check_qsp_text_directory(input_dir: str, pattern: str = "*.qsrc", is_unicode: bool = True) -> bool:
    """批量检查目录内的 QSP 源文件，常用于 qproj/qsrc 打包前。"""
    return analyze_qsp_directory(input_dir, pattern=pattern, is_unicode=is_unicode).ok


def analyze_qsp_text(
    text: str,
    filename: str = "<memory>",
    check_blocks: bool = False,
    check_control_syntax: bool = False,
    error_reporter: Optional["ErrorReporter"] = None,
    error_category: str = "build-syntax",
    source_root: Optional[str] = None,
    verbose: bool = True,
) -> QSPCheckResult:
    """
    库调用入口：检查一段 QSP 文本。

    返回 QSPCheckResult，调用方可以根据 ok/error_count 决定是否继续打包。
    """
    checker = QSPSyntaxChecker(
        text,
        filename,
        check_blocks=check_blocks,
        check_control_syntax=check_control_syntax,
        error_reporter=error_reporter,
        error_category=error_category,
        source_root=source_root,
        verbose=verbose,
    )
    ok = checker.run_checks()
    return QSPCheckResult(ok=ok, error_count=checker.error_count, file_count=1, files=[filename])


def analyze_qsp_file(
    file_path: str,
    is_unicode: bool = True,
    check_blocks: bool = False,
    check_control_syntax: bool = False,
    error_reporter: Optional["ErrorReporter"] = None,
    error_category: str = "build-syntax",
    source_root: Optional[str] = None,
    verbose: bool = True,
) -> QSPCheckResult:
    """库调用入口：检查单个 QSP/TXT/QSRC 文件。"""
    if verbose:
        logger.info(f"开始打包前语法检查: {file_path}")
    text_data = read_qsp_text_file(file_path, is_unicode=is_unicode)
    result = analyze_qsp_text(
        text_data,
        filename=file_path,
        check_blocks=check_blocks,
        check_control_syntax=check_control_syntax,
        error_reporter=error_reporter,
        error_category=error_category,
        source_root=source_root,
        verbose=verbose,
    )
    if result.ok and verbose:
        logger.success(f"打包前语法检查通过: {file_path}")
    elif not result.ok and verbose:
        logger.error(f"打包前语法检查失败: {file_path}")
    return result


def analyze_qsp_directory(
    input_dir: str,
    pattern: str = "*.qsrc",
    is_unicode: bool = True,
    check_blocks: bool = False,
    check_control_syntax: bool = False,
    error_reporter: Optional["ErrorReporter"] = None,
    error_category: str = "build-syntax",
    verbose: bool = True,
) -> QSPCheckResult:
    """库调用入口：批量检查目录内的 QSP 源文件。"""
    root = Path(input_dir)
    files = sorted(root.rglob(pattern))
    if not files:
        logger.warning(f"目录中没有找到待检查文件: {root} / {pattern}")
        return QSPCheckResult(ok=True, file_count=0)

    total_errors = 0
    if verbose:
        logger.info(f"开始批量语法检查，共 {len(files)} 个文件。")
    for file_path in files:
        text_data = read_qsp_text_file(str(file_path), is_unicode=is_unicode)
        checker = QSPSyntaxChecker(
            text_data,
            str(file_path),
            check_blocks=check_blocks,
            check_control_syntax=check_control_syntax,
            error_reporter=error_reporter,
            error_category=error_category,
            source_root=str(root),
            verbose=verbose,
        )
        if not checker.run_checks():
            total_errors += checker.error_count

    if total_errors:
        if verbose:
            logger.error(f"批量语法检查失败，共发现 {total_errors} 个问题。")
        return QSPCheckResult(
            ok=False,
            error_count=total_errors,
            file_count=len(files),
            files=[str(item) for item in files],
        )
    if verbose:
        logger.success("批量语法检查通过。")
    return QSPCheckResult(ok=True, error_count=0, file_count=len(files), files=[str(item) for item in files])


def dump_qsp_syntax_metadata(output_file: Optional[str] = None) -> Dict[str, Any]:
    """导出当前脚本内置的 QSP 语法元数据，便于调试打包规则。"""
    payload = {
        "version": QSP_VER,
        "errors": QSP_ERROR_DESCRIPTIONS,
        "error_hints": QSP_ERROR_HINTS,
        "statement_specs": QSP_STATEMENT_SPECS,
        "statement_aliases": QSP_STAT_ALIASES,
        "known_statements": sorted(QSP_KNOWN_STATEMENTS),
    }
    if output_file:
        Path(output_file).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.success(f"QSP 语法元数据已导出: {output_file}")
    return payload


# ==========================================
# 对外暴露的 API 函数 (解耦版)
# ==========================================
def convert_txt_to_gam(input_file: str, output_file: str, is_unicode: bool = True, is_old_format: bool = False,
                       startloc: str = QSP_STARTLOC, endloc: str = QSP_ENDLOC, password: str = QSP_PASSWD,
                       check_syntax: bool = True, error_reporter: Optional["ErrorReporter"] = None,
                       source_root: Optional[str] = None) -> bool:
    """
    API: 将纯文本文件编码转换为 QSP 游戏文件。
    适合在其他 Python 脚本中直接导入调用。
    """
    logger.info(f"开始编码任务: [{input_file}] -> [{output_file}]")
    world = QSPWorld()
    try:
        text_data = read_qsp_text_file(input_file, is_unicode=is_unicode)
    except Exception as e:
        logger.error(f"读取输入文件失败: {e}")
        if error_reporter:
            error_reporter.report(
                "build-merge",
                input_file,
                "读取打包输入文件失败。",
                details=(f"异常: {e}",),
                source_root=source_root,
            )
        return False

    if check_syntax:
        checker = QSPSyntaxChecker(
            text_data,
            input_file,
            error_reporter=error_reporter,
            error_category="build-syntax",
            source_root=source_root,
        )
        if not checker.run_checks():
            logger.warning("检测到语法错误，但不会中止打包，继续尝试生成游戏文件。")
    else:
        logger.warning("已跳过 QSP 严格语法检查，直接执行打包。")

    # 检查通过后，才开始加载和序列化
    world.load_from_text(text_data, startloc, endloc)
    logger.info(f"成功从文本加载了 {len(world.locations)} 个地点。")

    # world.load_from_text(text_data, startloc, endloc)
    # logger.info(f"成功从文本加载了 {len(world.locations)} 个地点。")

    game_data = world.save_to_game(is_old_format, is_unicode, password)

    try:
        with open(output_file, "wb") as f:
            f.write(game_data)
        logger.success(f"游戏文件已成功保存至: {output_file}")
        return True
    except Exception as e:
        logger.error(f"写入输出文件失败: {e}")
        if error_reporter:
            error_reporter.report(
                "build-merge",
                output_file,
                "写入游戏文件失败。",
                details=(f"异常: {e}",),
                source_root=source_root,
            )
        return False

def convert_gam_to_txt(input_file: str, output_file: str, is_unicode: bool = True,
                       startloc: str = QSP_STARTLOC, endloc: str = QSP_ENDLOC, password: str = QSP_PASSWD) -> bool:
    """
    API: 将 QSP 游戏文件解码为纯文本文件。
    适合在其他 Python 脚本中直接导入调用。
    """
    logger.info(f"开始解码任务: [{input_file}] -> [{output_file}]")
    world = QSPWorld()
    try:
        with open(input_file, "rb") as f:
            game_data = f.read()
    except Exception as e:
        logger.error(f"读取输入文件失败: {e}")
        return False

    if not world.load_from_game(game_data, password):
        logger.error("反序列化失败，游戏文件加载终止。")
        return False

    logger.info(f"成功从游戏文件中加载了 {len(world.locations)} 个地点。")
    text_data = world.save_to_text(startloc, endloc)

    try:
        with open(output_file, "wb") as f:
            if is_unicode:
                f.write(TXT2GAM_UTF8BOM)
                f.write(text_data.encode('utf-8'))
            else:
                f.write(text_data.encode('cp1251', errors='replace'))
        logger.success(f"纯文本文件已成功保存至: {output_file}")
        return True
    except Exception as e:
        logger.error(f"写入输出文件失败: {e}")
        return False


def build_qproj_to_gam(
    input_dir: str,
    qproj_file: str,
    output_txt: str,
    output_game: str,
    *,
    is_unicode: bool = True,
    is_old_format: bool = False,
    startloc: str = QSP_STARTLOC,
    endloc: str = QSP_ENDLOC,
    password: str = QSP_PASSWD,
    check_syntax: bool = True,
    error_reporter: Optional["ErrorReporter"] = None,
    source_root: Optional[str] = None,
) -> bool:
    """
    库调用入口：先检查并合并 qproj/qsrc，再转换为 qsp/gam。

    适合打包流程直接调用：
        build_qproj_to_gam("locations", "glife.qproj", "glife.txt", "glife.qsp")
    """
    logger.info("开始执行 QSP 项目打包流程：合并 -> 转换。")
    if not merge_qsrc_to_txt(
        input_dir=input_dir,
        qproj_file=qproj_file,
        output_txt=output_txt,
        check_syntax=check_syntax,
        error_reporter=error_reporter,
        source_root=source_root,
    ):
        logger.error("项目合并失败，已停止后续转换。")
        if error_reporter:
            error_reporter.report(
                "build-merge",
                qproj_file,
                "qproj 合并阶段失败，未能生成中间 txt。",
                details=(f"输出 txt: {output_txt}",),
                source_root=source_root,
            )
        return False
    return convert_txt_to_gam(
        input_file=output_txt,
        output_file=output_game,
        is_unicode=is_unicode,
        is_old_format=is_old_format,
        startloc=startloc,
        endloc=endloc,
        password=password,
        check_syntax=check_syntax,
        error_reporter=error_reporter,
        source_root=source_root,
    )


def build_txt_to_gam(
    input_txt: str,
    output_game: str,
    *,
    is_unicode: bool = True,
    is_old_format: bool = False,
    startloc: str = QSP_STARTLOC,
    endloc: str = QSP_ENDLOC,
    password: str = QSP_PASSWD,
    check_syntax: bool = True,
    error_reporter: Optional["ErrorReporter"] = None,
    source_root: Optional[str] = None,
) -> bool:
    """库调用入口：检查并转换单个 txt/qsrc 合并文本为 qsp/gam。"""
    return convert_txt_to_gam(
        input_file=input_txt,
        output_file=output_game,
        is_unicode=is_unicode,
        is_old_format=is_old_format,
        startloc=startloc,
        endloc=endloc,
        password=password,
        check_syntax=check_syntax,
        error_reporter=error_reporter,
        source_root=source_root,
    )


def run_project_test_build() -> bool:
    """
    项目内直接运行入口。

    适合在 GirlLifeLocalization 项目里直接运行本文件：
        python src/thirdparty/txt2gam.py

    路径约定来自 src.config.settings.filepath：
        data/test/locations -> data/test/glife.txt -> data/test/glife.qsp
    """
    from src.config.configuration import settings
    from src.config.logging import logger as raw_project_logger

    filepath = settings.filepath
    # project_logger = raw_project_logger.opt(colors=True)
    dir_source = filepath.root / filepath.data / "test"
    dir_locations = dir_source / "locations"
    qsp_file = dir_source / "glife.qsp"
    txt_file = dir_source / "glife.txt"
    qproj_file = dir_source / "glife.qproj"

    # project_logger.info(f"开始项目默认 QSP 打包: {dir_source}")
    if not merge_qsrc_to_txt(dir_locations, qproj_file, txt_file):
        # project_logger.error("qsrc 合并失败，已停止打包。")
        return False
    if not convert_txt_to_gam(txt_file, qsp_file):
        # project_logger.error("txt 转 qsp 失败。")
        return False
    # project_logger.success(f"项目默认 QSP 打包完成: {qsp_file}")
    return True


# ==========================================
# CLI 入口
# ==========================================
def main():
    """命令行接口解析"""
    parser = argparse.ArgumentParser(description=f"TXT2GAM 转换/语法检查工具, ver. {QSP_VER} (Python 3.11)")
    parser.add_argument("input_file", nargs="?", help="输入文件路径")
    parser.add_argument("output_file", nargs="?", help="输出文件路径")
    parser.add_argument("-a", "--ansi", action="store_true", help="ANSI 模式，默认为 Unicode (UTF-8, UCS-2/UTF-16) 模式")
    parser.add_argument("-o", "--old", action="store_true", help="以旧格式保存游戏，默认为新格式")
    parser.add_argument("-s", "--startloc", default=QSP_STARTLOC, help=f"地点起始标记，默认为 '{QSP_STARTLOC}'")
    parser.add_argument("-e", "--endloc", default=QSP_ENDLOC, help=f"地点结束标记，默认为 '{QSP_ENDLOC}'")
    parser.add_argument("-p", "--password", default=QSP_PASSWD, help=f"游戏密码，默认为 '{QSP_PASSWD}'")
    parser.add_argument("-c", "--encode", action="store_true", help="【编码】纯文本 -> 游戏文件 (默认模式)")
    parser.add_argument("-d", "--decode", action="store_true", help="【解码】游戏文件 -> 纯文本")
    parser.add_argument("--check", action="store_true", help="【检查】只检查单个 QSP/TXT/QSRC 文本语法，不生成游戏文件")
    parser.add_argument("--check-dir", type=str, help="【检查】批量检查目录中的 QSP 源文件")
    parser.add_argument("--pattern", default="*.qsrc", help="批量检查的文件匹配规则，默认 *.qsrc")
    parser.add_argument("--dump-metadata", type=str, help="导出脚本内置的 QSP 语法元数据 JSON")

    # 新增合并相关参数
    parser.add_argument("-m", "--merge", action="store_true", help="【合并】qproj 目录下的 qsrc 文件 -> 纯文本")
    parser.add_argument("--qproj", type=str, help="指定 .qproj 配置文件路径 (合并模式必需)")
    parser.add_argument("--idir", type=str, default=".", help="指定 .qsrc 文件所在目录 (默认为当前目录)")

    args = parser.parse_args()

    is_unicode = not args.ansi
    is_old_format = args.old

    if args.dump_metadata:
        dump_qsp_syntax_metadata(args.dump_metadata)
        return

    if args.check_dir:
        ok = check_qsp_text_directory(args.check_dir, pattern=args.pattern, is_unicode=is_unicode)
        sys.exit(0 if ok else 1)

    if args.check:
        if not args.input_file:
            logger.error("检查模式必须提供 input_file。")
            sys.exit(2)
        ok = check_qsp_text_file(args.input_file, is_unicode=is_unicode)
        sys.exit(0 if ok else 1)

    # 处理合并模式
    if args.merge:
        if not args.qproj:
            logger.error("合并模式下必须使用 --qproj 指定项目文件！")
            sys.exit(1)
        if not args.output_file:
            logger.error("合并模式必须提供 output_file。")
            sys.exit(2)

        ok = merge_qsrc_to_txt(
            input_dir=args.idir,
            qproj_file=args.qproj,
            output_txt=args.output_file
        )
        sys.exit(0 if ok else 1)

    if not args.input_file or not args.output_file:
        parser.error("转换模式必须提供 input_file 和 output_file；只检查请使用 --check 或 --check-dir。")

    # 如果指定了 -d，则进入解码模式；否则默认执行编码模式
    if args.decode:
        ok = convert_gam_to_txt(
            input_file=args.input_file,
            output_file=args.output_file,
            is_unicode=is_unicode,
            startloc=args.startloc,
            endloc=args.endloc,
            password=args.password
        )
    else:
        ok = convert_txt_to_gam(
            input_file=args.input_file,
            output_file=args.output_file,
            is_unicode=is_unicode,
            is_old_format=is_old_format,
            startloc=args.startloc,
            endloc=args.endloc,
            password=args.password
        )
    sys.exit(0 if ok else 1)


def merge_qsrc_to_txt(
    input_dir: str,
    qproj_file: str,
    output_txt: str,
    check_syntax: bool = True,
    error_reporter: Optional["ErrorReporter"] = None,
    source_root: Optional[str] = None,
) -> bool:
    """
    API: 根据 .qproj 文件，将目录下的 .qsrc 文件合并为单个 .txt 文件。
    在合并拼接前，会调用语法扫描器逐个检查模块文件。
    """
    import xml.etree.ElementTree as ET
    from datetime import date
    import os

    logger.info(f"开始执行模块合并与编译前检查: 依赖结构树 [{qproj_file}]")

    try:
        tree = ET.parse(qproj_file)
        root = tree.getroot()
    except Exception as e:
        logger.error(f"解析 .qproj XML 文件失败: {e}")
        if error_reporter:
            error_reporter.report(
                "build-merge",
                qproj_file,
                "解析 .qproj XML 文件失败。",
                details=(f"异常: {e}",),
                source_root=source_root,
            )
        return False

    merged_text_blocks = []
    total_errors = 0
    file_count = 0

    # 遍历 XML 中声明的所有 Location
    for location in root.iter("Location"):
        iname = location.attrib["name"]
        # 兼容旧版 txtmerge.py 把 $ 替换为 _ 的逻辑
        fname = iname.replace("$", "_") + ".qsrc"
        fpath = os.path.join(input_dir, fname)

        if not os.path.exists(fpath):
            logger.warning(f"警告: .qproj 中引用的地点文件 [{fname}] 不存在，已跳过。")
            if error_reporter:
                error_reporter.report(
                    "build-merge",
                    fpath,
                    "qproj 引用的 qsrc 文件不存在，已跳过。",
                    details=(f"qproj: {qproj_file}",),
                    source_root=source_root or input_dir,
                )
            continue

        try:
            with open(fpath, "rt", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            logger.error(f"读取模块文件 {fname} 失败: {e}")
            if error_reporter:
                error_reporter.report(
                    "build-merge",
                    fpath,
                    "读取模块文件失败。",
                    details=(f"异常: {e}",),
                    source_root=source_root or input_dir,
                )
            continue

        # ==========================================
        # 核心拦截：对单个 .qsrc 模块进行语法扫描
        # 错误日志将直接指向具体的模块文件和它的相对行号！
        # ==========================================
        if check_syntax:
            checker = QSPSyntaxChecker(
                text,
                fpath,
                error_reporter=error_reporter,
                error_category="build-syntax",
                source_root=source_root or input_dir,
            )
            if not checker.run_checks():
                # 我们不在这里直接 return，而是让它继续扫描其他文件
                # 这样用户一次编译就能看到所有文件的错误，不用改一次跑一次
                total_errors += checker.error_count

        # 确保拼接时文本不会粘连 (Windows 换行符保险)
        if not text.endswith("\n"):
            text += "\n\n"

        merged_text_blocks.append(text)
        file_count += 1

    # 终极清算
    if total_errors > 0:
        logger.warning(f"检测到 {total_errors} 处语法错误，但不会中止合并，继续生成文本。")

    if check_syntax:
        if total_errors > 0:
            logger.warning("部分 .qsrc 模块存在语法错误，已写入 errors 目录并继续生成合并文本。")
        else:
            logger.success("所有 .qsrc 模块均通过语法检查，开始生成合并文本。")
    else:
        logger.warning("已跳过 .qsrc 严格语法检查，开始生成合并文本。")

    # 追加版本编译日期 (继承原版 txtmerge.py 的强迫症行为)
    today = date.today()
    build_date_str = f"# addbuilddate\r\n$builddate = '{today.strftime('%B %d, %Y')}'\r\n--- addbuilddate ---------------------------------\r\n"
    merged_text_blocks.append(build_date_str)

    try:
        # 原版 txtmerge 使用 utf-16 和 \r\n 编码输出
        with open(output_txt, "w", encoding="utf-16", newline="\r\n") as f:
            f.write("".join(merged_text_blocks))
        logger.success(f"成功将 {file_count} 个模块合并为: {output_txt}")
        return True
    except Exception as e:
        logger.error(f"写入合并文件失败: {e}")
        if error_reporter:
            error_reporter.report(
                "build-merge",
                output_txt,
                "写入合并文本失败。",
                details=(f"异常: {e}",),
                source_root=source_root,
            )
        return False

if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.exit(0 if run_project_test_build() else 1)
    main()
