/**
 * Glorpo Interpreter Implementation
 * =================================
 * Executes parsed Glorpo AST nodes.
 *
 * Main Responsibilities:
 * - Evaluate expressions and statements.
 * - Manage runtime environments and values.
 * - Provide built-in behavior for Glorpo programs.
 *
 * Side Effects:
 * - Writes program output to stdout.
 * - Throws runtime errors for invalid execution.
 */
#include "interpreter.hpp"
#include "lexer.hpp"
#include "parser.hpp"
#include <algorithm>
#include <cctype>
#include <cstdint>
#include <cstdlib>
#include <cmath>
#include <iostream>
#include <sstream>
#include <utility>

namespace {
std::string display(ValuePtr v) {
    if (!v) return "None";
    if (v->kind == Value::Kind::Str) return v->s_val;
    return v->repr();
}

double as_number(ValuePtr v, int line) {
    if (v->kind == Value::Kind::Int) return static_cast<double>(v->i_val);
    if (v->kind == Value::Kind::Float) return v->f_val;
    throw RuntimeError("expected number, got " + v->type_name(), line);
}

bool is_int_pair(ValuePtr l, ValuePtr r) {
    return l->kind == Value::Kind::Int && r->kind == Value::Kind::Int;
}

long long as_int(ValuePtr v, int line) {
    if (v->kind == Value::Kind::Int) return v->i_val;
    if (v->kind == Value::Kind::Bool) return v->b_val ? 1 : 0;
    throw RuntimeError("expected int, got " + v->type_name(), line);
}

std::string as_text(ValuePtr v) {
    if (v->kind == Value::Kind::Str) return v->s_val;
    return display(v);
}

ValuePtr make_set(ValueList vals) {
    auto p = std::make_shared<Value>();
    p->kind = Value::Kind::Set;
    for (auto& v : vals) {
        bool exists = false;
        for (auto& cur : p->list_val) {
            if (cur->equals(*v)) {
                exists = true;
                break;
            }
        }
        if (!exists) p->list_val.push_back(v);
    }
    return p;
}

ValuePtr make_function_value(const std::string& name, void* ast, Environment* closure = nullptr, ValueList bound = {}) {
    auto v = std::make_shared<Value>();
    v->kind = Value::Kind::Function;
    v->func = std::make_shared<GlorpoFunction>();
    v->func->name = name;
    v->func->func_ast = ast;
    v->func->closure = closure;
    v->func->bound_args = std::move(bound);
    return v;
}

ValuePtr make_class_value(std::shared_ptr<GlorpoClass> klass) {
    auto v = std::make_shared<Value>();
    v->kind = Value::Kind::Class;
    v->klass = std::move(klass);
    return v;
}

ValuePtr make_instance_value(std::shared_ptr<GlorpoClass> klass) {
    auto v = std::make_shared<Value>();
    v->kind = Value::Kind::Instance;
    v->obj = std::make_shared<GlorpoObject>();
    v->obj->klass = std::move(klass);
    return v;
}
}

Interpreter::Interpreter() {
    globals_ = Environment::make();
    env_ = globals_;
    register_builtins();
}

void Interpreter::exec(const StmtList& stmts) {
    exec_block(stmts);
}

void Interpreter::exec_block(const StmtList& stmts) {
    for (auto& stmt : stmts) exec_stmt(*stmt);
}

void Interpreter::exec_stmt(const Stmt& s) {
    if (auto p = dynamic_cast<const ExprStmt*>(&s)) return exec_expr_stmt(*p);
    if (auto p = dynamic_cast<const AssignStmt*>(&s)) return exec_assign(*p);
    if (auto p = dynamic_cast<const AugAssignStmt*>(&s)) return exec_aug_assign(*p);
    if (auto p = dynamic_cast<const AnnAssignStmt*>(&s)) return exec_ann_assign(*p);
    if (auto p = dynamic_cast<const IfStmt*>(&s)) return exec_if(*p);
    if (auto p = dynamic_cast<const WhileStmt*>(&s)) return exec_while(*p);
    if (auto p = dynamic_cast<const ForStmt*>(&s)) return exec_for(*p);
    if (auto p = dynamic_cast<const MatchStmt*>(&s)) return exec_match(*p);
    if (auto p = dynamic_cast<const TryStmt*>(&s)) return exec_try(*p);
    if (auto p = dynamic_cast<const WithStmt*>(&s)) return exec_with(*p);
    if (auto p = dynamic_cast<const FuncDef*>(&s)) return exec_funcdef(*p);
    if (auto p = dynamic_cast<const ClassDef*>(&s)) return exec_classdef(*p);
    if (auto p = dynamic_cast<const AssertStmt*>(&s)) {
        if (!eval(*p->test)->is_truthy()) {
            std::string msg = p->msg ? display(eval(*p->msg.value())) : "assertion failed";
            throw RuntimeError(msg, s.line);
        }
        return;
    }
    if (auto p = dynamic_cast<const RaiseStmt*>(&s)) {
        std::string msg = p->exc ? display(eval(*p->exc.value())) : "raised exception";
        throw RuntimeError(msg, s.line);
    }
    if (auto p = dynamic_cast<const ImportStmt*>(&s)) return exec_import(*p);
    if (auto p = dynamic_cast<const ImportFromStmt*>(&s)) return exec_import_from(*p);
    if (auto p = dynamic_cast<const GlobalStmt*>(&s)) return exec_global(*p);
    if (auto p = dynamic_cast<const NonlocalStmt*>(&s)) return exec_nonlocal(*p);
    if (auto p = dynamic_cast<const DelStmt*>(&s)) return exec_del(*p);
    if (dynamic_cast<const PassStmt*>(&s)) return;
    if (dynamic_cast<const BreakStmt*>(&s)) throw BreakSignal{};
    if (dynamic_cast<const ContinueStmt*>(&s)) throw ContinueSignal{};
    if (auto p = dynamic_cast<const ReturnStmt*>(&s)) {
        ValuePtr value = p->value ? eval(*p->value.value()) : Value::make_none();
        throw ReturnSignal{value};
    }
    throw RuntimeError("statement not supported yet", s.line);
}

void Interpreter::exec_expr_stmt(const ExprStmt& s) {
    eval(*s.expr);
}

void Interpreter::exec_assign(const AssignStmt& s) {
    ValuePtr value = eval(*s.value);
    for (auto& target : s.targets) assign_target(*target, value);
}

void Interpreter::exec_aug_assign(const AugAssignStmt& s) {
    ValuePtr current;
    if (auto n = dynamic_cast<const NameExpr*>(s.target.get())) current = env_->get(n->name);
    else if (auto a = dynamic_cast<const AttrExpr*>(s.target.get())) current = get_attr(eval(*a->obj), a->attr, s.line);
    else if (auto i = dynamic_cast<const IndexExpr*>(s.target.get())) current = get_item(eval(*i->obj), eval(*i->key), s.line);
    else throw RuntimeError("augmented assignment target not supported", s.line);

    std::string op = s.op;
    if (op == "+") op = "+";
    ValuePtr value = arith(op, current, eval(*s.value), s.line);
    assign_target(*s.target, value);
}
void Interpreter::exec_ann_assign(const AnnAssignStmt&) { throw RuntimeError("annotated assignment not supported yet"); }

void Interpreter::exec_if(const IfStmt& s) {
    if (eval(*s.test)->is_truthy()) {
        exec_block(s.body);
        return;
    }
    for (auto& [cond, body] : s.elifs) {
        if (eval(*cond)->is_truthy()) {
            exec_block(body);
            return;
        }
    }
    exec_block(s.orelse);
}

void Interpreter::exec_while(const WhileStmt& s) {
    while (eval(*s.test)->is_truthy()) {
        try {
            exec_block(s.body);
        } catch (const ContinueSignal&) {
            continue;
        } catch (const BreakSignal&) {
            return;
        }
    }
}

void Interpreter::exec_for(const ForStmt& s) {
    ValuePtr iterable = eval(*s.iter);
    if (iterable->kind != Value::Kind::List && iterable->kind != Value::Kind::Tuple) {
        throw RuntimeError("for loop expected list/tuple/range", s.line);
    }
    for (auto& item : iterable->list_val) {
        assign_target(*s.target, item);
        try {
            exec_block(s.body);
        } catch (const ContinueSignal&) {
            continue;
        } catch (const BreakSignal&) {
            return;
        }
    }
}

void Interpreter::exec_match(const MatchStmt& s) {
    ValuePtr subject = eval(*s.subject);
    for (const auto& c : s.cases) {
        if (!c.pattern || subject->equals(*eval(*c.pattern.value()))) {
            exec_block(c.body);
            return;
        }
    }
}

void Interpreter::exec_try(const TryStmt& s) {
    bool failed = false;
    try {
        exec_block(s.body);
    } catch (const RuntimeError& err) {
        failed = true;
        bool handled = false;
        for (const auto& handler : s.handlers) {
            auto previous = env_;
            env_ = Environment::make(previous);
            if (!handler.name.empty()) env_->set(handler.name, Value::make_str(err.what()));
            try {
                exec_block(handler.body);
                handled = true;
                env_ = previous;
                break;
            } catch (...) {
                env_ = previous;
                throw;
            }
        }
        if (!handled && s.handlers.empty()) {
            try { exec_block(s.finalbody); } catch (...) { throw; }
            throw;
        }
        if (!handled) throw;
    }
    if (!failed) exec_block(s.orelse);
    exec_block(s.finalbody);
}

void Interpreter::exec_with(const WithStmt& s) {
    for (const auto& item : s.items) {
        ValuePtr ctx = eval(*item.ctx);
        if (item.var) assign_target(*item.var.value(), ctx);
    }
    exec_block(s.body);
}
void Interpreter::exec_funcdef(const FuncDef& s) {
    env_->set(s.name, make_function_value(s.name, const_cast<FuncDef*>(&s), env_.get()));
}

void Interpreter::exec_classdef(const ClassDef& s) {
    auto klass = std::make_shared<GlorpoClass>();
    klass->name = s.name;

    for (auto& base_expr : s.bases) {
        ValuePtr base = eval(*base_expr);
        if (base->kind != Value::Kind::Class || !base->klass) {
            throw RuntimeError("class base must be a class", s.line);
        }
        klass->bases.push_back(base->klass);
    }

    for (auto& stmt : s.body) {
        if (auto fn = dynamic_cast<const FuncDef*>(stmt.get())) {
            klass->methods[fn->name] = make_function_value(fn->name, const_cast<FuncDef*>(fn), globals_.get());
        } else if (!dynamic_cast<const PassStmt*>(stmt.get())) {
            throw RuntimeError("only methods are supported in glorpkin body", stmt->line);
        }
    }

    env_->set(s.name, make_class_value(std::move(klass)));
}
void Interpreter::exec_import(const ImportStmt& s) {
    for (const auto& alias : s.names) {
        auto mod = Value::make_dict();
        mod->dict_val["__name__"] = Value::make_str(alias.name);
        env_->set(alias.asname.empty() ? alias.name : alias.asname, mod);
    }
}
void Interpreter::exec_import_from(const ImportFromStmt& s) {
    for (const auto& alias : s.names) {
        env_->set(alias.asname.empty() ? alias.name : alias.asname, Value::make_none());
    }
}
void Interpreter::exec_global(const GlobalStmt&) {}
void Interpreter::exec_nonlocal(const NonlocalStmt&) { throw RuntimeError("nonlocal not supported yet"); }
void Interpreter::exec_del(const DelStmt& s) {
    for (auto& target : s.targets) {
        if (auto n = dynamic_cast<const NameExpr*>(target.get())) {
            if (!env_->erase(n->name)) throw RuntimeError("NameError: name '" + n->name + "' is not defined", target->line);
        } else if (auto a = dynamic_cast<const AttrExpr*>(target.get())) {
            auto obj = eval(*a->obj);
            if (obj->kind != Value::Kind::Instance || !obj->obj || !obj->obj->attrs.erase(a->attr)) {
                throw RuntimeError("cannot delete attribute '" + a->attr + "'", target->line);
            }
        } else {
            throw RuntimeError("delete target not supported", target->line);
        }
    }
}

ValuePtr Interpreter::eval(const Expr& e) {
    if (auto p = dynamic_cast<const IntLit*>(&e)) return eval_int_lit(*p);
    if (auto p = dynamic_cast<const FloatLit*>(&e)) return eval_float_lit(*p);
    if (auto p = dynamic_cast<const StrLit*>(&e)) return eval_str_lit(*p);
    if (auto p = dynamic_cast<const FStrLit*>(&e)) return eval_fstr_lit(*p);
    if (auto p = dynamic_cast<const BoolLit*>(&e)) return Value::make_bool(p->value);
    if (dynamic_cast<const NoneLit*>(&e)) return Value::make_none();
    if (auto p = dynamic_cast<const NameExpr*>(&e)) return eval_name(*p);
    if (auto p = dynamic_cast<const UnaryExpr*>(&e)) return eval_unary(*p);
    if (auto p = dynamic_cast<const BinaryExpr*>(&e)) return eval_binary(*p);
    if (auto p = dynamic_cast<const CompareExpr*>(&e)) return eval_compare(*p);
    if (auto p = dynamic_cast<const BoolOpExpr*>(&e)) return eval_bool_op(*p);
    if (auto p = dynamic_cast<const IfExpr*>(&e)) return eval_if_expr(*p);
    if (auto p = dynamic_cast<const AttrExpr*>(&e)) return eval_attr(*p);
    if (auto p = dynamic_cast<const IndexExpr*>(&e)) return eval_index(*p);
    if (auto p = dynamic_cast<const CallExpr*>(&e)) return eval_call(*p);
    if (auto p = dynamic_cast<const ListExpr*>(&e)) return eval_list(*p);
    if (auto p = dynamic_cast<const TupleExpr*>(&e)) return eval_tuple(*p);
    if (auto p = dynamic_cast<const DictExpr*>(&e)) return eval_dict(*p);
    if (auto p = dynamic_cast<const SetExpr*>(&e)) return eval_set(*p);
    if (auto p = dynamic_cast<const LambdaExpr*>(&e)) return eval_lambda(*p);
    throw RuntimeError("expression not supported yet", e.line);
}

ValuePtr Interpreter::eval_int_lit(const IntLit& e) { return Value::make_int(e.value); }
ValuePtr Interpreter::eval_float_lit(const FloatLit& e) { return Value::make_float(e.value); }
ValuePtr Interpreter::eval_str_lit(const StrLit& e) { return Value::make_str(e.value); }
ValuePtr Interpreter::eval_fstr_lit(const FStrLit& e) {
    if (e.parts.empty()) return Value::make_str("");
    const std::string& raw = e.parts[0].raw;
    std::string out;
    for (size_t i = 0; i < raw.size(); ++i) {
        if (raw[i] == '{') {
            if (i + 1 < raw.size() && raw[i + 1] == '{') {
                out += '{';
                ++i;
                continue;
            }
            size_t end = raw.find('}', i + 1);
            if (end == std::string::npos) throw RuntimeError("unterminated f-string expression", e.line);
            std::string expr_src = raw.substr(i + 1, end - i - 1);
            Lexer lexer(expr_src);
            Parser parser(lexer.tokenize());
            auto stmts = parser.parse();
            if (stmts.size() != 1) throw RuntimeError("invalid f-string expression", e.line);
            auto expr_stmt = dynamic_cast<ExprStmt*>(stmts[0].get());
            if (!expr_stmt) throw RuntimeError("invalid f-string expression", e.line);
            out += display(eval(*expr_stmt->expr));
            i = end;
        } else if (raw[i] == '}' && i + 1 < raw.size() && raw[i + 1] == '}') {
            out += '}';
            ++i;
        } else {
            out += raw[i];
        }
    }
    return Value::make_str(out);
}
ValuePtr Interpreter::eval_name(const NameExpr& e) { return env_->get(e.name); }

ValuePtr Interpreter::eval_unary(const UnaryExpr& e) {
    ValuePtr v = eval(*e.operand);
    if (e.op == "not") return Value::make_bool(!v->is_truthy());
    if (e.op == "+") return v;
    if (e.op == "-") {
        if (v->kind == Value::Kind::Int) return Value::make_int(-v->i_val);
        if (v->kind == Value::Kind::Float) return Value::make_float(-v->f_val);
    }
    if (e.op == "~") return Value::make_int(~as_int(v, e.line));
    throw RuntimeError("unsupported unary operator " + e.op, e.line);
}

ValuePtr Interpreter::eval_binary(const BinaryExpr& e) {
    ValuePtr l = eval(*e.left);
    ValuePtr r = eval(*e.right);
    return arith(e.op, l, r, e.line);
}

ValuePtr Interpreter::eval_compare(const CompareExpr& e) {
    ValuePtr left = eval(*e.left);
    for (size_t i = 0; i < e.ops.size(); ++i) {
        ValuePtr right = eval(*e.comparators[i]);
        const std::string& op = e.ops[i];
        bool ok = false;
        if (op == "==" || op == "=") ok = left->equals(*right);
        else if (op == "!=") ok = !left->equals(*right);
        else if (op == "<") ok = left->less_than(*right);
        else if (op == ">") ok = right->less_than(*left);
        else if (op == "<=") ok = left->less_than(*right) || left->equals(*right);
        else if (op == ">=") ok = right->less_than(*left) || left->equals(*right);
        else if (op == "in") {
            if (right->kind == Value::Kind::Str) ok = left->kind == Value::Kind::Str && right->s_val.find(left->s_val) != std::string::npos;
            else if (right->kind == Value::Kind::List || right->kind == Value::Kind::Tuple || right->kind == Value::Kind::Set) {
                ok = std::any_of(right->list_val.begin(), right->list_val.end(), [&](const ValuePtr& item) { return left->equals(*item); });
            } else if (right->kind == Value::Kind::Dict) {
                ok = right->dict_val.count(left->to_dict_key()) > 0;
            }
        }
        else if (op == "is") ok = left.get() == right.get() || (left->kind == Value::Kind::NoneType && right->kind == Value::Kind::NoneType);
        else throw RuntimeError("comparison not supported: " + op, e.line);
        if (!ok) return Value::make_bool(false);
        left = right;
    }
    return Value::make_bool(true);
}

ValuePtr Interpreter::eval_bool_op(const BoolOpExpr& e) {
    if (e.op == "and") {
        ValuePtr last = Value::make_bool(true);
        for (auto& item : e.values) {
            last = eval(*item);
            if (!last->is_truthy()) return last;
        }
        return last;
    }
    ValuePtr last = Value::make_bool(false);
    for (auto& item : e.values) {
        last = eval(*item);
        if (last->is_truthy()) return last;
    }
    return last;
}

ValuePtr Interpreter::eval_if_expr(const IfExpr& e) { return eval(*e.cond)->is_truthy() ? eval(*e.value) : eval(*e.alt); }
ValuePtr Interpreter::eval_attr(const AttrExpr& e) { return get_attr(eval(*e.obj), e.attr, e.line); }
ValuePtr Interpreter::eval_index(const IndexExpr& e) { return get_item(eval(*e.obj), eval(*e.key), e.line); }

ValuePtr Interpreter::eval_call(const CallExpr& e) {
    ValuePtr callee = eval(*e.callee);
    ValueList args;
    for (auto& arg : e.args) args.push_back(eval(*arg.value));
    return call_value(callee, std::move(args), e.line);
}

ValuePtr Interpreter::eval_list(const ListExpr& e) {
    ValueList vals;
    for (auto& item : e.elements) vals.push_back(eval(*item));
    return Value::make_list(std::move(vals));
}

ValuePtr Interpreter::eval_tuple(const TupleExpr& e) {
    ValueList vals;
    for (auto& item : e.elements) vals.push_back(eval(*item));
    return Value::make_tuple(std::move(vals));
}

ValuePtr Interpreter::eval_dict(const DictExpr& e) {
    auto d = Value::make_dict();
    for (size_t i = 0; i < e.keys.size(); ++i) {
        d->dict_val[eval(*e.keys[i])->to_dict_key()] = eval(*e.values[i]);
    }
    return d;
}
ValuePtr Interpreter::eval_set(const SetExpr& e) {
    ValueList vals;
    for (auto& item : e.elements) vals.push_back(eval(*item));
    return make_set(std::move(vals));
}
ValuePtr Interpreter::eval_lambda(const LambdaExpr& e) {
    return make_function_value("<lambda>", const_cast<LambdaExpr*>(&e), env_.get());
}

ValuePtr Interpreter::call_value(ValuePtr callee, ValueList args, int line) {
    if (callee->kind == Value::Kind::Builtin && callee->builtin) {
        return callee->builtin->fn(std::move(args));
    }
    if (callee->kind == Value::Kind::Function && callee->func) {
        return call_function(*callee->func, std::move(args), line);
    }
    if (callee->kind == Value::Kind::Class && callee->klass) {
        return call_class(*callee->klass, std::move(args), line);
    }
    throw RuntimeError("'" + callee->type_name() + "' object is not callable", line);
}

ValuePtr Interpreter::call_function(const GlorpoFunction& fn, ValueList args, int line) {
    ValueList actual = fn.bound_args;
    actual.insert(actual.end(), args.begin(), args.end());

    auto previous = env_;
    auto parent = globals_;
    if (fn.closure) {
        parent = static_cast<Environment*>(fn.closure)->shared_from_this();
    }
    env_ = Environment::make(parent);
    try {
        if (auto def = static_cast<FuncDef*>(fn.func_ast)) {
            if (fn.name != "<lambda>") {
                if (actual.size() > def->params.size()) {
                    throw RuntimeError("too many arguments for " + fn.name, line);
                }
                for (size_t i = 0; i < def->params.size(); ++i) {
                    if (i < actual.size()) {
                        env_->set(def->params[i].name, actual[i]);
                    } else if (def->params[i].default_val) {
                        env_->set(def->params[i].name, eval(*def->params[i].default_val.value()));
                    } else {
                        throw RuntimeError("missing argument '" + def->params[i].name + "'", line);
                    }
                }
                try {
                    exec_block(def->body);
                } catch (const ReturnSignal& ret) {
                    env_ = previous;
                    return ret.value ? ret.value : Value::make_none();
                }
                env_ = previous;
                return Value::make_none();
            }
        }

        auto lambda = static_cast<LambdaExpr*>(fn.func_ast);
        if (!lambda) throw RuntimeError("invalid function object", line);
        if (actual.size() != lambda->params.size()) throw RuntimeError("lambda argument count mismatch", line);
        for (size_t i = 0; i < lambda->params.size(); ++i) env_->set(lambda->params[i], actual[i]);
        ValuePtr result = eval(*lambda->body);
        env_ = previous;
        return result;
    } catch (...) {
        env_ = previous;
        throw;
    }
}

ValuePtr Interpreter::call_class(const GlorpoClass& klass, ValueList args, int line) {
    auto instance = make_instance_value(std::make_shared<GlorpoClass>(klass));
    auto init = klass.methods.find("__glorpbirth__");
    if (init != klass.methods.end()) {
        ValueList bound{instance};
        auto init_func = *init->second->func;
        init_func.bound_args = std::move(bound);
        call_function(init_func, std::move(args), line);
    }
    return instance;
}

void Interpreter::assign_target(const Expr& target, ValuePtr val) {
    if (auto n = dynamic_cast<const NameExpr*>(&target)) {
        env_->assign(n->name, std::move(val));
        return;
    }
    if (auto t = dynamic_cast<const TupleExpr*>(&target)) {
        if (val->kind != Value::Kind::List && val->kind != Value::Kind::Tuple) {
            throw RuntimeError("cannot unpack non-iterable " + val->type_name(), target.line);
        }
        if (t->elements.size() != val->list_val.size()) {
            throw RuntimeError("unpack count mismatch", target.line);
        }
        for (size_t i = 0; i < t->elements.size(); ++i) assign_target(*t->elements[i], val->list_val[i]);
        return;
    }
    if (auto l = dynamic_cast<const ListExpr*>(&target)) {
        if (val->kind != Value::Kind::List && val->kind != Value::Kind::Tuple) {
            throw RuntimeError("cannot unpack non-iterable " + val->type_name(), target.line);
        }
        if (l->elements.size() != val->list_val.size()) {
            throw RuntimeError("unpack count mismatch", target.line);
        }
        for (size_t i = 0; i < l->elements.size(); ++i) assign_target(*l->elements[i], val->list_val[i]);
        return;
    }
    if (auto a = dynamic_cast<const AttrExpr*>(&target)) {
        set_attr(eval(*a->obj), a->attr, std::move(val), target.line);
        return;
    }
    if (auto i = dynamic_cast<const IndexExpr*>(&target)) {
        set_item(eval(*i->obj), eval(*i->key), std::move(val), target.line);
        return;
    }
    throw RuntimeError("assignment target not supported", target.line);
}

ValuePtr Interpreter::make_iter(ValuePtr obj) { return Value::make_iterator(std::move(obj)); }
ValuePtr Interpreter::iter_next(ValuePtr it, bool& done) {
    done = true;
    if (!it || it->kind != Value::Kind::Iterator || !it->iter_source) return Value::make_none();
    auto src = it->iter_source;
    if (it->iter_idx < src->list_val.size()) {
        done = false;
        return src->list_val[it->iter_idx++];
    }
    return Value::make_none();
}

ValuePtr Interpreter::get_attr(ValuePtr obj, const std::string& name, int line) {
    if (obj->kind == Value::Kind::Instance && obj->obj) {
        auto attr = obj->obj->attrs.find(name);
        if (attr != obj->obj->attrs.end()) return attr->second;
        auto meth = obj->obj->klass->methods.find(name);
        if (meth != obj->obj->klass->methods.end()) {
            ValueList bound{obj};
            return make_function_value(
                name,
                meth->second->func->func_ast,
                static_cast<Environment*>(meth->second->func->closure),
                std::move(bound)
            );
        }
    }
    if (obj->kind == Value::Kind::List && name == "glorpshove") {
        return Value::make_builtin("glorpshove", [obj](ValueList args) -> ValuePtr {
            if (args.size() != 1) throw RuntimeError("glorpshove expects 1 argument");
            obj->list_val.push_back(args[0]);
            return Value::make_none();
        });
    }
    if (obj->kind == Value::Kind::List && name == "glorpyoink") {
        return Value::make_builtin("glorpyoink", [obj](ValueList args) -> ValuePtr {
            if (obj->list_val.empty()) throw RuntimeError("pop from empty list");
            long long idx = args.empty() ? static_cast<long long>(obj->list_val.size()) - 1 : as_int(args[0], 0);
            if (idx < 0) idx += static_cast<long long>(obj->list_val.size());
            if (idx < 0 || static_cast<size_t>(idx) >= obj->list_val.size()) throw RuntimeError("pop index out of range");
            auto value = obj->list_val[static_cast<size_t>(idx)];
            obj->list_val.erase(obj->list_val.begin() + idx);
            return value;
        });
    }
    if (obj->kind == Value::Kind::Dict) {
        if (name == "glorpkeys") return Value::make_builtin("glorpkeys", [obj](ValueList) -> ValuePtr {
            ValueList out;
            for (auto& [k, _] : obj->dict_val) out.push_back(Value::make_str(k));
            return Value::make_list(std::move(out));
        });
        if (name == "glorpvals") return Value::make_builtin("glorpvals", [obj](ValueList) -> ValuePtr {
            ValueList out;
            for (auto& [_, v] : obj->dict_val) out.push_back(v);
            return Value::make_list(std::move(out));
        });
        if (name == "glorpstuff") return Value::make_builtin("glorpstuff", [obj](ValueList) -> ValuePtr {
            ValueList out;
            for (auto& [k, v] : obj->dict_val) {
                ValueList pair{Value::make_str(k), v};
                out.push_back(Value::make_tuple(std::move(pair)));
            }
            return Value::make_list(std::move(out));
        });
    }
    if (obj->kind == Value::Kind::Str) {
        if (name == "glorpchop") return Value::make_builtin("glorpchop", [obj](ValueList args) -> ValuePtr {
            std::string sep = args.empty() || args[0]->kind == Value::Kind::NoneType ? " " : as_text(args[0]);
            ValueList out;
            size_t start = 0;
            while (start <= obj->s_val.size()) {
                size_t pos = obj->s_val.find(sep, start);
                std::string part = obj->s_val.substr(start, pos == std::string::npos ? std::string::npos : pos - start);
                if (!(sep == " " && part.empty())) out.push_back(Value::make_str(part));
                if (pos == std::string::npos) break;
                start = pos + sep.size();
            }
            return Value::make_list(std::move(out));
        });
        if (name == "glorptrim") return Value::make_builtin("glorptrim", [obj](ValueList) -> ValuePtr {
            const auto first = obj->s_val.find_first_not_of(" \t\r\n");
            if (first == std::string::npos) return Value::make_str("");
            const auto last = obj->s_val.find_last_not_of(" \t\r\n");
            return Value::make_str(obj->s_val.substr(first, last - first + 1));
        });
        if (name == "glorpswap") return Value::make_builtin("glorpswap", [obj](ValueList args) -> ValuePtr {
            if (args.size() < 2) throw RuntimeError("replace expects old and new");
            std::string out = obj->s_val, from = as_text(args[0]), to = as_text(args[1]);
            if (from.empty()) return Value::make_str(out);
            size_t pos = 0;
            while ((pos = out.find(from, pos)) != std::string::npos) {
                out.replace(pos, from.size(), to);
                pos += to.size();
            }
            return Value::make_str(out);
        });
        if (name == "glorpscream") return Value::make_builtin("glorpscream", [obj](ValueList) -> ValuePtr {
            std::string out = obj->s_val;
            std::transform(out.begin(), out.end(), out.begin(), [](unsigned char c) { return static_cast<char>(std::toupper(c)); });
            return Value::make_str(out);
        });
        if (name == "glorpwhisper") return Value::make_builtin("glorpwhisper", [obj](ValueList) -> ValuePtr {
            std::string out = obj->s_val;
            std::transform(out.begin(), out.end(), out.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
            return Value::make_str(out);
        });
        if (name == "glorpbegin") return Value::make_builtin("glorpbegin", [obj](ValueList args) -> ValuePtr {
            if (args.empty()) throw RuntimeError("startswith expects prefix");
            std::string prefix = as_text(args[0]);
            return Value::make_bool(obj->s_val.rfind(prefix, 0) == 0);
        });
        if (name == "glorpend") return Value::make_builtin("glorpend", [obj](ValueList args) -> ValuePtr {
            if (args.empty()) throw RuntimeError("endswith expects suffix");
            std::string suffix = as_text(args[0]);
            return Value::make_bool(obj->s_val.size() >= suffix.size() && obj->s_val.compare(obj->s_val.size() - suffix.size(), suffix.size(), suffix) == 0);
        });
        if (name == "glorpseek" || name == "glorpwhere") return Value::make_builtin(name, [obj, name](ValueList args) -> ValuePtr {
            if (args.empty()) throw RuntimeError("find/index expects substring");
            size_t pos = obj->s_val.find(as_text(args[0]));
            if (pos == std::string::npos) {
                if (name == "glorpwhere") throw RuntimeError("substring not found");
                return Value::make_int(-1);
            }
            return Value::make_int(static_cast<long long>(pos));
        });
        if (name == "glorptally") return Value::make_builtin("glorptally", [obj](ValueList args) -> ValuePtr {
            if (args.empty()) throw RuntimeError("count expects substring");
            std::string needle = as_text(args[0]);
            long long count = 0;
            for (size_t pos = 0; (pos = obj->s_val.find(needle, pos)) != std::string::npos; pos += needle.size()) ++count;
            return Value::make_int(count);
        });
        if (name == "glorpglue") return Value::make_builtin("glorpglue", [obj](ValueList args) -> ValuePtr {
            if (args.empty() || (args[0]->kind != Value::Kind::List && args[0]->kind != Value::Kind::Tuple)) throw RuntimeError("join expects iterable");
            std::string out;
            for (size_t i = 0; i < args[0]->list_val.size(); ++i) {
                if (i) out += obj->s_val;
                out += as_text(args[0]->list_val[i]);
            }
            return Value::make_str(out);
        });
    }
    throw RuntimeError("'" + obj->type_name() + "' object has no attribute '" + name + "'", line);
}

void Interpreter::set_attr(ValuePtr obj, const std::string& name, ValuePtr val, int line) {
    if (obj->kind == Value::Kind::Instance && obj->obj) {
        obj->obj->attrs[name] = std::move(val);
        return;
    }
    throw RuntimeError("cannot set attribute '" + name + "' on " + obj->type_name(), line);
}

ValuePtr Interpreter::get_item(ValuePtr obj, ValuePtr key, int line) {
    if ((obj->kind == Value::Kind::List || obj->kind == Value::Kind::Tuple) && key->kind == Value::Kind::Int) {
        long long idx = key->i_val;
        if (idx < 0) idx += static_cast<long long>(obj->list_val.size());
        if (idx < 0 || static_cast<size_t>(idx) >= obj->list_val.size()) throw RuntimeError("index out of range", line);
        return obj->list_val[static_cast<size_t>(idx)];
    }
    if (obj->kind == Value::Kind::Dict) return obj->dict_val[key->to_dict_key()];
    throw RuntimeError("indexing not supported for " + obj->type_name(), line);
}

void Interpreter::set_item(ValuePtr obj, ValuePtr key, ValuePtr val, int line) {
    if (obj->kind == Value::Kind::List && key->kind == Value::Kind::Int) {
        long long idx = key->i_val;
        if (idx < 0) idx += static_cast<long long>(obj->list_val.size());
        if (idx < 0 || static_cast<size_t>(idx) >= obj->list_val.size()) throw RuntimeError("index out of range", line);
        obj->list_val[static_cast<size_t>(idx)] = std::move(val);
        return;
    }
    if (obj->kind == Value::Kind::Dict) {
        obj->dict_val[key->to_dict_key()] = std::move(val);
        return;
    }
    throw RuntimeError("item assignment not supported for " + obj->type_name(), line);
}

ValuePtr Interpreter::arith(const std::string& op, ValuePtr l, ValuePtr r, int line) {
    if (op == "+" && l->kind == Value::Kind::Str && r->kind == Value::Kind::Str) return Value::make_str(l->s_val + r->s_val);
    if (op == "+" && l->kind == Value::Kind::List && r->kind == Value::Kind::List) {
        ValueList out = l->list_val;
        out.insert(out.end(), r->list_val.begin(), r->list_val.end());
        return Value::make_list(std::move(out));
    }
    if (op == "+" && l->kind == Value::Kind::Tuple && r->kind == Value::Kind::Tuple) {
        ValueList out = l->list_val;
        out.insert(out.end(), r->list_val.begin(), r->list_val.end());
        return Value::make_tuple(std::move(out));
    }
    if (op == "*" && l->kind == Value::Kind::Str && r->kind == Value::Kind::Int) {
        std::string out;
        for (long long i = 0; i < r->i_val; ++i) out += l->s_val;
        return Value::make_str(out);
    }
    if (op == "*" && l->kind == Value::Kind::Int && r->kind == Value::Kind::Str) {
        std::string out;
        for (long long i = 0; i < l->i_val; ++i) out += r->s_val;
        return Value::make_str(out);
    }

    if (is_int_pair(l, r) && op != "/") {
        if (op == "+") return Value::make_int(l->i_val + r->i_val);
        if (op == "-") return Value::make_int(l->i_val - r->i_val);
        if (op == "*") return Value::make_int(l->i_val * r->i_val);
        if (op == "//") return Value::make_int(l->i_val / r->i_val);
        if (op == "%") return Value::make_int(l->i_val % r->i_val);
        if (op == "**") return Value::make_int(static_cast<long long>(std::pow(l->i_val, r->i_val)));
        if (op == "<<") return Value::make_int(l->i_val << r->i_val);
        if (op == ">>") return Value::make_int(l->i_val >> r->i_val);
        if (op == "&") return Value::make_int(l->i_val & r->i_val);
        if (op == "|") return Value::make_int(l->i_val | r->i_val);
        if (op == "^") return Value::make_int(l->i_val ^ r->i_val);
    }

    double a = as_number(l, line);
    double b = as_number(r, line);
    if (op == "+") return Value::make_float(a + b);
    if (op == "-") return Value::make_float(a - b);
    if (op == "*") return Value::make_float(a * b);
    if (op == "/") return Value::make_float(a / b);
    if (op == "//") return Value::make_float(std::floor(a / b));
    if (op == "%") return Value::make_float(std::fmod(a, b));
    if (op == "**") return Value::make_float(std::pow(a, b));
    throw RuntimeError("unsupported operator " + op, line);
}

void Interpreter::register_builtins() {
    globals_->set("__glorpname__", Value::make_str("__glorpmain__"));
    globals_->set("glorpvoid", Value::make_none());
    globals_->set("glorpnotyet", Value::make_none());

    auto print_fn = [](ValueList args) -> ValuePtr {
        for (size_t i = 0; i < args.size(); ++i) {
            if (i) std::cout << " ";
            std::cout << display(args[i]);
        }
        std::cout << "\n";
        return Value::make_none();
    };
    globals_->set("glorp", Value::make_builtin("glorp", print_fn));
    globals_->set("print", Value::make_builtin("print", print_fn));

    globals_->set("glorplist", Value::make_builtin("glorplist", [](ValueList args) -> ValuePtr {
        return Value::make_list(std::move(args));
    }));

    globals_->set("glorpsize", Value::make_builtin("glorpsize", [](ValueList args) -> ValuePtr {
        if (args.size() != 1) throw RuntimeError("glorpsize expects 1 argument");
        auto v = args[0];
        if (v->kind == Value::Kind::Str) return Value::make_int(static_cast<long long>(v->s_val.size()));
        if (v->kind == Value::Kind::List || v->kind == Value::Kind::Tuple || v->kind == Value::Kind::Set) return Value::make_int(static_cast<long long>(v->list_val.size()));
        if (v->kind == Value::Kind::Dict) return Value::make_int(static_cast<long long>(v->dict_val.size()));
        throw RuntimeError("object has no length");
    }));

    globals_->set("glorpchonk", Value::make_builtin("glorpchonk", [this](ValueList args) -> ValuePtr {
        if (args.empty()) throw RuntimeError("glorpchonk expects an iterable");
        auto seq = args[0];
        if (seq->kind != Value::Kind::List && seq->kind != Value::Kind::Tuple && seq->kind != Value::Kind::Set) {
            throw RuntimeError("glorpchonk expects list/tuple/set");
        }
        if (seq->list_val.empty()) throw RuntimeError("glorpchonk got empty iterable");
        if (args.size() == 1) {
            return *std::max_element(seq->list_val.begin(), seq->list_val.end(), [](const ValuePtr& a, const ValuePtr& b) {
                return a->less_than(*b);
            });
        }
        auto key_fn = args[1];
        if (key_fn->kind != Value::Kind::Function && key_fn->kind != Value::Kind::Builtin) {
            throw RuntimeError("glorpchonk key must be callable");
        }
        ValuePtr best = seq->list_val[0];
        ValuePtr best_key = nullptr;
        auto call_key = [&](ValuePtr item) -> ValuePtr {
            ValueList one{item};
            if (key_fn->kind == Value::Kind::Builtin) return key_fn->builtin->fn(std::move(one));
            auto fn = *key_fn->func;
            return this->call_function(fn, std::move(one), 0);
        };
        best_key = call_key(best);
        for (size_t i = 1; i < seq->list_val.size(); ++i) {
            ValuePtr candidate_key = call_key(seq->list_val[i]);
            if (best_key->less_than(*candidate_key)) {
                best = seq->list_val[i];
                best_key = candidate_key;
            }
        }
        return best;
    }));

    globals_->set("glorprange", Value::make_builtin("glorprange", [](ValueList args) -> ValuePtr {
        long long start = 0, stop = 0, step = 1;
        if (args.size() == 1) {
            stop = args[0]->i_val;
        } else if (args.size() == 2) {
            start = args[0]->i_val; stop = args[1]->i_val;
        } else if (args.size() == 3) {
            start = args[0]->i_val; stop = args[1]->i_val; step = args[2]->i_val;
        } else {
            throw RuntimeError("glorprange expects 1-3 arguments");
        }
        if (step == 0) throw RuntimeError("range step cannot be zero");
        ValueList vals;
        if (step > 0) {
            for (long long i = start; i < stop; i += step) vals.push_back(Value::make_int(i));
        } else {
            for (long long i = start; i > stop; i += step) vals.push_back(Value::make_int(i));
        }
        return Value::make_list(std::move(vals));
    }));

    globals_->set("glorptext", Value::make_builtin("glorptext", [](ValueList args) -> ValuePtr {
        if (args.empty()) return Value::make_str("");
        return Value::make_str(display(args[0]));
    }));
    globals_->set("glorpnum", Value::make_builtin("glorpnum", [](ValueList args) -> ValuePtr {
        if (args.empty()) return Value::make_int(0);
        if (args[0]->kind == Value::Kind::Int) return args[0];
        if (args[0]->kind == Value::Kind::Float) return Value::make_int(static_cast<long long>(args[0]->f_val));
        if (args[0]->kind == Value::Kind::Str) return Value::make_int(std::stoll(args[0]->s_val));
        throw RuntimeError("cannot convert to int");
    }));
    globals_->set("glorpfloat", Value::make_builtin("glorpfloat", [](ValueList args) -> ValuePtr {
        if (args.empty()) return Value::make_float(0);
        if (args[0]->kind == Value::Kind::Float) return args[0];
        if (args[0]->kind == Value::Kind::Int) return Value::make_float(static_cast<double>(args[0]->i_val));
        if (args[0]->kind == Value::Kind::Str) return Value::make_float(std::stod(args[0]->s_val));
        throw RuntimeError("cannot convert to float");
    }));
    globals_->set("glorpbool", Value::make_builtin("glorpbool", [](ValueList args) -> ValuePtr {
        return Value::make_bool(!args.empty() && args[0]->is_truthy());
    }));

    globals_->set("glorpask", Value::make_builtin("glorpask", [](ValueList args) -> ValuePtr {
        if (!args.empty()) std::cout << display(args[0]);
        std::string line;
        std::getline(std::cin, line);
        return Value::make_str(line);
    }));
    globals_->set("glorpshow", Value::make_builtin("glorpshow", [](ValueList args) -> ValuePtr {
        return Value::make_str(args.empty() ? "" : args[0]->repr());
    }));
    globals_->set("glorpfmt", Value::make_builtin("glorpfmt", [](ValueList args) -> ValuePtr {
        return Value::make_str(args.empty() ? "" : display(args[0]));
    }));

    globals_->set("glorpmap", Value::make_builtin("glorpmap", [](ValueList) -> ValuePtr { return Value::make_dict(); }));
    globals_->set("glorpbag", Value::make_builtin("glorpbag", [](ValueList args) -> ValuePtr { return make_set(std::move(args)); }));
    globals_->set("glorptuple", Value::make_builtin("glorptuple", [](ValueList args) -> ValuePtr {
        if (args.size() == 1 && (args[0]->kind == Value::Kind::List || args[0]->kind == Value::Kind::Tuple || args[0]->kind == Value::Kind::Set)) return Value::make_tuple(args[0]->list_val);
        return Value::make_tuple(std::move(args));
    }));
    globals_->set("glorptype", Value::make_builtin("glorptype", [](ValueList args) -> ValuePtr {
        return Value::make_str(args.empty() ? "NoneType" : args[0]->type_name());
    }));
    globals_->set("glorpthing", Value::make_builtin("glorpthing", [](ValueList) -> ValuePtr {
        auto klass = std::make_shared<GlorpoClass>();
        klass->name = "object";
        return make_instance_value(std::move(klass));
    }));

    globals_->set("glorpid", Value::make_builtin("glorpid", [](ValueList args) -> ValuePtr {
        if (args.empty()) return Value::make_int(0);
        return Value::make_int(static_cast<long long>(reinterpret_cast<std::uintptr_t>(args[0].get())));
    }));
    globals_->set("glorphash", Value::make_builtin("glorphash", [](ValueList args) -> ValuePtr {
        if (args.empty()) return Value::make_int(0);
        return Value::make_int(static_cast<long long>(std::hash<std::string>{}(args[0]->repr())));
    }));
    globals_->set("glorpcall", Value::make_builtin("glorpcall", [](ValueList args) -> ValuePtr {
        if (args.empty()) return Value::make_bool(false);
        return Value::make_bool(args[0]->kind == Value::Kind::Function || args[0]->kind == Value::Kind::Builtin || args[0]->kind == Value::Kind::Class);
    }));
    globals_->set("glorpisa", Value::make_builtin("glorpisa", [](ValueList args) -> ValuePtr {
        if (args.size() < 2) return Value::make_bool(false);
        if (args[1]->kind == Value::Kind::Str) return Value::make_bool(args[0]->type_name() == args[1]->s_val);
        if (args[1]->kind == Value::Kind::Class && args[0]->kind == Value::Kind::Instance && args[0]->obj) {
            return Value::make_bool(args[0]->obj->klass->name == args[1]->klass->name);
        }
        return Value::make_bool(false);
    }));
    globals_->set("glorpkidof", Value::make_builtin("glorpkidof", [](ValueList args) -> ValuePtr {
        return Value::make_bool(args.size() >= 2 && args[0]->kind == Value::Kind::Class && args[1]->kind == Value::Kind::Class && args[0]->klass->name == args[1]->klass->name);
    }));

    globals_->set("glorphas", Value::make_builtin("glorphas", [this](ValueList args) -> ValuePtr {
        if (args.size() < 2) return Value::make_bool(false);
        try { get_attr(args[0], as_text(args[1]), 0); return Value::make_bool(true); }
        catch (const RuntimeError&) { return Value::make_bool(false); }
    }));
    globals_->set("glorpgrab", Value::make_builtin("glorpgrab", [this](ValueList args) -> ValuePtr {
        if (args.size() < 2) throw RuntimeError("glorpgrab expects object and name");
        try { return get_attr(args[0], as_text(args[1]), 0); }
        catch (const RuntimeError&) { if (args.size() >= 3) return args[2]; throw; }
    }));
    globals_->set("glorpset", Value::make_builtin("glorpset", [this](ValueList args) -> ValuePtr {
        if (args.size() < 3) throw RuntimeError("glorpset expects object, name, value");
        set_attr(args[0], as_text(args[1]), args[2], 0);
        return Value::make_none();
    }));
    globals_->set("glorpdrop", Value::make_builtin("glorpdrop", [](ValueList args) -> ValuePtr {
        if (args.size() < 2 || args[0]->kind != Value::Kind::Instance || !args[0]->obj) throw RuntimeError("glorpdrop expects object and name");
        args[0]->obj->attrs.erase(as_text(args[1]));
        return Value::make_none();
    }));

    globals_->set("glorpcount", Value::make_builtin("glorpcount", [](ValueList args) -> ValuePtr {
        if (args.empty()) throw RuntimeError("glorpcount expects iterable");
        ValuePtr seq = args[0];
        long long start = args.size() > 1 ? as_int(args[1], 0) : 0;
        ValueList out;
        for (auto& item : seq->list_val) out.push_back(Value::make_tuple(ValueList{Value::make_int(start++), item}));
        return Value::make_list(std::move(out));
    }));
    globals_->set("glorpzip", Value::make_builtin("glorpzip", [](ValueList args) -> ValuePtr {
        if (args.empty()) return Value::make_list();
        size_t n = args[0]->list_val.size();
        for (auto& seq : args) n = std::min(n, seq->list_val.size());
        ValueList out;
        for (size_t i = 0; i < n; ++i) {
            ValueList row;
            for (auto& seq : args) row.push_back(seq->list_val[i]);
            out.push_back(Value::make_tuple(std::move(row)));
        }
        return Value::make_list(std::move(out));
    }));
    globals_->set("glorpmorph", Value::make_builtin("glorpmorph", [this](ValueList args) -> ValuePtr {
        if (args.size() < 2) throw RuntimeError("glorpmorph expects function and iterable");
        ValueList out;
        for (auto& item : args[1]->list_val) out.push_back(call_value(args[0], ValueList{item}, 0));
        return Value::make_list(std::move(out));
    }));
    globals_->set("glorpsift", Value::make_builtin("glorpsift", [this](ValueList args) -> ValuePtr {
        if (args.size() < 2) throw RuntimeError("glorpsift expects function and iterable");
        ValueList out;
        for (auto& item : args[1]->list_val) if (call_value(args[0], ValueList{item}, 0)->is_truthy()) out.push_back(item);
        return Value::make_list(std::move(out));
    }));
    globals_->set("glorpsort", Value::make_builtin("glorpsort", [](ValueList args) -> ValuePtr {
        if (args.empty()) throw RuntimeError("glorpsort expects iterable");
        ValueList out = args[0]->list_val;
        std::sort(out.begin(), out.end(), [](const ValuePtr& a, const ValuePtr& b) { return a->less_than(*b); });
        return Value::make_list(std::move(out));
    }));
    globals_->set("glorpflip", Value::make_builtin("glorpflip", [](ValueList args) -> ValuePtr {
        if (args.empty()) throw RuntimeError("glorpflip expects iterable");
        ValueList out = args[0]->list_val;
        std::reverse(out.begin(), out.end());
        return Value::make_list(std::move(out));
    }));
    globals_->set("glorpwalk", Value::make_builtin("glorpwalk", [](ValueList args) -> ValuePtr {
        if (args.empty()) throw RuntimeError("glorpwalk expects iterable");
        return Value::make_iterator(args[0]);
    }));
    globals_->set("glorpnext", Value::make_builtin("glorpnext", [](ValueList args) -> ValuePtr {
        if (args.empty() || args[0]->kind != Value::Kind::Iterator) throw RuntimeError("glorpnext expects iterator");
        bool done = false;
        auto src = args[0]->iter_source;
        if (src && args[0]->iter_idx < src->list_val.size()) return src->list_val[args[0]->iter_idx++];
        if (args.size() > 1) return args[1];
        throw RuntimeError("iterator exhausted");
    }));

    globals_->set("glorpabs", Value::make_builtin("glorpabs", [](ValueList args) -> ValuePtr {
        if (args.empty()) throw RuntimeError("glorpabs expects number");
        if (args[0]->kind == Value::Kind::Int) return Value::make_int(std::llabs(args[0]->i_val));
        return Value::make_float(std::fabs(as_number(args[0], 0)));
    }));
    globals_->set("glorpsmol", Value::make_builtin("glorpsmol", [](ValueList args) -> ValuePtr {
        if (args.empty()) throw RuntimeError("glorpsmol expects values");
        ValueList vals = (args.size() == 1 && (args[0]->kind == Value::Kind::List || args[0]->kind == Value::Kind::Tuple || args[0]->kind == Value::Kind::Set)) ? args[0]->list_val : args;
        return *std::min_element(vals.begin(), vals.end(), [](const ValuePtr& a, const ValuePtr& b) { return a->less_than(*b); });
    }));
    globals_->set("glorpsum", Value::make_builtin("glorpsum", [](ValueList args) -> ValuePtr {
        if (args.empty()) return Value::make_int(0);
        ValueList vals = (args[0]->kind == Value::Kind::List || args[0]->kind == Value::Kind::Tuple || args[0]->kind == Value::Kind::Set) ? args[0]->list_val : args;
        double total = 0;
        bool all_int = true;
        for (auto& v : vals) {
            if (v->kind == Value::Kind::Int) total += v->i_val;
            else { total += as_number(v, 0); all_int = false; }
        }
        return all_int ? Value::make_int(static_cast<long long>(total)) : Value::make_float(total);
    }));
    globals_->set("glorpround", Value::make_builtin("glorpround", [](ValueList args) -> ValuePtr {
        if (args.empty()) throw RuntimeError("glorpround expects number");
        return Value::make_int(static_cast<long long>(std::llround(as_number(args[0], 0))));
    }));
    globals_->set("glorppow", Value::make_builtin("glorppow", [](ValueList args) -> ValuePtr {
        if (args.size() < 2) throw RuntimeError("glorppow expects base and exponent");
        return Value::make_float(std::pow(as_number(args[0], 0), as_number(args[1], 0)));
    }));
    globals_->set("glorpdivmod", Value::make_builtin("glorpdivmod", [](ValueList args) -> ValuePtr {
        if (args.size() < 2) throw RuntimeError("glorpdivmod expects two ints");
        long long a = as_int(args[0], 0), b = as_int(args[1], 0);
        return Value::make_tuple(ValueList{Value::make_int(a / b), Value::make_int(a % b)});
    }));
    globals_->set("glorphex", Value::make_builtin("glorphex", [](ValueList args) -> ValuePtr {
        std::stringstream ss; ss << "0x" << std::hex << as_int(args[0], 0); return Value::make_str(ss.str());
    }));
    globals_->set("glorpoct", Value::make_builtin("glorpoct", [](ValueList args) -> ValuePtr {
        std::stringstream ss; ss << "0o" << std::oct << as_int(args[0], 0); return Value::make_str(ss.str());
    }));
    globals_->set("glorpbin", Value::make_builtin("glorpbin", [](ValueList args) -> ValuePtr {
        long long v = as_int(args[0], 0);
        if (v == 0) return Value::make_str("0b0");
        std::string bits;
        while (v > 0) { bits.push_back((v & 1) ? '1' : '0'); v >>= 1; }
        std::reverse(bits.begin(), bits.end());
        return Value::make_str("0b" + bits);
    }));
    globals_->set("glorpchr", Value::make_builtin("glorpchr", [](ValueList args) -> ValuePtr {
        return Value::make_str(std::string(1, static_cast<char>(as_int(args[0], 0))));
    }));
    globals_->set("glorpord", Value::make_builtin("glorpord", [](ValueList args) -> ValuePtr {
        if (args.empty() || args[0]->kind != Value::Kind::Str || args[0]->s_val.empty()) throw RuntimeError("glorpord expects character");
        return Value::make_int(static_cast<unsigned char>(args[0]->s_val[0]));
    }));
    globals_->set("glorpany", Value::make_builtin("glorpany", [](ValueList args) -> ValuePtr {
        if (args.empty()) return Value::make_bool(false);
        for (auto& v : args[0]->list_val) if (v->is_truthy()) return Value::make_bool(true);
        return Value::make_bool(false);
    }));
    globals_->set("glorpall", Value::make_builtin("glorpall", [](ValueList args) -> ValuePtr {
        if (args.empty()) return Value::make_bool(true);
        for (auto& v : args[0]->list_val) if (!v->is_truthy()) return Value::make_bool(false);
        return Value::make_bool(true);
    }));

    auto unsupported = [](const std::string& name) {
        return Value::make_builtin(name, [name](ValueList) -> ValuePtr {
            throw RuntimeError(name + " is declared by Glorpo but not implemented in the native interpreter yet");
        });
    };
    for (const std::string& name : {
        "glorpopen", "glorpfrozen", "glorpbytes", "glorpcomplex", "glorpslice",
        "glorpsuper", "glorpprop", "glorpstatic", "glorpclassy"
    }) {
        globals_->set(name, unsupported(name));
    }
}
