import unittest

from lip.jobs import GenJob, JobStore


def _job(pid="p1", seed=0, tag="interior"):
    return GenJob(id=f"J-{pid}-{seed}", prompt_id=pid, tag=tag, seed=seed, positive="a room")


class TestJobStore(unittest.TestCase):
    def test_lifecycle_and_summary(self):
        s = JobStore()
        j = s.create(_job())
        s.mark(j.id, "generating")
        s.mark(j.id, "optimizing")
        s.mark(j.id, "done", bytes_total=1000)
        summ = s.summary()
        self.assertEqual(summ["totals"]["done"], 1)
        self.assertEqual(summ["totals"]["bytes_total"], 1000)
        self.assertEqual(summ["distribution"], [{"tag": "interior", "value": 1}])

    def test_started_and_completed_timestamps(self):
        s = JobStore()
        j = s.create(_job())
        self.assertIsNone(s.jobs()[0].started_at)
        s.mark(j.id, "generating")
        self.assertIsNotNone(s.jobs()[0].started_at)
        s.mark(j.id, "done")
        self.assertIsNotNone(s.jobs()[0].completed_at)

    def test_control_flags(self):
        s = JobStore()
        self.assertFalse(s.is_paused)
        s.pause(); self.assertTrue(s.is_paused)
        s.resume(); self.assertFalse(s.is_paused)
        self.assertFalse(s.should_stop)
        s.stop(); self.assertTrue(s.should_stop)
        s.cancel("p9"); self.assertTrue(s.is_cancelled("p9"))
        self.assertFalse(s.is_cancelled("p8"))

    def test_events_and_status_label(self):
        s = JobStore()
        s.event("warning", "hello")
        self.assertEqual(s.events()[0].message, "hello")
        j = s.create(_job())
        s.mark(j.id, "generating")
        self.assertEqual(s.jobs()[0].as_dict()["status_label"], "생성 중")


if __name__ == "__main__":
    unittest.main()
