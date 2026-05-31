/**
 * Environment Header
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
#include "value.hpp"
#include <string>
#include <unordered_map>
#include <memory>
#include <stdexcept>

// --- Environment (variable scope) --------------------------------------------
struct Environment : std::enable_shared_from_this<Environment> {
    using EnvPtr = std::shared_ptr<Environment>;

    std::unordered_map<std::string, ValuePtr> vars;
    EnvPtr parent;

    explicit Environment(EnvPtr parent = nullptr) : parent(std::move(parent)) {}

    // Get - walks up the scope chain
    ValuePtr get(const std::string& name) const {
        auto it = vars.find(name);
        if (it != vars.end()) return it->second;
        if (parent) return parent->get(name);
        throw RuntimeError("NameError: name '" + name + "' is not defined");
    }

    // Set in current scope
    void set(const std::string& name, ValuePtr val) {
        vars[name] = std::move(val);
    }

    // Assign - finds existing binding and updates it; creates in current scope if not found
    void assign(const std::string& name, ValuePtr val) {
        if (vars.count(name)) { vars[name] = std::move(val); return; }
        if (parent)           { parent->assign(name, std::move(val)); return; }
        vars[name] = std::move(val);  // define in current scope
    }

    bool erase(const std::string& name) {
        if (vars.erase(name)) return true;
        if (parent) return parent->erase(name);
        return false;
    }

    // Force define in global (for `global` keyword)
    EnvPtr global() {
        Environment* e = this;
        while (e->parent) e = e->parent.get();
        return e->shared_from_this();
    }

    static EnvPtr make(EnvPtr parent = nullptr) {
        return std::make_shared<Environment>(std::move(parent));
    }
};
