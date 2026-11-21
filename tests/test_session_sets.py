import unittest

from session_ui import Session


class SessionSetsTests(unittest.TestCase):
    def test_set_boundary_pauses_and_requires_start(self):
        session = Session(target=2, sets=3)
        session.start(0)
        session.add(2, 5)
        self.assertEqual((session.count, session.completed_sets, session.set_reps), (2, 1, 2))
        self.assertTrue(session.awaiting_next_set)
        self.assertIsNone(session.completed_at)
        session.add(1, 30)
        self.assertEqual(session.count, 2)
        session.start(40)
        session.add(0, 41)
        self.assertFalse(session.awaiting_next_set)
        self.assertEqual((session.set_number, session.set_reps), (2, 0))
        session.add(2, 45)
        session.start(100)
        session.add(2, 105)
        self.assertEqual((session.count, session.completed_sets, session.total_target), (6, 3, 6))
        self.assertIsNotNone(session.completed_at)
        self.assertEqual(session.seconds(500), 15)

    def test_simultaneous_reps_do_not_spill_into_rest(self):
        session = Session(target=3, sets=2)
        session.start(0)
        session.add(2, 1)
        session.add(2, 2)
        self.assertEqual(session.count, 3)
        self.assertTrue(session.awaiting_next_set)
        session.start(10)
        session.add(0, 11)
        self.assertEqual(session.set_reps, 0)
        session.add(3, 12)
        self.assertEqual(session.count, 6)

    def test_reset_clears_sets_and_keeps_goals(self):
        session = Session(target=5, sets=4)
        session.start(0)
        session.add(5, 2)
        session.reset()
        self.assertEqual((session.count, session.completed_sets, session.set_reps), (0, 0, 0))
        self.assertEqual((session.target, session.sets_target, session.total_target), (5, 4, 20))
        self.assertFalse(session.awaiting_next_set)
        self.assertEqual(session.set_number, 1)

    def test_single_set_still_completes_normally(self):
        session = Session(target=2)
        session.start(0)
        session.add(2, 5)
        self.assertIsNotNone(session.completed_at)
        session.add(1, 6)
        self.assertEqual(session.count, 2)


if __name__ == '__main__':
    unittest.main()
