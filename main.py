import math
import logging
import arcade
import pymunk
from typing import List

from game_object import Bird, Column, Pig, YellowBird, BlueBird, LevelManager
from game_logic import get_impulse_vector, Point2D, get_distance, ImpulseVector

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("arcade").setLevel(logging.WARNING)
logging.getLogger("pymunk").setLevel(logging.WARNING)
logging.getLogger("PIL").setLevel(logging.WARNING)

logger = logging.getLogger("main")

WIDTH = 1800
HEIGHT = 800
TITLE = "Angry birds"
GRAVITY = -900  # coincide con space.gravity

# -----------------------
# Slingshot / parámetros
# -----------------------
SLINGSHOT_X = 180   # ajusta según tu escena
SLINGSHOT_Y = 160

# Parametros por tipo (puedes ajustarlos)
DEFAULT_PARAMS = {
    "red":   {"mass": 5, "radius": 12, "max_impulse": 200, "power_multiplier": 45},
    "yellow":{"mass": 4, "radius": 12, "max_impulse": 240, "power_multiplier": 50, "boost_multiplier": 2.2},
    "blue":  {"mass": 4, "radius": 10, "max_impulse": 180, "power_multiplier": 42, "split_angle_deg": 30.0},
}


class App(arcade.View):
    def __init__(self):
        super().__init__()
        self.background = arcade.load_texture("assets/img/background3.png")

        # Pymunk space
        self.space = pymunk.Space()
        self.space.gravity = (0, GRAVITY)

        # Piso
        floor_body = pymunk.Body(body_type=pymunk.Body.STATIC)
        floor_shape = pymunk.Segment(floor_body, [0, 15], [WIDTH, 15], 0.0)
        floor_shape.friction = 10
        self.space.add(floor_body, floor_shape)

        # Sprite lists
        self.sprites = arcade.SpriteList()   # todos
        self.birds = arcade.SpriteList()     # solo birds
        self.world = arcade.SpriteList()     # cerdos/columnas/objetos destructibles

        # Crear mundo inicial
        self.add_columns()
        self.add_pigs()

        # Aiming
        self.start_point = Point2D()
        self.end_point = Point2D()
        self.draw_line = False
        self.preview_points: List[tuple] = []

        # Score & levels
        self.score = 0
        self.level_manager = LevelManager()
        # add levels (threshold, setup_fn)
        self.level_manager.add_level(0, self.setup_level_0)
        self.level_manager.add_level(100, self.setup_level_1)
        # puedes agregar más con level_manager.add_level(...)
        self.level_manager.start(self)

        # collision handler
        self.handler = self.space.add_default_collision_handler()
        self.handler.post_solve = self.collision_handler

        # selección manual de pájaro (None = automático por distancia)
        self.forced_bird_type = None  # "red","blue","yellow" o None

    # ------------------------
    # Level setup examples
    # ------------------------
    def setup_level_0(self, game, level_idx):
        logger.debug(f"Setup level {level_idx}: nivel inicial (sin cambios).")
        # ejemplo: limpiar y volver a añadir pigs/columns si lo deseas
        # aquí no hacemos nada

    def setup_level_1(self, game, level_idx):
        logger.debug(f"Setup level {level_idx}: añadir 2 cerdos extra.")
        # Añadir cerdos ejemplo
        pig_a = Pig(WIDTH / 2 + 120, 100, self.space)
        pig_b = Pig(WIDTH / 2 + 200, 100, self.space)
        self.sprites.append(pig_a); self.sprites.append(pig_b)
        self.world.append(pig_a); self.world.append(pig_b)

    # ------------------------
    # Collision handling
    # ------------------------
    def collision_handler(self, arbiter, space, data):
        """
        Post-solve: eliminar objetos si el impulso es suficiente.
        Incrementa score si se destruye un Pig y pregunta al LevelManager si avanzar.
        """
        impulse_norm = arbiter.total_impulse.length
        if impulse_norm < 100:
            return True
        logger.debug(f"Collision impulse: {impulse_norm}")
        if impulse_norm > 1200:
            removed_any = False
            for obj in list(self.world):
                try:
                    if obj.shape in arbiter.shapes:
                        if isinstance(obj, Pig):
                            self.score += 100
                            logger.debug(f"Pig destruido -> score = {self.score}")
                            self.level_manager.update_score(self.score)
                            self.level_manager.check_and_advance(self)

                        try:
                            obj.remove_from_sprite_lists()
                        except Exception:
                            pass
                        try:
                            self.space.remove(obj.shape, obj.body)
                        except Exception:
                            pass
                        try:
                            self.world.remove(obj)
                        except Exception:
                            pass
                        removed_any = True
                except Exception:
                    pass
            if removed_any:
                logger.debug("Objetos removidos por colisión fuerte.")
        return True

    # ------------------------
    # World construction
    # ------------------------
    def add_columns(self):
        for x in range(WIDTH // 2, WIDTH, 400):
            column = Column(x, 50, self.space)
            self.sprites.append(column)
            self.world.append(column)

    def add_pigs(self):
        pig1 = Pig(WIDTH / 2, 100, self.space)
        self.sprites.append(pig1)
        self.world.append(pig1)

    # ------------------------
    # Update
    # ------------------------
    def on_update(self, delta_time: float):
        self.space.step(1 / 60.0)
        self.update_collisions()
        self.sprites.update(delta_time)
        # sincronizar niveles
        self.level_manager.update_score(self.score)
        self.level_manager.check_and_advance(self)

    def update_collisions(self):
        """
        Remover sprites que quedaron fuera de la escena y sus cuerpos del space.
        """
        offscreen = []
        for spr in list(self.sprites):
            if spr.center_y < -200 or spr.center_x < -500 or spr.center_x > WIDTH + 500:
                offscreen.append(spr)

        for spr in offscreen:
            try:
                if hasattr(spr, "shape") and hasattr(spr, "body"):
                    try:
                        self.space.remove(spr.shape, spr.body)
                    except Exception:
                        pass
                spr.remove_from_sprite_lists()
            except Exception:
                pass

    # ------------------------
    # Predict trajectory (preview)
    # ------------------------
    def compute_predicted_path(self, start: Point2D, end: Point2D, bird_choice: str, steps: int = 80, dt: float = 0.04):
        """
        Calcula puntos previos usando la misma fórmula de impulso que crea el Bird:
        applied_impulse = min(max_impulse, iv.impulse) * power_multiplier
        v0 = applied_impulse / mass
        y(t) = y0 + vy0 * t + 0.5 * gy * t^2
        """
        iv = get_impulse_vector(start, end)
        # seleccionar parámetros
        if bird_choice == "yellow":
            p = DEFAULT_PARAMS["yellow"]
        elif bird_choice == "blue":
            p = DEFAULT_PARAMS["blue"]
        else:
            p = DEFAULT_PARAMS["red"]

        applied_impulse = min(p["max_impulse"], iv.impulse) * p["power_multiplier"]
        if p["mass"] == 0:
            return []
        v0 = applied_impulse / p["mass"]
        angle = iv.angle
        vx0 = math.cos(angle) * v0
        vy0 = math.sin(angle) * v0

        gx, gy = self.space.gravity

        points = []
        x0 = SLINGSHOT_X
        y0 = SLINGSHOT_Y
        t = 0.0
        for i in range(steps):
            x_t = x0 + vx0 * t
            y_t = y0 + vy0 * t + 0.5 * gy * (t ** 2)
            points.append((x_t, y_t))
            if y_t < 20:
                break
            t += dt
        return points

    # ------------------------
    # Input: mouse (aim + abilities)
    # ------------------------
    def on_mouse_press(self, x, y, button, modifiers):
        # Si hay un pájaro en vuelo y NO estamos apuntando => activar habilidad
        if button == arcade.MOUSE_BUTTON_LEFT and not self.draw_line:
            for b in self.birds:
                if getattr(b, "launched", False) and not getattr(b, "used_ability", False):
                    if isinstance(b, YellowBird):
                        activated = b.on_click_ability()
                        if activated:
                            logger.debug("YellowBird ability activated.")
                            return
                    if isinstance(b, BlueBird):
                        children = b.on_click_ability(self.sprites)
                        if children:
                            logger.debug(f"BlueBird split into {len(children)} birds.")
                            for c in children:
                                self.birds.append(c)
                            return

        # Inicio de apuntado: origen = slingshot fijo
        if button == arcade.MOUSE_BUTTON_LEFT:
            self.start_point = Point2D(SLINGSHOT_X, SLINGSHOT_Y)
            self.end_point = Point2D(x, y)
            self.draw_line = True
            # recalcular preview
            choice = self._choose_bird_by_distance()
            self.preview_points = self.compute_predicted_path(self.start_point, self.end_point, choice)
            logger.debug(f"Aiming start at {self.start_point}, choice={choice}")

    def on_mouse_drag(self, x: int, y: int, dx: int, dy: int, buttons: int, modifiers: int):
        if buttons == arcade.MOUSE_BUTTON_LEFT and self.draw_line:
            self.end_point = Point2D(x, y)
            # actualizar preview
            choice = self._choose_bird_by_distance()
            self.preview_points = self.compute_predicted_path(self.start_point, self.end_point, choice)

    def on_mouse_release(self, x: int, y: int, button: int, modifiers: int):
        if button == arcade.MOUSE_BUTTON_LEFT and self.draw_line:
            self.draw_line = False
            impulse_vector = get_impulse_vector(self.start_point, self.end_point)
            dist = get_distance(self.start_point, self.end_point)

            # decidir tipo por selección forzada o distancia
            if self.forced_bird_type is not None:
                choice = self.forced_bird_type
            else:
                choice = self._choose_bird_by_distance()

            # crear según choice, siempre en SLINGSHOT coords
            if choice == "yellow":
                p = DEFAULT_PARAMS["yellow"]
                bird = YellowBird("assets/img/yellow.png", impulse_vector,
                                  SLINGSHOT_X, SLINGSHOT_Y, self.space,
                                  mass=p["mass"], radius=p["radius"],
                                  max_impulse=p["max_impulse"], power_multiplier=p["power_multiplier"])
                bird.boost_multiplier = p.get("boost_multiplier", 2.0)
                logger.debug("Created YellowBird")
            elif choice == "blue":
                p = DEFAULT_PARAMS["blue"]
                bird = BlueBird("assets/img/blue.png", impulse_vector,
                                SLINGSHOT_X, SLINGSHOT_Y, self.space,
                                mass=p["mass"], radius=p["radius"],
                                max_impulse=p["max_impulse"], power_multiplier=p["power_multiplier"],
                                split_angle_deg=p.get("split_angle_deg", 30.0))
                logger.debug("Created BlueBird")
            else:
                p = DEFAULT_PARAMS["red"]
                bird = Bird("assets/img/red-bird3.png", impulse_vector,
                            SLINGSHOT_X, SLINGSHOT_Y, self.space,
                            mass=p["mass"], radius=p["radius"],
                            max_impulse=p["max_impulse"], power_multiplier=p["power_multiplier"])
                logger.debug("Created RedBird")

            self.sprites.append(bird)
            self.birds.append(bird)
            # limpiar preview cache
            self.preview_points = []

    def _choose_bird_by_distance(self):
        """Elige bird por distancia (cuando forced_bird_type es None)."""
        dist = get_distance(self.start_point, self.end_point)
        if dist > 200:
            return "yellow"
        elif dist > 100:
            return "blue"
        else:
            return "red"

    # ------------------------
    # Key input: selección de pájaro manual y otros controles
    # ------------------------
    def on_key_press(self, symbol, modifiers):
        # Selección rápida R=red, B=blue, Y=yellow. SPACE = volver a automático
        if symbol == arcade.key.R:
            self.forced_bird_type = "red"
            logger.debug("Forced bird type -> red")
        elif symbol == arcade.key.B:
            self.forced_bird_type = "blue"
            logger.debug("Forced bird type -> blue")
        elif symbol == arcade.key.Y:
            self.forced_bird_type = "yellow"
            logger.debug("Forced bird type -> yellow")
        elif symbol == arcade.key.SPACE:
            self.forced_bird_type = None
            logger.debug("Forced bird type cleared (auto)")
        # conservación de compatibilidad: también aceptar 1/2/3
        elif symbol == arcade.key.KEY_1:
            self.forced_bird_type = "red"
            logger.debug("Forced bird type -> red (1)")
        elif symbol == arcade.key.KEY_2:
            self.forced_bird_type = "blue"
            logger.debug("Forced bird type -> blue (2)")
        elif symbol == arcade.key.KEY_3:
            self.forced_bird_type = "yellow"
            logger.debug("Forced bird type -> yellow (3)")

    # ------------------------
    # Draw
    # ------------------------
    def on_draw(self):
        self.clear()
        # textura de fondo
        try:
            arcade.draw_texture_rect(self.background, arcade.LRBT(0, WIDTH, 0, HEIGHT))
        except Exception:
            # fallback si la función de textura no está disponible en la versión
            arcade.draw_lrwh_rectangle_textured(0, 0, WIDTH, HEIGHT, self.background)

        self.sprites.draw()

        # dibujar línea de apuntado + preview (puntos)
        if self.draw_line:
            arcade.draw_line(self.start_point.x, self.start_point.y, self.end_point.x, self.end_point.y,
                             arcade.color.BLACK, 3)
            # si no hay preview calculada, calcularla ahora
            if not self.preview_points:
                choice = self._choose_bird_by_distance()
                self.preview_points = self.compute_predicted_path(self.start_point, self.end_point, choice)
            for i, (px, py) in enumerate(self.preview_points):
                radius = max(2, 6 - (i // 10))
                arcade.draw_circle_filled(px, py, radius, arcade.color.ASH_GREY)

        # HUD
        arcade.draw_text(f"Score: {self.score}", 10, HEIGHT - 30, arcade.color.WHITE, 20)
        cur_level = self.level_manager.current_level
        arcade.draw_text(f"Level: {cur_level}", 10, HEIGHT - 60, arcade.color.WHITE, 16)
        forced = self.forced_bird_type or "auto"
        arcade.draw_text(f"Bird select: {forced}", 10, HEIGHT - 90, arcade.color.WHITE, 14)

    # ------------------------
    # Level loading helper
    # ------------------------
    def load_level(self, level_idx):
        """Limpiar el mundo actual y ejecutar setup del nivel indicado."""
        # remover world (shapes/bodies y sprites)
        for obj in list(self.world):
            try:
                if hasattr(obj, "shape") and hasattr(obj, "body"):
                    try:
                        self.space.remove(obj.shape, obj.body)
                    except Exception:
                        pass
                obj.remove_from_sprite_lists()
            except Exception:
                pass
        self.world = arcade.SpriteList()

        # ejecutar setup
        if 0 <= level_idx < len(self.level_manager.levels):
            _, setup = self.level_manager.levels[level_idx]
            if setup:
                setup(self, level_idx)
            self.level_manager.current_level = level_idx

# ------------------------
# main
# ------------------------
def main():
    window = arcade.Window(WIDTH, HEIGHT, TITLE)
    game = App()
    window.show_view(game)
    arcade.run()


if __name__ == "__main__":
    main()
