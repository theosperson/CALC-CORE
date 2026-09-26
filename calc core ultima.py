import os
import json
import math
import sys
import re
import time
import io
import threading
import tkinter as tk
import customtkinter as ctk
from typing import List, Dict, Any, Optional

# Image & Clipboard Libraries
from PIL import Image

# Chart & Data Processing Libraries
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Hardware & System Libraries
import serial
import serial.tools.list_ports
import psutil

# Platform-specific Clipboard handling for images
try:
    import win32clipboard

    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False


# =====================================================================
# RESOURCE RESOLUTION & GLOBAL CONSTANTS
# =====================================================================

def resource_path(relative_path: str) -> str:
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


HISTORY_FILE = "history.json"
DEFAULT_BAUD_RATES = [9600, 115200, 57600, 38400, 19200]


# =====================================================================
# LEXICAL ANALYZER & TOKENIZER
# =====================================================================

class TokenType:
    NUMBER = "NUMBER"
    IDENTIFIER = "IDENTIFIER"
    OP_ADD = "OP_ADD"
    OP_SUB = "OP_SUB"
    OP_MUL = "OP_MUL"
    OP_DIV = "OP_DIV"
    OP_POW = "OP_POW"
    OP_MOD = "OP_MOD"
    LPAREN = "LPAREN"
    RPAREN = "RPAREN"
    ASSIGN = "ASSIGN"
    COMMA = "COMMA"
    EOF = "EOF"


class Token:
    def __init__(self, type_: str, value: Any, line: int = 1, col: int = 1):
        self.type = type_
        self.value = value
        self.line = line
        self.col = col


class Lexer:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.line = 1
        self.col = 1
        self.current_char = self.text[0] if text else None

    def advance(self):
        if self.current_char == '\n':
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        self.pos += 1
        self.current_char = self.text[self.pos] if self.pos < len(self.text) else None

    def tokenize(self) -> List[Token]:
        tokens = []
        while self.current_char is not None:
            if self.current_char.isspace():
                self.advance()
            elif self.current_char.isdigit() or self.current_char == '.':
                tokens.append(self._number())
            elif self.current_char.isalpha() or self.current_char == '_':
                tokens.append(self._identifier())
            elif self.current_char == '+':
                tokens.append(Token(TokenType.OP_ADD, '+', self.line, self.col))
                self.advance()
            elif self.current_char == '-':
                tokens.append(Token(TokenType.OP_SUB, '-', self.line, self.col))
                self.advance()
            elif self.current_char == '*':
                tokens.append(Token(TokenType.OP_MUL, '*', self.line, self.col))
                self.advance()
            elif self.current_char == '/':
                tokens.append(Token(TokenType.OP_DIV, '/', self.line, self.col))
                self.advance()
            elif self.current_char == '^':
                tokens.append(Token(TokenType.OP_POW, '^', self.line, self.col))
                self.advance()
            elif self.current_char == '%':
                tokens.append(Token(TokenType.OP_MOD, '%', self.line, self.col))
                self.advance()
            elif self.current_char == '=':
                tokens.append(Token(TokenType.ASSIGN, '=', self.line, self.col))
                self.advance()
            elif self.current_char == '(':
                tokens.append(Token(TokenType.LPAREN, '(', self.line, self.col))
                self.advance()
            elif self.current_char == ')':
                tokens.append(Token(TokenType.RPAREN, ')', self.line, self.col))
                self.advance()
            elif self.current_char == ',':
                tokens.append(Token(TokenType.COMMA, ',', self.line, self.col))
                self.advance()
            else:
                self.advance()
        tokens.append(Token(TokenType.EOF, None, self.line, self.col))
        return tokens

    def _number(self) -> Token:
        num_str = ""
        dot_count = 0
        start_col = self.col
        while self.current_char is not None and (self.current_char.isdigit() or self.current_char == '.'):
            if self.current_char == '.':
                dot_count += 1
                if dot_count > 1:
                    break
            num_str += self.current_char
            self.advance()
        return Token(TokenType.NUMBER, float(num_str), self.line, start_col)

    def _identifier(self) -> Token:
        id_str = ""
        start_col = self.col
        while self.current_char is not None and (self.current_char.isalnum() or self.current_char == '_'):
            id_str += self.current_char
            self.advance()
        return Token(TokenType.IDENTIFIER, id_str, self.line, start_col)


# =====================================================================
# AST NODES & PARSER
# =====================================================================

class ASTNode: pass


class NumberNode(ASTNode):
    def __init__(self, token: Token):
        self.value = token.value


class VarNode(ASTNode):
    def __init__(self, token: Token):
        self.name = token.value


class BinOpNode(ASTNode):
    def __init__(self, left: ASTNode, op_token: Token, right: ASTNode):
        self.left = left
        self.op = op_token.value
        self.right = right


class UnaryOpNode(ASTNode):
    def __init__(self, op_token: Token, expr: ASTNode):
        self.op = op_token.value
        self.expr = expr


class FuncCallNode(ASTNode):
    def __init__(self, func_token: Token, args: List[ASTNode]):
        self.func_name = func_token.value
        self.args = args


class AssignNode(ASTNode):
    def __init__(self, var_token: Token, expr: ASTNode):
        self.var_name = var_token.value
        self.expr = expr


class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0
        self.current_token = self.tokens[0]

    def eat(self, token_type: str):
        if self.current_token.type == token_type:
            self.pos += 1
            if self.pos < len(self.tokens):
                self.current_token = self.tokens[self.pos]
            else:
                self.current_token = Token(TokenType.EOF, None)
        else:
            raise SyntaxError(f"Expected '{token_type}'")

    def peek_token(self) -> Token:
        if self.pos + 1 < len(self.tokens):
            return self.tokens[self.pos + 1]
        return Token(TokenType.EOF, None)

    def parse(self) -> ASTNode:
        if self.current_token.type == TokenType.IDENTIFIER and self.peek_token().type == TokenType.ASSIGN:
            var_token = self.current_token
            self.eat(TokenType.IDENTIFIER)
            self.eat(TokenType.ASSIGN)
            return AssignNode(var_token, self.expr())
        return self.expr()

    def expr(self) -> ASTNode:
        node = self.term()
        while self.current_token.type in (TokenType.OP_ADD, TokenType.OP_SUB):
            token = self.current_token
            self.eat(token.type)
            node = BinOpNode(left=node, op_token=token, right=self.term())
        return node

    def term(self) -> ASTNode:
        node = self.factor()
        while self.current_token.type in (TokenType.OP_MUL, TokenType.OP_DIV, TokenType.OP_MOD):
            token = self.current_token
            self.eat(token.type)
            node = BinOpNode(left=node, op_token=token, right=self.factor())
        return node

    def factor(self) -> ASTNode:
        token = self.current_token
        if token.type in (TokenType.OP_ADD, TokenType.OP_SUB):
            self.eat(token.type)
            return UnaryOpNode(op_token=token, expr=self.factor())
        return self.power()

    def power(self) -> ASTNode:
        node = self.primary()
        if self.current_token.type == TokenType.OP_POW:
            token = self.current_token
            self.eat(TokenType.OP_POW)
            node = BinOpNode(left=node, op_token=token, right=self.factor())
        return node

    def primary(self) -> ASTNode:
        token = self.current_token
        if token.type == TokenType.NUMBER:
            self.eat(TokenType.NUMBER)
            return NumberNode(token)
        elif token.type == TokenType.IDENTIFIER:
            if self.peek_token().type == TokenType.LPAREN:
                func_token = token
                self.eat(TokenType.IDENTIFIER)
                self.eat(TokenType.LPAREN)
                args = []
                if self.current_token.type != TokenType.RPAREN:
                    args.append(self.expr())
                    while self.current_token.type == TokenType.COMMA:
                        self.eat(TokenType.COMMA)
                        args.append(self.expr())
                self.eat(TokenType.RPAREN)
                return FuncCallNode(func_token, args)
            else:
                self.eat(TokenType.IDENTIFIER)
                return VarNode(token)
        elif token.type == TokenType.LPAREN:
            self.eat(TokenType.LPAREN)
            node = self.expr()
            self.eat(TokenType.RPAREN)
            return node
        raise SyntaxError(f"Unexpected token '{token.value}'")


# =====================================================================
# FAIL-SAFE MATHEMATICAL ENGINE
# =====================================================================

class UltimaEngine:
    FUNCTIONS = {
        'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
        'asin': math.asin, 'acos': math.acos, 'atan': math.atan,
        'sinh': math.sinh, 'cosh': math.cosh, 'tanh': math.tanh,
        'sqrt': math.sqrt, 'log': math.log10, 'ln': math.log,
        'abs': abs, 'rad': math.radians, 'deg': math.degrees,
        'ceil': math.ceil, 'floor': math.floor, 'fact': math.factorial
    }

    def __init__(self):
        self.variables: Dict[str, float] = {
            'pi': math.pi, 'e': math.e, 'tau': math.tau, 'ans': 0.0, 'phi': 1.618033988749895
        }
        self.history: List[str] = self.load_history()

    def load_history(self) -> List[str]:
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r') as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def save_history(self):
        try:
            with open(HISTORY_FILE, 'w') as f:
                json.dump(self.history, f, indent=2)
        except Exception:
            pass

    def clear_history(self):
        self.history = []
        self.save_history()

    def evaluate(self, node: ASTNode) -> float:
        if isinstance(node, NumberNode):
            return float(node.value)
        elif isinstance(node, VarNode):
            if node.name in self.variables:
                return float(self.variables[node.name])
            raise NameError(f"Undefined variable '{node.name}'")
        elif isinstance(node, UnaryOpNode):
            val = self.evaluate(node.expr)
            return +val if node.op == '+' else -val
        elif isinstance(node, BinOpNode):
            left_val = self.evaluate(node.left)
            right_val = self.evaluate(node.right)
            if node.op == '+':
                return left_val + right_val
            elif node.op == '-':
                return left_val - right_val
            elif node.op == '*':
                return left_val * right_val
            elif node.op == '/':
                if right_val == 0: raise ZeroDivisionError("Division by zero")
                return left_val / right_val
            elif node.op == '%':
                return left_val % right_val
            elif node.op == '^':
                return math.pow(left_val, right_val)
        elif isinstance(node, FuncCallNode):
            args_eval = [self.evaluate(arg) for arg in node.args]
            if node.func_name in self.FUNCTIONS:
                return float(self.FUNCTIONS[node.func_name](*args_eval))
            raise NameError(f"Unknown function '{node.func_name}'")
        elif isinstance(node, AssignNode):
            val = self.evaluate(node.expr)
            self.variables[node.var_name] = val
            return val
        raise RuntimeError("Invalid AST Node")

    def sanitize_expression(self, expr: str) -> str:
        cleaned = expr.strip()
        cleaned = re.sub(r'(\d)\s*\(', r'\1*(', cleaned)
        cleaned = re.sub(r'\)\s*\(', r')*(', cleaned)
        cleaned = re.sub(r'(\d)\s*([a-zA-Z])', r'\1*\2', cleaned)

        open_p = cleaned.count('(')
        close_p = cleaned.count(')')
        if open_p > close_p:
            cleaned += ')' * (open_p - close_p)
        return cleaned

    def parse_natural_query(self, query: str) -> Optional[float]:
        cleaned = query.lower()
        cleaned = re.sub(r'\bwhat\s+is\b|\bcalculate\b|\bcompute\b|\bevaluate\b|\bsolve\b', '', cleaned)
        cleaned = re.sub(r'\bplus\b', '+', cleaned)
        cleaned = re.sub(r'\bminus\b', '-', cleaned)
        cleaned = re.sub(r'\btimes\b|\bmultiplied\s+by\b', '*', cleaned)
        cleaned = re.sub(r'\bdivided\s+by\b', '/', cleaned)

        match = re.search(r'[\d\.\s\+\-\*\/\^\%\(\)\w]+', cleaned)
        if match:
            expr_str = match.group(0).strip()
            if expr_str:
                return self.execute(expr_str)
        return None

    def execute(self, expression: str) -> float:
        cleaned_expr = self.sanitize_expression(expression)
        if not cleaned_expr: return 0.0

        try:
            lexer = Lexer(cleaned_expr)
            tokens = lexer.tokenize()
            parser = Parser(tokens)
            ast = parser.parse()
            result = self.evaluate(ast)
        except Exception:
            nat_res = self.parse_natural_query(cleaned_expr)
            if nat_res is not None:
                result = nat_res
            else:
                try:
                    result = float(eval(cleaned_expr, {"__builtins__": None}, self.FUNCTIONS))
                except Exception:
                    result = 0.0

        self.variables['ans'] = result
        self.history.append(f"{expression.strip()} = {result:g}")
        self.save_history()
        return result

    def orbital_velocity(self, mass: float, radius: float) -> float:
        if radius <= 0: return 0.0
        return math.sqrt((6.67430e-11 * mass) / radius)

    def kinetic_energy(self, mass: float, velocity: float) -> float:
        if mass < 0: return 0.0
        return 0.5 * mass * (velocity ** 2)


# =====================================================================
# MAIN WORKSTATION GUI
# =====================================================================

class CalcCoreUltima(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Smart Workstation & Calculator Core")
        self.geometry("1200x860")
        self.minsize(1000, 720)

        ctk.set_appearance_mode("Dark")

        self.engine = UltimaEngine()
        self.serial_thread = None
        self.serial_port = None
        self.is_serial_connected = False
        self.sensor_data_points: List[float] = []

        self.plot_canvas = None
        self.current_fig = None
        self.nav_buttons: Dict[str, ctk.CTkButton] = {}
        self.view_cache: Dict[str, ctk.CTkFrame] = {}
        self.current_view_key = ""

        self.configure(fg_color=("#f8fafc", "#080c14"))
        self._build_layout()
        self.after(1000, self._update_perf_loop)

    def _build_layout(self):
        self.sidebar = ctk.CTkFrame(
            self, width=250, corner_radius=0,
            fg_color=("#ffffff", "#0f172a"),
            border_width=1, border_color=("#e2e8f0", "#1e293b")
        )
        self.sidebar.pack(side="left", fill="y", padx=0, pady=0)
        self.sidebar.pack_propagate(False)

        brand_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand_frame.pack(fill="x", padx=20, pady=(24, 20))

        ctk.CTkLabel(
            brand_frame, text="ULTIMA CORE",
            font=("Consolas", 22, "bold"), text_color=("#0284c7", "#38bdf8"), anchor="w"
        ).pack(fill="x")

        ctk.CTkLabel(
            brand_frame, text="Workstation Engine",
            font=("Segoe UI", 10, "bold"), text_color=("#64748b", "#64748b"), anchor="w"
        ).pack(fill="x")

        modes = [
            ("Scientific Calculator", "calc"),
            ("Computer Performance", "perf"),
            ("Chart & Graph Maker", "graph"),
            ("Space & Gravity", "space"),
            ("Physics & Energy", "physics"),
            ("Live Sensor Tracker", "sensor")
        ]

        for name, key in modes:
            btn = ctk.CTkButton(
                self.sidebar, text=f"  {name}",
                command=lambda k=key: self._switch_view(k),
                fg_color="transparent", text_color=("#475569", "#94a3b8"),
                hover_color=("#f1f5f9", "#1e293b"), anchor="w",
                font=("Segoe UI", 13, "bold"), height=40, corner_radius=10
            )
            btn.pack(fill="x", padx=12, pady=3)
            self.nav_buttons[key] = btn

        theme_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        theme_frame.pack(side="bottom", fill="x", padx=16, pady=20)

        ctk.CTkLabel(theme_frame, text="App Theme:", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 6))
        self.theme_menu = ctk.CTkOptionMenu(
            theme_frame, values=["Dark", "Light"], command=self._change_theme,
            fg_color=("#f1f5f9", "#1e293b"), button_color=("#cbd5e1", "#334155"),
            text_color=("#0f172a", "#38bdf8"), dropdown_fg_color=("#ffffff", "#0f172a"),
            corner_radius=8, height=34
        )
        self.theme_menu.pack(fill="x")

        self.workspace = ctk.CTkFrame(self, fg_color=("#f8fafc", "#080c14"), corner_radius=0)
        self.workspace.pack(side="right", fill="both", expand=True, padx=22, pady=22)

        self._switch_view("calc")

    def _change_theme(self, new_mode: str):
        ctk.set_appearance_mode(new_mode)

    def _switch_view(self, key: str):
        if self.current_view_key == key:
            return

        for k, btn in self.nav_buttons.items():
            if k == key:
                btn.configure(fg_color=("#e2e8f0", "#1e293b"), text_color=("#0284c7", "#38bdf8"))
            else:
                btn.configure(fg_color="transparent", text_color=("#475569", "#94a3b8"))

        if self.current_view_key in self.view_cache:
            self.view_cache[self.current_view_key].pack_forget()

        self.current_view_key = key

        if key not in self.view_cache:
            view_frame = ctk.CTkFrame(self.workspace, fg_color="transparent")
            self.view_cache[key] = view_frame
            getattr(self, f"_build_{key}_view")(view_frame)

        self.view_cache[key].pack(fill="both", expand=True)

    def _create_header(self, parent: ctk.CTkFrame, title: str, subtitle: str):
        header_frame = ctk.CTkFrame(parent, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 18))
        ctk.CTkLabel(
            header_frame, text=title, font=("Segoe UI", 24, "bold"),
            text_color=("#0f172a", "#f8fafc"), anchor="w"
        ).pack(fill="x")
        ctk.CTkLabel(
            header_frame, text=subtitle, font=("Segoe UI", 11),
            text_color=("#64748b", "#94a3b8"), anchor="w"
        ).pack(fill="x")

    # --- VIEW 1: SCIENTIFIC CALCULATOR ---
    def _build_calc_view(self, parent: ctk.CTkFrame):
        self._create_header(parent, "Scientific Calculator",
                            "Fail-safe engine with round buttons & single-digit backspace")

        main_container = ctk.CTkFrame(parent, fg_color="transparent")
        main_container.pack(fill="both", expand=True)

        calc_card = ctk.CTkFrame(main_container, fg_color=("#ffffff", "#0f172a"), corner_radius=16)
        calc_card.pack(side="left", fill="both", expand=True, padx=(0, 10))

        self.calc_entry = ctk.CTkEntry(
            calc_card, font=("Consolas", 28, "bold"), height=70,
            justify="right", fg_color=("#f8fafc", "#020617"),
            text_color=("#0284c7", "#38bdf8"), state="normal", corner_radius=12
        )
        self.calc_entry.pack(fill="x", padx=20, pady=20)
        self.calc_entry.focus_set()

        grid = ctk.CTkFrame(calc_card, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Re-arranged button grid incorporating the left-oriented Backspace Delete ('⌫')
        buttons = [
            ('C', 0, 0), ('⌫', 0, 1), ('(', 0, 2), (')', 0, 3), ('^', 0, 4),
            ('sin', 1, 0), ('cos', 1, 1), ('tan', 1, 2), ('sqrt', 1, 3), ('/', 1, 4),
            ('7', 2, 0), ('8', 2, 1), ('9', 2, 2), ('log', 2, 3), ('*', 2, 4),
            ('4', 3, 0), ('5', 3, 1), ('6', 3, 2), ('ln', 3, 3), ('-', 3, 4),
            ('1', 4, 0), ('2', 4, 1), ('3', 4, 2), ('pi', 4, 3), ('+', 4, 4),
            ('0', 5, 0), ('.', 5, 1), ('ans', 5, 2), ('e', 5, 3), ('=', 5, 4),
        ]

        for (text, row, col) in buttons:
            color_bg = ("#e2e8f0", "#1e293b") if not text.isdigit() and text != '.' else ("#cbd5e1", "#334155")
            if text == '=':
                color_bg = ("#0284c7", "#0284c7")
            elif text == 'C':
                color_bg = ("#ef4444", "#ef4444")
            elif text == '⌫':
                color_bg = ("#f59e0b", "#d97706")  # Highlighted deletion key

            # corner_radius=28 renders fully rounded / circular buttons
            btn = ctk.CTkButton(
                grid, text=text, font=("Segoe UI", 16, "bold"), corner_radius=28,
                fg_color=color_bg,
                command=lambda t=text: self._calc_click(t)
            )
            btn.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")

        for i in range(5): grid.grid_columnconfigure(i, weight=1)
        for i in range(6): grid.grid_rowconfigure(i, weight=1)

        history_card = ctk.CTkFrame(main_container, width=280, fg_color=("#ffffff", "#0f172a"), corner_radius=16)
        history_card.pack(side="right", fill="both", padx=(10, 0))
        history_card.pack_propagate(False)

        hist_header = ctk.CTkFrame(history_card, fg_color="transparent")
        hist_header.pack(fill="x", padx=15, pady=15)

        ctk.CTkLabel(hist_header, text="History", font=("Segoe UI", 16, "bold")).pack(side="left")

        ctk.CTkButton(
            hist_header, text="Clear", width=50, height=28, corner_radius=14,
            fg_color="#ef4444", hover_color="#dc2626",
            command=self._clear_calc_history
        ).pack(side="right")

        self.history_box = ctk.CTkTextbox(history_card, font=("Consolas", 12), state="normal", corner_radius=10)
        self.history_box.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        self._refresh_history_ui()

    def _calc_click(self, char: str):
        curr = self.calc_entry.get()
        if char == 'C':
            self.calc_entry.delete(0, "end")
        elif char == '⌫':  # Delete only one single digit or character from the right
            if len(curr) > 0:
                self.calc_entry.delete(len(curr) - 1, "end")
        elif char == '=':
            res = self.engine.execute(curr)
            self.calc_entry.delete(0, "end")
            self.calc_entry.insert(0, f"{res:g}")
            self._refresh_history_ui()
        else:
            self.calc_entry.insert("end", char)

    def _refresh_history_ui(self):
        if hasattr(self, 'history_box') and self.history_box.winfo_exists():
            self.history_box.delete("1.0", "end")
            for entry in self.engine.history:
                self.history_box.insert("end", entry + "\n")
            self.history_box.see("end")

    def _clear_calc_history(self):
        self.engine.clear_history()
        self._refresh_history_ui()

    # --- VIEW 2: COMPUTER PERFORMANCE CHECKER ---
    def _build_perf_view(self, parent: ctk.CTkFrame):
        self._create_header(parent, "Computer Performance Checker", "Live hardware monitoring metrics")

        card = ctk.CTkFrame(parent, fg_color=("#ffffff", "#0f172a"), corner_radius=16)
        card.pack(fill="both", expand=True, padx=5, pady=5)

        cpu_frame = ctk.CTkFrame(card, fg_color="transparent")
        cpu_frame.pack(fill="x", padx=20, pady=15)
        self.cpu_label = ctk.CTkLabel(cpu_frame, text="CPU Usage: 0%", font=("Segoe UI", 14, "bold"))
        self.cpu_label.pack(anchor="w")
        self.cpu_bar = ctk.CTkProgressBar(cpu_frame, height=18, corner_radius=9)
        self.cpu_bar.set(0)
        self.cpu_bar.pack(fill="x", pady=5)

        ram_frame = ctk.CTkFrame(card, fg_color="transparent")
        ram_frame.pack(fill="x", padx=20, pady=15)
        self.ram_label = ctk.CTkLabel(ram_frame, text="RAM Usage: 0%", font=("Segoe UI", 14, "bold"))
        self.ram_label.pack(anchor="w")
        self.ram_bar = ctk.CTkProgressBar(ram_frame, height=18, corner_radius=9)
        self.ram_bar.set(0)
        self.ram_bar.pack(fill="x", pady=5)

        disk_frame = ctk.CTkFrame(card, fg_color="transparent")
        disk_frame.pack(fill="x", padx=20, pady=15)
        self.disk_label = ctk.CTkLabel(disk_frame, text="Disk Usage: 0%", font=("Segoe UI", 14, "bold"))
        self.disk_label.pack(anchor="w")
        self.disk_bar = ctk.CTkProgressBar(disk_frame, height=18, corner_radius=9)
        self.disk_bar.set(0)
        self.disk_bar.pack(fill="x", pady=5)

        self.uptime_label = ctk.CTkLabel(card, text="System Uptime: --", font=("Consolas", 12))
        self.uptime_label.pack(padx=20, pady=15, anchor="w")

    def _update_perf_loop(self):
        if self.current_view_key == "perf":
            try:
                cpu = psutil.cpu_percent()
                ram = psutil.virtual_memory().percent
                disk = psutil.disk_usage('/').percent
                uptime_sec = time.time() - psutil.boot_time()
                uptime_str = time.strftime("%H hours, %M mins, %S secs", time.gmtime(uptime_sec))

                if hasattr(self, 'cpu_label') and self.cpu_label.winfo_exists():
                    self.cpu_label.configure(text=f"CPU Usage: {cpu}%")
                    self.cpu_bar.set(cpu / 100.0)

                if hasattr(self, 'ram_label') and self.ram_label.winfo_exists():
                    self.ram_label.configure(text=f"RAM Usage: {ram}%")
                    self.ram_bar.set(ram / 100.0)

                if hasattr(self, 'disk_label') and self.disk_label.winfo_exists():
                    self.disk_label.configure(text=f"Disk Usage: {disk}%")
                    self.disk_bar.set(disk / 100.0)

                if hasattr(self, 'uptime_label') and self.uptime_label.winfo_exists():
                    self.uptime_label.configure(text=f"System Uptime: {uptime_str}")
            except Exception:
                pass

        self.after(1000, self._update_perf_loop)

    # --- VIEW 3: CHART & GRAPH MAKER ---
    def _build_graph_view(self, parent: ctk.CTkFrame):
        self._create_header(parent, "Chart & Graph Maker", "Plot unlimited datasets and copy directly to clipboard")

        main_card = ctk.CTkFrame(parent, fg_color=("#ffffff", "#0f172a"), corner_radius=16)
        main_card.pack(fill="both", expand=True, padx=5, pady=5)

        left_input_panel = ctk.CTkFrame(main_card, width=320, fg_color="transparent")
        left_input_panel.pack(side="left", fill="y", padx=15, pady=15)
        left_input_panel.pack_propagate(False)

        ctk.CTkLabel(
            left_input_panel, text="Data Entry (Infinite Rows):",
            font=("Segoe UI", 13, "bold")
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkLabel(
            left_input_panel,
            text="Format per line: [Label, Value] or just [Value]\nSupports unlimited values (infinity).",
            font=("Segoe UI", 10), text_color=("#64748b", "#94a3b8")
        ).pack(anchor="w", pady=(0, 8))

        self.graph_data_editor = ctk.CTkTextbox(
            left_input_panel, font=("Consolas", 12), corner_radius=10
        )
        self.graph_data_editor.pack(fill="both", expand=True, pady=(0, 10))

        sample_data = "Item A, 12.5\nItem B, 24.8\nItem C, 18.2\nItem D, 35.0\nItem E, 22.4\nItem F, 41.1"
        self.graph_data_editor.insert("1.0", sample_data)

        opts_frame = ctk.CTkFrame(left_input_panel, fg_color="transparent")
        opts_frame.pack(fill="x")

        self.graph_type = ctk.CTkOptionMenu(
            opts_frame, values=["Line Graph", "Bar Chart", "Scatter Plot"],
            height=34, corner_radius=10
        )
        self.graph_type.pack(fill="x", pady=(0, 8))

        ctk.CTkButton(
            opts_frame, text="Render Chart", command=self._plot_custom_graph,
            height=36, corner_radius=10, fg_color="#0284c7", hover_color="#0369a1"
        ).pack(fill="x")

        right_graph_panel = ctk.CTkFrame(main_card, fg_color="transparent")
        right_graph_panel.pack(side="right", fill="both", expand=True, padx=(0, 15), pady=15)

        top_toolbar = ctk.CTkFrame(right_graph_panel, fg_color="transparent")
        top_toolbar.pack(fill="x", pady=(0, 10))

        self.graph_status_lbl = ctk.CTkLabel(
            top_toolbar, text="Ready", font=("Segoe UI", 12, "bold"), text_color=("#64748b", "#94a3b8")
        )
        self.graph_status_lbl.pack(side="left")

        self.copy_btn = ctk.CTkButton(
            top_toolbar, text="📋 Copy Graph to Clipboard", command=self._copy_graph_to_clipboard,
            height=34, corner_radius=10, fg_color="#10b981", hover_color="#059669"
        )
        self.copy_btn.pack(side="right")

        self.graph_container = ctk.CTkFrame(right_graph_panel, fg_color=("#f8fafc", "#020617"), corner_radius=10)
        self.graph_container.pack(fill="both", expand=True)

        self._plot_custom_graph()

    def _plot_custom_graph(self):
        try:
            raw_text = self.graph_data_editor.get("1.0", "end").strip()
            if not raw_text:
                self.graph_status_lbl.configure(text="Error: Data editor is empty.")
                return

            x_list = []
            y_vals = []

            lines = raw_text.splitlines()
            for idx, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                parts = re.split(r'[,;\t]+', line)
                if len(parts) >= 2:
                    label = parts[0].strip()
                    try:
                        val = float(parts[1].strip())
                        x_list.append(label)
                        y_vals.append(val)
                    except ValueError:
                        continue
                elif len(parts) == 1:
                    try:
                        val = float(parts[0].strip())
                        x_list.append(str(idx + 1))
                        y_vals.append(val)
                    except ValueError:
                        continue

            if not y_vals:
                self.graph_status_lbl.configure(text="Error: Could not parse numeric data points.")
                return

            fig, ax = plt.subplots(figsize=(6, 4), dpi=100)
            chart_kind = self.graph_type.get()

            if "Bar" in chart_kind:
                ax.bar(x_list, y_vals, color='#0284c7', edgecolor='#0369a1')
            elif "Scatter" in chart_kind:
                ax.scatter(x_list, y_vals, color='#0284c7', s=50)
            else:
                ax.plot(x_list, y_vals, color='#0284c7', marker='o', linewidth=2)

            ax.grid(True, linestyle='--', alpha=0.5)
            ax.set_title(f"Plotted Data ({len(y_vals)} total data points)")
            fig.tight_layout()

            if self.plot_canvas:
                self.plot_canvas.get_tk_widget().destroy()

            self.current_fig = fig
            self.plot_canvas = FigureCanvasTkAgg(fig, master=self.graph_container)
            self.plot_canvas.draw()
            self.plot_canvas.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)
            self.graph_status_lbl.configure(text=f"Successfully plotted {len(y_vals)} data points.")
        except Exception as e:
            self.graph_status_lbl.configure(text=f"Plot Error: {str(e)}")

    def _copy_graph_to_clipboard(self):
        if self.current_fig is None:
            self.graph_status_lbl.configure(text="No active graph to copy.")
            return

        try:
            buf = io.BytesIO()
            self.current_fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
            buf.seek(0)
            img = Image.open(buf)

            if WIN32_AVAILABLE and sys.platform.startswith('win'):
                output = io.BytesIO()
                img.convert('RGB').save(output, 'BMP')
                data = output.getvalue()[14:]  # Remove BMP header
                output.close()

                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
                win32clipboard.CloseClipboard()
                self.graph_status_lbl.configure(text="✅ Graph copied to Clipboard!")
            else:
                img.save("clipboard_graph.png")
                self.graph_status_lbl.configure(text="✅ Copied & saved chart to clipboard_graph.png")
            buf.close()
        except Exception as e:
            self.graph_status_lbl.configure(text=f"Clipboard Error: {str(e)}")

    # --- VIEW 4: SPACE & GRAVITY ---
    def _build_space_view(self, parent: ctk.CTkFrame):
        self._create_header(parent, "Space & Gravity Calculator", "Orbital velocity computation")

        card = ctk.CTkFrame(parent, fg_color=("#ffffff", "#0f172a"), corner_radius=16)
        card.pack(fill="x", padx=5, pady=10)

        f = ctk.CTkFrame(card, fg_color="transparent")
        f.pack(padx=20, pady=20, fill="x")

        ctk.CTkLabel(f, text="Mass (kg):").grid(row=0, column=0, padx=10, pady=10)
        self.m_entry = ctk.CTkEntry(f, placeholder_text="Enter Mass in kg", corner_radius=10)
        self.m_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(f, text="Radius (m):").grid(row=1, column=0, padx=10, pady=10)
        self.r_entry = ctk.CTkEntry(f, placeholder_text="Enter Radius in meters", corner_radius=10)
        self.r_entry.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        f.grid_columnconfigure(1, weight=1)

        self.orbit_res = ctk.CTkLabel(card, text="Speed: -- m/s", font=("Consolas", 16, "bold"))
        self.orbit_res.pack(pady=15)

        ctk.CTkButton(card, text="Calculate Orbital Speed", command=self._calc_space, corner_radius=10).pack(
            pady=(0, 20))

    def _calc_space(self):
        try:
            m_str = self.m_entry.get().strip()
            r_str = self.r_entry.get().strip()
            v = self.engine.orbital_velocity(float(m_str), float(r_str))
            self.orbit_res.configure(text=f"Orbit Speed: {v:,.2f} m/s")
        except Exception as e:
            self.orbit_res.configure(text=f"Error: {str(e)}")

    # --- VIEW 5: PHYSICS & ENERGY ---
    def _build_physics_view(self, parent: ctk.CTkFrame):
        self._create_header(parent, "Physics & Energy", "Kinetic energy computation")

        card = ctk.CTkFrame(parent, fg_color=("#ffffff", "#0f172a"), corner_radius=16)
        card.pack(fill="x", padx=5, pady=10)

        f = ctk.CTkFrame(card, fg_color="transparent")
        f.pack(padx=20, pady=20, fill="x")

        ctk.CTkLabel(f, text="Mass (kg):").grid(row=0, column=0, padx=10, pady=10)
        self.pm_entry = ctk.CTkEntry(f, placeholder_text="Enter Mass in kg", corner_radius=10)
        self.pm_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(f, text="Velocity (m/s):").grid(row=1, column=0, padx=10, pady=10)
        self.pv_entry = ctk.CTkEntry(f, placeholder_text="Enter Velocity in m/s", corner_radius=10)
        self.pv_entry.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        f.grid_columnconfigure(1, weight=1)

        self.phys_res = ctk.CTkLabel(card, text="Energy: -- J", font=("Consolas", 16, "bold"))
        self.phys_res.pack(pady=15)

        ctk.CTkButton(card, text="Calculate Kinetic Energy", command=self._calc_phys, corner_radius=10).pack(
            pady=(0, 20))

    def _calc_phys(self):
        try:
            m_str = self.pm_entry.get().strip()
            v_str = self.pv_entry.get().strip()
            ke = self.engine.kinetic_energy(float(m_str), float(v_str))
            self.phys_res.configure(text=f"Energy: {ke:,.2f} Joules")
        except Exception as e:
            self.phys_res.configure(text=f"Error: {str(e)}")

    # --- VIEW 6: SENSOR TRACKER ---
    def _build_sensor_view(self, parent: ctk.CTkFrame):
        self._create_header(parent, "Live Sensor Tracker", "Pure real-time serial logging with auto-charting")

        card = ctk.CTkFrame(parent, fg_color=("#ffffff", "#0f172a"), corner_radius=16)
        card.pack(fill="both", expand=True, padx=5, pady=10)

        ctrl = ctk.CTkFrame(card, fg_color="transparent")
        ctrl.pack(fill="x", padx=15, pady=15)

        ports = [p.device for p in serial.tools.list_ports.comports()]
        if not ports: ports = ["No COM Ports Detected"]

        self.port_menu = ctk.CTkOptionMenu(ctrl, values=ports, corner_radius=10)
        self.port_menu.pack(side="left", padx=5)

        self.baud_menu = ctk.CTkOptionMenu(ctrl, values=[str(b) for b in DEFAULT_BAUD_RATES], corner_radius=10)
        self.baud_menu.pack(side="left", padx=5)

        ctk.CTkButton(
            ctrl, text="Refresh", width=80, corner_radius=10,
            command=self._refresh_serial_ports
        ).pack(side="left", padx=5)

        btn_text = "Disconnect" if self.is_serial_connected else "Connect"
        btn_color = "#ef4444" if self.is_serial_connected else "#10b981"
        hover_color = "#dc2626" if self.is_serial_connected else "#059669"

        self.connect_btn = ctk.CTkButton(
            ctrl, text=btn_text, fg_color=btn_color, hover_color=hover_color, corner_radius=10,
            command=self._toggle_serial_connection
        )
        self.connect_btn.pack(side="left", padx=5)

        self.plot_stream_btn = ctk.CTkButton(
            ctrl, text="Plot Stream", width=100, corner_radius=10,
            command=self._plot_sensor_stream
        )
        self.plot_stream_btn.pack(side="right", padx=5)

        self.sensor_log = ctk.CTkTextbox(card, font=("Consolas", 12), state="normal", corner_radius=10)
        self.sensor_log.pack(fill="both", expand=True, padx=15, pady=(0, 15))

    def _refresh_serial_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if not ports: ports = ["No COM Ports Detected"]
        self.port_menu.configure(values=ports)
        self.port_menu.set(ports[0])

    def _toggle_serial_connection(self):
        if self.is_serial_connected:
            self.is_serial_connected = False
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
            self.connect_btn.configure(text="Connect", fg_color="#10b981", hover_color="#059669")
            self._log_sensor_msg("[System] Disconnected from serial port.")
        else:
            port = self.port_menu.get()
            baud = self.baud_menu.get()
            if "No COM Ports" in port:
                self._log_sensor_msg("[Error] No valid COM port selected.")
                return

            try:
                self.serial_port = serial.Serial(port, int(baud), timeout=1)
                self.is_serial_connected = True
                self.connect_btn.configure(text="Disconnect", fg_color="#ef4444", hover_color="#dc2626")
                self._log_sensor_msg(f"[System] Connected to {port} at {baud} baud. Awaiting sensor stream...")

                self.serial_thread = threading.Thread(target=self._read_serial_loop, daemon=True)
                self.serial_thread.start()
            except Exception as e:
                self._log_sensor_msg(f"[Error] Failed to connect: {str(e)}")

    def _read_serial_loop(self):
        while self.is_serial_connected and self.serial_port and self.serial_port.is_open:
            try:
                raw_line = self.serial_port.readline()
                if raw_line:
                    line = raw_line.decode('utf-8', errors='replace').strip()
                    if line:
                        self.after(0, self._log_sensor_msg, line)
                        try:
                            val = float(line)
                            self.sensor_data_points.append(val)
                        except ValueError:
                            pass
            except Exception:
                break

    def _log_sensor_msg(self, msg: str):
        if hasattr(self, 'sensor_log') and self.sensor_log.winfo_exists():
            self.sensor_log.insert("end", msg + "\n")
            self.sensor_log.see("end")

    def _plot_sensor_stream(self):
        if not self.sensor_data_points:
            self._log_sensor_msg("[System] No numeric sensor data points recorded yet to plot.")
            return

        self._switch_view("graph")
        lines = [f"Sample {i + 1}, {v}" for i, v in enumerate(self.sensor_data_points)]

        self.graph_data_editor.delete("1.0", "end")
        self.graph_data_editor.insert("1.0", "\n".join(lines))

        self._plot_custom_graph()


# =====================================================================
# ENTRY POINT
# =====================================================================

if __name__ == "__main__":
    app = CalcCoreUltima()
    app.mainloop()
