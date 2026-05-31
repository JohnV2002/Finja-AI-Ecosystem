/**
 * Glorpo True Interpreter Entrypoint
 * ==================================
 * Runs the standalone Glorpo lexer, parser, and interpreter pipeline.
 *
 * Main Responsibilities:
 * - Read .glp files from disk.
 * - Tokenize, parse, and execute Glorpo source.
 * - Optionally dump lexer output for debugging.
 *
 * Side Effects:
 * - Reads source files from disk.
 * - Writes interpreter output and errors to stdout/stderr.
 */
#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include <stdexcept>

#include "lexer.hpp"
#include "parser.hpp"
#include "interpreter.hpp"

static std::string read_file(const std::string& path) {
    std::ifstream f(path);
    if (!f.is_open())
        throw std::runtime_error("Cannot open file: " + path);
    std::ostringstream buf;
    buf << f.rdbuf();
    return buf.str();
}

static void print_usage(const char* exe) {
    std::cerr << "Glorpo True Interpreter v1.0\n"
              << "Usage:\n"
              << "  " << exe << " <file.glp>             run a script\n"
              << "  " << exe << " --tokens <file.glp>    dump lexer output\n"
              << "\nGlorpo is pain.\n";
}

int main(int argc, char* argv[]) {
    if (argc < 2) { print_usage(argv[0]); return 1; }

    bool dump_tokens = false;
    std::string filepath;

    if (std::string(argv[1]) == "--tokens") {
        if (argc < 3) { print_usage(argv[0]); return 1; }
        dump_tokens = true;
        filepath    = argv[2];
    } else {
        filepath = argv[1];
    }

    std::string source;
    try {
        source = read_file(filepath);
    } catch (const std::exception& e) {
        std::cerr << e.what() << "\n";
        return 1;
    }

    // -- Lex -----------------------------------------------------------------
    std::vector<Token> tokens;
    try {
        Lexer lexer(source);
        tokens = lexer.tokenize();
    } catch (const LexError& e) {
        std::cerr << "[LexError] " << e.what() << "\n";
        return 1;
    }

    if (dump_tokens) {
        for (auto& t : tokens) {
            std::cout << "  L" << t.line << ":C" << t.col
                      << "  type=" << (int)t.type
                      << "  val='" << t.value << "'\n";
        }
        return 0;
    }

    // -- Parse ----------------------------------------------------------------
    StmtList ast;
    try {
        Parser parser(std::move(tokens));
        ast = parser.parse();
    } catch (const ParseError& e) {
        std::cerr << "[ParseError] " << e.what() << "\n";
        return 1;
    }

    // -- Interpret ------------------------------------------------------------
    try {
        Interpreter interp;
        interp.exec(ast);
    } catch (const ReturnSignal&) {
        std::cerr << "[RuntimeError] glorpback outside function\n";
        return 1;
    } catch (const BreakSignal&) {
        std::cerr << "[RuntimeError] glorpsnap outside loop\n";
        return 1;
    } catch (const ContinueSignal&) {
        std::cerr << "[RuntimeError] glorpskip outside loop\n";
        return 1;
    } catch (const GlorpoException& e) {
        std::cerr << "[" << e.type_name << "] " << e.message << "\n";
        return 1;
    } catch (const RuntimeError& e) {
        std::cerr << "[RuntimeError] " << e.what() << "\n";
        return 1;
    } catch (const std::exception& e) {
        std::cerr << "[Error] " << e.what() << "\n";
        return 1;
    }

    return 0;
}
