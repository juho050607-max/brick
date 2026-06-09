import math
import random
import time
import tkinter as tk
import pygame


WIDTH = 800
HEIGHT = 780  # 세로 확장
UI_HEIGHT = 50

STAGE_COUNT = 5

# 벽돌 배치: 행 수 증가, 가로 간격 축소
BRICK_ROWS = 7
BRICK_COLS = 16
BRICK_GAP_X = 5
BRICK_GAP_Y = 10
BRICK_MARGIN_X = 24
BRICK_START_Y = 80
BRICK_HEIGHT = 28
BRICK_WIDTH = (WIDTH - BRICK_MARGIN_X * 2 - BRICK_GAP_X * (BRICK_COLS - 1)) // BRICK_COLS

PADDLE_Y = HEIGHT - 80
PADDLE_WIDTH = 120
PADDLE_HEIGHT = 16
PADDLE_SPEED = 14  # 기존 대비 1.2배 수준

BALL_RADIUS = 9
BALL_BASE_SPEED = 6.0  # 기존 대비 1.2배 수준
FPS_DELAY_MS = 13

STAGE_SPEED_STEP = 0.04
FEAR_HIDE_MIN = 0.5
FEAR_HIDE_MAX = 3.0
FEAR_HIDDEN_DURATION = 0.5

ITEM_MSG_DURATION = 0.4
PADDLE_EFFECT_DURATION = 5.0
EMOTION_EXPLOSION_CHAIN = 5
EMOTION_LOCK_DURATION = 5.0


def clamp(value, low, high):
    return max(low, min(high, value))


def angle_to_vector(angle_deg, speed):
    rad = math.radians(angle_deg)
    return math.cos(rad) * speed, math.sin(rad) * speed


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

    def add_chain(self, emotion):
        if self.last_emotion == emotion:
            self.chain_count += 1
        else:
            self.chain_count = 1
            self.last_emotion = emotion
        return self.chain_count

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

    def set_scale(self, scale, now, duration=0.0, effect_type=None):
        self.scale = scale
        self.effect_until = now + duration if duration > 0 else 0.0
        self.effect_type = effect_type

    def update_effect(self, now):
        if self.effect_until and now >= self.effect_until:
            self.scale = 1.0
            self.effect_until = 0.0
            self.effect_type = None

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
            return base * 1.4
        if self.emotion == "JOY":
            return base * 1.0
        if self.emotion == "FEAR":
            return base * 0.7
        if self.emotion == "SURPRISE":
            return base * 1.15
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
    def __init__(self, x, y, emotion, hp, score_value, color):
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

    def draw(self, canvas):
        if self.destroyed or not self.visible:
            if self.canvas_item is not None:
                canvas.itemconfigure(self.canvas_item, state="hidden")
            if self.crack_item is not None:
                canvas.itemconfigure(self.crack_item, state="hidden")
            return

        if self.canvas_item is None:
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
            canvas.itemconfigure(self.canvas_item, state="normal")
            canvas.itemconfigure(self.crack_item, state="normal")

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
    def __init__(self, x, y, now):
        super().__init__(x, y, "fear", 1, 80, "#5c4b99")
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
    def __init__(self, x, y):
        super().__init__(x, y, "surprise", 2, 70, "#ff8fcf")


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
        pygame.mixer.music.play(-1)  #무한반복
        
        self.root.title("감정 파괴자")
        self.canvas = tk.Canvas(self.root, width=WIDTH, height=HEIGHT, bg="black")
        self.canvas.pack()

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

        self.stage_speed_multiplier = 1.0 + (self.stage - 1) * STAGE_SPEED_STEP
        self.game_running = True
        self.state = "stage_intro"
        self.stage_started = False
        self.stage_cleared = False

        self.paused_total = 0.0
        self.pause_started_at = None
        self.pending_main_launch_at = None

        self.messages = []
        self.items = []
        self.balls = []

        self.paddle = Paddle(self.canvas)
        self.main_ball = Ball(self.canvas, self.paddle.x + self.paddle.width / 2, self.paddle.y - 20, is_main=True)
        self.main_ball.attach_to_paddle(self.paddle.x, self.paddle.width, self.paddle.y)
        self.balls.append(self.main_ball)

        self.bricks = []
        self.create_stage()

        self.score_text = self.canvas.create_text(90, 22, fill="white", text="Score: 0", font=("Arial", 14, "bold"), tags=("ui",))
        self.chain_text = self.canvas.create_text(260, 22, fill="white", text="Chain: 0", font=("Arial", 14, "bold"), tags=("ui",))
        self.life_text = self.canvas.create_text(450, 22, fill="white", text="Life: 3", font=("Arial", 14, "bold"), tags=("ui",))
        self.emotion_text = self.canvas.create_text(650, 22, fill="cyan", text="NORMAL", font=("Arial", 14, "bold"), tags=("ui",))

        self.show_stage_intro()

    def create_stage(self):
        now = self.game_now()
        emotions = ["anger", "joy", "fear", "surprise"]
        for r in range(BRICK_ROWS):
            for c in range(BRICK_COLS):
                x = BRICK_MARGIN_X + c * (BRICK_WIDTH + BRICK_GAP_X)
                y = BRICK_START_Y + r * (BRICK_HEIGHT + BRICK_GAP_Y)
                emotion = random.choice(emotions)
                if emotion == "anger":
                    brick = Brick(x, y, "anger", 3, 100, "#a53d3d")
                elif emotion == "joy":
                    brick = Brick(x, y, "joy", 1, 60, "#d8d23f")
                elif emotion == "fear":
                    brick = FearBrick(x, y, now)
                else:
                    brick = SurpriseBrick(x, y)
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
        self.clear_overlay()
        self.canvas.create_text(
            WIDTH // 2, HEIGHT // 2 - 30,
            text="축하합니다!",
            fill="hot pink",
            font=("Arial", 34, "bold"),
            tags=("overlay",),
        )
        self.canvas.create_text(
            WIDTH // 2, HEIGHT // 2 + 25,
            text="게임 클리어!",
            fill="sky blue",
            font=("Arial", 34, "bold"),
            tags=("overlay",),
        )

    def show_game_over(self):
        self.state = "game_over"
        self.clear_overlay()
        self.canvas.create_text(
            WIDTH // 2, HEIGHT // 2 - 20,
            text="GAME OVER",
            fill="red",
            font=("Arial", 34, "bold"),
            tags=("overlay",),
        )
        self.canvas.create_text(
            WIDTH // 2, HEIGHT // 2 + 28,
            text="R 키로 다시 시작",
            fill="white",
            font=("Arial", 16, "bold"),
            tags=("overlay",),
        )

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
        if random.random() > 0.30:
            return
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
            self.paddle.set_scale(1.5, now, duration=PADDLE_EFFECT_DURATION, effect_type="up")
            self.add_message("늘어나라!", "yellow")
        elif kind == "paddle_down":
            self.paddle.set_scale(0.66, now, duration=PADDLE_EFFECT_DURATION, effect_type="down")
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
        self.main_ball.attach_to_paddle(self.paddle.x, self.paddle.width, self.paddle.y)
        self.pending_main_launch_at = self.game_now() + 0.15

    def launch_pending_main_ball_if_needed(self):
        if self.state != "playing":
            return
        if self.main_ball.attached and self.pending_main_launch_at is not None and self.game_now() >= self.pending_main_launch_at:
            self.main_ball.launch_from_paddle(self.stage_speed_multiplier)
            self.pending_main_launch_at = None

    def create_stage_clear_transition(self):
        # 점수/목숨은 유지, 나머지 객체는 새 스테이지로 정리
        self.clear_overlay()
        self.canvas.delete("game")
        self.canvas.delete("ui")
        self.bricks.clear()
        self.items.clear()
        self.messages.clear()
        self.balls.clear()

        self.paddle = Paddle(self.canvas)
        self.main_ball = Ball(self.canvas, self.paddle.x + self.paddle.width / 2, self.paddle.y - 20, is_main=True)
        self.main_ball.attach_to_paddle(self.paddle.x, self.paddle.width, self.paddle.y)
        self.balls.append(self.main_ball)

        self.stage_speed_multiplier = 1.0 + (self.stage - 1) * STAGE_SPEED_STEP
        self.create_stage()
        self.score_text = self.canvas.create_text(90, 22, fill="white", text=f"Score: {self.score_manager.total_score}", font=("Arial", 14, "bold"), tags=("ui",))
        self.chain_text = self.canvas.create_text(260, 22, fill="white", text=f"Chain: {self.chain_system.chain_count}", font=("Arial", 14, "bold"), tags=("ui",))
        self.life_text = self.canvas.create_text(450, 22, fill="white", text=f"Life: {self.lives}", font=("Arial", 14, "bold"), tags=("ui",))
        self.emotion_text = self.canvas.create_text(650, 22, fill="cyan", text="NORMAL", font=("Arial", 14, "bold"), tags=("ui",))
        self.show_stage_intro()

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

    def damage_value_for_ball(self, ball):
        return 0.5 if ball.emotion == "FEAR" else 1.0

    def ball_bounce_x(self, ball):
        ball.vx *= -1
        if ball.emotion == "ANGER":
            ball.randomize_direction_small(15, 30)
        elif ball.emotion == "SURPRISE":
            ball.randomize_direction_small(5, 30)

    def ball_bounce_y(self, ball):
        ball.vy *= -1
        if ball.emotion == "ANGER":
            ball.randomize_direction_small(15, 30)
        elif ball.emotion == "SURPRISE":
            ball.randomize_direction_small(5, 30)

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

        # 달라붙지 않도록 패들 위로 정확히 되돌리고, 아래 방향 속도를 없앰
        ball.y = paddle_top - ball.radius - 1

        # 기본 반사 각도
        hit_ratio = (ball.x - paddle_left) / max(1.0, self.paddle.width)
        hit_ratio = clamp(hit_ratio, 0.0, 1.0)
        angle = 225 + hit_ratio * 90  # 225~315도, 항상 위쪽으로 발사

        # 기쁨 공은 다음 벽돌 방향으로 살짝 유도
        if ball.emotion == "JOY":
            target_x = self.find_nearest_brick_x(ball.x)
            if target_x is not None:
                target_ratio = (target_x - paddle_left) / max(1.0, self.paddle.width)
                target_ratio = clamp(target_ratio, 0.0, 1.0)
                angle = 230 + target_ratio * 80

        speed = math.hypot(ball.vx, ball.vy)
        if speed <= 0:
            speed = BALL_BASE_SPEED * self.stage_speed_multiplier * ball.current_speed_multiplier()

        # 감정별 약간의 추가 흔들림
        if ball.emotion == "ANGER":
            angle += random.uniform(-20, 20)
        elif ball.emotion == "SURPRISE":
            angle += random.uniform(-15, 15)

        # 위쪽 반사로 보장
        angle = clamp(angle, 200, 340)
        vx, vy = angle_to_vector(angle, speed)
        if vy > -0.2:
            vy = -abs(vy) if abs(vy) > 0.2 else -0.2
        ball.vx = vx
        ball.vy = vy
        ball.redraw()

    def handle_brick_collision(self, ball, brick):
        if brick.destroyed or not brick.visible:
            return

        damage = self.damage_value_for_ball(ball)
        destroyed_now = brick.hit(damage)

        if ball.emotion != "FEAR":
            self.resolve_brick_reflection(ball, brick)

        if destroyed_now:
            # 놀람 벽돌은 아이템 드랍 확률 30% (clone ball은 드랍 없음)
            if isinstance(brick, SurpriseBrick) and ball.affects_emotion:
                self.spawn_item(brick.x + brick.w / 2, brick.y + brick.h / 2)

            self.score_manager.add_score(brick.score_value)
            chain = self.chain_system.add_chain(brick.emotion)
            if chain > 1:
                self.score_manager.add_score((chain - 1) * 20)

            self.set_ball_emotion_from_brick(ball, brick.emotion)

            if chain >= EMOTION_EXPLOSION_CHAIN:
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
        # 주위 최대 8개 파괴
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
            brick.destroyed = True
            brick.visible = False
            self.score_manager.add_score(brick.score_value // 2 + 20)
            if isinstance(brick, SurpriseBrick):
                self.spawn_item(brick.x + brick.w / 2, brick.y + brick.h / 2)
            if brick.canvas_item is not None:
                self.canvas.itemconfigure(brick.canvas_item, state="hidden")
            if brick.crack_item is not None:
                self.canvas.itemconfigure(brick.crack_item, state="hidden")

        self.chain_system.penalty_after_explosion()
        now = self.game_now()
        self.main_ball.set_emotion(emotion.upper(), now, lock=True, lock_duration=EMOTION_LOCK_DURATION)

    def resolve_brick_reflection(self, ball, brick):
        # 이전 위치를 기준으로 어느 면에 충돌했는지 판정
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
            # 교차가 애매하면 겹침이 작은 축으로 반사
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

            # 패드에 닿았을 때만 발동
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
        self.canvas.itemconfig(self.life_text, text=f"Life: {self.lives}")
        self.canvas.itemconfig(self.emotion_text, text=self.main_ball.emotion)

    def update_balls(self):
        if self.state != "playing":
            self.main_ball.attach_to_paddle(self.paddle.x, self.paddle.width, self.paddle.y)
            return

        self.launch_pending_main_ball_if_needed()

        # 기쁨 공은 시간이 흐를수록 조금씩 빨라짐
        now = self.game_now()
        for ball in self.balls:
            if ball.emotion == "JOY" and not ball.attached:
                ball.emotion_speed_bonus = clamp(ball.emotion_speed_bonus + 0.0015, 0.0, 0.6)
                desired = BALL_BASE_SPEED * self.stage_speed_multiplier * ball.current_speed_multiplier()
                ball.set_speed_preserve_direction(desired)

        for ball in list(self.balls):
            if ball.attached:
                ball.attach_to_paddle(self.paddle.x, self.paddle.width, self.paddle.y)
                continue

            ball.maybe_unlock_emotion(now)
            ball.move_with_velocity()
            ball.redraw()

            # 벽 충돌
            if ball.x - ball.radius <= 0:
                ball.x = ball.radius + 1
                self.ball_bounce_x(ball)
            elif ball.x + ball.radius >= WIDTH:
                ball.x = WIDTH - ball.radius - 1
                self.ball_bounce_x(ball)

            if ball.y - ball.radius <= UI_HEIGHT:
                ball.y = UI_HEIGHT + ball.radius + 1
                self.ball_bounce_y(ball)

            # 패드 충돌: 달라붙는 버그 방지용으로 "위에서 내려오는 경우"만 허용
            self.handle_paddle_collision(ball)

            # 바닥 이탈
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

            # 벽돌 충돌
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
        self.paddle.update(now)

        if self.state == "playing":
            self.update_balls()
            self.update_items()
            self.update_messages()
            self.update_bricks()
            self.update_ui()
            self.stage_clear_check()
        elif self.state == "paused":
            self.update_bricks()
            self.update_ui()
        elif self.state == "stage_intro":
            self.main_ball.attach_to_paddle(self.paddle.x, self.paddle.width, self.paddle.y)
            self.update_bricks()
            self.update_ui()
        elif self.state in ("game_clear", "game_over"):
            self.update_bricks()
            self.update_ui()

        self.root.after(FPS_DELAY_MS, self.run)


if __name__ == "__main__":
    EmotionDestroyer()



