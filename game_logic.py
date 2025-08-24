import math
import arcade
from dataclasses import dataclass
from logging import getLogger

logger = getLogger(__name__)


@dataclass
class ImpulseVector:
    angle: float
    impulse: float


@dataclass
class Point2D:
    x: float = 0
    y: float = 0


def get_angle_radians(point_a: Point2D, point_b: Point2D) -> float:
    delta_x = point_a.x - point_b.x
    delta_y = point_a.y - point_b.y
    angle = math.atan2(delta_y, delta_x)
    return angle



def get_distance(point_a: Point2D, point_b: Point2D) -> float:
    delta_x = point_b.x - point_a.x
    delta_y = point_b.y - point_a.y
    dist = math.sqrt(delta_x**2 + delta_y**2)
    return dist


def get_impulse_vector(start_point: Point2D, end_point: Point2D) -> ImpulseVector:
    angle = get_angle_radians(start_point, end_point)
    impulse = get_distance(start_point, end_point)
    return ImpulseVector(angle, impulse)