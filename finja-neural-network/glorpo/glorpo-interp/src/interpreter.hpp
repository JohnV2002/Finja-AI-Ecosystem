/**
 * Interpreter Header
 * ==================
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
#include "ast.hpp"
#include "value.hpp"
#include "environment.hpp"
#include <memory>

class Interpreter {
public:
    Interpreter();
    void exec(const StmtList& stmts);           // run a list of statements

private:
    Environment::EnvPtr env_;                   // current scope
    Environment::EnvPtr globals_;               // global scope (for builtins)

    // -- Statement execution ---------------------------------------------------
    void exec_stmt(const Stmt& s);
    void exec_block(const StmtList& stmts);

    void exec_expr_stmt(const ExprStmt& s);
    void exec_assign(const AssignStmt& s);
    void exec_aug_assign(const AugAssignStmt& s);
    void exec_ann_assign(const AnnAssignStmt& s);
    void exec_if(const IfStmt& s);
    void exec_while(const WhileStmt& s);
    void exec_for(const ForStmt& s);
    void exec_match(const MatchStmt& s);
    void exec_try(const TryStmt& s);
    void exec_with(const WithStmt& s);
    void exec_funcdef(const FuncDef& s);
    void exec_classdef(const ClassDef& s);
    void exec_import(const ImportStmt& s);
    void exec_import_from(const ImportFromStmt& s);
    void exec_global(const GlobalStmt& s);
    void exec_nonlocal(const NonlocalStmt& s);
    void exec_del(const DelStmt& s);

    // -- Expression evaluation -------------------------------------------------
    ValuePtr eval(const Expr& e);
    ValuePtr eval_int_lit(const IntLit& e);
    ValuePtr eval_float_lit(const FloatLit& e);
    ValuePtr eval_str_lit(const StrLit& e);
    ValuePtr eval_fstr_lit(const FStrLit& e);
    ValuePtr eval_name(const NameExpr& e);
    ValuePtr eval_unary(const UnaryExpr& e);
    ValuePtr eval_binary(const BinaryExpr& e);
    ValuePtr eval_compare(const CompareExpr& e);
    ValuePtr eval_bool_op(const BoolOpExpr& e);
    ValuePtr eval_if_expr(const IfExpr& e);
    ValuePtr eval_attr(const AttrExpr& e);
    ValuePtr eval_index(const IndexExpr& e);
    ValuePtr eval_call(const CallExpr& e);
    ValuePtr eval_list(const ListExpr& e);
    ValuePtr eval_tuple(const TupleExpr& e);
    ValuePtr eval_dict(const DictExpr& e);
    ValuePtr eval_set(const SetExpr& e);
    ValuePtr eval_lambda(const LambdaExpr& e);

    // -- Call dispatch ---------------------------------------------------------
    ValuePtr call_value(ValuePtr callee, ValueList args, int line);
    ValuePtr call_function(const GlorpoFunction& fn, ValueList args, int line);
    ValuePtr call_class(const GlorpoClass& klass, ValueList args, int line);

    // -- Assignment helpers ----------------------------------------------------
    void assign_target(const Expr& target, ValuePtr val);

    // -- Iterator protocol -----------------------------------------------------
    ValuePtr   make_iter(ValuePtr obj);
    ValuePtr   iter_next(ValuePtr it, bool& done);

    // -- Attribute / item access -----------------------------------------------
    ValuePtr   get_attr(ValuePtr obj, const std::string& name, int line);
    void       set_attr(ValuePtr obj, const std::string& name, ValuePtr val, int line);
    ValuePtr   get_item(ValuePtr obj, ValuePtr key, int line);
    void       set_item(ValuePtr obj, ValuePtr key, ValuePtr val, int line);

    // -- Arithmetic helpers ----------------------------------------------------
    ValuePtr   arith(const std::string& op, ValuePtr l, ValuePtr r, int line);

    // -- Builtins registration -------------------------------------------------
    void register_builtins();

    // -- Global tracking for `global` keyword ---------------------------------
    std::unordered_map<std::string, Environment*> global_vars_;
};
