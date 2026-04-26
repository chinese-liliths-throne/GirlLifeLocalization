# Generated from D:/VSC/GirlLifeLocalization/src/parser/python_grammar/qsrcParser.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .qsrcParser import qsrcParser
else:
    from qsrcParser import qsrcParser

# This class defines a complete generic visitor for a parse tree produced by qsrcParser.

class qsrcParserVisitor(ParseTreeVisitor):

    # Visit a parse tree produced by qsrcParser#passage.
    def visitPassage(self, ctx:qsrcParser.PassageContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#block.
    def visitBlock(self, ctx:qsrcParser.BlockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#statementLine.
    def visitStatementLine(self, ctx:qsrcParser.StatementLineContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#emptyLine.
    def visitEmptyLine(self, ctx:qsrcParser.EmptyLineContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#actBlock.
    def visitActBlock(self, ctx:qsrcParser.ActBlockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#actInline.
    def visitActInline(self, ctx:qsrcParser.ActInlineContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#actPicture.
    def visitActPicture(self, ctx:qsrcParser.ActPictureContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#ifInline.
    def visitIfInline(self, ctx:qsrcParser.IfInlineContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#ifBlock.
    def visitIfBlock(self, ctx:qsrcParser.IfBlockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#elseIfBlock.
    def visitElseIfBlock(self, ctx:qsrcParser.ElseIfBlockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#elseBlock.
    def visitElseBlock(self, ctx:qsrcParser.ElseBlockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#command.
    def visitCommand(self, ctx:qsrcParser.CommandContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#commandLine.
    def visitCommandLine(self, ctx:qsrcParser.CommandLineContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#commandAppended.
    def visitCommandAppended(self, ctx:qsrcParser.CommandAppendedContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#addobj.
    def visitAddobj(self, ctx:qsrcParser.AddobjContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#assignment.
    def visitAssignment(self, ctx:qsrcParser.AssignmentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#assignmentNumber.
    def visitAssignmentNumber(self, ctx:qsrcParser.AssignmentNumberContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#assignmentString.
    def visitAssignmentString(self, ctx:qsrcParser.AssignmentStringContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#assignmentoperator.
    def visitAssignmentoperator(self, ctx:qsrcParser.AssignmentoperatorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#comment.
    def visitComment(self, ctx:qsrcParser.CommentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#commentAttached.
    def visitCommentAttached(self, ctx:qsrcParser.CommentAttachedContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#copyarr.
    def visitCopyarr(self, ctx:qsrcParser.CopyarrContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#delact.
    def visitDelact(self, ctx:qsrcParser.DelactContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#dynamic.
    def visitDynamic(self, ctx:qsrcParser.DynamicContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#gosub.
    def visitGosub(self, ctx:qsrcParser.GosubContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#gt.
    def visitGt(self, ctx:qsrcParser.GtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#xgt.
    def visitXgt(self, ctx:qsrcParser.XgtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#jump.
    def visitJump(self, ctx:qsrcParser.JumpContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#jumpmarker.
    def visitJumpmarker(self, ctx:qsrcParser.JumpmarkerContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#killvar.
    def visitKillvar(self, ctx:qsrcParser.KillvarContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#msg.
    def visitMsg(self, ctx:qsrcParser.MsgContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#multilineBlock.
    def visitMultilineBlock(self, ctx:qsrcParser.MultilineBlockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#innerMultilineBlock.
    def visitInnerMultilineBlock(self, ctx:qsrcParser.InnerMultilineBlockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#opengame.
    def visitOpengame(self, ctx:qsrcParser.OpengameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#play.
    def visitPlay(self, ctx:qsrcParser.PlayContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#print.
    def visitPrint(self, ctx:qsrcParser.PrintContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#printMain.
    def visitPrintMain(self, ctx:qsrcParser.PrintMainContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#printNewlineMain.
    def visitPrintNewlineMain(self, ctx:qsrcParser.PrintNewlineMainContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#printNewlinepreMain.
    def visitPrintNewlinepreMain(self, ctx:qsrcParser.PrintNewlinepreMainContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#printEmptyLineMain.
    def visitPrintEmptyLineMain(self, ctx:qsrcParser.PrintEmptyLineMainContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#printSide.
    def visitPrintSide(self, ctx:qsrcParser.PrintSideContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#printNewlineSide.
    def visitPrintNewlineSide(self, ctx:qsrcParser.PrintNewlineSideContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#printNewlinepreSide.
    def visitPrintNewlinepreSide(self, ctx:qsrcParser.PrintNewlinepreSideContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#printEmptyLineSide.
    def visitPrintEmptyLineSide(self, ctx:qsrcParser.PrintEmptyLineSideContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#savegame.
    def visitSavegame(self, ctx:qsrcParser.SavegameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#syscall.
    def visitSyscall(self, ctx:qsrcParser.SyscallContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#syssetting.
    def visitSyssetting(self, ctx:qsrcParser.SyssettingContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#view.
    def visitView(self, ctx:qsrcParser.ViewContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#wait.
    def visitWait(self, ctx:qsrcParser.WaitContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#identifier.
    def visitIdentifier(self, ctx:qsrcParser.IdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#identifierNumber.
    def visitIdentifierNumber(self, ctx:qsrcParser.IdentifierNumberContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#identifierString.
    def visitIdentifierString(self, ctx:qsrcParser.IdentifierStringContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#arrayIndex.
    def visitArrayIndex(self, ctx:qsrcParser.ArrayIndexContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#compareOperator.
    def visitCompareOperator(self, ctx:qsrcParser.CompareOperatorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#notEqual.
    def visitNotEqual(self, ctx:qsrcParser.NotEqualContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#value.
    def visitValue(self, ctx:qsrcParser.ValueContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#numberLiteralWithOptionalSign.
    def visitNumberLiteralWithOptionalSign(self, ctx:qsrcParser.NumberLiteralWithOptionalSignContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#functionWithNumberReturn.
    def visitFunctionWithNumberReturn(self, ctx:qsrcParser.FunctionWithNumberReturnContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#invert.
    def visitInvert(self, ctx:qsrcParser.InvertContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#numberOperator.
    def visitNumberOperator(self, ctx:qsrcParser.NumberOperatorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#functionWithStringReturn.
    def visitFunctionWithStringReturn(self, ctx:qsrcParser.FunctionWithStringReturnContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#functionArguments.
    def visitFunctionArguments(self, ctx:qsrcParser.FunctionArgumentsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#escapedString.
    def visitEscapedString(self, ctx:qsrcParser.EscapedStringContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#stringAtom.
    def visitStringAtom(self, ctx:qsrcParser.StringAtomContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#stringTemplateVar.
    def visitStringTemplateVar(self, ctx:qsrcParser.StringTemplateVarContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#stringTemplateVarSuffix.
    def visitStringTemplateVarSuffix(self, ctx:qsrcParser.StringTemplateVarSuffixContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#doubleQuoteAtom.
    def visitDoubleQuoteAtom(self, ctx:qsrcParser.DoubleQuoteAtomContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#stringTemplateVarDQ.
    def visitStringTemplateVarDQ(self, ctx:qsrcParser.StringTemplateVarDQContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by qsrcParser#stringDQTemplateVarSuffix.
    def visitStringDQTemplateVarSuffix(self, ctx:qsrcParser.StringDQTemplateVarSuffixContext):
        return self.visitChildren(ctx)



del qsrcParser