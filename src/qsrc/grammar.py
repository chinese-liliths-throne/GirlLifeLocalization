GRAMMAR = r"""
start: document
document: passage+
passage: HEADER stmt* FOOTER

?stmt: BLANK
    | COMMENT
    | LABEL
    | GENERIC
    | FOR_INLINE
    | IF_INLINE
    | ELSEIF_INLINE
    | ELSE_INLINE
    | ACT_INLINE
    | if_block
    | act_block
    | for_block

if_block: IF_BLOCK stmt* elseif_clause* else_clause? END
elseif_clause: ELSEIF_BLOCK stmt*
else_clause: ELSE_BLOCK stmt*

act_block: ACT_BLOCK stmt* END
for_block: FOR_BLOCK stmt* END

HEADER: "HEADER"
FOOTER: "FOOTER"
BLANK: "BLANK"
COMMENT: "COMMENT"
LABEL: "LABEL"
GENERIC: "GENERIC"
FOR_INLINE: "FOR_INLINE"
FOR_BLOCK: "FOR_BLOCK"
IF_INLINE: "IF_INLINE"
IF_BLOCK: "IF_BLOCK"
ELSEIF_INLINE: "ELSEIF_INLINE"
ELSEIF_BLOCK: "ELSEIF_BLOCK"
ELSE_INLINE: "ELSE_INLINE"
ELSE_BLOCK: "ELSE_BLOCK"
ACT_INLINE: "ACT_INLINE"
ACT_BLOCK: "ACT_BLOCK"
END: "END"

%import common.NEWLINE
%import common.WS_INLINE
%ignore WS_INLINE
%ignore NEWLINE
"""
