import math
import arcade
import pymunk
from typing import List, Optional, Callable, Tuple

from game_logic import ImpulseVector


# -------------------------
# Base classes`
# -------------------------
class Bird(arcade.Sprite):
    """
    Bird class. This represents an angry bird. All the physics is handled by Pymunk.
    El constructor aplica el impulso inicial (como ya tenías).
    """
    def __init__(
        self,
        image_path: str,
        impulse_vector: ImpulseVector,
        x: float,
        y: float,
        space: pymunk.Space,
        mass: float = 5,
        radius: float = 12,
        max_impulse: float = 100,
        power_multiplier: float = 50,
        elasticity: float = 0.8,
        friction: float = 1,
        collision_layer: int = 0,
    ):
        super().__init__(image_path, 1)
        # Guardar para reconstrucción/children
        self.image_path = image_path

        # body
        moment = pymunk.moment_for_circle(mass, 0, radius)
        body = pymunk.Body(mass, moment)
        body.position = (x, y)

        # Calculamos el impulso aplicado como en main.py: clamp(impulse) * power_multiplier
        impulse_value = min(max_impulse, impulse_vector.impulse) * power_multiplier
        impulse_pymunk = impulse_value * pymunk.Vec2d(1, 0)
        body.apply_impulse_at_local_point(impulse_pymunk.rotated(impulse_vector.angle))

        # shape
        shape = pymunk.Circle(body, radius)
        shape.elasticity = elasticity
        shape.friction = friction
        shape.collision_type = collision_layer

        space.add(body, shape)

        self.body = body
        self.shape = shape
        self.space = space  # referencia al space para operaciones futuras

        # estado de habilidad
        self.launched = True
        self.used_ability = False

        # parámetros para reconstrución
        self._mass = mass
        self._radius = radius
        self._max_impulse = max_impulse
        self._power_multiplier = power_multiplier

    def update(self, delta_time):
        """
        Sincroniza la posición y rotación del sprite con pymunk.
        """
        self.center_x = self.shape.body.position.x
        self.center_y = self.shape.body.position.y
        self.radians = self.shape.body.angle

    def remove_from_space_and_lists(self):
        """
        Quita body/shape del pymunk.Space y remueve el sprite de cualquier SpriteList.
        """
        try:
            if self.space is not None:
                self.space.remove(self.body, self.shape)
        except Exception:
            pass
        try:
            self.kill()
        except Exception:
            try:
                self.remove_from_sprite_lists()
            except Exception:
                pass


class Pig(arcade.Sprite):
    def __init__(
        self,
        x: float,
        y: float,
        space: pymunk.Space,
        mass: float = 2,
        elasticity: float = 0.8,
        friction: float = 0.4,
        collision_layer: int = 0,
    ):
        super().__init__("assets/img/pig_failed.png", 0.1)
        moment = pymunk.moment_for_circle(mass, 0, self.width / 2 - 3)
        body = pymunk.Body(mass, moment)
        body.position = (x, y)
        shape = pymunk.Circle(body, self.width / 2 - 3)
        shape.elasticity = elasticity
        shape.friction = friction
        shape.collision_type = collision_layer
        space.add(body, shape)
        self.body = body
        self.shape = shape
        self.space = space

    def update(self, delta_time):
        self.center_x = self.shape.body.position.x
        self.center_y = self.shape.body.position.y
        self.radians = self.shape.body.angle


class PassiveObject(arcade.Sprite):
    """
    Passive object que puede colisionar y ser destruido.
    """
    def __init__(
        self,
        image_path: str,
        x: float,
        y: float,
        space: pymunk.Space,
        mass: float = 2,
        elasticity: float = 0.8,
        friction: float = 1,
        collision_layer: int = 0,
    ):
        super().__init__(image_path, 1)

        moment = pymunk.moment_for_box(mass, (self.width, self.height))
        body = pymunk.Body(mass, moment)
        body.position = (x, y)
        shape = pymunk.Poly.create_box(body, (self.width, self.height))
        shape.elasticity = elasticity
        shape.friction = friction
        shape.collision_type = collision_layer
        space.add(body, shape)
        self.body = body
        self.shape = shape
        self.space = space

    def update(self, delta_time):
        self.center_x = self.shape.body.position.x
        self.center_y = self.shape.body.position.y
        self.radians = self.shape.body.angle


class Column(PassiveObject):
    def __init__(self, x, y, space):
        super().__init__("assets/img/column.png", x, y, space)


class StaticObject(arcade.Sprite):
    """
    Objetos estáticos (no se mueven). Se usa pymunk.Body.STATIC.
    """
    def __init__(
            self,
            image_path: str,
            x: float,
            y: float,
            space: pymunk.Space,
            elasticity: float = 0.8,
            friction: float = 1,
            collision_layer: int = 0,
    ):
        super().__init__(image_path, 1)
        body = pymunk.Body(body_type=pymunk.Body.STATIC)
        body.position = (x, y)
        shape = pymunk.Poly.create_box(body, (self.width, self.height))
        shape.elasticity = elasticity
        shape.friction = friction
        shape.collision_type = collision_layer
        space.add(body, shape)
        self.body = body
        self.shape = shape
        self.space = space

    def update(self, delta_time):
        self.center_x = self.shape.body.position.x
        self.center_y = self.shape.body.position.y
        self.radians = self.shape.body.angle


# -------------------------
# YellowBird: boost
# -------------------------
class YellowBird(Bird):
    """
    Si el usuario hace clic izquierdo mientras está en vuelo, incrementa
    su velocidad multiplicando body.velocity por boost_multiplier.
    """
    def __init__(
        self,
        image_path: str,
        impulse_vector: ImpulseVector,
        x: float,
        y: float,
        space: pymunk.Space,
        boost_multiplier: float = 2.0,
        scale: float = 0.1,
        **kwargs
    ):
        super().__init__(image_path, impulse_vector, x, y, space, **kwargs)
        self.boost_multiplier = boost_multiplier
        self.scale = scale

    def on_click_ability(self) -> bool:
        if not getattr(self, "launched", False):
            return False
        if getattr(self, "used_ability", False):
            return False

        vx, vy = self.body.velocity.x, self.body.velocity.y
        speed = math.hypot(vx, vy)
        if speed < 1e-3:
            return False

        new_v = pymunk.Vec2d(vx, vy) * self.boost_multiplier
        self.body.velocity = new_v
        self.used_ability = True
        return True


# -------------------------
# BlueBird: split
# -------------------------
class BlueBird(Bird):
    """
    Si el usuario hace clic mientras está en vuelo, se divide en 3 pájaros con
    separación angular (split_angle_deg). Conserva la magnitud de la velocidad.
    """
    def __init__(
        self,
        image_path: str,
        impulse_vector: ImpulseVector,
        x: float,
        y: float,
        space: pymunk.Space,
        split_angle_deg: float = 30.0,
        child_class: Optional[Callable] = None,
        scale: float = 0.3,
        **kwargs
    ):
        super().__init__(image_path, impulse_vector, x, y, space, **kwargs)
        self.split_angle_deg = split_angle_deg
        self.child_class = child_class or Bird
        self.scale = scale

    def split(self, sprite_list: arcade.SpriteList) -> List[Bird]:
        if not getattr(self, "launched", False) or getattr(self, "used_ability", False):
            return []

        vx, vy = self.body.velocity.x, self.body.velocity.y
        speed = math.hypot(vx, vy)
        if speed < 1e-3:
            return []

        base_angle_deg = math.degrees(math.atan2(vy, vx))
        angles = [base_angle_deg + self.split_angle_deg, base_angle_deg, base_angle_deg - self.split_angle_deg]

        children: List[Bird] = []
        for ang_deg in angles:
            ang_rad = math.radians(ang_deg)
            # crear impulsito nulo para no re-aplicar impulso
            zero_impulse = ImpulseVector(angle=0.0, impulse=0.0)
            # crear instancia del child
            child = self.child_class(
                self.image_path,
                zero_impulse,
                self.center_x,
                self.center_y,
                self.space,
                mass=getattr(self, "_mass", 5),
                radius=getattr(self, "_radius", 12),
            )
            # setear velocidad manteniendo magnitud
            vx_child = math.cos(ang_rad) * speed
            vy_child = math.sin(ang_rad) * speed
            child.body.velocity = pymunk.Vec2d(vx_child, vy_child)
            child.launched = True
            child.used_ability = True
            sprite_list.append(child)
            children.append(child)

        # remover el original del space y de listas
        self.used_ability = True
        try:
            self.remove_from_space_and_lists()
        except Exception:
            pass

        return children

    def on_click_ability(self, sprite_list: arcade.SpriteList) -> List[Bird]:
        return self.split(sprite_list)


# -------------------------
# LevelManager: extra
# -------------------------
class LevelManager:
    """
    Gestión simple de niveles basada en umbrales de puntaje.
    """
    def __init__(self):
        self.levels: List[Tuple[int, Optional[Callable]]] = []
        self.current_level: int = -1
        self.score: int = 0

    def add_level(self, threshold: int, setup_callback: Optional[Callable] = None):
        self.levels.append((threshold, setup_callback))

    def start(self, game):
        if not self.levels:
            return
        self.current_level = 0
        thresh, setup = self.levels[0]
        if setup:
            setup(game, 0)

    def update_score(self, new_score: int):
        self.score = new_score

    def check_and_advance(self, game) -> bool:
        if self.current_level + 1 >= len(self.levels):
            return False
        next_idx = self.current_level + 1
        thresh, setup = self.levels[next_idx]
        if self.score >= thresh:
            self.current_level = next_idx
            if setup:
                setup(game, next_idx)
            return True
        return False

    def is_last_level(self) -> bool:
        return self.current_level == len(self.levels) - 1


# -------------------------
# Helpers
# -------------------------
def example_create_yellow(texture: str, x: float, y: float, space: pymunk.Space) -> YellowBird:
    # crear con impulsito nulo para luego lanzarlo manualmente si lo necesitas
    iv = ImpulseVector(angle=0.0, impulse=0.0)
    return YellowBird(texture, iv, x, y, space)


def example_create_blue(texture: str, x: float, y: float, space: pymunk.Space) -> BlueBird:
    iv = ImpulseVector(angle=0.0, impulse=0.0)
    return BlueBird(texture, iv, x, y, space)
