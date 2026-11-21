import unittest

import verify as V


class VerificationTests(unittest.TestCase):
    def test_limit_cannot_silently_omit_late_solution(self):
        with self.assertRaisesRegex(RuntimeError, 'incomplete'):
            V.all_of(lambda x: x == 5, range(6), limit=5)

    def test_exactly_limit_is_complete(self):
        self.assertEqual(V.all_of(lambda x: x % 2 == 0, range(5), limit=5), [0, 2, 4])

    def test_count_refuses_incomplete_search(self):
        with self.assertRaises(RuntimeError):
            V.brute_count(lambda x: True, range(5), limit=4)

    def test_cycle_requires_at_least_two_observed_repetitions(self):
        self.assertIsNone(V.find_cycle([1, 2, 3], max_len=100))
        self.assertEqual(V.find_cycle([1, 2, 1, 2]), [1, 2])

    def test_zero_take_does_not_consume_generator(self):
        generator = iter([1, 2])
        self.assertEqual(V.take(generator, 0), [])
        self.assertEqual(next(generator), 1)

    def test_invalid_cycle_index_is_not_wraparound(self):
        with self.assertRaises(ValueError):
            V.nth_by_cycle([1, 2], 0)


if __name__ == '__main__':
    unittest.main()
