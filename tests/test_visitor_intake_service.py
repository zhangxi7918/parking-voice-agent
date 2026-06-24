import unittest

from voice_agent.app.visitor_intake_service import VisitorIntakeService
from voice_agent.domain.visitor import VisitorIntake


class VisitorIntakeServiceTest(unittest.TestCase):
    def test_extracts_complete_intake_from_one_turn(self):
        service = VisitorIntakeService()
        intake = VisitorIntake()

        result = service.process_caller_text(
            intake,
            "你好，我叫张师傅，手机号是13800138000，车牌沪A12345，来找王经理送货",
        )

        self.assertTrue(result.completed)
        self.assertEqual(result.intake.visitor_name, "张师傅")
        self.assertEqual(result.intake.phone, "13800138000")
        self.assertEqual(result.intake.plate_number, "沪A12345")
        self.assertEqual(result.intake.visit_purpose, "送货")
        self.assertEqual(result.intake.host_name, "王经理")

    def test_asks_for_next_missing_field(self):
        service = VisitorIntakeService()
        intake = VisitorIntake(visitor_name="张", phone="13800138000")

        result = service.process_caller_text(intake, "我到了")

        self.assertFalse(result.completed)
        self.assertIn("车牌", result.agent_text)


if __name__ == "__main__":
    unittest.main()
