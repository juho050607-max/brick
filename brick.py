"""
brick.py

========================================
감정 파괴자 (Emotion Destroyer)
벽돌 클래스 모음
========================================

[구성]

- Brick          : 모든 벽돌의 부모 클래스
- AngerBrick     : 분노 벽돌
- JoyBrick       : 기쁨 벽돌
- FearBrick      : 공포 벽돌
- SurpriseBrick  : 놀람 벽돌

========================================
감정 종류 (프로젝트 전체 통일 권장)
========================================

anger
joy
fear
surprise
"""

import random
import time


class Brick:
    WIDTH = 70
    HEIGHT = 30

    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.destroyed = False
        self.hp = 1
        self.score = 0
        self.emotion = "none"
        self.color = "gray"
        self.rect_id = None
        self.text_id = None

    def hit(self, damage=1):
        self.hp -= damage

        if self.hp <= 0:
            self.destroyed = True
            return {
                "destroyed": True,
                "score": self.score,
                "emotion": self.emotion,
                "item": None
            }

        return {
            "destroyed": False,
            "score": 0,
            "emotion": self.emotion,
            "item": None
        }

    def update(self):
        pass

    def draw(self, canvas):

        if self.destroyed:
            return

        if self.rect_id is None:

            self.rect_id = canvas.create_rectangle(
                self.x,
                self.y,
                self.x + self.WIDTH,
                self.y + self.HEIGHT,
                fill=self.color,
                outline="black"
            )

            self.text_id = canvas.create_text(
                self.x + self.WIDTH//2,
                self.y + self.HEIGHT//2,
                text=str(self.hp),
                fill="white"
            )

        else:

            canvas.itemconfig(
                self.text_id,
                text=str(self.hp)
            )

    def get_score(self):
        return self.score

    def get_emotion(self):
        return self.emotion

    def is_destroyed(self):
        return self.destroyed
    
    def remove(self, canvas):

        if self.rect_id:
            canvas.delete(self.rect_id)

        if self.text_id:
            canvas.delete(self.text_id)


class AngerBrick(Brick):
    def __init__(self, x, y):
        super().__init__(x, y)
        self.hp = 3
        self.score = 100
        self.emotion = "anger"
        self.color = "red"


class JoyBrick(Brick):
    def __init__(self, x, y):
        super().__init__(x, y)
        self.hp = 1
        self.score = 60
        self.emotion = "joy"
        self.color = "yellow"


class FearBrick(Brick):
    def __init__(self, x, y):
        super().__init__(x, y)

        self.hp = 1
        self.score = 80
        self.emotion = "fear"
        self.color = "purple"

        self.visible = True
        self.next_event = time.time() + random.uniform(2, 5)

    def update(self):
        current = time.time()

        if current >= self.next_event:
            if random.random() < 0.5:
                self.visible = not self.visible

            self.next_event = current + random.uniform(2, 5)

    def hit(self, damage=1):
        if not self.visible:
            return {
                "destroyed": False,
                "score": 0,
                "emotion": self.emotion,
                "item": None
            }

        return super().hit(damage)

    def draw(self, canvas):
        if not self.visible:
            return

        super().draw(canvas)


class SurpriseBrick(Brick):

    ITEM_LIST = [
        "extra_life",
        "multi_ball",
        "score_bonus",
        "speed_up"
    ]

    def __init__(self, x, y):
        super().__init__(x, y)

        self.hp = 2
        self.score = 70
        self.emotion = "surprise"
        self.color = "cyan"

    def hit(self, damage=1):
        result = super().hit(damage)

        if result["destroyed"]:
            result["item"] = random.choice(self.ITEM_LIST)

        return result
