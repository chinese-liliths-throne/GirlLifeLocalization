from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class StatementSpec:
    canonical: str
    aliases: tuple[str, ...]
    min_args: int
    max_args: int


STATEMENT_SPECS: tuple[StatementSpec, ...] = (
    StatementSpec("act", ("act",), 1, 2),
    StatementSpec("if", ("if",), 1, 1),
    StatementSpec("elseif", ("elseif",), 1, 1),
    StatementSpec("else", ("else",), 0, 0),
    StatementSpec("end", ("end",), 0, 0),
    StatementSpec("for", ("for",), 0, 0),
    StatementSpec("addobj", ("addobj", "add obj"), 1, 3),
    StatementSpec("cla", ("cla",), 0, 0),
    StatementSpec("closeall", ("close all",), 0, 0),
    StatementSpec("close", ("close",), 0, 1),
    StatementSpec("cls", ("cls",), 0, 0),
    StatementSpec("cmdclear", ("cmdclear", "cmdclr"), 0, 0),
    StatementSpec("copyarr", ("copyarr",), 2, 4),
    StatementSpec("delact", ("delact", "del act"), 1, 1),
    StatementSpec("delobj", ("delobj", "del obj"), 1, 1),
    StatementSpec("dynamic", ("dynamic",), 1, 10),
    StatementSpec("exec", ("exec",), 1, 1),
    StatementSpec("exit", ("exit",), 0, 0),
    StatementSpec("freelib", ("freelib", "dellib", "killqst"), 0, 0),
    StatementSpec("gosub", ("gosub", "gs"), 1, 10),
    StatementSpec("goto", ("goto", "gt"), 1, 10),
    StatementSpec("inclib", ("inclib", "addlib", "addqst"), 1, 1),
    StatementSpec("jump", ("jump",), 1, 1),
    StatementSpec("killall", ("killall",), 0, 0),
    StatementSpec("killobj", ("killobj",), 0, 1),
    StatementSpec("killvar", ("killvar",), 0, 2),
    StatementSpec("menu", ("menu",), 1, 3),
    StatementSpec("msg", ("msg",), 1, 1),
    StatementSpec("opengame", ("opengame",), 0, 1),
    StatementSpec("openqst", ("openqst",), 1, 1),
    StatementSpec("play", ("play",), 1, 2),
    StatementSpec("refint", ("refint",), 0, 0),
    StatementSpec("savegame", ("savegame",), 0, 1),
    StatementSpec("settimer", ("settimer",), 1, 1),
    StatementSpec("showacts", ("showacts",), 1, 1),
    StatementSpec("showinput", ("showinput",), 1, 1),
    StatementSpec("showobjs", ("showobjs",), 1, 1),
    StatementSpec("showstat", ("showstat",), 1, 1),
    StatementSpec("unselect", ("unselect", "unsel"), 0, 0),
    StatementSpec("view", ("view",), 0, 1),
    StatementSpec("wait", ("wait",), 1, 1),
    StatementSpec("xgoto", ("xgoto", "xgt"), 1, 10),
    StatementSpec("p", ("p", "*p"), 1, 1),
    StatementSpec("pl", ("pl", "*pl"), 0, 1),
    StatementSpec("nl", ("nl", "*nl"), 0, 1),
    StatementSpec("clear", ("clear", "clr", "*clear", "*clr"), 0, 0),
)


STATEMENT_BY_ALIAS = {
    alias.casefold(): spec
    for spec in STATEMENT_SPECS
    for alias in spec.aliases
}


def find_statement(alias: str) -> StatementSpec | None:
    return STATEMENT_BY_ALIAS.get(alias.casefold())
