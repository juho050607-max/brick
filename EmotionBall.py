import tkinter as tk
import math
import random
import time


class EmotionBall:
    def __init__(self, canvas, x, y, radius, base_speed):
        self.canvas = canvas

        self.x = x
        self.y = y
        self.radius = radius
        self.base_speed = base_speed
        self.speed = base_speed

        angle = math.radians(random.uniform(225, 315))
        self.vx = math.cos(angle) * self.speed
        self.vy = math.sin(angle) * self.speed

        self.emotion = "NORMAL"

        self.locked_emotion = False
        self.lock_end_time = 0

        self.joy_speed_multiplier = 1.0

        self.colors = {
            "NORMAL": "white",
            "ANGER": "red",
            "JOY": "yellow",
            "FEAR": "purple",
            "SURPRISE": "cyan"
        }

        # 공 생성
        self.ball_id = canvas.create_oval(
            x - radius,
            y - radius,
            x + radius,
            y + radius,
            fill=self.colors["NORMAL"],
            outline=""
        )

    def set_emotion(self, new_emotion, is_explosion=False):

        current_time = time.time()

        if self.locked_emotion:
            if current_time < self.lock_end_time:
                return
            else:
                self.locked_emotion = False

        self.emotion = new_emotion
        self.joy_speed_multiplier = 1.0

        if is_explosion:
            self.locked_emotion = True
            self.lock_end_time = current_time + 5

        self.canvas.itemconfig(
            self.ball_id,
            fill=self.colors[self.emotion]
        )

        self._apply_emotion_speed()

    def _apply_emotion_speed(self):

        if self.emotion == "ANGER":
            self.speed = self.base_speed * 1.4

        elif self.emotion == "JOY":
            self.speed = self.base_speed * self.joy_speed_multiplier

        elif self.emotion == "FEAR":
            self.speed = self.base_speed * 0.7

        elif self.emotion == "SURPRISE":
            self.speed = self.base_speed * random.uniform(0.5, 1.8)

        else:
            self.speed = self.base_speed

        self._normalize_velocity()

    def _normalize_velocity(self):

        current_speed = math.hypot(self.vx, self.vy)

        if current_speed == 0:
            return

        self.vx = (self.vx / current_speed) * self.speed
        self.vy = (self.vy / current_speed) * self.speed

    def update(self):

        if self.emotion == "JOY":

            if self.joy_speed_multiplier < 1.6:

                self.joy_speed_multiplier += 0.002
                self.joy_speed_multiplier = min(
                    self.joy_speed_multiplier,
                    1.6
                )

                self._apply_emotion_speed()

        self.x += self.vx
        self.y += self.vy

        # 캔버스 위치 갱신
        self.canvas.coords(
            self.ball_id,
            self.x - self.radius,
            self.y - self.radius,
            self.x + self.radius,
            self.y + self.radius
        )

    def bounce(self, axis):

        if axis == 'x':
            self.vx *= -1

        elif axis == 'y':
            self.vy *= -1

        if self.emotion in ["ANGER", "SURPRISE"]:

            current_angle = math.atan2(
                self.vy,
                self.vx
            )

            if self.emotion == "ANGER":

                angle_modifier = math.radians(
                    random.uniform(15, 30)
                ) * random.choice([1, -1])

            else:

                angle_modifier = math.radians(
                    random.uniform(-45, 45)
                )

                self._apply_emotion_speed()

            new_angle = current_angle + angle_modifier

            self.vx = math.cos(new_angle) * self.speed
            self.vy = math.sin(new_angle) * self.speed

    def handle_brick_collision(self, brick):

        if self.emotion == "FEAR":
            return 0.5

        return 1.0

    def handle_paddle_collision(
            self,
            paddle_x,
            paddle_width,
            active_bricks
        ):

            hit_pos = (self.x - paddle_x) / paddle_width

            offset = (
                (self.x - paddle_x)
                / paddle_width
            )

            offset = (offset - 0.5) * 2

            self.vx = offset * self.speed

            self.vy = -(
                self.speed**2 - self.vx**2
            ) ** 0.5
    
            if self.emotion == "SURPRISE":
                self._apply_emotion_speed()