/**
 * Glorpo Parser Implementation
 * ============================
 * Builds an AST from Glorpo lexer tokens.
 *
 * Main Responsibilities:
 * - Parse statements and expressions.
 * - Validate token order and syntax.
 * - Produce AST nodes for the interpreter.
 *
 * Side Effects:
 * - Throws ParseError for invalid syntax.
 */
#include "parser.hpp"
#include <cstdlib>
#include <utility>

namespace {
template <typename T>
std::unique_ptr<T> node(int line) {
    auto n = std::make_unique<T>();
    n->line = line;
    return n;
}
}

Parser::Parser(std::vector<Token> tokens) : tokens_(std::move(tokens)) {}

Token& Parser::peek(int offset) {
    long long idx_signed = static_cast<long long>(pos_) + offset;
    size_t idx = idx_signed < 0 ? 0 : static_cast<size_t>(idx_signed);
    if (idx >= tokens_.size()) return tokens_.back();
    return tokens_[idx];
}

Token& Parser::advance() {
    if (!at_end()) ++pos_;
    return tokens_[pos_ - 1];
}

bool Parser::check(TT t) const {
    if (pos_ >= tokens_.size()) return false;
    return tokens_[pos_].type == t;
}

bool Parser::match(TT t) {
    if (!check(t)) return false;
    advance();
    return true;
}

bool Parser::match_any(std::initializer_list<TT> ts) {
    for (auto t : ts) {
        if (check(t)) {
            advance();
            return true;
        }
    }
    return false;
}

Token& Parser::expect(TT t, const std::string& msg) {
    if (check(t)) return advance();
    throw ParseError(msg, peek().line, peek().col);
}

bool Parser::at_end() const {
    return pos_ >= tokens_.size() || tokens_[pos_].type == TT::END_OF_FILE;
}

void Parser::skip_newlines() {
    while (match(TT::NEWLINE)) {}
}

StmtList Parser::parse() {
    StmtList stmts;
    skip_newlines();
    while (!at_end()) {
        stmts.push_back(parse_stmt());
        skip_newlines();
    }
    return stmts;
}

StmtPtr Parser::parse_stmt() {
    if (match(TT::KW_ASYNC)) {
        if (check(TT::KW_DEF)) return parse_funcdef(true);
        if (check(TT::KW_FOR)) return parse_for();
        if (check(TT::KW_WITH)) return parse_with();
        throw ParseError("expected gloo/glorpach/glorpwith after glorpfast", peek().line, peek().col);
    }
    if (check(TT::KW_IF)) return parse_if();
    if (check(TT::KW_WHILE)) return parse_while();
    if (check(TT::KW_FOR)) return parse_for();
    if (check(TT::KW_MATCH)) return parse_match();
    if (check(TT::KW_DEF)) return parse_funcdef(false);
    if (check(TT::KW_CLASS)) return parse_classdef();
    if (check(TT::KW_TRY)) return parse_try();
    if (check(TT::KW_WITH)) return parse_with();
    if (check(TT::KW_IMPORT)) return parse_import();
    if (check(TT::KW_FROM)) return parse_import_from();
    if (check(TT::KW_GLOBAL)) return parse_global();
    if (check(TT::KW_NONLOCAL)) return parse_nonlocal();
    if (check(TT::KW_DEL)) return parse_del();
    if (check(TT::KW_ASSERT)) return parse_assert();
    if (check(TT::KW_RAISE)) return parse_raise();
    return parse_simple_stmt();
}

StmtPtr Parser::parse_simple_stmt() {
    int line = peek().line;
    if (match(TT::KW_PASS)) return node<PassStmt>(line);
    if (match(TT::KW_BREAK)) return node<BreakStmt>(line);
    if (match(TT::KW_CONTINUE)) return node<ContinueStmt>(line);
    if (match(TT::KW_RETURN)) {
        auto s = node<ReturnStmt>(line);
        if (!check(TT::NEWLINE) && !check(TT::DEDENT) && !at_end()) {
            s->value = parse_expr();
        }
        return s;
    }
    return parse_assign_or_expr();
}

StmtPtr Parser::parse_compound_stmt() {
    return parse_stmt();
}

StmtList Parser::parse_block() {
    StmtList body;
    skip_newlines();
    while (!at_end() && !check(TT::DEDENT)) {
        body.push_back(parse_stmt());
        skip_newlines();
    }
    expect(TT::DEDENT, "expected DEDENT after block");
    return body;
}

StmtList Parser::parse_suite() {
    expect(TT::COLON, "expected ':' before block");
    if (match(TT::NEWLINE)) {
        expect(TT::INDENT, "expected indented block");
        return parse_block();
    }
    StmtList body;
    body.push_back(parse_simple_stmt());
    return body;
}

StmtPtr Parser::parse_if() {
    Token tok = expect(TT::KW_IF, "expected if");
    auto s = node<IfStmt>(tok.line);
    s->test = parse_expr();
    s->body = parse_suite();
    skip_newlines();
    while (match(TT::KW_ELIF)) {
        auto cond = parse_expr();
        auto body = parse_suite();
        s->elifs.emplace_back(std::move(cond), std::move(body));
        skip_newlines();
    }
    if (match(TT::KW_ELSE)) {
        s->orelse = parse_suite();
    }
    return s;
}

StmtPtr Parser::parse_while() {
    Token tok = expect(TT::KW_WHILE, "expected while");
    auto s = node<WhileStmt>(tok.line);
    s->test = parse_expr();
    s->body = parse_suite();
    return s;
}

StmtPtr Parser::parse_for() {
    Token tok = expect(TT::KW_FOR, "expected for");
    auto s = node<ForStmt>(tok.line);
    if (check(TT::IDENT)) {
        Token target = advance();
        auto name = node<NameExpr>(target.line);
        name->name = target.value;
        s->target = std::move(name);
    } else {
        s->target = parse_primary();
    }
    expect(TT::KW_IN, "expected 'glorpin' in for loop");
    s->iter = parse_expr();
    s->body = parse_suite();
    return s;
}

StmtPtr Parser::parse_match() {
    Token tok = expect(TT::KW_MATCH, "expected match");
    auto s = node<MatchStmt>(tok.line);
    s->subject = parse_expr();
    expect(TT::COLON, "expected ':' after match subject");
    expect(TT::NEWLINE, "expected newline after match");
    expect(TT::INDENT, "expected indented case block");
    skip_newlines();
    while (!at_end() && !check(TT::DEDENT)) {
        expect(TT::KW_CASE, "expected case in match block");
        MatchCase c;
        if (check(TT::IDENT) && peek().value == "_") {
            advance();
        } else {
            c.pattern = parse_expr();
        }
        c.body = parse_suite();
        s->cases.push_back(std::move(c));
        skip_newlines();
    }
    expect(TT::DEDENT, "expected DEDENT after match block");
    return s;
}

StmtPtr Parser::parse_try() {
    Token tok = expect(TT::KW_TRY, "expected try");
    auto s = node<TryStmt>(tok.line);
    s->body = parse_suite();
    skip_newlines();
    while (match(TT::KW_EXCEPT)) {
        ExceptHandler h;
        if (!check(TT::COLON)) {
            h.type = parse_expr();
            if (match(TT::KW_AS)) h.name = expect(TT::IDENT, "expected exception name").value;
        }
        h.body = parse_suite();
        s->handlers.push_back(std::move(h));
        skip_newlines();
    }
    if (match(TT::KW_ELSE)) {
        s->orelse = parse_suite();
        skip_newlines();
    }
    if (match(TT::KW_FINALLY)) {
        s->finalbody = parse_suite();
    }
    if (s->handlers.empty() && s->finalbody.empty()) {
        throw ParseError("try requires catch or finally", tok.line, tok.col);
    }
    return s;
}

StmtPtr Parser::parse_with() {
    Token tok = expect(TT::KW_WITH, "expected with");
    auto s = node<WithStmt>(tok.line);
    do {
        WithItem item;
        item.ctx = parse_expr();
        if (match(TT::KW_AS)) item.var = parse_expr();
        s->items.push_back(std::move(item));
    } while (match(TT::COMMA));
    s->body = parse_suite();
    return s;
}
StmtPtr Parser::parse_funcdef(bool) {
    Token tok = expect(TT::KW_DEF, "expected gloo");
    Token name = expect(TT::IDENT, "expected function name");
    auto s = node<FuncDef>(tok.line);
    s->name = name.value;
    expect(TT::LPAREN, "expected '(' after function name");
    s->params = parse_func_params();
    expect(TT::RPAREN, "expected ')' after function parameters");
    s->body = parse_suite();
    return s;
}

StmtPtr Parser::parse_classdef() {
    Token tok = expect(TT::KW_CLASS, "expected glorpkin");
    Token name = expect(TT::IDENT, "expected class name");
    auto s = node<ClassDef>(tok.line);
    s->name = name.value;
    if (match(TT::LPAREN)) {
        if (!check(TT::RPAREN)) {
            do {
                s->bases.push_back(parse_expr());
            } while (match(TT::COMMA) && !check(TT::RPAREN));
        }
        expect(TT::RPAREN, "expected ')' after base classes");
    }
    s->body = parse_suite();
    return s;
}
StmtPtr Parser::parse_return() { return parse_simple_stmt(); }
StmtPtr Parser::parse_raise() {
    Token tok = expect(TT::KW_RAISE, "expected raise");
    auto s = node<RaiseStmt>(tok.line);
    if (!check(TT::NEWLINE) && !check(TT::DEDENT) && !at_end()) s->exc = parse_expr();
    return s;
}

StmtPtr Parser::parse_assert() {
    Token tok = expect(TT::KW_ASSERT, "expected assert");
    auto s = node<AssertStmt>(tok.line);
    s->test = parse_expr();
    if (match(TT::COMMA)) s->msg = parse_expr();
    return s;
}

StmtPtr Parser::parse_import() {
    Token tok = expect(TT::KW_IMPORT, "expected import");
    auto s = node<ImportStmt>(tok.line);
    do {
        ImportStmt::Alias alias;
        alias.name = expect(TT::IDENT, "expected module name").value;
        if (match(TT::KW_AS)) alias.asname = expect(TT::IDENT, "expected alias").value;
        s->names.push_back(std::move(alias));
    } while (match(TT::COMMA));
    return s;
}

StmtPtr Parser::parse_import_from() {
    Token tok = expect(TT::KW_FROM, "expected from");
    auto s = node<ImportFromStmt>(tok.line);
    s->module = expect(TT::IDENT, "expected module name").value;
    expect(TT::KW_IMPORT, "expected import");
    do {
        ImportFromStmt::Alias alias;
        alias.name = expect(TT::IDENT, "expected imported name").value;
        if (match(TT::KW_AS)) alias.asname = expect(TT::IDENT, "expected alias").value;
        s->names.push_back(std::move(alias));
    } while (match(TT::COMMA));
    return s;
}

StmtPtr Parser::parse_global() {
    Token tok = expect(TT::KW_GLOBAL, "expected global");
    auto s = node<GlobalStmt>(tok.line);
    do {
        s->names.push_back(expect(TT::IDENT, "expected global name").value);
    } while (match(TT::COMMA));
    return s;
}

StmtPtr Parser::parse_nonlocal() {
    Token tok = expect(TT::KW_NONLOCAL, "expected nonlocal");
    auto s = node<NonlocalStmt>(tok.line);
    do {
        s->names.push_back(expect(TT::IDENT, "expected nonlocal name").value);
    } while (match(TT::COMMA));
    return s;
}

StmtPtr Parser::parse_del() {
    Token tok = expect(TT::KW_DEL, "expected del");
    auto s = node<DelStmt>(tok.line);
    s->targets = parse_expr_list();
    return s;
}

StmtPtr Parser::parse_assign_or_expr() {
    auto left = parse_expr();
    int line = left->line;
    if (match(TT::COMMA)) {
        auto tuple = node<TupleExpr>(line);
        tuple->elements.push_back(std::move(left));
        do {
            tuple->elements.push_back(parse_expr());
        } while (match(TT::COMMA) && !check(TT::OP_ASSIGN));
        left = std::move(tuple);
    }
    if (match(TT::OP_ASSIGN)) {
        auto s = node<AssignStmt>(line);
        s->targets.push_back(std::move(left));
        s->value = parse_expr();
        return s;
    }
    if (match_any({TT::OP_PLUS_ASS, TT::OP_MINUS_ASS, TT::OP_STAR_ASS, TT::OP_SLASH_ASS, TT::OP_PERCENT_ASS, TT::OP_DSTAR_ASS, TT::OP_DSLASH_ASS})) {
        Token op = tokens_[pos_ - 1];
        auto s = node<AugAssignStmt>(line);
        s->target = std::move(left);
        s->op = op.value;
        s->value = parse_expr();
        return s;
    }
    auto s = node<ExprStmt>(line);
    s->expr = std::move(left);
    return s;
}

ExprPtr Parser::parse_expr() { return parse_lambda(); }

ExprPtr Parser::parse_lambda() {
    if (!match(TT::KW_LAMBDA)) return parse_ternary();
    auto n = node<LambdaExpr>(peek(-1).line);
    if (!check(TT::COLON)) {
        do {
            Token name = expect(TT::IDENT, "expected lambda parameter name");
            n->params.push_back(name.value);
        } while (match(TT::COMMA) && !check(TT::COLON));
    }
    expect(TT::COLON, "expected ':' after lambda parameters");
    n->body = parse_expr();
    return n;
}

ExprPtr Parser::parse_ternary() {
    auto value = parse_or();
    if (!match(TT::KW_IF)) return value;
    auto n = node<IfExpr>(value->line);
    n->value = std::move(value);
    n->cond = parse_or();
    expect(TT::KW_ELSE, "expected else in conditional expression");
    n->alt = parse_expr();
    return n;
}

ExprPtr Parser::parse_or() {
    auto expr = parse_and();
    while (match(TT::KW_OR)) {
        auto n = node<BoolOpExpr>(expr->line);
        n->op = "or";
        n->values.push_back(std::move(expr));
        n->values.push_back(parse_and());
        expr = std::move(n);
    }
    return expr;
}

ExprPtr Parser::parse_and() {
    auto expr = parse_not();
    while (match(TT::KW_AND)) {
        auto n = node<BoolOpExpr>(expr->line);
        n->op = "and";
        n->values.push_back(std::move(expr));
        n->values.push_back(parse_not());
        expr = std::move(n);
    }
    return expr;
}

ExprPtr Parser::parse_not() {
    if (match(TT::KW_NOT)) {
        auto n = node<UnaryExpr>(peek(-1).line);
        n->op = "not";
        n->operand = parse_not();
        return n;
    }
    return parse_compare();
}

ExprPtr Parser::parse_compare() {
    auto expr = parse_bitor();
    if (match_any({TT::OP_EQ, TT::OP_NEQ, TT::OP_LT, TT::OP_GT, TT::OP_LEQ, TT::OP_GEQ, TT::KW_IS, TT::KW_IN})) {
        auto n = node<CompareExpr>(expr->line);
        n->left = std::move(expr);
        do {
            Token op = tokens_[pos_ - 1];
            n->ops.push_back(op.value.empty() ? (op.type == TT::KW_IN ? "in" : "is") : op.value);
            n->comparators.push_back(parse_bitor());
        } while (match_any({TT::OP_EQ, TT::OP_NEQ, TT::OP_LT, TT::OP_GT, TT::OP_LEQ, TT::OP_GEQ, TT::KW_IS, TT::KW_IN}));
        return n;
    }
    return expr;
}

ExprPtr Parser::parse_bitor() {
    auto expr = parse_bitxor();
    while (match(TT::OP_BITOR)) {
        auto n = node<BinaryExpr>(expr->line);
        n->op = "|";
        n->left = std::move(expr);
        n->right = parse_bitxor();
        expr = std::move(n);
    }
    return expr;
}

ExprPtr Parser::parse_bitxor() {
    auto expr = parse_bitand();
    while (match(TT::OP_BITXOR)) {
        auto n = node<BinaryExpr>(expr->line);
        n->op = "^";
        n->left = std::move(expr);
        n->right = parse_bitand();
        expr = std::move(n);
    }
    return expr;
}

ExprPtr Parser::parse_bitand() {
    auto expr = parse_shift();
    while (match(TT::OP_BITAND)) {
        auto n = node<BinaryExpr>(expr->line);
        n->op = "&";
        n->left = std::move(expr);
        n->right = parse_shift();
        expr = std::move(n);
    }
    return expr;
}

ExprPtr Parser::parse_shift() {
    auto expr = parse_add();
    while (match_any({TT::OP_LSHIFT, TT::OP_RSHIFT})) {
        Token op = tokens_[pos_ - 1];
        auto n = node<BinaryExpr>(expr->line);
        n->op = op.value;
        n->left = std::move(expr);
        n->right = parse_add();
        expr = std::move(n);
    }
    return expr;
}

ExprPtr Parser::parse_add() {
    auto expr = parse_mul();
    while (match_any({TT::OP_PLUS, TT::OP_MINUS})) {
        Token op = tokens_[pos_ - 1];
        auto n = node<BinaryExpr>(expr->line);
        n->op = op.value;
        n->left = std::move(expr);
        n->right = parse_mul();
        expr = std::move(n);
    }
    return expr;
}

ExprPtr Parser::parse_mul() {
    auto expr = parse_unary();
    while (match_any({TT::OP_STAR, TT::OP_SLASH, TT::OP_DSLASH, TT::OP_PERCENT})) {
        Token op = tokens_[pos_ - 1];
        auto n = node<BinaryExpr>(expr->line);
        n->op = op.value;
        n->left = std::move(expr);
        n->right = parse_unary();
        expr = std::move(n);
    }
    return expr;
}

ExprPtr Parser::parse_unary() {
    if (match_any({TT::OP_PLUS, TT::OP_MINUS, TT::OP_BITNOT})) {
        Token op = tokens_[pos_ - 1];
        auto n = node<UnaryExpr>(op.line);
        n->op = op.value;
        n->operand = parse_unary();
        return n;
    }
    return parse_power();
}

ExprPtr Parser::parse_power() {
    auto expr = parse_await();
    if (match(TT::OP_DSTAR)) {
        auto n = node<BinaryExpr>(expr->line);
        n->op = "**";
        n->left = std::move(expr);
        n->right = parse_unary();
        return n;
    }
    return expr;
}

ExprPtr Parser::parse_await() { return parse_postfix(); }

ExprPtr Parser::parse_postfix() {
    auto expr = parse_primary();
    bool keep_going = true;
    while (keep_going) {
        if (match(TT::DOT)) {
            Token name = expect(TT::IDENT, "expected attribute name after '.'");
            auto n = node<AttrExpr>(expr->line);
            n->obj = std::move(expr);
            n->attr = name.value;
            expr = std::move(n);
        } else if (match(TT::LBRACKET)) {
            auto n = node<IndexExpr>(expr->line);
            n->obj = std::move(expr);
            n->key = parse_expr();
            expect(TT::RBRACKET, "expected ']' after index");
            expr = std::move(n);
        } else if (match(TT::LPAREN)) {
            auto n = node<CallExpr>(expr->line);
            n->callee = std::move(expr);
            if (!check(TT::RPAREN)) {
                n->args = parse_call_args();
            }
            expect(TT::RPAREN, "expected ')' after call arguments");
            expr = std::move(n);
        } else {
            keep_going = false;
        }
    }
    return expr;
}

static std::string unquote_token(const std::string& raw) {
    size_t q = raw.find_first_of("'\"");
    if (q == std::string::npos) return raw;
    char quote = raw[q];
    bool triple = raw.size() >= q + 3 && raw[q + 1] == quote && raw[q + 2] == quote;
    size_t start = q + (triple ? 3 : 1);
    size_t end = raw.size();
    if (triple && end >= 3) end -= 3;
    else if (end > start) end -= 1;
    std::string s = raw.substr(start, end > start ? end - start : 0);
    std::string out;
    for (size_t i = 0; i < s.size(); ++i) {
        if (s[i] == '\\' && i + 1 < s.size()) {
            char n = s[++i];
            if (n == 'n') out += '\n';
            else if (n == 't') out += '\t';
            else out += n;
        } else {
            out += s[i];
        }
    }
    return out;
}

ExprPtr Parser::parse_primary() {
    Token tok = advance();
    switch (tok.type) {
        case TT::LIT_INT: {
            auto n = node<IntLit>(tok.line);
            n->value = std::stoll(tok.value, nullptr, 0);
            return n;
        }
        case TT::LIT_FLOAT: {
            auto n = node<FloatLit>(tok.line);
            n->value = std::stod(tok.value);
            return n;
        }
        case TT::LIT_STR:
        {
            auto n = node<StrLit>(tok.line);
            n->value = unquote_token(tok.value);
            return n;
        }
        case TT::LIT_FSTR: {
            auto n = node<FStrLit>(tok.line);
            FStrLit::Part part;
            part.is_expr = false;
            part.raw = unquote_token(tok.value);
            n->parts.push_back(std::move(part));
            return n;
        }
        case TT::KW_TRUE: {
            auto n = node<BoolLit>(tok.line);
            n->value = true;
            return n;
        }
        case TT::KW_FALSE: {
            auto n = node<BoolLit>(tok.line);
            n->value = false;
            return n;
        }
        case TT::KW_NONE:
            return node<NoneLit>(tok.line);
        case TT::IDENT: {
            auto n = node<NameExpr>(tok.line);
            n->name = tok.value;
            return n;
        }
        case TT::LBRACKET:
            return parse_list_literal();
        case TT::LPAREN:
            return parse_tuple_or_paren();
        case TT::LBRACE:
            return parse_dict_or_set_literal();
        default:
            throw ParseError("expected expression", tok.line, tok.col);
    }
}

ExprPtr Parser::parse_list_literal() {
    auto n = node<ListExpr>(peek(-1).line);
    if (!check(TT::RBRACKET)) {
        do {
            n->elements.push_back(parse_expr());
        } while (match(TT::COMMA) && !check(TT::RBRACKET));
    }
    expect(TT::RBRACKET, "expected ']'");
    return n;
}

ExprPtr Parser::parse_dict_or_set_literal() {
    int line = peek(-1).line;
    if (match(TT::RBRACE)) return node<DictExpr>(line);

    auto first = parse_expr();
    if (match(TT::COLON)) {
        auto n = node<DictExpr>(line);
        n->keys.push_back(std::move(first));
        n->values.push_back(parse_expr());
        while (match(TT::COMMA) && !check(TT::RBRACE)) {
            n->keys.push_back(parse_expr());
            expect(TT::COLON, "expected ':' in dict literal");
            n->values.push_back(parse_expr());
        }
        expect(TT::RBRACE, "expected '}' after dict literal");
        return n;
    }

    auto n = node<SetExpr>(line);
    n->elements.push_back(std::move(first));
    while (match(TT::COMMA) && !check(TT::RBRACE)) {
        n->elements.push_back(parse_expr());
    }
    expect(TT::RBRACE, "expected '}' after set literal");
    return n;
}

ExprPtr Parser::parse_tuple_or_paren() {
    int line = peek(-1).line;
    if (match(TT::RPAREN)) {
        auto n = node<TupleExpr>(line);
        return n;
    }
    auto first = parse_expr();
    if (!match(TT::COMMA)) {
        expect(TT::RPAREN, "expected ')'");
        return first;
    }
    auto n = node<TupleExpr>(line);
    n->elements.push_back(std::move(first));
    while (!check(TT::RPAREN)) {
        n->elements.push_back(parse_expr());
        if (!match(TT::COMMA)) break;
    }
    expect(TT::RPAREN, "expected ')'");
    return n;
}

ExprList Parser::parse_expr_list() {
    ExprList items;
    items.push_back(parse_expr());
    while (match(TT::COMMA)) {
        items.push_back(parse_expr());
    }
    return items;
}

std::vector<CallArg> Parser::parse_call_args() {
    std::vector<CallArg> args;
    do {
        CallArg arg;
        if (check(TT::IDENT) && peek(1).type == TT::OP_ASSIGN) {
            arg.name = advance().value;
            advance();
            arg.value = parse_expr();
        } else {
            arg.value = parse_expr();
        }
        args.push_back(std::move(arg));
    } while (match(TT::COMMA) && !check(TT::RPAREN));
    return args;
}

std::vector<FuncParam> Parser::parse_func_params() {
    std::vector<FuncParam> params;
    if (check(TT::RPAREN)) return params;
    do {
        FuncParam param;
        Token name = expect(TT::IDENT, "expected parameter name");
        param.name = name.value;
        if (match(TT::OP_ASSIGN)) {
            param.default_val = parse_expr();
        }
        params.push_back(std::move(param));
    } while (match(TT::COMMA) && !check(TT::RPAREN));
    return params;
}
