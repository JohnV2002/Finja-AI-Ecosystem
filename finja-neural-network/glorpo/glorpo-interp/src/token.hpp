/**
 * Token Header
 * ============
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
#include <string>
#include <unordered_map>
#include <initializer_list>

// --- Token Types -------------------------------------------------------------
enum class TT {
    // Literals
    LIT_INT, LIT_FLOAT, LIT_STR, LIT_FSTR,

    // Control flow
    KW_IF, KW_ELIF, KW_ELSE,
    KW_FOR, KW_WHILE, KW_BREAK, KW_CONTINUE, KW_PASS,
    KW_MATCH, KW_CASE,

    // Functions / Classes
    KW_DEF, KW_RETURN, KW_CLASS, KW_LAMBDA,
    KW_YIELD, KW_ASYNC, KW_AWAIT,

    // Values
    KW_TRUE, KW_FALSE, KW_NONE,

    // Logic
    KW_AND, KW_OR, KW_NOT, KW_IS, KW_IN,

    // Imports
    KW_IMPORT, KW_FROM, KW_AS,

    // Error handling
    KW_TRY, KW_EXCEPT, KW_FINALLY, KW_RAISE, KW_ASSERT,

    // Scope
    KW_GLOBAL, KW_NONLOCAL, KW_DEL, KW_WITH,

    // Identifier
    IDENT,

    // Arithmetic operators
    OP_PLUS, OP_MINUS, OP_STAR, OP_SLASH,
    OP_DSLASH, OP_PERCENT, OP_DSTAR,

    // Comparison
    OP_EQ, OP_NEQ, OP_LT, OP_GT, OP_LEQ, OP_GEQ,

    // Assignment
    OP_ASSIGN,
    OP_PLUS_ASS, OP_MINUS_ASS, OP_STAR_ASS, OP_SLASH_ASS,
    OP_PERCENT_ASS, OP_DSTAR_ASS, OP_DSLASH_ASS,

    // Bitwise
    OP_BITAND, OP_BITOR, OP_BITXOR, OP_BITNOT, OP_LSHIFT, OP_RSHIFT,

    // Other
    OP_WALRUS,   // :=
    OP_ARROW,    // ->
    OP_AT,       // @  (decorator / matmul)

    // Delimiters
    LPAREN, RPAREN,
    LBRACE, RBRACE,
    LBRACKET, RBRACKET,
    COMMA, DOT, COLON, SEMICOLON, ELLIPSIS,

    // Indent / Newline
    NEWLINE,
    INDENT,
    DEDENT,
    END_OF_FILE,
};

// --- Glorpo keyword -> Token mapping ------------------------------------------
// The lexer speaks Glorpo natively - no pre-translation needed.
inline const std::unordered_map<std::string, TT>& glorpo_keywords() {
    static const std::unordered_map<std::string, TT> kw = {
        // Control flow
        {"glorb",       TT::KW_IF},
        {"glorbelif",   TT::KW_ELIF},
        {"glorpelse",   TT::KW_ELSE},
        {"glorpach",    TT::KW_FOR},
        {"glorploop",   TT::KW_WHILE},
        {"glorpsnap",   TT::KW_BREAK},
        {"glorpskip",   TT::KW_CONTINUE},
        {"glorpnull",   TT::KW_PASS},
        {"glorpcheck",  TT::KW_MATCH},
        {"glorpwhen",   TT::KW_CASE},
        // Functions / Classes
        {"gloo",        TT::KW_DEF},
        {"glorpback",   TT::KW_RETURN},
        {"glorpkin",    TT::KW_CLASS},
        {"glorbda",     TT::KW_LAMBDA},
        {"glorpgive",   TT::KW_YIELD},
        {"glorpfast",   TT::KW_ASYNC},
        {"glorpwait",   TT::KW_AWAIT},
        // Values
        {"glorpyes",    TT::KW_TRUE},
        {"glorpno",     TT::KW_FALSE},
        {"glorpvoid",   TT::KW_NONE},
        // Logic
        {"glorpand",    TT::KW_AND},
        {"glorpor",     TT::KW_OR},
        {"glorpnot",    TT::KW_NOT},
        {"glorpis",     TT::KW_IS},
        {"glorpin",     TT::KW_IN},
        // Imports
        {"glorpget",    TT::KW_IMPORT},
        {"glorpfrom",   TT::KW_FROM},
        {"glorpas",     TT::KW_AS},
        // Error handling
        {"glorptry",    TT::KW_TRY},
        {"glorpcatch",  TT::KW_EXCEPT},
        {"glorpalways", TT::KW_FINALLY},
        {"glorpyeet",   TT::KW_RAISE},
        {"glorpswear",  TT::KW_ASSERT},
        // Scope
        {"glorpwide",   TT::KW_GLOBAL},
        {"glorpreach",  TT::KW_NONLOCAL},
        {"glorpbye",    TT::KW_DEL},
        {"glorpwith",   TT::KW_WITH},
    };
    return kw;
}

// --- Token -------------------------------------------------------------------
struct Token {
    TT          type;
    std::string value;   // raw source text
    int         line;
    int         col;

    Token(TT t, std::string v, int l, int c)
        : type(t), value(std::move(v)), line(l), col(c) {}

    bool is(TT t) const { return type == t; }
    bool is_any(std::initializer_list<TT> ts) const {
        for (auto t : ts) if (type == t) return true;
        return false;
    }
};
