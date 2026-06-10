import math
import os
import random
import time
from pathlib import Path

import tkinter as tk
import tkinter.font as tkfont

from PIL import Image, ImageTk

import pygame  


WIDTH = 800
HEIGHT = 780  # 세로 확장
UI_HEIGHT = 50

STAGE_COUNT = 5

# 벽돌 배치: 행 수 증가, 가로 간격 축소
BRICK_ROWS = 6
BRICK_COLS = 10
BRICK_GAP_X = 5
BRICK_GAP_Y = 10
BRICK_MARGIN_X = 24
BRICK_START_Y = 80
BRICK_HEIGHT = 28
BRICK_WIDTH = (WIDTH - BRICK_MARGIN_X * 2 - BRICK_GAP_X * (BRICK_COLS - 1)) // BRICK_COLS

PADDLE_Y = HEIGHT - 80
PADDLE_WIDTH = 120
PADDLE_HEIGHT = 16
PADDLE_SPEED = 18.2  # 기존 대비 1.3배 수준

BALL_RADIUS = 9
BALL_BASE_SPEED = 6.0  # 기존 대비 1.2배 수준
FPS_DELAY_MS = 13

UI_BOX_HEIGHT = 24
UI_BOX_Y_TOP = 10
UI_BOX_Y_BOTTOM = UI_BOX_Y_TOP + UI_BOX_HEIGHT + 4
UI_RIGHT_BOX_WIDTH = 150
UI_LIFE_X = WIDTH - UI_RIGHT_BOX_WIDTH - 10
UI_HIGH_SCORE_X = 10

STAGE_SPEED_STEP = 0.04
FEAR_HIDE_MIN = 0.5
FEAR_HIDE_MAX = 3.0
FEAR_HIDDEN_DURATION = 0.5

ITEM_MSG_DURATION = 0.4
PADDLE_EFFECT_DURATION = 5.0
EMOTION_EXPLOSION_CHAIN = 3
EMOTION_LOCK_DURATION = 5.0


def clamp(value, low, high):
    return max(low, min(high, value))


def angle_to_vector(angle_deg, speed):
    rad = math.radians(angle_deg)
    return math.cos(rad) * speed, math.sin(rad) * speed


def find_asset_path(filename):
    base_dir = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
    candidates = [
        base_dir / filename,
        base_dir / "assets" / "image" / filename,
        base_dir / "assets" / "images" / filename,
        base_dir / "images" / filename,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


class FloatingMessage:
    def __init__(self, canvas, text, color, created_at, duration=ITEM_MSG_DURATION, font_size=24):
        self.canvas = canvas
        self.text = text
        self.color = color
        self.created_at = created_at
        self.duration = duration
        self.font_size = font_size 
        self.item_id = None

    def draw(self):
        if self.item_id is None:
            self.item_id = self.canvas.create_text(
                WIDTH // 2,
                HEIGHT // 2 - 120,
                text=self.text,
                fill=self.color,
                font=("Arial", self.font_size, "bold"),
                tags=("overlay",),
            )

    def expired(self, now):
        return now - self.created_at >= self.duration


class EmotionChainSystem:
    def __init__(self):
        self.chain_count = 0
        self.last_emotion = None
        self.pending_explosion = False

    def add_chain(self, emotion):
        if self.last_emotion == emotion:
            self.chain_count += 1
        else:
            self.chain_count = 1
            self.last_emotion = emotion
        return self.chain_count

    def arm_pending_explosion(self):
        if self.chain_count >= EMOTION_EXPLOSION_CHAIN:
            self.pending_explosion = True

    def consume_pending_explosion(self):
        armed = self.pending_explosion
        self.pending_explosion = False
        return armed

    def clear_pending_explosion(self):
        self.pending_explosion = False

    def penalty_after_explosion(self):
        self.chain_count = max(0, self.chain_count - 3)


class ScoreManager:
    def __init__(self):
        self.total_score = 0

    def add_score(self, points):
        self.total_score += points



class Paddle:
    def __init__(self, canvas):
        self.canvas = canvas
        self.x = (WIDTH - PADDLE_WIDTH) / 2
        self.y = PADDLE_Y
        self.base_width = PADDLE_WIDTH
        self.height = PADDLE_HEIGHT
        self.speed = PADDLE_SPEED
        self.move_left_flag = False
        self.move_right_flag = False
        self.scale = 1.0
        self.active_effects = {}
        self.effect_until = 0.0
        self.effect_type = None
        self.id = self.canvas.create_rectangle(
            self.x,
            self.y,
            self.x + self.base_width,
            self.y + self.height,
            fill="white",
            outline="white",
            tags=("game",),
        )

    @property
    def width(self):
        return self.base_width * self.scale

    def apply_effect(self, effect_type, factor, now, duration):
        if effect_type in self.active_effects:
            old_factor, _ = self.active_effects.pop(effect_type)
            self.scale /= old_factor
        self.scale *= factor
        self.active_effects[effect_type] = (factor, now + duration)
        self.effect_until = now + duration
        self.effect_type = effect_type

    def set_scale(self, scale, now, duration=0.0, effect_type=None):
        if effect_type is None:
            effect_type = f"scale_{len(self.active_effects) + 1}"
        if duration <= 0:
            self.scale = scale
            self.active_effects[effect_type] = (scale, now)
            self.effect_until = 0.0
            self.effect_type = effect_type
            return
        self.apply_effect(effect_type, scale, now, duration)

    def update_effect(self, now):
        expired = []
        for effect_type, (factor, until) in list(self.active_effects.items()):
            if now >= until:
                expired.append((effect_type, factor))
        for effect_type, factor in expired:
            if effect_type in self.active_effects:
                self.active_effects.pop(effect_type, None)
                if factor != 0:
                    self.scale /= factor
        if not self.active_effects:
            self.effect_until = 0.0
            self.effect_type = None
        self.scale = clamp(self.scale, 0.3, 3.0)

    def update(self, now):
        self.update_effect(now)
        if self.move_left_flag:
            self.x -= self.speed
        if self.move_right_flag:
            self.x += self.speed
        self.x = clamp(self.x, 0, WIDTH - self.width)
        self.canvas.coords(self.id, self.x, self.y, self.x + self.width, self.y + self.height)


class Ball:
    def __init__(self, canvas, x, y, radius=BALL_RADIUS, is_main=True):
        self.canvas = canvas
        self.x = x
        self.y = y
        self.prev_x = x
        self.prev_y = y
        self.radius = radius
        self.is_main = is_main
        self.is_clone = not is_main
        self.affects_emotion = bool(is_main)
        self.attached = bool(is_main)
        self.vx = 0.0
        self.vy = 0.0
        self.emotion = "NORMAL"
        self.emotion_locked_until = 0.0
        self.emotion_lock_value = None
        self.emotion_speed_bonus = 0.0  # joy 계열
        self.item_speed_bonus = 0.0
        self.fear_escape_armed = True
        self.id = self.canvas.create_oval(
            self.x - self.radius,
            self.y - self.radius,
            self.x + self.radius,
            self.y + self.radius,
            fill="cyan",
            outline="white",
            tags=("game",),
        )
        if self.is_clone:
            self.canvas.itemconfig(self.id, fill="white")

    def current_speed_multiplier(self):
        base = 1.0 + self.emotion_speed_bonus + self.item_speed_bonus
        if self.emotion == "ANGER":
            return base * 1.3
        if self.emotion == "JOY":
            return base * 1.0
        if self.emotion == "FEAR":
            return base * 0.95
        if self.emotion == "SURPRISE":
            return base * 1.0
        return base

    def set_emotion(self, emotion, now, lock=False, lock_duration=0.0):
        if self.emotion_lock_value is not None and now < self.emotion_locked_until:
            return
        self.emotion = emotion
        color_map = {
            "ANGER": "red",
            "JOY": "yellow",
            "FEAR": "purple",
            "SURPRISE": "pink",
            "NORMAL": "cyan",
        }
        self.canvas.itemconfig(self.id, fill=color_map.get(emotion, "cyan"))
        self.fear_escape_armed = emotion == "FEAR"
        if lock:
            self.emotion_lock_value = emotion
            self.emotion_locked_until = now + lock_duration

    def maybe_unlock_emotion(self, now):
        if self.emotion_lock_value is not None and now >= self.emotion_locked_until:
            self.emotion_lock_value = None
            self.emotion_locked_until = 0.0

    def launch_from_paddle(self, stage_multiplier):
        speed = BALL_BASE_SPEED * stage_multiplier * self.current_speed_multiplier()
        angle = random.uniform(240, 300)  # 위쪽 방향
        vx, vy = angle_to_vector(angle, speed)
        if abs(vx) < 1.8:
            vx = 1.8 * (-1 if random.random() < 0.5 else 1)
        self.vx = vx
        self.vy = vy
        self.attached = False

    def attach_to_paddle(self, paddle_x, paddle_width, paddle_y):
        self.attached = True
        self.vx = 0.0
        self.vy = 0.0
        self.x = paddle_x + paddle_width / 2
        self.y = paddle_y - self.radius - 2
        self.redraw()

    def move_with_velocity(self):
        if self.attached:
            return
        self.prev_x = self.x
        self.prev_y = self.y
        self.x += self.vx
        self.y += self.vy

    def redraw(self):
        self.canvas.coords(
            self.id,
            self.x - self.radius,
            self.y - self.radius,
            self.x + self.radius,
            self.y + self.radius,
        )

    def set_velocity_by_angle(self, angle_deg, speed=None):
        if speed is None:
            speed = math.hypot(self.vx, self.vy)
            if speed == 0:
                speed = BALL_BASE_SPEED
        self.vx, self.vy = angle_to_vector(angle_deg, speed)

    def set_speed_preserve_direction(self, new_speed):
        speed = math.hypot(self.vx, self.vy)
        if speed == 0:
            return
        scale = new_speed / speed
        self.vx *= scale
        self.vy *= scale

    def launch_clone_random(self, stage_multiplier):
        speed = BALL_BASE_SPEED * stage_multiplier
        angle = random.uniform(235, 305)
        vx, vy = angle_to_vector(angle, speed)
        if vy > 0:
            vy *= -1
        self.vx = vx
        self.vy = vy
        self.attached = False

    def randomize_direction_small(self, min_deg=5, max_deg=30):
        if self.attached:
            return
        angle = math.degrees(math.atan2(self.vy, self.vx))
        delta = random.uniform(min_deg, max_deg) * random.choice([-1, 1])
        angle += delta
        speed = math.hypot(self.vx, self.vy)
        self.vx, self.vy = angle_to_vector(angle, speed)


class Brick:
    def __init__(self, x, y, emotion, hp, score_value, color, image_dict=None):
        self.x = x
        self.y = y
        self.w = BRICK_WIDTH
        self.h = BRICK_HEIGHT
        self.emotion = emotion
        self.max_hp = hp
        self.hp = float(hp)
        self.score_value = score_value
        self.color = color
        self.destroyed = False
        self.visible = True
        self.canvas_item = None
        self.crack_item = None
        self.image_dict = image_dict or {}
        self.finalized = False

    def _hp_level(self):
        if self.max_hp >= 3:
            return 3 if self.hp >= 3 else 2 if self.hp >= 2 else 1
        if self.max_hp == 2:
            return 2 if self.hp >= 2 else 1
        return 1

    def _image_key(self):
        if self.emotion == "anger":
            return f"anger_hp{self._hp_level()}"
        if self.emotion == "joy":
            return "joy"
        if self.emotion == "fear":
            return "fear"
        if self.emotion == "surprise":
            return f"surprise_hp{2 if self.hp >= 2 else 1}"
        return None

    def _image_obj(self):
        key = self._image_key()
        if key is None:
            return None
        return self.image_dict.get(key)

    def draw(self, canvas):
        if self.destroyed or not self.visible:
            if self.canvas_item is not None:
                canvas.itemconfigure(self.canvas_item, state="hidden")
            if self.crack_item is not None:
                canvas.itemconfigure(self.crack_item, state="hidden")
            return

        image_obj = self._image_obj()
        if self.canvas_item is None:
            if image_obj is not None:
                self.canvas_item = canvas.create_image(
                    self.x + self.w / 2,
                    self.y + self.h / 2,
                    image=image_obj,
                    tags=("game",),
                )
                self.crack_item = None
            else:
                self.canvas_item = canvas.create_rectangle(
                    self.x, self.y, self.x + self.w, self.y + self.h,
                    fill=self.color, outline="white", width=1, tags=("game",)
                )
                self.crack_item = canvas.create_text(
                    self.x + self.w / 2,
                    self.y + self.h / 2,
                    text="",
                    fill="white",
                    font=("Arial", 10, "bold"),
                    tags=("game",)
                )
        else:
            if image_obj is not None:
                canvas.itemconfigure(self.canvas_item, image=image_obj, state="normal")
                if self.crack_item is not None:
                    canvas.itemconfigure(self.crack_item, state="hidden")
            else:
                canvas.itemconfigure(self.canvas_item, state="normal")
                if self.crack_item is not None:
                    canvas.itemconfigure(self.crack_item, state="normal")
                    if self.max_hp >= 3:
                        crack_text = "III" if self.hp >= 3 else "II" if self.hp >= 2 else "I"
                    elif self.max_hp == 2:
                        crack_text = "II" if self.hp >= 2 else "I"
                    else:
                        crack_text = ""
                    canvas.itemconfigure(self.crack_item, text=crack_text)

        if self.crack_item is not None and image_obj is None:
            if self.max_hp >= 3:
                crack_text = "III" if self.hp >= 3 else "II" if self.hp >= 2 else "I"
            elif self.max_hp == 2:
                crack_text = "II" if self.hp >= 2 else "I"
            else:
                crack_text = ""
            canvas.itemconfigure(self.crack_item, text=crack_text)

    def remove(self, canvas):
        self.destroyed = True
        self.visible = False
        if self.canvas_item is not None:
            canvas.itemconfigure(self.canvas_item, state="hidden")
        if self.crack_item is not None:
            canvas.itemconfigure(self.crack_item, state="hidden")

    def hit(self, damage):
        if self.destroyed:
            return False
        self.hp -= damage
        if self.hp <= 0:
            self.destroyed = True
            self.visible = False
            return True
        return False


class FearBrick(Brick):

    def __init__(self, x, y, now, image_dict=None):
        super().__init__(x, y, "fear", 1, 80, "#5c4b99", image_dict)
        self.next_toggle_at = now + random.uniform(FEAR_HIDE_MIN, FEAR_HIDE_MAX)
        self.hidden_until = None

    def update_visibility(self, now):
        if self.destroyed:
            return
        if self.visible and now >= self.next_toggle_at:
            self.visible = False
            self.hidden_until = now + FEAR_HIDDEN_DURATION
        elif (not self.visible) and self.hidden_until is not None and now >= self.hidden_until:
            self.visible = True
            self.next_toggle_at = now + random.uniform(FEAR_HIDE_MIN, FEAR_HIDE_MAX)
            self.hidden_until = None

    def draw(self, canvas):
        super().draw(canvas)


class SurpriseBrick(Brick):
    def __init__(self, x, y, image_dict=None):
        super().__init__(x, y, "surprise", 2, 70, "#ff8fcf", image_dict)


class ItemDrop:
    COLOR_MAP = {
        "multi_ball": "hot pink",
        "life": "orange",
        "paddle_up": "yellow",
        "paddle_down": "red",
    }

    def __init__(self, canvas, x, y, kind):
        self.canvas = canvas
        self.kind = kind
        self.x = x
        self.y = y
        self.radius = BALL_RADIUS
        self.side = self.radius * 2
        self.speed = 1.8
        self.active = True
        half = self.side / 2
        self.id = self.canvas.create_rectangle(
            self.x - half, self.y - half,
            self.x + half, self.y + half,
            fill=self.COLOR_MAP[kind],
            outline="white",
            tags=("game",)
        )

    def update(self):
        if not self.active:
            return
        self.y += self.speed
        half = self.side / 2
        self.canvas.coords(
            self.id,
            self.x - half, self.y - half,
            self.x + half, self.y + half,
        )

    def remove(self):
        self.active = False
        self.canvas.delete(self.id)



class EmotionDestroyer:
    def __init__(self):
        self.root = tk.Tk()

        pygame.mixer.init()
        pygame.mixer.music.load("assets/sounds/freesound_community-8bit-music-for-game-68698.mp3")
        pygame.mixer.music.set_volume(0.5)
        pygame.mixer.music.play(-1)

        self.root.title("감정 파괴자")
        self.canvas = tk.Canvas(self.root, width=WIDTH, height=HEIGHT, bg="black")
        self.canvas.pack()

        self.brick_images = self.load_brick_images()

        self.high_score = 0
        self.stage_timer_start = None
        self.stage_timer_frozen = None

        self.ui_font = tkfont.Font(family="Arial", size=14, weight="bold")
        self.ui_font_small = tkfont.Font(family="Arial", size=12, weight="bold")

        self.root.bind("<Left>", self.key_left_press)
        self.root.bind("<Right>", self.key_right_press)
        self.root.bind("a", self.key_left_press)
        self.root.bind("d", self.key_right_press)
        self.root.bind("<KeyRelease-Left>", self.key_left_release)
        self.root.bind("<KeyRelease-Right>", self.key_right_release)
        self.root.bind("<KeyRelease-a>", self.key_left_release)
        self.root.bind("<KeyRelease-d>", self.key_right_release)
        self.root.bind("<space>", self.space_handler)
        self.root.bind("r", self.restart_game)
        self.root.bind("R", self.restart_game)

        self.reset_game(full_reset=True)
        self.run()
        self.root.mainloop()

    def game_now(self):
        if self.pause_started_at is not None:
            return self.pause_started_at - self.paused_total
        return time.time() - self.paused_total

    def current_elapsed_time(self):
        if self.stage_timer_frozen is not None:
            return self.stage_timer_frozen
        if self.stage_timer_start is None:
            return 0.0
        return max(0.0, self.game_now() - self.stage_timer_start)

    def format_elapsed_time(self):
        elapsed = self.current_elapsed_time()
        total_cs = int(round(elapsed * 100))
        minutes = total_cs // 6000
        seconds = (total_cs // 100) % 60
        centis = total_cs % 100
        return f"{minutes:02d}.{seconds:02d}"

    def freeze_timer(self):
        if self.stage_timer_start is not None and self.stage_timer_frozen is None:
            self.stage_timer_frozen = self.current_elapsed_time()

    def start_timer_if_needed(self):
        if self.stage_timer_start is None and self.stage == 1:
            self.stage_timer_start = self.game_now()
            self.stage_timer_frozen = None

    def update_high_score(self, final_score=None):
        if final_score is None:
            final_score = self.score_manager.total_score
        if final_score > self.high_score:
            self.high_score = final_score

    def compute_clear_time_bonus(self):
        elapsed = self.current_elapsed_time()
        if elapsed < 600:
            return 20000
        if elapsed < 900:
            return 15000
        if elapsed < 1200:
            return 10000
        if elapsed < 1500:
            return 5000
        return 0

    def _measure_text_width(self, text, font_obj=None):
        if font_obj is None:
            font_obj = self.ui_font
        return font_obj.measure(text)

    def _create_or_update_text(self, item_id, x, y, text, fill="white", font=None, tags=("ui",)):
        if font is None:
            font = self.ui_font
        if item_id is None:
            return self.canvas.create_text(x, y, text=text, fill=fill, font=font, tags=tags)
        self.canvas.coords(item_id, x, y)
        self.canvas.itemconfig(item_id, text=text, fill=fill, font=font)
        return item_id

    def _create_or_update_rect(self, item_id, x1, y1, x2, y2, fill="white", outline="black", tags=("ui",)):
        if item_id is None:
            return self.canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, tags=tags)
        self.canvas.coords(item_id, x1, y1, x2, y2)
        self.canvas.itemconfig(item_id, fill=fill, outline=outline)
        return item_id

    def _create_ui_items(self):
        self.score_text = self.canvas.create_text(90, 22, fill="white", text="Score: 0", font=self.ui_font, tags=("ui",))
        self.chain_text = self.canvas.create_text(250, 22, fill="white", text="Chain: 0", font=self.ui_font, tags=("ui",))
        self.emotion_text = self.canvas.create_text(560, 22, fill="cyan", text="NORMAL", font=self.ui_font, tags=("ui",))

        self.life_box_rect = self.canvas.create_rectangle(
            UI_LIFE_X, UI_BOX_Y_TOP, UI_LIFE_X + UI_RIGHT_BOX_WIDTH, UI_BOX_Y_TOP + UI_BOX_HEIGHT,
            fill="black", outline="black", tags=("ui",)
        )
        self.life_box_text = self.canvas.create_text(
            UI_LIFE_X + UI_RIGHT_BOX_WIDTH / 2, UI_BOX_Y_TOP + UI_BOX_HEIGHT / 2,
            fill="white", text="Life: 3", font=self.ui_font, tags=("ui",)
        )

        self.time_box_rect = self.canvas.create_rectangle(
            UI_LIFE_X, UI_BOX_Y_BOTTOM, UI_LIFE_X + UI_RIGHT_BOX_WIDTH, UI_BOX_Y_BOTTOM + UI_BOX_HEIGHT,
            fill="black", outline="black", tags=("ui",)
        )
        self.time_box_text = self.canvas.create_text(
            UI_LIFE_X + UI_RIGHT_BOX_WIDTH / 2, UI_BOX_Y_BOTTOM + UI_BOX_HEIGHT / 2,
            fill="white", text="걸린 시간 : 00.00", font=self.ui_font, tags=("ui",)
        )

        high_text = f"최고 점수 : {self.high_score}점"
        high_width = max(120, int(self._measure_text_width(high_text, self.ui_font) * 1.1))
        self.high_score_box_rect = self.canvas.create_rectangle(
            UI_HIGH_SCORE_X, UI_BOX_Y_BOTTOM, UI_HIGH_SCORE_X + high_width, UI_BOX_Y_BOTTOM + UI_BOX_HEIGHT,
            fill="black", outline="black", tags=("ui",)
        )
        self.high_score_box_text = self.canvas.create_text(
            UI_HIGH_SCORE_X + high_width / 2, UI_BOX_Y_BOTTOM + UI_BOX_HEIGHT / 2,
            fill="white", text=high_text, font=self.ui_font, tags=("ui",)
        )

    def _create_side_walls(self):
        self.side_wall_width = BRICK_MARGIN_X

    def find_asset_path(self, filename):
        base_dir = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
        candidates = [
            base_dir / filename,
            base_dir / "assets" / "image" / filename,
            base_dir / "assets" / "images" / filename,
            base_dir / "images" / filename,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def load_brick_images(self):
        image_files = {
            "anger_hp1": "anger1.png",
            "anger_hp2": "anger2.png",
            "anger_hp3": "anger3.png",
            "fear": "fear.png",
            "joy": "joy.png",
            "surprise_hp1": "surprise1.png",
            "surprise_hp2": "surprise2.png",
        }
        loaded = {}
        resample = getattr(Image, "Resampling", Image).LANCZOS
        for key, filename in image_files.items():
            path = self.find_asset_path(filename)
            if path is None:
                loaded[key] = None
                continue
            try:
                img = Image.open(path).convert("RGBA").resize((BRICK_WIDTH+33, BRICK_HEIGHT+33), resample)
                loaded[key] = ImageTk.PhotoImage(img)
            except Exception:
                loaded[key] = None
        return loaded

    def reset_game(self, full_reset=True, preserve_score=False, preserve_lives=False, preserve_stage=False):
        if hasattr(self, "canvas"):
            self.canvas.delete("all")

        if full_reset:
            self.stage = 1
            self.lives = 3
            self.score_manager = ScoreManager()
            self.chain_system = EmotionChainSystem()
            self.emotion_counts = {"anger": 0, "joy": 0, "fear": 0, "surprise": 0}
        else:
            if not preserve_stage:
                self.stage = 1
            if not preserve_lives:
                self.lives = 3
            if not preserve_score:
                self.score_manager = ScoreManager()
            if not hasattr(self, "chain_system"):
                self.chain_system = EmotionChainSystem()

        self.stage_speed_multiplier = 1.10 + (self.stage - 1) * STAGE_SPEED_STEP
        self.chain_system.clear_pending_explosion()
        self.game_running = True
        self.state = "stage_intro"
        self.stage_started = False
        self.stage_cleared = False

        self.paused_total = 0.0
        self.pause_started_at = None
        self.pending_main_launch_at = None
        self.stage_timer_frozen = None
        self.stage_timer_start = None
        self.clear_time_bonus = 0
        self.chain_system.clear_pending_explosion()

        self.messages = []
        self.items = []
        self.balls = []

        self._create_side_walls()
        self.paddle = Paddle(self.canvas)
        self.main_ball = Ball(self.canvas, self.paddle.x + self.paddle.width / 2, self.paddle.y - 20, is_main=True)
        self.main_ball.attach_to_paddle(self.paddle.x, self.paddle.width, self.paddle.y)
        self.balls.append(self.main_ball)

        self.bricks = []
        self.create_stage()

        self._create_ui_items()
        self.show_stage_intro()
        self.update_ui()

    def create_stage(self):
        now = self.game_now()
        emotions = ["anger", "joy", "fear", "surprise"]
        for r in range(BRICK_ROWS):
            for c in range(BRICK_COLS):
                x = BRICK_MARGIN_X + c * (BRICK_WIDTH + BRICK_GAP_X)
                y = BRICK_START_Y + r * (BRICK_HEIGHT + BRICK_GAP_Y)
                emotion = random.choice(emotions)
                if emotion == "anger":
                    brick = Brick(x, y, "anger", 3, 100, "#a53d3d", self.brick_images)
                elif emotion == "joy":
                    brick = Brick(x, y, "joy", 1, 60, "#d8d23f", self.brick_images)
                elif emotion == "fear":
                    brick = FearBrick(x, y, now, self.brick_images)
                else:
                    brick = SurpriseBrick(x, y, self.brick_images)
                self.bricks.append(brick)
                brick.draw(self.canvas)

    def show_stage_intro(self):
        self.state = "stage_intro"
        self.clear_overlay()
        self.draw_overlay_text(
            f"스테이지 {self.stage}",
            "스페이스 바를 눌러 시작",
            main_color="white",
            sub_color="gray",
            main_size=36,
            sub_size=18,
        )
        self.main_ball.attach_to_paddle(self.paddle.x, self.paddle.width, self.paddle.y)
        self.pending_main_launch_at = None

    def show_pause_overlay(self):
        self.clear_overlay()
        self.draw_overlay_text(
            "게임 중지됨",
            "스페이스 바를 눌러 다시 시작",
            main_color="white",
            sub_color="gray",
            main_size=36,
            sub_size=18,
        )

    def show_game_clear(self):
        self.state = "game_clear"
        self.freeze_timer()
        self.clear_time_bonus = self.compute_clear_time_bonus()
        self.update_high_score(self.score_manager.total_score + self.clear_time_bonus)
        self.clear_overlay()

        panel_w = int(WIDTH * 0.6)
        panel_h = int(HEIGHT * 0.6)
        x0 = (WIDTH - panel_w) / 2
        y0 = (HEIGHT - panel_h) / 2
        x1 = x0 + panel_w
        y1 = y0 + panel_h

        self.canvas.create_rectangle(x0, y0, x1, y1, fill="white", outline="black", tags=("overlay",))

        restart_base = 18
        score_bonus = self.clear_time_bonus
        score_line = f"점수 : {self.score_manager.total_score}점"
        if score_bonus > 0:
            score_line = f"점수 : {self.score_manager.total_score}점  시간 보너스 +{score_bonus}점"

        texts = [
            "축하합니다!",
            "게임 클리어!",
            f"걸린 시간 : {self.format_elapsed_time()}",
            score_line,
            "R키를 눌러 재시작",
        ]

        base_sizes = [
            restart_base * 1.8,
            restart_base * 1.8,
            restart_base * 0.45,
            restart_base * (0.9 if score_bonus == 0 else 0.45),
            restart_base,
        ]

        scale = 1.0
        while True:
            sizes = [max(1, int(round(s * scale))) for s in base_sizes]
            fonts = [tkfont.Font(family="Arial", size=size, weight="bold") for size in sizes]
            widths = [font.measure(text_item) for font, text_item in zip(fonts, texts)]
            heights = [font.metrics("linespace") for font in fonts]
            gaps = [
                max(4, int(heights[0] * 0.14)),
                max(3, int(heights[1] * 0.14)),
                max(3, int(heights[2] * 0.18)),
                max(3, int(heights[3] * 0.14)),
            ]
            total_h = sum(heights) + sum(gaps)
            max_w = max(widths)
            if (max_w <= panel_w * 0.90 and total_h <= panel_h * 0.90) or scale <= 0.25:
                break
            scale *= 0.95

        center_x = (x0 + x1) / 2
        y = y0 + (panel_h - total_h) / 2
        for idx, (text_item, font, h) in enumerate(zip(texts, fonts, heights)):
            self.canvas.create_text(center_x, y + h / 2, text=text_item, fill="black", font=font, tags=("overlay",))
            if idx < len(gaps):
                y += h + gaps[idx]

    def show_game_over(self):
        self.state = "game_over"
        self.freeze_timer()
        self.update_high_score()
        self.clear_overlay()

        panel_w = int(WIDTH * 0.4)
        panel_h = int(HEIGHT * 0.4)
        x0 = (WIDTH - panel_w) / 2
        y0 = (HEIGHT - panel_h) / 2
        x1 = x0 + panel_w
        y1 = y0 + panel_h

        self.canvas.create_rectangle(x0, y0, x1, y1, fill="black", outline="white", tags=("overlay",))

        restart_base = 16
        base_sizes = [restart_base * 1.8, restart_base * 0.45, restart_base * 0.9, restart_base]
        texts = [
            "게임 종료",
            f"걸린 시간 : {self.format_elapsed_time()}",
            f"점수 : {self.score_manager.total_score}점",
            "R키를 눌러 재시작",
        ]

        scale = 1.0
        while True:
            sizes = [max(1, int(round(s * scale))) for s in base_sizes]
            fonts = [tkfont.Font(family="Arial", size=size, weight="bold") for size in sizes]
            widths = [font.measure(text) for font, text in zip(fonts, texts)]
            heights = [font.metrics("linespace") for font in fonts]
            total_h = sum(heights) + int(heights[0] * 0.18) + int(heights[1] * 0.25) + int(heights[2] * 0.25)
            max_w = max(widths)
            if (max_w <= panel_w * 0.88 and total_h <= panel_h * 0.88) or scale <= 0.25:
                break
            scale *= 0.95

        center_x = (x0 + x1) / 2
        y = y0 + (panel_h - total_h) / 2
        spacings = [int(heights[0] * 0.18), int(heights[1] * 0.25), int(heights[2] * 0.25), 0]
        for idx, (text, font, h) in enumerate(zip(texts, fonts, heights)):
            self.canvas.create_text(
                center_x,
                y + h / 2,
                text=text,
                fill="white",
                font=font,
                tags=("overlay",),
            )
            if idx < len(spacings):
                y += h + spacings[idx]

    def clear_overlay(self):
        self.canvas.delete("overlay")

    def draw_overlay_text(self, main_text, sub_text, main_color="white", sub_color="gray", main_size=36, sub_size=18):
        self.canvas.create_text(
            WIDTH // 2, HEIGHT // 2 - 30,
            text=main_text,
            fill=main_color,
            font=("Arial", main_size, "bold"),
            tags=("overlay",),
        )
        self.canvas.create_text(
            WIDTH // 2, HEIGHT // 2 + 25,
            text=sub_text,
            fill=sub_color,
            font=("Arial", sub_size, "bold"),
            tags=("overlay",),
        )

    def add_message(self, text, color):
        msg = FloatingMessage(self.canvas, text, color, created_at=self.game_now())
        msg.draw()
        self.messages.append(msg)

    def spawn_item(self, x, y):
        kind = random.choice(["multi_ball", "life", "paddle_up", "paddle_down"])
        self.items.append(ItemDrop(self.canvas, x, y, kind))

    def apply_item(self, kind):
        now = self.game_now()
        if kind == "multi_ball":
            self.spawn_surprise_multiball()
            self.add_message("서프라이즈 멀티볼!", "hot pink")
        elif kind == "life":
            self.lives += 1
            self.add_message("목숨 추가!", "orange")
        elif kind == "paddle_up":
            self.paddle.apply_effect("up", 1.5, now, PADDLE_EFFECT_DURATION)
            self.add_message("늘어나라!", "yellow")
        elif kind == "paddle_down":
            self.paddle.apply_effect("down", 0.66, now, PADDLE_EFFECT_DURATION)
            self.add_message("짧아져라!", "red")

    def spawn_surprise_multiball(self):
        base_x = self.main_ball.x if self.main_ball else self.paddle.x + self.paddle.width / 2
        base_y = self.main_ball.y if self.main_ball else self.paddle.y - 20
        for _ in range(2):
            clone = Ball(self.canvas, base_x, base_y, is_main=False)
            clone.affects_emotion = False
            clone.emotion = "NORMAL"
            self.canvas.itemconfig(clone.id, fill="white")
            clone.launch_clone_random(self.stage_speed_multiplier)
            self.balls.append(clone)

    def key_left_press(self, event=None):
        self.paddle.move_left_flag = True

    def key_right_press(self, event=None):
        self.paddle.move_right_flag = True

    def key_left_release(self, event=None):
        self.paddle.move_left_flag = False

    def key_right_release(self, event=None):
        self.paddle.move_right_flag = False

    def restart_game(self, event=None):
        self.reset_game(full_reset=True)

    def space_handler(self, event=None):
        if self.state == "stage_intro":
            self.start_stage_play()
        elif self.state == "playing":
            self.pause_started_at = time.time()
            self.state = "paused"
            self.show_pause_overlay()
        elif self.state == "paused":
            self.paused_total += time.time() - self.pause_started_at
            self.pause_started_at = None
            self.state = "playing"
            self.clear_overlay()

    def start_stage_play(self):
        self.state = "playing"
        self.clear_overlay()
        self.start_timer_if_needed()
        self.main_ball.attach_to_paddle(self.paddle.x, self.paddle.width, self.paddle.y)
        self.pending_main_launch_at = self.game_now() + 0.15

    def launch_pending_main_ball_if_needed(self):
        if self.state != "playing":
            return
        if self.main_ball.attached and self.pending_main_launch_at is not None and self.game_now() >= self.pending_main_launch_at:
            self.main_ball.launch_from_paddle(self.stage_speed_multiplier)
            self.pending_main_launch_at = None

    def create_stage_clear_transition(self):
        self.clear_overlay()
        self.canvas.delete("game")
        self.canvas.delete("wall")
        self.bricks.clear()
        self.items.clear()
        self.messages.clear()
        self.balls.clear()

        self._create_side_walls()
        self.paddle = Paddle(self.canvas)
        self.main_ball = Ball(self.canvas, self.paddle.x + self.paddle.width / 2, self.paddle.y - 20, is_main=True)
        self.main_ball.attach_to_paddle(self.paddle.x, self.paddle.width, self.paddle.y)
        self.balls.append(self.main_ball)

        self.stage_speed_multiplier = 1.10 + (self.stage - 1) * STAGE_SPEED_STEP
        self.create_stage()
        self.show_stage_intro()
        self.update_ui()

    def advance_stage_or_clear(self):
        if all(brick.destroyed for brick in self.bricks):
            if self.stage >= STAGE_COUNT:
                self.show_game_clear()
            else:
                self.stage += 1
                self.chain_system.chain_count = 0
                self.chain_system.last_emotion = None
                self.create_stage_clear_transition()

    def find_nearest_brick_x(self, ball_x):
        alive = [b for b in self.bricks if not b.destroyed and b.visible]
        if not alive:
            return None
        nearest = min(alive, key=lambda b: abs((b.x + b.w / 2) - ball_x))
        return nearest.x + nearest.w / 2

    def apply_surprise_speed_and_angle(self, ball, min_deg=5, max_deg=30):
        angle = math.degrees(math.atan2(ball.vy, ball.vx))
        delta = random.uniform(min_deg, max_deg) * random.choice([-1, 1])
        angle += delta
        speed = math.hypot(ball.vx, ball.vy) * random.uniform(0.9, 1.1)
        ball.vx, ball.vy = angle_to_vector(angle, speed)

    def apply_surprise_paddle_bounce(self, ball, base_angle, speed):
        delta = random.uniform(5, 30) * random.choice([-1, 1])
        angle = clamp(base_angle + delta, 200, 340)
        speed *= random.uniform(0.9, 1.1)
        vx, vy = angle_to_vector(angle, speed)
        if vy > -0.2:
            vy = -abs(vy) if abs(vy) > 0.2 else -0.2
        ball.vx = vx
        ball.vy = vy

    def ball_bounce_x(self, ball):
        ball.vx *= -1
        if ball.emotion == "SURPRISE":
            self.apply_surprise_speed_and_angle(ball, 5, 30)

    def ball_bounce_y(self, ball):
        ball.vy *= -1
        if ball.emotion == "SURPRISE":
            self.apply_surprise_speed_and_angle(ball, 5, 30)

    def handle_fear_escape(self, ball):
        if ball.emotion != "FEAR":
            return

        threshold = HEIGHT * 0.6
        if ball.y < threshold - ball.radius:
            ball.fear_escape_armed = True

        if not ball.fear_escape_armed or ball.y < threshold:
            return

        shift = WIDTH * 0.3
        play_left = self.side_wall_width + ball.radius + 1
        play_right = WIDTH - self.side_wall_width - ball.radius - 1
        new_x = ball.x + shift if random.random() < 0.5 else ball.x - shift
        ball.x = clamp(new_x, play_left, play_right)
        ball.fear_escape_armed = False
        ball.redraw()

    def handle_paddle_collision(self, ball):
        if ball.vy <= 0:
            return

        paddle_left = self.paddle.x
        paddle_right = self.paddle.x + self.paddle.width
        paddle_top = self.paddle.y

        prev_bottom = ball.prev_y + ball.radius
        curr_bottom = ball.y + ball.radius

        crossed_from_above = prev_bottom <= paddle_top and curr_bottom >= paddle_top
        within_x = paddle_left - ball.radius <= ball.x <= paddle_right + ball.radius

        if not (crossed_from_above and within_x):
            return

        ball.y = paddle_top - ball.radius - 1

        hit_ratio = (ball.x - paddle_left) / max(1.0, self.paddle.width)
        hit_ratio = clamp(hit_ratio, 0.0, 1.0)
        angle = 225 + hit_ratio * 90

        speed = math.hypot(ball.vx, ball.vy)
        if speed <= 0:
            speed = BALL_BASE_SPEED * self.stage_speed_multiplier * ball.current_speed_multiplier()

        if ball.emotion == "SURPRISE":
            self.apply_surprise_paddle_bounce(ball, angle, speed)
            ball.redraw()
            return

        angle = clamp(angle, 200, 340)
        vx, vy = angle_to_vector(angle, speed)
        if vy > -0.2:
            vy = -abs(vy) if abs(vy) > 0.2 else -0.2
        ball.vx = vx
        ball.vy = vy
        ball.redraw()

    def damage_value_for_ball(self, ball):
        return 1.0


    def finalize_destroyed_brick(self, brick, score_value, spawn_item=False):
        if brick.finalized:
            return
        brick.finalized = True
        brick.destroyed = True
        brick.visible = False
        if score_value is not None:
            self.score_manager.add_score(score_value)
        if spawn_item and isinstance(brick, SurpriseBrick):
            self.spawn_item(brick.x + brick.w / 2, brick.y + brick.h / 2)
        if brick.canvas_item is not None:
            self.canvas.itemconfigure(brick.canvas_item, state="hidden")
        if brick.crack_item is not None:
            self.canvas.itemconfigure(brick.crack_item, state="hidden")

    def apply_joy_side_damage(self, center_brick):
        # 행복이 세배: 양옆 벽돌도 동일하게 1 데미지를 준다.
        row_y = center_brick.y
        target_xs = [center_brick.x - (BRICK_WIDTH + BRICK_GAP_X), center_brick.x + (BRICK_WIDTH + BRICK_GAP_X)]
        for target_x in target_xs:
            for brick in self.bricks:
                if brick.destroyed or not brick.visible:
                    continue
                if abs(brick.y - row_y) <= 1 and abs(brick.x - target_x) <= 1:
                    if brick.hit(1.0):
                        self.finalize_destroyed_brick(brick, brick.score_value, spawn_item=True)
                    break

    def handle_brick_collision(self, ball, brick):
        if brick.destroyed or not brick.visible:
            return

        damage = self.damage_value_for_ball(ball)
        destroyed_now = brick.hit(damage)

        self.resolve_brick_reflection(ball, brick)

        if destroyed_now:
            self.finalize_destroyed_brick(brick, brick.score_value, spawn_item=True)

        if ball.emotion == "JOY":
            self.apply_joy_side_damage(brick)

        if destroyed_now:
            chain = self.chain_system.add_chain(brick.emotion)
            if chain > 1:
                self.score_manager.add_score((chain - 1) * 20)

            self.set_ball_emotion_from_brick(ball, brick.emotion)

            if self.chain_system.consume_pending_explosion() or chain == EMOTION_EXPLOSION_CHAIN:
                self.emotion_explosion(brick, brick.emotion)

    def set_ball_emotion_from_brick(self, ball, brick_emotion):
        if not ball.affects_emotion:
            return
        mapping = {
            "anger": "ANGER",
            "joy": "JOY",
            "fear": "FEAR",
            "surprise": "SURPRISE",
        }
        now = self.game_now()
        ball.set_emotion(mapping[brick_emotion], now)
        ball.set_speed_preserve_direction(BALL_BASE_SPEED * self.stage_speed_multiplier * ball.current_speed_multiplier())

    def emotion_explosion(self, center_brick, emotion):
        targets = []
        for brick in self.bricks:
            if brick.destroyed or brick is center_brick:
                continue
            dx = abs(brick.x - center_brick.x)
            dy = abs(brick.y - center_brick.y)
            if dx <= (BRICK_WIDTH + BRICK_GAP_X) and dy <= (BRICK_HEIGHT + BRICK_GAP_Y):
                targets.append(brick)

        for brick in targets[:8]:
            if brick.destroyed:
                continue
            self.finalize_destroyed_brick(brick, brick.score_value // 2 + 20, spawn_item=True)

    def resolve_brick_reflection(self, ball, brick):
        prev_left = ball.prev_x - ball.radius
        prev_right = ball.prev_x + ball.radius
        prev_top = ball.prev_y - ball.radius
        prev_bottom = ball.prev_y + ball.radius

        curr_left = ball.x - ball.radius
        curr_right = ball.x + ball.radius
        curr_top = ball.y - ball.radius
        curr_bottom = ball.y + ball.radius

        brick_left = brick.x
        brick_right = brick.x + brick.w
        brick_top = brick.y
        brick_bottom = brick.y + brick.h

        hit_from_top = prev_bottom <= brick_top and curr_bottom >= brick_top
        hit_from_bottom = prev_top >= brick_bottom and curr_top <= brick_bottom
        hit_from_left = prev_right <= brick_left and curr_right >= brick_left
        hit_from_right = prev_left >= brick_right and curr_left <= brick_right

        if hit_from_top:
            ball.y = brick_top - ball.radius - 1
            self.ball_bounce_y(ball)
        elif hit_from_bottom:
            ball.y = brick_bottom + ball.radius + 1
            self.ball_bounce_y(ball)
        elif hit_from_left:
            ball.x = brick_left - ball.radius - 1
            self.ball_bounce_x(ball)
        elif hit_from_right:
            ball.x = brick_right + ball.radius + 1
            self.ball_bounce_x(ball)
        else:
            overlap_left = curr_right - brick_left
            overlap_right = brick_right - curr_left
            overlap_top = curr_bottom - brick_top
            overlap_bottom = brick_bottom - curr_top
            min_overlap = min(overlap_left, overlap_right, overlap_top, overlap_bottom)

            if min_overlap == overlap_left:
                ball.x = brick_left - ball.radius - 1
                self.ball_bounce_x(ball)
            elif min_overlap == overlap_right:
                ball.x = brick_right + ball.radius + 1
                self.ball_bounce_x(ball)
            elif min_overlap == overlap_top:
                ball.y = brick_top - ball.radius - 1
                self.ball_bounce_y(ball)
            else:
                ball.y = brick_bottom + ball.radius + 1
                self.ball_bounce_y(ball)

        ball.redraw()

    def update_bricks(self):
        now = self.game_now()
        for brick in self.bricks:
            if isinstance(brick, FearBrick):
                brick.update_visibility(now)
            brick.draw(self.canvas)

    def update_items(self):
        if self.state != "playing":
            return

        for item in list(self.items):
            if not item.active:
                continue
            item.update()

            half = item.side / 2
            if (
                self.paddle.x <= item.x <= self.paddle.x + self.paddle.width and
                self.paddle.y <= item.y + half <= self.paddle.y + self.paddle.height
            ):
                self.apply_item(item.kind)
                item.remove()
                self.items.remove(item)
                continue

            if item.y - item.side / 2 > HEIGHT:
                item.remove()
                self.items.remove(item)

    def update_messages(self):
        now = self.game_now()
        for msg in list(self.messages):
            if msg.expired(now):
                if msg.item_id is not None:
                    self.canvas.delete(msg.item_id)
                self.messages.remove(msg)

    def update_ui(self):
        self.canvas.itemconfig(self.score_text, text=f"Score: {self.score_manager.total_score}")
        self.canvas.itemconfig(self.chain_text, text=f"Chain: {self.chain_system.chain_count}")
        self.canvas.itemconfig(self.life_box_text, text=f"Life: {self.lives}")
        self.canvas.itemconfig(self.time_box_text, text=f"걸린 시간 : {self.format_elapsed_time()}")
        self.canvas.itemconfig(self.emotion_text, text=self.main_ball.emotion)

        high_text = f"최고 점수 : {self.high_score}점"
        high_width = max(120, int(self._measure_text_width(high_text, self.ui_font) * 1.1))
        self.canvas.coords(self.high_score_box_rect,
                           UI_HIGH_SCORE_X, UI_BOX_Y_BOTTOM,
                           UI_HIGH_SCORE_X + high_width, UI_BOX_Y_BOTTOM + UI_BOX_HEIGHT)
        self.canvas.coords(self.high_score_box_text,
                           UI_HIGH_SCORE_X + high_width / 2, UI_BOX_Y_BOTTOM + UI_BOX_HEIGHT / 2)
        self.canvas.itemconfig(self.high_score_box_text, text=high_text)

        self.canvas.coords(self.life_box_rect, UI_LIFE_X, UI_BOX_Y_TOP, UI_LIFE_X + UI_RIGHT_BOX_WIDTH, UI_BOX_Y_TOP + UI_BOX_HEIGHT)
        self.canvas.coords(self.life_box_text, UI_LIFE_X + UI_RIGHT_BOX_WIDTH / 2, UI_BOX_Y_TOP + UI_BOX_HEIGHT / 2)
        self.canvas.coords(self.time_box_rect, UI_LIFE_X, UI_BOX_Y_BOTTOM, UI_LIFE_X + UI_RIGHT_BOX_WIDTH, UI_BOX_Y_BOTTOM + UI_BOX_HEIGHT)
        self.canvas.coords(self.time_box_text, UI_LIFE_X + UI_RIGHT_BOX_WIDTH / 2, UI_BOX_Y_BOTTOM + UI_BOX_HEIGHT / 2)

    def update_balls(self):
        if self.state != "playing":
            self.main_ball.attach_to_paddle(self.paddle.x, self.paddle.width, self.paddle.y)
            return

        self.launch_pending_main_ball_if_needed()

        now = self.game_now()

        for ball in list(self.balls):
            if ball.attached:
                ball.attach_to_paddle(self.paddle.x, self.paddle.width, self.paddle.y)
                continue

            ball.maybe_unlock_emotion(now)
            ball.move_with_velocity()
            ball.redraw()

            self.handle_fear_escape(ball)

            if ball.x - ball.radius <= self.side_wall_width:
                ball.x = self.side_wall_width + ball.radius + 1
                self.ball_bounce_x(ball)
            elif ball.x + ball.radius >= WIDTH - self.side_wall_width:
                ball.x = WIDTH - self.side_wall_width - ball.radius - 1
                self.ball_bounce_x(ball)

            if ball.y - ball.radius <= UI_BOX_Y_BOTTOM + UI_BOX_HEIGHT + 2:
                ball.y = UI_BOX_Y_BOTTOM + UI_BOX_HEIGHT + ball.radius + 1
                self.ball_bounce_y(ball)

            self.handle_paddle_collision(ball)

            if ball.y - ball.radius > HEIGHT:
                if ball.is_main:
                    self.lives -= 1
                    if self.lives <= 0:
                        self.show_game_over()
                        return
                    ball.attach_to_paddle(self.paddle.x, self.paddle.width, self.paddle.y)
                    self.pending_main_launch_at = self.game_now() + 0.6
                else:
                    if ball in self.balls:
                        self.balls.remove(ball)
                continue

            for brick in self.bricks:
                if brick.destroyed or not brick.visible:
                    continue
                if (
                    ball.x + ball.radius >= brick.x and
                    ball.x - ball.radius <= brick.x + brick.w and
                    ball.y + ball.radius >= brick.y and
                    ball.y - ball.radius <= brick.y + brick.h
                ):
                    self.handle_brick_collision(ball, brick)
                    break

    def stage_clear_check(self):
        if all(brick.destroyed for brick in self.bricks):
            self.advance_stage_or_clear()

    def run(self):
        if not self.game_running:
            return

        now = self.game_now()

        if self.state == "playing":
            self.paddle.update(now)
            self.update_balls()
            self.update_items()
            self.update_messages()
            self.update_bricks()
            self.update_ui()
            self.stage_clear_check()
        elif self.state == "paused":
            self.paddle.update_effect(now)
            self.update_bricks()
            self.update_ui()
        elif self.state == "stage_intro":
            self.paddle.update_effect(now)
            self.main_ball.attach_to_paddle(self.paddle.x, self.paddle.width, self.paddle.y)
            self.update_bricks()
            self.update_ui()
        elif self.state in ("game_clear", "game_over"):
            self.paddle.update_effect(now)
            self.update_bricks()
            self.update_ui()

        self.root.after(FPS_DELAY_MS, self.run)


if __name__ == "__main__":
    EmotionDestroyer()











