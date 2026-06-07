
import tkinter as tk
import random
import os

from brick import AngerBrick, JoyBrick, FearBrick, SurpriseBrick
from EmotionBall import EmotionBall
from ScoreChain import EmotionChainSystem, ScoreManager

WIDTH = 800
HEIGHT = 600


class Paddle:
    def __init__(self, canvas):
        self.canvas = canvas
        self.width = 120
        self.height = 15
        self.x = 340
        self.y = 550
        self.move_left_flag = False
        self.move_right_flag = False
        self.speed = 10

        self.id = canvas.create_rectangle(
            self.x, self.y,
            self.x + self.width,
            self.y + self.height,
            fill="white"
        )

    def move_left(self):
        self.x = max(0, self.x - self.speed)

    def move_right(self):
        self.x = min(WIDTH - self.width, self.x + self.speed)

    def update(self):
        
        if self.move_left_flag:
            self.x -= self.speed
        if self.move_right_flag:
            self.x += self.speed

        self.x = max(0,min(self.x,800-self.width))

        self.canvas.coords(self.id,self.x,self.y,self.x+self.width,self.y+self.height)

class EmotionDestroyer:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("감정 파괴자")

        self.canvas = tk.Canvas(
            self.root,
            width=WIDTH,
            height=HEIGHT,
            bg="black"
        )
        self.canvas.pack()

        self.paddle = Paddle(self.canvas)

        self.ball = EmotionBall(
            self.canvas,
            WIDTH // 2,
            500,
            10,
            6
        )

        self.chain_system = EmotionChainSystem()
        self.score_manager = ScoreManager()

        self.lives = 3
        self.game_running = True

        self.waiting_for_launch = True
        self.ball.vx = 0
        self.ball.vy = 0

        self.bricks = []
        self.create_stage()

        self.score_text = self.canvas.create_text(
            90, 20, fill="white",
            text="Score: 0"
        )

        self.chain_text = self.canvas.create_text(
            260, 20, fill="white",
            text="Chain: 0"
        )

        self.life_text = self.canvas.create_text(
            420, 20, fill="white",
            text="Life: 3"
        )

        self.emotion_text = self.canvas.create_text(
            650, 20, fill="cyan",
            text="NORMAL"
        )

        self.root.bind("<Left>", lambda e: self.paddle.move_left())
        self.root.bind("<Right>", lambda e: self.paddle.move_right())
        self.root.bind("a", lambda e: self.paddle.move_left())
        self.root.bind("d", lambda e: self.paddle.move_right())
        self.root.bind("<KeyPress>",self.key_press)
        self.root.bind("<KeyRelease>",self.key_release)
        self.root.bind("r", self.restart_game)
        self.root.bind("R", self.restart_game)   #r,R 누를 시 재시작
        self.root.bind("<space>",self.launch_ball)   #스페이스 누르면 발사


        self.run()
        self.root.mainloop()
    def restart_game(self, event=None):

        self.canvas.delete("all")

        self.lives = 3

        self.game_running = True

        self.chain_system = EmotionChainSystem()

        self.score_manager = ScoreManager()

        self.bricks = []

        self.paddle = Paddle(self.canvas)

        self.ball = EmotionBall(
            self.canvas,
            WIDTH // 2,
            500,
            10,
            6
        )

        self.create_stage()

        self.score_text = self.canvas.create_text(
            90, 20,
            fill="white",
            text="Score: 0"
        )

        self.chain_text = self.canvas.create_text(
            260, 20,
            fill="white",
            text="Chain: 0"
        )

        self.life_text = self.canvas.create_text(
            420, 20,
            fill="white",
            text="Life: 3"
        )

        self.emotion_text = self.canvas.create_text(
            650, 20,
            fill="cyan",
            text="NORMAL"
        )

        self.run()

    def create_stage(self):
        for r in range(5):
            for c in range(10):

                x = 40 + c * 75
                y = 60 + r * 35

                brick_type = random.choice(
                    ["anger", "joy", "fear", "surprise"]
                )

                if brick_type == "anger":
                    brick = AngerBrick(x, y)
                elif brick_type == "joy":
                    brick = JoyBrick(x, y)
                elif brick_type == "fear":
                    brick = FearBrick(x, y)
                else:
                    brick = SurpriseBrick(x, y)

                brick.draw(self.canvas)
                self.bricks.append(brick)

    def update_ui(self):
        self.canvas.itemconfig(
            self.score_text,
            text=f"Score: {self.score_manager.total_score}"
        )

        self.canvas.itemconfig(
            self.chain_text,
            text=f"Chain: {self.chain_system.chain_count}"
        )

        self.canvas.itemconfig(
            self.life_text,
            text=f"Life: {self.lives}"
        )

        self.canvas.itemconfig(
            self.emotion_text,
            text=self.ball.emotion
        )

    def wall_collision(self):

        if self.ball.x <= self.ball.radius:
            self.ball.bounce("x")

        if self.ball.x >= WIDTH - self.ball.radius:
            self.ball.bounce("x")

        UI_HEIGHT = 40

        if self.ball.y <= UI_HEIGHT + self.ball.radius:
            self.ball.y = UI_HEIGHT + self.ball.radius
            self.ball.bounce("y")
        
        if self.ball.y > HEIGHT:

            self.lives -= 1

            self.chain_system.reset()

            self.ball.x = self.paddle.x + self.paddle.width / 2
            self.ball.y = self.paddle.y - 20

            self.ball.vx = 0
            self.ball.vy = 0

            self.waiting_for_launch = True

            if self.lives == 0:
                self.game_over()

    def paddle_collision(self):

        px = self.paddle.x
        py = self.paddle.y
        pw = self.paddle.width
        ph = self.paddle.height

        if (px <= self.ball.x <= px + pw and
            py <= self.ball.y + self.ball.radius <= py + ph):

            active = [
                b for b in self.bricks
                if not b.destroyed
            ]

            self.ball.handle_paddle_collision(
                px, pw, active
            )

    def brick_collision(self):

        for brick in self.bricks:

            if brick.destroyed:
                continue

            if isinstance(brick, FearBrick):
                brick.update()

            if isinstance(brick, FearBrick) and not brick.visible:
                continue

            if (brick.x <= self.ball.x <= brick.x + brick.WIDTH and
                brick.y <= self.ball.y <= brick.y + brick.HEIGHT):

                damage = self.ball.handle_brick_collision(brick)

                result = brick.hit(damage)

                if not result["destroyed"]:
                    brick.draw(self.canvas)

                if self.ball.emotion != "FEAR":
                    self.ball.bounce("y")

                if result["destroyed"]:

                    brick.remove(self.canvas)

                    chain = self.chain_system.add_chain(
                        result["emotion"]
                    )

                    points = self.score_manager.calculate_score(
                        result["emotion"],
                        chain
                    )

                    self.score_manager.add_score(points)

                    emotion_map = {
                        "anger": "ANGER",
                        "joy": "JOY",
                        "fear": "FEAR",
                        "surprise": "SURPRISE"
                    }

                    self.ball.set_emotion(
                        emotion_map[result["emotion"]]
                    )

                    if chain >= 5:
                        self.emotion_explosion(
                            brick,
                            result["emotion"]
                        )

                break

    def emotion_explosion(self, center, emotion):

        for brick in self.bricks:

            if brick.destroyed:
                continue

            dx = abs(brick.x - center.x)
            dy = abs(brick.y - center.y)

            if dx <= 80 and dy <= 40:

                brick.destroyed = True
                brick.remove(self.canvas)

                bonus = self.score_manager.calculate_score(
                    brick.emotion,
                    5,
                    True
                )

                self.score_manager.add_score(bonus)

        self.chain_system.reset()

        self.ball.set_emotion(
            emotion.upper(),
            is_explosion=True
        )

    def save_score(self):

        best = 0

        if os.path.exists("score.txt"):
            try:
                with open("score.txt", "r") as f:
                    best = int(f.read())
            except:
                pass

        if self.score_manager.total_score > best:
            with open("score.txt", "w") as f:
                f.write(str(self.score_manager.total_score))

    def game_over(self):

        self.game_running = False

        self.canvas.create_text(
        WIDTH // 2,
        HEIGHT // 2 - 20,
        text="GAME OVER",
        fill="red",
        font=("Arial", 30)
        )

        self.canvas.create_text(
        WIDTH // 2,
        HEIGHT // 2 + 20,
        text="Press R to Restart",
        fill="white",
        font=("Arial", 15)
        )

    def run(self):

        if not self.game_running:
            return

        if self.waiting_for_launch:

            self.ball.x = (
            self.paddle.x
            + self.paddle.width / 2
        )

            self.ball.y = (
                self.paddle.y
                - 20
            )

            self.canvas.coords(
                self.ball.ball_id,
                self.ball.x - self.ball.radius,
                self.ball.y - self.ball.radius,
                self.ball.x + self.ball.radius,
                self.ball.y + self.ball.radius
            )

        else:
            self.ball.update()
        
        self.paddle.update()

        self.wall_collision()
        self.paddle_collision()
        self.brick_collision()

        self.update_ui()

        self.root.after(16, self.run)

    def key_press(self,event):
        
        if event.keysym in ["Left","a"]:
            self.paddle.move_left_flag = True
        
        elif event.keysym in ["Right","d"]:
            self.paddle.move_right_flag = True

    def key_release(self,event):

        if event.keysym in ["Left","a"]:
            self.paddle.move_left_flag = False

        elif event.keysym in ["Right","d"]:
            self.paddle.move_right_flag = False 
    
    def launch_ball(self, event=None):

        if not self.waiting_for_launch:
            return

        self.waiting_for_launch = False

        self.ball.vx = random.choice([-4, 4])
        self.ball.vy = -6

if __name__ == "__main__":
    EmotionDestroyer()
