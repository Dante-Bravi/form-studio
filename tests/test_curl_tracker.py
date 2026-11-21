"""Exercise the lift/top/rearm behavior with deterministic visible arm poses."""
import math
from types import SimpleNamespace
import unittest

from live_camera import CurlTracker


def pose(angle):
    points = [SimpleNamespace(x=.5, y=.5, visibility=1, presence=1) for _ in range(33)]
    points[11].y = .3
    points[15].x = .5 + .2 * math.sin(math.radians(angle))
    points[15].y = .5 - .2 * math.cos(math.radians(angle))
    return points


class CurlTrackerTests(unittest.TestCase):
    def setUp(self):
        self.tracker = CurlTracker()
        self.now = 0

    def feed(self, angles, moving=True):
        events = 0
        for angle in angles:
            self.now += .125
            events += self.tracker.update(pose(angle), 0, 1, self.now, moving)
        return events

    def lift(self):
        return self.feed([170]*6 + [150,130,115,100,85,75,75])

    def test_counts_before_any_lowering(self):
        self.assertEqual(self.lift(), 1)
        self.assertEqual(self.tracker.phase, 'top')

    def test_holding_and_jitter_do_not_count_again(self):
        self.lift()
        self.assertEqual(self.feed([75]*30, moving=False), 0)
        self.assertEqual(self.feed([80,76,83,75]*4), 0)
        self.assertEqual(self.tracker.phase, 'top')

    def test_lowering_rearms_without_awarding_a_rep(self):
        self.lift()
        self.assertEqual(self.feed([100,130,155,170,170]), 0)
        self.assertEqual(self.lift(), 1)

    def test_partial_lift_and_still_pose_do_not_count(self):
        self.assertEqual(self.feed([170]*6+[160,150,145,145,150,160,170]*2), 0)
        self.tracker.reset()
        self.assertEqual(self.feed([75]*20, moving=False), 0)

    def test_shorter_range_lift_counts_at_held_top(self):
        self.assertEqual(self.feed([170]*6+[150,130,115,112,112,112,112,112]), 1)
        self.assertEqual(self.tracker.phase, 'top')


if __name__ == '__main__':
    unittest.main()
