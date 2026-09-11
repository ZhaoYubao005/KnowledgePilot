import importlib
import json
import sys
import types
import unittest
from unittest.mock import patch

from knowledge_pilot.tools.calculator import calculator
from knowledge_pilot.tools.schemas import (
    calculator_schema,
    search_knowledge_base_schema,
)


class CalculatorTests(unittest.TestCase):
    def test_four_supported_operations(self):
        cases = [
            ("add", 15),
            ("subtract", 5),
            ("multiply", 50),
            ("divide", 2),
        ]

        for operation, expected in cases:
            with self.subTest(operation=operation):
                self.assertEqual(calculator(10, 5, operation), expected)

    def test_division_by_zero_raises_value_error(self):
        with self.assertRaisesRegex(ValueError, "除数不能为0"):
            calculator(10, 0, "divide")


class SchemaTests(unittest.TestCase):
    def test_calculator_schema_name_matches_tool_name(self):
        self.assertEqual(
            calculator_schema["function"]["name"],
            "calculator",
        )

    def test_knowledge_base_schema_name_matches_tool_name(self):
        self.assertEqual(
            search_knowledge_base_schema["function"]["name"],
            "search_knowledge_base",
        )


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.fake_search = lambda **arguments: arguments
        fake_module = types.ModuleType(
            "knowledge_pilot.tools.knowledge_base_tool"
        )
        fake_module.search_knowledge_base = self.fake_search
        self.module_patch = patch.dict(
            sys.modules,
            {"knowledge_pilot.tools.knowledge_base_tool": fake_module},
        )
        self.module_patch.start()
        sys.modules.pop("knowledge_pilot.tools.registry", None)
        self.registry = importlib.import_module(
            "knowledge_pilot.tools.registry"
        )

    def tearDown(self):
        sys.modules.pop("knowledge_pilot.tools.registry", None)
        self.module_patch.stop()

    def test_registry_uses_canonical_name(self):
        self.assertTrue(hasattr(self.registry, "TOOL_REGISTRY"))

    def test_registry_can_execute_calculator(self):
        self.assertEqual(
            self.registry.execute_tool(
                "calculator",
                {"a": 19, "b": 23, "operation": "multiply"},
            ),
            437,
        )

    def test_registry_can_find_search_knowledge_base(self):
        result = self.registry.execute_tool(
            "search_knowledge_base",
            {"query": "机器学习", "top_k": 3},
        )

        self.assertEqual(
            result,
            {"query": "机器学习", "top_k": 3},
        )

    def test_unknown_tool_raises_value_error(self):
        with self.assertRaisesRegex(ValueError, "工具不存在"):
            self.registry.execute_tool("unknown_tool", {})

    def test_execute_tool_call_accepts_dict_arguments(self):
        result = self.registry.execute_tool_call(
            {
                "function": {
                    "name": "calculator",
                    "arguments": {
                        "a": 8,
                        "b": 4,
                        "operation": "divide",
                    },
                }
            }
        )

        self.assertEqual(result, 2)

    def test_execute_tool_call_accepts_json_string_arguments(self):
        result = self.registry.execute_tool_call(
            {
                "function": {
                    "name": "calculator",
                    "arguments": json.dumps(
                        {"a": 7, "b": 6, "operation": "multiply"}
                    ),
                }
            }
        )

        self.assertEqual(result, 42)


if __name__ == "__main__":
    unittest.main()
