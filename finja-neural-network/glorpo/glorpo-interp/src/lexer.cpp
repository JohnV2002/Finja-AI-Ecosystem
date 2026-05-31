/**
 * Glorpo Lexer Implementation
 * ===========================
 * Tokenizes Glorpo source code for the standalone interpreter.
 *
 * Main Responsibilities:
 * - Scan source text into tokens.
 * - Track line and column positions.
 * - Report lexical errors with context.
 *
 * Side Effects:
 * - Throws LexError for invalid source.
 */
#include "lexer.hpp"
#include <cctype>
#include <sstream>

// --- Ctor --------------------------------------------------------------------
Lexer::Lexer(std::string source) : src_(std::move(source)) {}

// --- Char helpers ------------------------------------------------------------
char Lexer::peek(int offset) const {
    size_t idx = pos_ + offset;
    return (idx < src_.size()) ? src_[idx] : '\0';
}

char Lexer::advance() {
    char c = src_[pos_++];
    if (c == '\n') { ++line_; col_ = 1; }
    else           { ++col_; }
    return c;
}

bool Lexer::match(char expected) {
    if (at_end() || src_[pos_] != expected) return false;
    advance();
    return true;
}

// --- Indentation handler -----------------------------------------------------
std::vector<Token> Lexer::handle_indent(int spaces) {
    std::vector<Token> toks;
    int current = indent_stack_.back();

    if (spaces > current) {
        indent_stack_.push_back(spaces);
        toks.push_back({TT::INDENT, "", line_, 1});
    } else {
        while (spaces < indent_stack_.back()) {
            indent_stack_.pop_back();
            toks.push_back({TT::DEDENT, "", line_, 1});
        }
        if (spaces != indent_stack_.back()) {
            throw LexError("Inconsistent indentation", line_, 1);
        }
    }
    return toks;
}

// --- Comment skipper ---------------------------------------------------------
void Lexer::skip_comment() {
    while (!at_end() && peek() != '\n') advance();
}

// --- Number scanner ----------------------------------------------------------
Token Lexer::scan_number(int line, int col) {
    std::string num;
    bool is_float = false;

    // Hex / bin / oct literals
    if (peek(-1) == '0') {
        char base = peek();
        if (base == 'x' || base == 'X') {
            num += '0'; num += advance();
            while (std::isxdigit(peek())) num += advance();
            return {TT::LIT_INT, num, line, col};
        }
        if (base == 'b' || base == 'B') {
            num += '0'; num += advance();
            while (peek() == '0' || peek() == '1') num += advance();
            return {TT::LIT_INT, num, line, col};
        }
        if (base == 'o' || base == 'O') {
            num += '0'; num += advance();
            while (peek() >= '0' && peek() <= '7') num += advance();
            return {TT::LIT_INT, num, line, col};
        }
    }

    // Re-include first digit (already advanced by caller)
    num += src_[pos_ - 1];
    while (std::isdigit(peek())) num += advance();

    if (peek() == '.' && std::isdigit(peek(1))) {
        is_float = true;
        num += advance();  // '.'
        while (std::isdigit(peek())) num += advance();
    }
    if (peek() == 'e' || peek() == 'E') {
        is_float = true;
        num += advance();
        if (peek() == '+' || peek() == '-') num += advance();
        while (std::isdigit(peek())) num += advance();
    }
    return {is_float ? TT::LIT_FLOAT : TT::LIT_INT, num, line, col};
}

// --- String scanner ----------------------------------------------------------
Token Lexer::scan_string(int line, int col) {
    // Collect prefix characters (already consumed up to the quote)
    // We back up 1 to see the quote, but prefix chars came before.
    // Strategy: scan prefix from result buffer - easier to just check preceding chars.
    // The quote char is the last char advanced before calling this.
    char q = src_[pos_ - 1];

    // Detect f-string prefix by looking back
    bool is_fstr = false;
    for (int back = 1; back <= 2 && (int)pos_ - 1 - back >= 0; ++back) {
        char pc = std::tolower((unsigned char)src_[pos_ - 1 - back]);
        if (pc == 'f') { is_fstr = true; break; }
        if (pc != 'r' && pc != 'b' && pc != 'u') break;
    }

    // Triple or single?
    bool triple = (peek() == q && peek(1) == q);
    if (triple) { advance(); advance(); }

    std::string content;
    content += q;
    if (triple) { content += q; content += q; }

    int depth = 0;  // for f-string { } tracking

    while (!at_end()) {
        char c = peek();

        // End condition
        if (triple) {
            if (c == q && peek(1) == q && peek(2) == q) {
                advance(); advance(); advance();
                content += q; content += q; content += q;
                break;
            }
        } else {
            if (c == q) { advance(); content += q; break; }
            if (c == '\n') throw LexError("Unterminated string", line, col);
        }

        if (c == '\\') {
            content += advance();  // '\'
            if (!at_end()) content += advance();  // escaped char
            continue;
        }

        // f-string { expression } - just collect raw for now (parser handles)
        content += advance();
    }

    return {is_fstr ? TT::LIT_FSTR : TT::LIT_STR, content, line, col};
}

// --- Identifier / keyword scanner --------------------------------------------
Token Lexer::scan_ident_or_keyword(int line, int col) {
    std::string word;
    word += src_[pos_ - 1];   // first char already consumed
    while (!at_end() && (std::isalnum(peek()) || peek() == '_')) {
        word += advance();
    }

    // Check Glorpo keyword map
    const auto& kw = glorpo_keywords();
    auto it = kw.find(word);
    if (it != kw.end()) return {it->second, word, line, col};

    // Plain identifier
    return {TT::IDENT, word, line, col};
}

// --- Main tokenize loop -------------------------------------------------------
std::vector<Token> Lexer::tokenize() {
    std::vector<Token> tokens;

    while (!at_end()) {
        // -- Indentation (only at start of a logical line) ------------------
        if (at_line_start_ && paren_depth_ == 0) {
            int spaces = 0;
            while (!at_end() && (peek() == ' ' || peek() == '\t')) {
                spaces += (peek() == '\t') ? 8 : 1;
                advance();
            }
            // Blank / comment lines don't change indent
            if (!at_end() && peek() != '\n' && peek() != '#') {
                auto indent_toks = handle_indent(spaces);
                for (auto& t : indent_toks) tokens.push_back(t);
            }
            at_line_start_ = false;
        }

        if (at_end()) break;

        int line = line_, col = col_;
        char c = advance();

        // -- Whitespace (non-indent) ----------------------------------------
        if (c == ' ' || c == '\t' || c == '\r') continue;

        // -- Continuation line ----------------------------------------------
        if (c == '\\' && peek() == '\n') { advance(); continue; }

        // -- Newline -------------------------------------------------------
        if (c == '\n') {
            if (paren_depth_ == 0 && !tokens.empty() &&
                !tokens.back().is_any({TT::NEWLINE, TT::INDENT, TT::DEDENT})) {
                tokens.push_back({TT::NEWLINE, "\n", line, col});
            }
            at_line_start_ = true;
            continue;
        }

        // -- Comment -------------------------------------------------------
        if (c == '#') { skip_comment(); continue; }

        // -- String literal (with optional prefix f/r/b/u/F/R/B/U) --------
        if (c == '"' || c == '\'') {
            tokens.push_back(scan_string(line, col));
            continue;
        }
        // String prefix then quote
        if ((c == 'f' || c == 'F' || c == 'r' || c == 'R' ||
             c == 'b' || c == 'B' || c == 'u' || c == 'U') &&
            (peek() == '"' || peek() == '\'' ||
             ((peek() == 'f' || peek() == 'F' || peek() == 'r' || peek() == 'R') &&
              (peek(1) == '"' || peek(1) == '\'')))) {
            // Collect prefix
            std::string pref(1, c);
            if (peek() != '"' && peek() != '\'') pref += advance();
            advance();  // consume the quote
            tokens.push_back(scan_string(line, col));
            tokens.back().value = pref + tokens.back().value;
            continue;
        }

        // -- Number --------------------------------------------------------
        if (std::isdigit(c)) {
            tokens.push_back(scan_number(line, col));
            continue;
        }

        // -- Identifier / keyword ------------------------------------------
        if (std::isalpha(c) || c == '_') {
            tokens.push_back(scan_ident_or_keyword(line, col));
            continue;
        }

        // -- Operators & delimiters ----------------------------------------
        switch (c) {
            case '+': tokens.push_back({match('=') ? TT::OP_PLUS_ASS  : TT::OP_PLUS,   std::string(1,c), line, col}); break;
            case '-': tokens.push_back({match('=') ? TT::OP_MINUS_ASS : match('>') ? TT::OP_ARROW : TT::OP_MINUS, std::string(1,c), line, col}); break;
            case '%': tokens.push_back({match('=') ? TT::OP_PERCENT_ASS : TT::OP_PERCENT, std::string(1,c), line, col}); break;
            case '@': tokens.push_back({TT::OP_AT, "@", line, col}); break;
            case '~': tokens.push_back({TT::OP_BITNOT, "~", line, col}); break;
            case '&': tokens.push_back({TT::OP_BITAND, "&", line, col}); break;
            case '|': tokens.push_back({TT::OP_BITOR, "|", line, col}); break;
            case '^': tokens.push_back({TT::OP_BITXOR, "^", line, col}); break;

            case '*':
                if (match('*')) tokens.push_back({match('=') ? TT::OP_DSTAR_ASS  : TT::OP_DSTAR,  "**", line, col});
                else            tokens.push_back({match('=') ? TT::OP_STAR_ASS   : TT::OP_STAR,   "*",  line, col});
                break;

            case '/':
                if (match('/')) tokens.push_back({match('=') ? TT::OP_DSLASH_ASS : TT::OP_DSLASH, "//", line, col});
                else            tokens.push_back({match('=') ? TT::OP_SLASH_ASS  : TT::OP_SLASH,  "/",  line, col});
                break;

            case '<':
                if (match('<'))      tokens.push_back({TT::OP_LSHIFT, "<<", line, col});
                else if (match('=')) tokens.push_back({TT::OP_LEQ,    "<=", line, col});
                else                 tokens.push_back({TT::OP_LT,     "<",  line, col});
                break;

            case '>':
                if (match('>'))      tokens.push_back({TT::OP_RSHIFT, ">>", line, col});
                else if (match('=')) tokens.push_back({TT::OP_GEQ,    ">=", line, col});
                else                 tokens.push_back({TT::OP_GT,     ">",  line, col});
                break;

            case '=':
                tokens.push_back({match('=') ? TT::OP_EQ  : TT::OP_ASSIGN, std::string(1,c), line, col});
                break;

            case '!':
                if (!match('=')) throw LexError("Expected '=' after '!'", line, col);
                tokens.push_back({TT::OP_NEQ, "!=", line, col});
                break;

            case ':':
                tokens.push_back({match('=') ? TT::OP_WALRUS : TT::COLON, std::string(1,c), line, col});
                break;

            case '(': ++paren_depth_; tokens.push_back({TT::LPAREN,   "(", line, col}); break;
            case ')': --paren_depth_; tokens.push_back({TT::RPAREN,   ")", line, col}); break;
            case '[': ++paren_depth_; tokens.push_back({TT::LBRACKET, "[", line, col}); break;
            case ']': --paren_depth_; tokens.push_back({TT::RBRACKET, "]", line, col}); break;
            case '{': ++paren_depth_; tokens.push_back({TT::LBRACE,   "{", line, col}); break;
            case '}': --paren_depth_; tokens.push_back({TT::RBRACE,   "}", line, col}); break;

            case ',': tokens.push_back({TT::COMMA,     ",", line, col}); break;
            case ';': tokens.push_back({TT::SEMICOLON, ";", line, col}); break;
            case '.':
                if (peek() == '.' && peek(1) == '.') {
                    advance(); advance();
                    tokens.push_back({TT::ELLIPSIS, "...", line, col});
                } else {
                    tokens.push_back({TT::DOT, ".", line, col});
                }
                break;

            default:
                throw LexError(std::string("Unexpected character '") + c + "'", line, col);
        }
    }

    // Emit trailing DEDENTs
    while (indent_stack_.size() > 1) {
        indent_stack_.pop_back();
        tokens.push_back({TT::DEDENT, "", line_, col_});
    }
    tokens.push_back({TT::END_OF_FILE, "", line_, col_});
    return tokens;
}
