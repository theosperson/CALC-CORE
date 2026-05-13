import pygame
import os
import sys
import re
import random

# --- MECHANICAL CONFIG ---
VERSION = "Star AI // CALC-CORE"
THEME_COLOR = (0, 255, 180)
BG_COLOR = (5, 8, 12)


class StarAI:
    def __init__(self):
        pygame.init()
        self.w, self.h = 850, 480
        self.screen = pygame.display.set_mode((self.w, self.h))
        pygame.display.set_caption(VERSION)

        self.font = pygame.font.SysFont("Consolas", 20)
        self.font_b = pygame.font.SysFont("Consolas", 24, bold=True)
        self.clock = pygame.time.Clock()

        self.user_text = ""
        self.feed = [("Star AI", "CALC-CORE ONLINE. SYSTEM STABLE.")]
        self.shake = 0
        self.cursor_visible = True
        self.last_toggle = pygame.time.get_ticks()

    def rumble(self, intensity):
        self.shake = intensity

    def solve(self, text):
        """Extracts math from natural language to prevent image_2026-05-13_133329661.png errors."""
        self.rumble(10)
        # Normalize: 'x' to '*' and remove fluff
        clean = text.lower().replace('x', '*')
        # Find only the sequence of numbers and operators
        math_match = re.findall(r'[\d\+\-\*\/\.\(\)\%]+', clean)
        expr = "".join(math_match)

        if not expr or not any(char.isdigit() for char in expr):
            return "ERROR: NO NUMERIC DATA DETECTED"

        try:
            # Safe evaluation of the extracted expression
            result = eval(expr, {"__builtins__": None}, {})
            # Format result: float if has decimals, else int
            formatted_res = f"{result:.4f}".rstrip('0').rstrip('.') if '.' in str(result) else result
            return f"CALCULATION: {formatted_res}"
        except ZeroDivisionError:
            return "ERROR: MATH VIOLATION (DIV BY 0)"
        except Exception:
            return "ERROR: SYNTAX FAILURE"

    def draw_ui(self):
        offset = [random.randint(-self.shake, self.shake),
                  random.randint(-self.shake, self.shake)] if self.shake > 0 else [0, 0]
        if self.shake > 0: self.shake -= 1

        self.screen.fill(BG_COLOR)

        # High-Density Scanlines
        for i in range(0, self.h, 3):
            pygame.draw.line(self.screen, (10, 15, 20), (0, i), (self.w, i))

        # Header
        self.screen.blit(self.font_b.render(VERSION, True, THEME_COLOR), (25 + offset[0], 20 + offset[1]))

        # Display Box
        pygame.draw.rect(self.screen, THEME_COLOR, (20 + offset[0], 70 + offset[1], self.w - 40, self.h - 180), 1)

        y = 100 + offset[1]
        for name, msg in self.feed[-6:]:
            color = THEME_COLOR if name == "Star AI" else (150, 180, 255)
            prefix = self.font_b.render(f"[{name}] ", True, color)
            self.screen.blit(prefix, (45 + offset[0], y))

            content = self.font.render(msg, True, (230, 230, 230))
            self.screen.blit(content, (45 + prefix.get_width() + offset[0], y))
            y += 45

        # Input Bay
        input_y = self.h - 80 + offset[1]
        pygame.draw.rect(self.screen, (15, 22, 32), (20 + offset[0], input_y, self.w - 40, 60))
        pygame.draw.rect(self.screen, THEME_COLOR, (20 + offset[0], input_y, self.w - 40, 60), 2)

        if pygame.time.get_ticks() - self.last_toggle > 400:
            self.cursor_visible = not self.cursor_visible
            self.last_toggle = pygame.time.get_ticks()

        txt = self.user_text + ("█" if self.cursor_visible else " ")
        self.screen.blit(self.font.render(txt, True, (255, 255, 255)), (45 + offset[0], input_y + 18))

    def run(self):
        while True:
            self.draw_ui()
            for event in pygame.event.get():
                if event.type == pygame.QUIT: pygame.quit(); sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN and self.user_text.strip():
                        self.feed.append(("USER", self.user_text))
                        self.feed.append(("Star AI", self.solve(self.user_text)))
                        self.user_text = ""
                    elif event.key == pygame.K_BACKSPACE:
                        self.user_text = self.user_text[:-1]
                    else:
                        if len(self.user_text) < 55: self.user_text += event.unicode
            pygame.display.flip()
            self.clock.tick(60)


if __name__ == "__main__":
    StarAI().run()

