/**
 * Glorpo Native Runner
 * ====================
 * Runs .glp files by translating Glorpo tokens back to Python and invoking Python.
 *
 * Main Responsibilities:
 * - Read Glorpo source files.
 * - Deglorpify tokens while preserving strings and comments.
 * - Execute the translated Python through the system Python interpreter.
 *
 * Side Effects:
 * - Reads source files from disk.
 * - Writes temporary Python files.
 * - Launches a Python subprocess.
 */
#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <stdexcept>

#include "glorpo_dict.hpp"

// --- Helpers -----------------------------------------------------------------

static bool is_word_char(char c) {
    return std::isalnum((unsigned char)c) || c == '_';
}

/**
 * Returns true if the quote at `quote_pos` is preceded by an f/F prefix
 * (handles f, F, rf, fr, Rf, fR, RF, FR, rb, br, etc.)
 */
static bool is_fstring_prefix(const std::string& code, size_t quote_pos) {
    std::string seen;
    int p = (int)quote_pos - 1;
    while (p >= 0 && seen.size() < 2) {
        char lc = (char)std::tolower((unsigned char)code[p]);
        if (lc == 'f' || lc == 'r' || lc == 'b' || lc == 'u') {
            seen += lc;
            --p;
        } else {
            break;
        }
    }
    return seen.find('f') != std::string::npos;
}

/**
 * Scans an f-string expression starting right after the '{' at open_brace.
 * Handles nested braces.
 * Returns the translated expression and sets `end_pos` to the closing '}'.
 */
static std::string scan_fstring_expr(const std::string& code,
                                     size_t open_brace,
                                     size_t& end_pos);  // forward decl (deglorpify calls this)

// --- Core Deglorpifier --------------------------------------------------------

/**
 * Translates Glorpo tokens back to Python, character by character.
 *   - String literals: content preserved, f-string {expressions} translated
 *   - Comments (#...): copied as-is
 *   - Tokens: replaced at proper word boundaries (longest-match first)
 */
static std::string deglorpify(const std::string& code) {
    std::string result;
    result.reserve(code.size());
    size_t i = 0;

    while (i < code.size()) {

        // -- String literal ------------------------------------------------
        if (code[i] == '"' || code[i] == '\'') {
            bool fstr = is_fstring_prefix(code, i);
            char q = code[i];

            // Triple or single quote?
            bool triple = (i + 2 < code.size() &&
                           code[i+1] == q && code[i+2] == q);
            size_t seq_len = triple ? 3 : 1;
            std::string end_seq(seq_len, q);

            // Emit opening quote(s)
            result += code.substr(i, seq_len);
            size_t seg_start = i + seq_len;
            i = seg_start;

            while (i < code.size()) {
                // End of string?
                if (code.substr(i, seq_len) == end_seq) {
                    result += code.substr(seg_start, i - seg_start);
                    result += end_seq;
                    i += seq_len;
                    break;
                }
                // Escape sequence
                if (code[i] == '\\' && i + 1 < code.size()) {
                    i += 2;
                    continue;
                }
                // f-string expression
                if (fstr && code[i] == '{' &&
                    i + 1 < code.size() && code[i+1] != '{') {
                    // flush segment so far
                    result += code.substr(seg_start, i - seg_start + 1); // incl. '{'
                    size_t close_brace = 0;
                    std::string translated = scan_fstring_expr(code, i, close_brace);
                    result += translated;
                    result += '}';
                    i = close_brace + 1;
                    seg_start = i;
                    continue;
                }
                ++i;
            }
            // Unclosed string edge-case: flush remainder
            if (i >= code.size() && seg_start < code.size()) {
                result += code.substr(seg_start);
            }
            continue;
        }

        // -- Comment -------------------------------------------------------
        if (code[i] == '#') {
            while (i < code.size() && code[i] != '\n') {
                result += code[i++];
            }
            continue;
        }

        // -- Token substitution --------------------------------------------
        bool matched = false;
        for (const auto& [src, dst] : DEGLORPO_MAP) {
            size_t src_len = src.size();
            if (i + src_len > code.size()) continue;
            if (code.compare(i, src_len, src) != 0) continue;

            bool before_ok = (i == 0 || !is_word_char(code[i - 1]));
            size_t after = i + src_len;
            bool after_ok = (after >= code.size() || !is_word_char(code[after]));

            if (before_ok && after_ok) {
                result += dst;
                i += src_len;
                matched = true;
                break;
            }
        }

        if (!matched) {
            result += code[i++];
        }
    }

    return result;
}

// Needs to be defined after deglorpify (recursive call)
static std::string scan_fstring_expr(const std::string& code,
                                     size_t open_brace,
                                     size_t& end_pos) {
    int depth = 1;
    size_t j = open_brace + 1;
    size_t expr_start = j;
    while (j < code.size() && depth > 0) {
        if (code[j] == '{') ++depth;
        else if (code[j] == '}') --depth;
        if (depth > 0) ++j;
    }
    end_pos = j; // position of closing '}'
    std::string expr = code.substr(expr_start, j - expr_start);
    return deglorpify(expr);
}

// --- Python Finder ------------------------------------------------------------

/**
 * Returns the Python interpreter command available on this system.
 * Tries python3 first, then python.
 */
static std::string find_python() {
#ifdef _WIN32
    if (std::system("python --version >nul 2>&1") == 0) return "python";
    return "python3";
#else
    if (std::system("python3 --version >/dev/null 2>&1") == 0) return "python3";
    return "python";
#endif
}

// --- Main ---------------------------------------------------------------------

int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cerr << "Glorpo Native Runner\n"
                  << "Usage:  glorpo <file.glp>\n"
                  << "        glorpo --deglorpify <file.glp>   (show translated Python)\n"
                  << "\nGlorpo is pain.\n";
        return 1;
    }

    // --deglorpify mode: just print translated Python, don't execute
    bool dump_only = false;
    std::string filepath;
    if (std::strcmp(argv[1], "--deglorpify") == 0) {
        if (argc < 3) {
            std::cerr << "Error: --deglorpify needs a file argument.\n";
            return 1;
        }
        dump_only = true;
        filepath = argv[2];
    } else {
        filepath = argv[1];
    }

    // Read .glp file
    std::ifstream file(filepath);
    if (!file.is_open()) {
        std::cerr << "Error: Cannot open '" << filepath << "'\n";
        return 1;
    }
    std::ostringstream buf;
    buf << file.rdbuf();
    std::string glorpo_code = buf.str();

    // Deglorpify
    std::string python_code = deglorpify(glorpo_code);

    if (dump_only) {
        std::cout << python_code;
        return 0;
    }

    if (python_code.find("\"__glorpmain__\"") != std::string::npos ||
        python_code.find("'__glorpmain__'") != std::string::npos) {
        python_code = "__name__ = \"__glorpmain__\"\n" + python_code;
    }

    // Write to temp file
    auto tmp_path = std::filesystem::temp_directory_path() / "glorpo_run_tmp.py";
    {
        std::ofstream tmp(tmp_path);
        if (!tmp.is_open()) {
            std::cerr << "Error: Cannot write temp file: " << tmp_path << "\n";
            return 1;
        }
        tmp << python_code;
    }

    // Run via Python
    std::string python = find_python();
    std::string cmd = python + " \"" + tmp_path.string() + "\"";

    // Forward extra args to the script
    for (int a = 2; a < argc; ++a) {
        cmd += " ";
        cmd += argv[a];
    }

    int ret = std::system(cmd.c_str());

    // Cleanup
    std::filesystem::remove(tmp_path);

    return ret;
}
