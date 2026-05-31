/**
 * Value Header
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
#include <unordered_map>
#include <memory>
#include <functional>
#include <stdexcept>
#include <variant>
#include <optional>

// Forward declarations
struct Value;
struct GlorpoObject;
struct GlorpoFunction;
struct GlorpoClass;
using ValuePtr  = std::shared_ptr<Value>;
using ValueList = std::vector<ValuePtr>;

// --- Runtime Error -----------------------------------------------------------
struct RuntimeError : std::runtime_error {
    int line;
    explicit RuntimeError(const std::string& msg, int line = 0)
        : std::runtime_error(msg), line(line) {}
};

// Exception thrown by raise
struct GlorpoException {
    std::string type_name;
    std::string message;
    int         line = 0;
};

// Control flow signals
struct ReturnSignal { ValuePtr value; };
struct BreakSignal  {};
struct ContinueSignal {};

// --- Callable type -----------------------------------------------------------
struct Callable {
    std::string name;
    std::function<ValuePtr(ValueList)> fn;
};

// --- Value -------------------------------------------------------------------
struct Value {
    enum class Kind {
        Int, Float, Str, Bool, NoneType,
        List, Dict, Tuple, Set,
        Function, Class, Instance,
        Builtin,
        Iterator,
    };

    Kind kind;

    // Primitive storage
    long long   i_val  = 0;
    double      f_val  = 0.0;
    std::string s_val;
    bool        b_val  = false;

    // Container storage
    ValueList                                   list_val;
    std::unordered_map<std::string, ValuePtr>   dict_val;   // str-keyed for simplicity

    // Callable
    std::shared_ptr<Callable>        builtin;
    std::shared_ptr<GlorpoFunction>  func;
    std::shared_ptr<GlorpoClass>     klass;

    // Instance attributes
    std::shared_ptr<GlorpoObject>    obj;

    // Iterator state
    size_t iter_idx = 0;
    ValuePtr iter_source;

    // -- Constructors ---------------------------------------------------------
    static ValuePtr make_int(long long v);
    static ValuePtr make_float(double v);
    static ValuePtr make_str(std::string v);
    static ValuePtr make_bool(bool v);
    static ValuePtr make_none();
    static ValuePtr make_list(ValueList v = {});
    static ValuePtr make_tuple(ValueList v = {});
    static ValuePtr make_dict();
    static ValuePtr make_builtin(std::string name, std::function<ValuePtr(ValueList)> fn);
    static ValuePtr make_iterator(ValuePtr source);

    // -- Helpers ---------------------------------------------------------------
    bool is_truthy() const;
    std::string repr() const;
    std::string type_name() const;
    bool equals(const Value& other) const;
    bool less_than(const Value& other) const;

    // Dict key (str only for now)
    std::string to_dict_key() const {
        if (kind == Kind::Str) return s_val;
        if (kind == Kind::Int) return std::to_string(i_val);
        if (kind == Kind::Bool) return b_val ? "True" : "False";
        return repr();
    }
};

// --- GlorpoFunction ----------------------------------------------------------
struct GlorpoFunction {
    std::string name;
    // params and body stored as-is from AST - interpreter handles them
    // We keep a raw pointer to avoid circular includes; interpreter fills this
    void* func_ast = nullptr;   // actually FuncDef*
    void* closure  = nullptr;   // actually Environment*
    ValueList bound_args;       // receiver / partial args for bound methods
};

// --- GlorpoClass -------------------------------------------------------------
struct GlorpoClass {
    std::string                                name;
    std::unordered_map<std::string, ValuePtr>  methods;
    std::vector<std::shared_ptr<GlorpoClass>>  bases;
};

// --- GlorpoObject (instance) -------------------------------------------------
struct GlorpoObject {
    std::shared_ptr<GlorpoClass>               klass;
    std::unordered_map<std::string, ValuePtr>  attrs;
};

// --- Value implementations (inline for header-only convenience) ---------------
inline ValuePtr Value::make_int(long long v) {
    auto p = std::make_shared<Value>(); p->kind = Kind::Int;  p->i_val = v; return p;
}
inline ValuePtr Value::make_float(double v) {
    auto p = std::make_shared<Value>(); p->kind = Kind::Float; p->f_val = v; return p;
}
inline ValuePtr Value::make_str(std::string v) {
    auto p = std::make_shared<Value>(); p->kind = Kind::Str;  p->s_val = std::move(v); return p;
}
inline ValuePtr Value::make_bool(bool v) {
    auto p = std::make_shared<Value>(); p->kind = Kind::Bool; p->b_val = v; return p;
}
inline ValuePtr Value::make_none() {
    auto p = std::make_shared<Value>(); p->kind = Kind::NoneType; return p;
}
inline ValuePtr Value::make_list(ValueList v) {
    auto p = std::make_shared<Value>(); p->kind = Kind::List; p->list_val = std::move(v); return p;
}
inline ValuePtr Value::make_tuple(ValueList v) {
    auto p = std::make_shared<Value>(); p->kind = Kind::Tuple; p->list_val = std::move(v); return p;
}
inline ValuePtr Value::make_dict() {
    auto p = std::make_shared<Value>(); p->kind = Kind::Dict; return p;
}
inline ValuePtr Value::make_builtin(std::string name, std::function<ValuePtr(ValueList)> fn) {
    auto p  = std::make_shared<Value>(); p->kind = Kind::Builtin;
    p->builtin = std::make_shared<Callable>(); p->builtin->name = std::move(name); p->builtin->fn = std::move(fn);
    return p;
}
inline ValuePtr Value::make_iterator(ValuePtr source) {
    auto p = std::make_shared<Value>(); p->kind = Kind::Iterator;
    p->iter_source = std::move(source); p->iter_idx = 0;
    return p;
}

inline bool Value::is_truthy() const {
    switch (kind) {
        case Kind::Bool:     return b_val;
        case Kind::Int:      return i_val != 0;
        case Kind::Float:    return f_val != 0.0;
        case Kind::Str:      return !s_val.empty();
        case Kind::NoneType: return false;
        case Kind::List:
        case Kind::Tuple:    return !list_val.empty();
        case Kind::Dict:     return !dict_val.empty();
        default:             return true;
    }
}

inline std::string Value::type_name() const {
    switch (kind) {
        case Kind::Int:      return "int";
        case Kind::Float:    return "float";
        case Kind::Str:      return "str";
        case Kind::Bool:     return "bool";
        case Kind::NoneType: return "NoneType";
        case Kind::List:     return "list";
        case Kind::Tuple:    return "tuple";
        case Kind::Dict:     return "dict";
        case Kind::Set:      return "set";
        case Kind::Function: return "function";
        case Kind::Class:    return "class";
        case Kind::Instance: return "object";
        case Kind::Builtin:  return "builtin_function_or_method";
        case Kind::Iterator: return "iterator";
        default:             return "unknown";
    }
}

inline std::string Value::repr() const {
    switch (kind) {
        case Kind::Int:      return std::to_string(i_val);
        case Kind::Float: {
            std::string s = std::to_string(f_val);
            // trim trailing zeros but keep at least one decimal
            auto dot = s.find('.');
            if (dot != std::string::npos) {
                size_t last = s.find_last_not_of('0');
                if (last == dot) ++last;
                s = s.substr(0, last + 1);
            }
            return s;
        }
        case Kind::Str:      return "'" + s_val + "'";
        case Kind::Bool:     return b_val ? "True" : "False";
        case Kind::NoneType: return "None";
        case Kind::List: {
            std::string r = "[";
            for (size_t i = 0; i < list_val.size(); ++i) {
                if (i) r += ", ";
                r += list_val[i]->repr();
            }
            return r + "]";
        }
        case Kind::Tuple: {
            std::string r = "(";
            for (size_t i = 0; i < list_val.size(); ++i) {
                if (i) r += ", ";
                r += list_val[i]->repr();
            }
            if (list_val.size() == 1) r += ",";
            return r + ")";
        }
        case Kind::Dict: {
            std::string r = "{";
            bool first = true;
            for (auto& [k, v] : dict_val) {
                if (!first) r += ", "; first = false;
                r += "'" + k + "': " + v->repr();
            }
            return r + "}";
        }
        case Kind::Set: {
            std::string r = "{";
            for (size_t i = 0; i < list_val.size(); ++i) {
                if (i) r += ", ";
                r += list_val[i]->repr();
            }
            return r + "}";
        }
        case Kind::Function:
            return "<function " + (func ? func->name : "?") + ">";
        case Kind::Class:
            return "<class '" + (klass ? klass->name : "?") + "'>";
        case Kind::Instance:
            return "<" + (obj && obj->klass ? obj->klass->name : "object") + " instance>";
        case Kind::Builtin:
            return "<built-in function " + (builtin ? builtin->name : "?") + ">";
        default: return "<value>";
    }
}

inline bool Value::equals(const Value& o) const {
    if (kind == Kind::Bool && o.kind == Kind::Bool) return b_val == o.b_val;
    if (kind == Kind::NoneType && o.kind == Kind::NoneType) return true;
    if (kind == Kind::Int   && o.kind == Kind::Int)   return i_val == o.i_val;
    if (kind == Kind::Float && o.kind == Kind::Float) return f_val == o.f_val;
    if (kind == Kind::Int   && o.kind == Kind::Float) return (double)i_val == o.f_val;
    if (kind == Kind::Float && o.kind == Kind::Int)   return f_val == (double)o.i_val;
    if (kind == Kind::Str   && o.kind == Kind::Str)   return s_val == o.s_val;
    if (kind == Kind::List  && o.kind == Kind::List) {
        if (list_val.size() != o.list_val.size()) return false;
        for (size_t i = 0; i < list_val.size(); ++i)
            if (!list_val[i]->equals(*o.list_val[i])) return false;
        return true;
    }
    if (kind == Kind::Tuple && o.kind == Kind::Tuple) {
        if (list_val.size() != o.list_val.size()) return false;
        for (size_t i = 0; i < list_val.size(); ++i)
            if (!list_val[i]->equals(*o.list_val[i])) return false;
        return true;
    }
    return false;
}

inline bool Value::less_than(const Value& o) const {
    if (kind == Kind::Int   && o.kind == Kind::Int)   return i_val < o.i_val;
    if (kind == Kind::Float && o.kind == Kind::Float) return f_val < o.f_val;
    if (kind == Kind::Int   && o.kind == Kind::Float) return (double)i_val < o.f_val;
    if (kind == Kind::Float && o.kind == Kind::Int)   return f_val < (double)o.i_val;
    if (kind == Kind::Str   && o.kind == Kind::Str)   return s_val < o.s_val;
    throw RuntimeError("'<' not supported between '" + type_name() + "' and '" + o.type_name() + "'");
}
