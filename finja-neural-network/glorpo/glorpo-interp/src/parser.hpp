/**
 * Parser Header
 * =============
 * Declares types and interfaces for the Glorpo standalone interpreter.
 *
 * Main Responsibilities:
 * - Define interpreter data structures or class interfaces.
 * - Share declarations between C++ translation units.
 *
 * Side Effects:
 * - Included by C++ source files during compilation.
 */
#pragma once
#include "token.hpp"
#include "ast.hpp"
#include <vector>
#include <stdexcept>
#include <string>
#include <initializer_list>

struct ParseError : std::runtime_error {
    int line, col;
    ParseError(const std::string& msg, int l, int c)
        : std::runtime_error("ParseError line " + std::to_string(l) +
                             ", col " + std::to_string(c) + ": " + msg)
        , line(l), col(c) {}
};

class Parser {
public:
    explicit Parser(std::vector<Token> tokens);
    StmtList parse();   // returns top-level statements

private:
    std::vector<Token> tokens_;
    size_t             pos_ = 0;

    // -- Token helpers ---------------------------------------------------------
    Token&       peek(int offset = 0);
    Token&       advance();
    bool         check(TT t) const;
    bool         match(TT t);
    bool         match_any(std::initializer_list<TT> ts);
    Token&       expect(TT t, const std::string& msg);
    bool         at_end() const;
    void         skip_newlines();

    // -- Statement parsers -----------------------------------------------------
    StmtPtr      parse_stmt();
    StmtPtr      parse_simple_stmt();
    StmtPtr      parse_compound_stmt();
    StmtList     parse_block();           // INDENT stmts DEDENT
    StmtList     parse_suite();           // : (simple | block)

    StmtPtr      parse_if();
    StmtPtr      parse_while();
    StmtPtr      parse_for();
    StmtPtr      parse_match();
    StmtPtr      parse_try();
    StmtPtr      parse_with();
    StmtPtr      parse_funcdef(bool is_async = false);
    StmtPtr      parse_classdef();

    StmtPtr      parse_return();
    StmtPtr      parse_raise();
    StmtPtr      parse_assert();
    StmtPtr      parse_import();
    StmtPtr      parse_import_from();
    StmtPtr      parse_global();
    StmtPtr      parse_nonlocal();
    StmtPtr      parse_del();
    StmtPtr      parse_assign_or_expr();

    // -- Expression parsers (precedence climbing) ------------------------------
    ExprPtr      parse_expr();
    ExprPtr      parse_lambda();
    ExprPtr      parse_ternary();
    ExprPtr      parse_or();
    ExprPtr      parse_and();
    ExprPtr      parse_not();
    ExprPtr      parse_compare();
    ExprPtr      parse_bitor();
    ExprPtr      parse_bitxor();
    ExprPtr      parse_bitand();
    ExprPtr      parse_shift();
    ExprPtr      parse_add();
    ExprPtr      parse_mul();
    ExprPtr      parse_unary();
    ExprPtr      parse_power();
    ExprPtr      parse_await();
    ExprPtr      parse_postfix();         // calls, subscripts, attributes
    ExprPtr      parse_primary();

    ExprPtr      parse_list_literal();
    ExprPtr      parse_dict_or_set_literal();
    ExprPtr      parse_tuple_or_paren();

    ExprList     parse_expr_list();       // comma-separated expressions
    std::vector<CallArg> parse_call_args();
    std::vector<FuncParam> parse_func_params();
};
