/**
 * Lexer Header
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
#include <vector>
#include <stdexcept>
#include "token.hpp"

// --- Lex Error ----------------------------------------------------------------
struct LexError : std::runtime_error {
    int line, col;
    LexError(const std::string& msg, int l, int c)
        : std::runtime_error("LexError line " + std::to_string(l) +
                             ", col " + std::to_string(c) + ": " + msg)
        , line(l), col(c) {}
};

// --- Lexer -------------------------------------------------------------------
class Lexer {
public:
    explicit Lexer(std::string source);
    std::vector<Token> tokenize();

private:
    std::string src_;
    size_t      pos_  = 0;
    int         line_ = 1;
    int         col_  = 1;

    // Indentation state
    std::vector<int> indent_stack_ = {0};
    bool at_line_start_            = true;
    int  paren_depth_              = 0;   // (), [], {} - suppress NEWLINE inside

    // -- Char helpers ---------------------------------------------------------
    char peek(int offset = 0) const;
    char advance();
    bool match(char expected);
    bool at_end() const { return pos_ >= src_.size(); }

    // -- Scanners --------------------------------------------------------------
    void        skip_comment();
    Token       scan_number(int line, int col);
    Token       scan_string(int line, int col);
    Token       scan_ident_or_keyword(int line, int col);
    std::vector<Token> handle_indent(int spaces);
};
