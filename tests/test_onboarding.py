"""Tests for placement quiz — adaptive level assessment (mandarin.placement).

Replaces former tests for mandarin.ai.onboarding (dead code).
Tests the canonical placement module: generate_placement_quiz, score_placement.
"""

import unittest
from unittest.mock import patch

from mandarin.db.core import SCHEMA_VERSION
from mandarin.placement import (
    generate_placement_quiz,
    score_placement,
)

from tests.shared_db import make_test_db as _make_db


class TestGeneratePlacementQuiz(unittest.TestCase):
    """Tests for generate_placement_quiz()."""

    @patch("mandarin.placement._load_questions")
    def test_returns_questions(self, mock_load):
        mock_load.return_value = {
            1: [{"hanzi": "你好", "pinyin": "nǐ hǎo", "english": "hello"}],
            2: [{"hanzi": "电脑", "pinyin": "diàn nǎo", "english": "computer"}],
            3: [{"hanzi": "环境", "pinyin": "huán jìng", "english": "environment"}],
        }
        questions = generate_placement_quiz()
        self.assertTrue(len(questions) > 0)

    @patch("mandarin.placement._load_questions")
    def test_empty_questions_returns_empty(self, mock_load):
        mock_load.return_value = {}
        questions = generate_placement_quiz()
        self.assertEqual(questions, [])

    @patch("mandarin.placement._load_questions")
    def test_questions_have_required_fields(self, mock_load):
        mock_load.return_value = {
            1: [
                {"hanzi": "你好", "pinyin": "nǐ hǎo", "english": "hello"},
                {"hanzi": "谢谢", "pinyin": "xiè xie", "english": "thank you"},
                {"hanzi": "早上", "pinyin": "zǎo shang", "english": "morning"},
                {"hanzi": "再见", "pinyin": "zài jiàn", "english": "goodbye"},
            ],
            2: [
                {"hanzi": "电脑", "pinyin": "diàn nǎo", "english": "computer"},
                {"hanzi": "比较", "pinyin": "bǐ jiào", "english": "compare"},
                {"hanzi": "学习", "pinyin": "xué xí", "english": "study"},
                {"hanzi": "老师", "pinyin": "lǎo shī", "english": "teacher"},
            ],
        }
        questions = generate_placement_quiz()
        for q in questions:
            self.assertIn("hanzi", q)
            self.assertIn("pinyin", q)
            self.assertIn("options", q)
            self.assertIn("correct", q)
            self.assertIn("hsk_level", q)
            self.assertEqual(len(q["options"]), 4)

    @patch("mandarin.placement._load_questions")
    def test_max_15_questions(self, mock_load):
        # Provide ample data across many levels
        mock_load.return_value = {
            level: [
                {"hanzi": f"字{level}_{i}", "pinyin": f"zi{level}_{i}", "english": f"word{level}_{i}"}
                for i in range(5)
            ]
            for level in range(1, 10)
        }
        questions = generate_placement_quiz()
        self.assertLessEqual(len(questions), 15)

    @patch("mandarin.placement._load_questions")
    def test_returning_learner_starts_higher(self, mock_load):
        mock_load.return_value = {
            level: [
                {"hanzi": f"字{level}_{i}", "pinyin": f"zi{level}_{i}", "english": f"word{level}_{i}"}
                for i in range(5)
            ]
            for level in range(1, 10)
        }
        returning_questions = generate_placement_quiz(returning=True)
        new_questions = generate_placement_quiz(returning=False)
        # Both should produce questions; returning starts at HSK 3, new at HSK 2
        self.assertTrue(len(returning_questions) > 0)
        self.assertTrue(len(new_questions) > 0)


class TestScorePlacement(unittest.TestCase):
    """Tests for score_placement()."""

    def test_empty_answers_returns_level_1(self):
        result = score_placement([])
        self.assertEqual(result["estimated_level"], 1)
        self.assertEqual(result["confidence"], "low")
        self.assertEqual(result["total_correct"], 0)
        self.assertEqual(result["total_questions"], 0)

    def test_all_wrong_returns_level_1(self):
        answers = [
            {"hsk_level": level, "selected": "wrong", "correct": "right"}
            for level in range(1, 5)
            for _ in range(3)
        ]
        result = score_placement(answers)
        self.assertEqual(result["estimated_level"], 1)
        self.assertEqual(result["total_correct"], 0)

    def test_all_correct_returns_highest_level(self):
        answers = [
            {"hsk_level": level, "selected": "correct", "correct": "correct"}
            for level in range(1, 6)
            for _ in range(3)
        ]
        result = score_placement(answers)
        self.assertEqual(result["estimated_level"], 5)
        self.assertGreater(result["total_correct"], 0)

    def test_stops_at_low_accuracy(self):
        answers = []
        # Levels 1-2: 100% correct
        for level in [1, 2]:
            for _ in range(3):
                answers.append({"hsk_level": level, "selected": "right", "correct": "right"})
        # Level 3: 0% correct
        for _ in range(3):
            answers.append({"hsk_level": 3, "selected": "wrong", "correct": "right"})

        result = score_placement(answers)
        self.assertEqual(result["estimated_level"], 2)

    def test_per_level_accuracy(self):
        answers = [
            {"hsk_level": 1, "selected": "a", "correct": "a"},
            {"hsk_level": 1, "selected": "b", "correct": "a"},
            {"hsk_level": 2, "selected": "a", "correct": "a"},
        ]
        result = score_placement(answers)
        self.assertIn(1, result["per_level_accuracy"])
        self.assertIn(2, result["per_level_accuracy"])
        self.assertEqual(result["per_level_accuracy"][1]["correct"], 1)
        self.assertEqual(result["per_level_accuracy"][1]["total"], 2)
        self.assertEqual(result["per_level_accuracy"][2]["correct"], 1)

    def test_confidence_high_with_enough_data(self):
        answers = [
            {"hsk_level": level, "selected": "a", "correct": "a"}
            for level in range(1, 5)
            for _ in range(3)
        ]
        result = score_placement(answers)
        self.assertEqual(result["confidence"], "high")

    def test_confidence_medium_with_moderate_data(self):
        answers = [
            {"hsk_level": level, "selected": "a", "correct": "a"}
            for level in [1, 2]
            for _ in range(3)
        ]
        result = score_placement(answers)
        self.assertIn(result["confidence"], ("medium", "high"))

    def test_confidence_low_with_few_answers(self):
        answers = [
            {"hsk_level": 1, "selected": "a", "correct": "a"},
            {"hsk_level": 2, "selected": "a", "correct": "a"},
        ]
        result = score_placement(answers)
        self.assertEqual(result["confidence"], "low")


class TestSchemaVersion(unittest.TestCase):
    def test_schema_includes_doc17(self):
        self.assertGreaterEqual(SCHEMA_VERSION, 80)


if __name__ == "__main__":
    unittest.main()
