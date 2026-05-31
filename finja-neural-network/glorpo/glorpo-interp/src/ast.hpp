/**
 * Ast Header
 * ==========
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
#include <memory>
#include <optional>

// Forward declarations
struct Expr;
struct Stmt;
using ExprPtr = std::unique_ptr<Expr>;
using StmtPtr = std::unique_ptr<Stmt>;
using ExprList = std::vector<ExprPtr>;
using StmtList = std::vector<StmtPtr>;

// --- Expressions -------------------------------------------------------------
struct Expr {
    int line = 0;
    virtual ~Expr() = default;
};

// Literals
struct IntLit    : Expr { long long value; };
struct FloatLit  : Expr { double value; };
struct StrLit    : Expr { std::string value; };
struct FStrLit   : Expr {
    // Parts: alternating raw text and sub-expressions
    struct Part { bool is_expr; std::string raw; ExprPtr expr; };
    std::vector<Part> parts;
};
struct BoolLit   : Expr { bool value; };
struct NoneLit   : Expr {};
struct EllipsisLit : Expr {};

// Name
struct NameExpr  : Expr { std::string name; };

// Unary / Binary
struct UnaryExpr : Expr {
    std::string op;
    ExprPtr     operand;
};
struct BinaryExpr : Expr {
    std::string op;
    ExprPtr     left, right;
};

// Comparison chain: left op1 m1 op2 m2 ...
struct CompareExpr : Expr {
    ExprPtr left;
    std::vector<std::string> ops;
    ExprList comparators;
};

// Boolean ops
struct BoolOpExpr : Expr {
    std::string op;  // "and" or "or"
    ExprList    values;
};

// Attribute access: obj.attr
struct AttrExpr : Expr {
    ExprPtr     obj;
    std::string attr;
};

// Subscript: obj[key]
struct IndexExpr : Expr {
    ExprPtr obj, key;
};

// Slice: obj[start:stop:step]
struct SliceExpr : Expr {
    ExprPtr            obj;
    std::optional<ExprPtr> start, stop, step;
};

// Call: func(args, *args, kw=val, **kwargs)
struct CallArg {
    std::string name;   // empty = positional, "*" = starred, "**" = double-starred
    ExprPtr     value;
};
struct CallExpr : Expr {
    ExprPtr              callee;
    std::vector<CallArg> args;
};

// Lambda: lambda params: body
struct LambdaExpr : Expr {
    std::vector<std::string> params;
    ExprPtr                  body;
};

// Ternary: value if cond else alt
struct IfExpr : Expr {
    ExprPtr value, cond, alt;
};

// Containers
struct ListExpr  : Expr { ExprList elements; };
struct TupleExpr : Expr { ExprList elements; };
struct SetExpr   : Expr { ExprList elements; };
struct DictExpr  : Expr {
    ExprList keys, values;   // keys[i] == nullptr -> **unpacking
};

// Comprehension
struct Comprehension {
    ExprPtr              target;
    ExprPtr              iter;
    std::vector<ExprPtr> ifs;
    bool                 is_async = false;
};
struct ListComp  : Expr { ExprPtr elt; std::vector<Comprehension> comps; };
struct SetComp   : Expr { ExprPtr elt; std::vector<Comprehension> comps; };
struct DictComp  : Expr { ExprPtr key, value; std::vector<Comprehension> comps; };
struct GeneratorExpr : Expr { ExprPtr elt; std::vector<Comprehension> comps; };

// Yield
struct YieldExpr      : Expr { std::optional<ExprPtr> value; };
struct YieldFromExpr  : Expr { ExprPtr value; };

// Await
struct AwaitExpr : Expr { ExprPtr value; };

// --- Statements --------------------------------------------------------------
struct Stmt {
    int line = 0;
    virtual ~Stmt() = default;
};

// Expression statement
struct ExprStmt : Stmt { ExprPtr expr; };

// Assignment
struct AssignStmt : Stmt {
    ExprList targets;   // a = b = expr  (multiple targets)
    ExprPtr  value;
};

// Augmented assignment: x += 1
struct AugAssignStmt : Stmt {
    ExprPtr     target;
    std::string op;
    ExprPtr     value;
};

// Annotated assignment: x: int = 1
struct AnnAssignStmt : Stmt {
    ExprPtr target, annotation;
    std::optional<ExprPtr> value;
};

// Delete
struct DelStmt : Stmt { ExprList targets; };

// Return
struct ReturnStmt : Stmt { std::optional<ExprPtr> value; };

// Raise
struct RaiseStmt : Stmt {
    std::optional<ExprPtr> exc;
    std::optional<ExprPtr> cause;
};

// Assert
struct AssertStmt : Stmt {
    ExprPtr test;
    std::optional<ExprPtr> msg;
};

// Pass / Break / Continue
struct PassStmt     : Stmt {};
struct BreakStmt    : Stmt {};
struct ContinueStmt : Stmt {};

// Global / Nonlocal
struct GlobalStmt   : Stmt { std::vector<std::string> names; };
struct NonlocalStmt : Stmt { std::vector<std::string> names; };

// Import
struct ImportStmt : Stmt {
    struct Alias { std::string name, asname; };
    std::vector<Alias> names;
};
struct ImportFromStmt : Stmt {
    std::string module;
    struct Alias { std::string name, asname; };
    std::vector<Alias> names;
    int level = 0;  // dots for relative import
};

// If statement
struct IfStmt : Stmt {
    ExprPtr  test;
    StmtList body;
    std::vector<std::pair<ExprPtr, StmtList>> elifs;
    StmtList orelse;
};

// While
struct WhileStmt : Stmt {
    ExprPtr  test;
    StmtList body;
    StmtList orelse;
};

// For
struct ForStmt : Stmt {
    ExprPtr  target;
    ExprPtr  iter;
    StmtList body;
    StmtList orelse;
    bool     is_async = false;
};

struct MatchCase {
    std::optional<ExprPtr> pattern; // empty = wildcard "_"
    StmtList body;
};
struct MatchStmt : Stmt {
    ExprPtr subject;
    std::vector<MatchCase> cases;
};

// With
struct WithItem { ExprPtr ctx; std::optional<ExprPtr> var; };
struct WithStmt : Stmt {
    std::vector<WithItem> items;
    StmtList              body;
    bool                  is_async = false;
};

// Try / Except
struct ExceptHandler {
    std::optional<ExprPtr>     type;
    std::string                name;
    StmtList                   body;
};
struct TryStmt : Stmt {
    StmtList                   body;
    std::vector<ExceptHandler> handlers;
    StmtList                   orelse;
    StmtList                   finalbody;
};

// Function definition
struct FuncParam {
    std::string            name;
    std::optional<ExprPtr> annotation;
    std::optional<ExprPtr> default_val;
    bool                   is_star    = false;  // *args
    bool                   is_dstar   = false;  // **kwargs
    bool                   kw_only    = false;  // after *
};
struct FuncDef : Stmt {
    std::string              name;
    std::vector<FuncParam>   params;
    StmtList                 body;
    std::optional<ExprPtr>   return_annotation;
    std::vector<ExprPtr>     decorators;
    bool                     is_async = false;
};

// Class definition
struct ClassDef : Stmt {
    std::string          name;
    ExprList             bases;
    StmtList             body;
    std::vector<ExprPtr> decorators;
};
