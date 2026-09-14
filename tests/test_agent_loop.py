import copy
import unittest
from unittest.mock import Mock, call, patch

from knowledge_pilot.llm.ollama_client import chat_with_ollama
from knowledge_pilot.tools.schemas import (
    calculator_schema,
    search_knowledge_base_schema,
)


class AgentLoopTests(unittest.TestCase):
    @staticmethod
    def _messages():
        return [
            {
                "role": "system",
                "content": "你是一个助手。",
            },
            {
                "role": "user",
                "content": "请完成任务。",
            },
        ]

    @staticmethod
    def _response(message):
        response = Mock()
        response.json.return_value = {"message": message}
        return response

    def _capture_payloads(self, mock_post, *assistant_messages):
        responses = iter(
            self._response(message) for message in assistant_messages
        )
        payloads = []

        def post(*args, **kwargs):
            payloads.append(copy.deepcopy(kwargs["json"]))
            return next(responses)

        mock_post.side_effect = post
        return payloads

    def _assert_tools_in_every_payload(self, payloads):
        self.assertTrue(payloads)
        for payload in payloads:
            self.assertEqual(
                payload["tools"],
                [calculator_schema, search_knowledge_base_schema],
            )

    def _assert_agent_result(self, result):
        self.assertEqual(
            set(result),
            {"answer", "trace", "stop_reason"},
        )

    @patch("knowledge_pilot.llm.ollama_client.requests.post")
    def test_returns_direct_answer_without_tool_calls(self, mock_post):
        mock_post.return_value.json.return_value = {
            "message": {
                "content": "你好，有什么可以帮你？"
            }
        }
        messages = [
            {
                "role": "system",
                "content": "你是一个助手。",
            },
            {
                "role": "user",
                "content": "你好",
            },
        ]

        result = chat_with_ollama(messages)

        mock_post.assert_called_once()
        self._assert_agent_result(result)
        self.assertEqual(result["answer"], "你好，有什么可以帮你？")
        self.assertEqual(result["trace"], [])
        self.assertEqual(result["stop_reason"], "completed")
        self._assert_tools_in_every_payload(
            [mock_post.call_args.kwargs["json"]]
        )

    @patch("knowledge_pilot.llm.ollama_client.execute_tool_call")
    @patch("knowledge_pilot.llm.ollama_client.requests.post")
    def test_executes_single_calculator_tool(
        self,
        mock_post,
        mock_execute_tool_call,
    ):
        calculator_call = {
            "function": {
                "name": "calculator",
                "arguments": {
                    "a": 19,
                    "b": 23,
                    "operation": "multiply",
                },
            }
        }
        payloads = self._capture_payloads(
            mock_post,
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [calculator_call],
            },
            {
                "role": "assistant",
                "content": "19 × 23 = 437。",
            },
        )
        mock_execute_tool_call.return_value = 437
        messages = self._messages()

        result = chat_with_ollama(messages)

        mock_execute_tool_call.assert_called_once_with(calculator_call)
        self._assert_agent_result(result)
        self.assertEqual(result["answer"], "19 × 23 = 437。")
        self.assertEqual(result["stop_reason"], "completed")
        self.assertEqual(
            result["trace"],
            [
                {
                    "step": 1,
                    "tool": "calculator",
                    "arguments": calculator_call["function"]["arguments"],
                    "result": 437,
                }
            ],
        )
        self.assertEqual(
            payloads[1]["messages"][-1],
            {
                "role": "tool",
                "tool_name": "calculator",
                "content": "437",
            },
        )
        self._assert_tools_in_every_payload(payloads)

    @patch("knowledge_pilot.llm.ollama_client.execute_tool_call")
    @patch("knowledge_pilot.llm.ollama_client.requests.post")
    def test_executes_single_knowledge_base_tool(
        self,
        mock_post,
        mock_execute_tool_call,
    ):
        knowledge_call = {
            "function": {
                "name": "search_knowledge_base",
                "arguments": {
                    "query": "KnowledgePilot V1.0 测试分数",
                    "top_k": 3,
                },
            }
        }
        knowledge_result = [
            {
                "content": "测试分数为 32。",
                "source": "data/v10_agent_loop_test.txt",
            }
        ]
        payloads = self._capture_payloads(
            mock_post,
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [knowledge_call],
            },
            {
                "role": "assistant",
                "content": "知识库中的测试分数为 32。",
            },
        )
        mock_execute_tool_call.return_value = knowledge_result
        messages = self._messages()

        result = chat_with_ollama(messages)

        mock_execute_tool_call.assert_called_once_with(knowledge_call)
        self._assert_agent_result(result)
        self.assertEqual(result["answer"], "知识库中的测试分数为 32。")
        self.assertEqual(result["stop_reason"], "completed")
        self.assertEqual(
            result["trace"],
            [
                {
                    "step": 1,
                    "tool": "search_knowledge_base",
                    "arguments": knowledge_call["function"]["arguments"],
                    "result": knowledge_result,
                }
            ],
        )
        self.assertEqual(
            payloads[1]["messages"][-1],
            {
                "role": "tool",
                "tool_name": "search_knowledge_base",
                "content": str(knowledge_result),
            },
        )
        self._assert_tools_in_every_payload(payloads)

    @patch("knowledge_pilot.llm.ollama_client.execute_tool_call")
    @patch("knowledge_pilot.llm.ollama_client.requests.post")
    def test_runs_knowledge_base_then_calculator_across_steps(
        self,
        mock_post,
        mock_execute_tool_call,
    ):
        knowledge_call = {
            "function": {
                "name": "search_knowledge_base",
                "arguments": {"query": "V1.0 测试分数"},
            }
        }
        calculator_call = {
            "function": {
                "name": "calculator",
                "arguments": {
                    "a": 32,
                    "b": 3,
                    "operation": "multiply",
                },
            }
        }
        knowledge_result = [
            {
                "content": "测试分数为 32。",
                "source": "data/v10_agent_loop_test.txt",
            }
        ]
        payloads = self._capture_payloads(
            mock_post,
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [knowledge_call],
            },
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [calculator_call],
            },
            {
                "role": "assistant",
                "content": "32 × 3 = 96。",
            },
        )
        mock_execute_tool_call.side_effect = [knowledge_result, 96]
        messages = self._messages()

        result = chat_with_ollama(messages)

        self.assertEqual(
            mock_execute_tool_call.call_args_list,
            [call(knowledge_call), call(calculator_call)],
        )
        self._assert_agent_result(result)
        self.assertEqual(result["answer"], "32 × 3 = 96。")
        self.assertEqual(result["stop_reason"], "completed")
        self.assertEqual(
            result["trace"],
            [
                {
                    "step": 1,
                    "tool": "search_knowledge_base",
                    "arguments": knowledge_call["function"]["arguments"],
                    "result": knowledge_result,
                },
                {
                    "step": 2,
                    "tool": "calculator",
                    "arguments": calculator_call["function"]["arguments"],
                    "result": 96,
                },
            ],
        )
        self.assertEqual(
            payloads[1]["messages"][-1]["content"],
            str(knowledge_result),
        )
        self.assertEqual(payloads[2]["messages"][-1]["content"], "96")
        self._assert_tools_in_every_payload(payloads)

    @patch("knowledge_pilot.llm.ollama_client.execute_tool_call")
    @patch("knowledge_pilot.llm.ollama_client.requests.post")
    def test_converts_tool_error_to_observation_and_continues(
        self,
        mock_post,
        mock_execute_tool_call,
    ):
        calculator_call = {
            "function": {
                "name": "calculator",
                "arguments": {
                    "a": 10,
                    "b": 0,
                    "operation": "divide",
                },
            }
        }
        payloads = self._capture_payloads(
            mock_post,
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [calculator_call],
            },
            {
                "role": "assistant",
                "content": "计算工具执行失败。",
            },
        )
        mock_execute_tool_call.side_effect = ValueError("除数不能为0")
        messages = self._messages()

        result = chat_with_ollama(messages)

        error_result = "Tool execution failed: 除数不能为0"
        self.assertEqual(mock_post.call_count, 2)
        self._assert_agent_result(result)
        self.assertEqual(result["stop_reason"], "completed")
        self.assertEqual(result["trace"][0]["result"], error_result)
        self.assertEqual(
            payloads[1]["messages"][-1],
            {
                "role": "tool",
                "tool_name": "calculator",
                "content": error_result,
            },
        )
        self._assert_tools_in_every_payload(payloads)

    @patch("knowledge_pilot.llm.ollama_client.execute_tool_call")
    @patch("knowledge_pilot.llm.ollama_client.requests.post")
    def test_converts_missing_tool_name_to_error_observation(
        self,
        mock_post,
        mock_execute_tool_call,
    ):
        malformed_call = {
            "function": {
                "arguments": {
                    "a": 1,
                    "b": 2,
                    "operation": "add",
                }
            }
        }
        payloads = self._capture_payloads(
            mock_post,
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [malformed_call],
            },
            {
                "role": "assistant",
                "content": "已处理缺少工具名称的错误。",
            },
        )

        result = chat_with_ollama(self._messages())

        error_result = (
            "Tool execution failed: Tool call missing function.name"
        )
        mock_execute_tool_call.assert_not_called()
        self.assertEqual(mock_post.call_count, 2)
        self._assert_agent_result(result)
        self.assertEqual(result["answer"], "已处理缺少工具名称的错误。")
        self.assertEqual(result["stop_reason"], "completed")
        self.assertEqual(
            result["trace"],
            [
                {
                    "step": 1,
                    "tool": "unknown_tool",
                    "arguments": malformed_call["function"]["arguments"],
                    "result": error_result,
                }
            ],
        )
        self.assertEqual(
            payloads[1]["messages"][-1],
            {
                "role": "tool",
                "tool_name": "unknown_tool",
                "content": error_result,
            },
        )
        self._assert_tools_in_every_payload(payloads)

    @patch("knowledge_pilot.llm.ollama_client.execute_tool_call")
    @patch("knowledge_pilot.llm.ollama_client.requests.post")
    def test_converts_missing_tool_arguments_to_error_observation(
        self,
        mock_post,
        mock_execute_tool_call,
    ):
        malformed_call = {
            "function": {
                "name": "calculator",
            }
        }
        payloads = self._capture_payloads(
            mock_post,
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [malformed_call],
            },
            {
                "role": "assistant",
                "content": "已处理缺少工具参数的错误。",
            },
        )

        result = chat_with_ollama(self._messages())

        error_result = (
            "Tool execution failed: Tool call missing function.arguments"
        )
        mock_execute_tool_call.assert_not_called()
        self.assertEqual(mock_post.call_count, 2)
        self._assert_agent_result(result)
        self.assertEqual(result["answer"], "已处理缺少工具参数的错误。")
        self.assertEqual(result["stop_reason"], "completed")
        self.assertEqual(
            result["trace"],
            [
                {
                    "step": 1,
                    "tool": "calculator",
                    "arguments": None,
                    "result": error_result,
                }
            ],
        )
        self.assertEqual(
            payloads[1]["messages"][-1],
            {
                "role": "tool",
                "tool_name": "calculator",
                "content": error_result,
            },
        )
        self._assert_tools_in_every_payload(payloads)

    @patch("knowledge_pilot.llm.ollama_client.execute_tool_call")
    @patch("knowledge_pilot.llm.ollama_client.requests.post")
    def test_returns_max_steps_result_when_limit_is_reached(
        self,
        mock_post,
        mock_execute_tool_call,
    ):
        first_call = {
            "function": {
                "name": "calculator",
                "arguments": {"a": 1, "b": 1, "operation": "add"},
            }
        }
        second_call = {
            "function": {
                "name": "calculator",
                "arguments": {"a": 2, "b": 2, "operation": "add"},
            }
        }
        payloads = self._capture_payloads(
            mock_post,
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [first_call],
            },
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [second_call],
            },
        )
        mock_execute_tool_call.side_effect = [2, 4]

        result = chat_with_ollama(self._messages(), max_steps=2)

        self._assert_agent_result(result)
        self.assertEqual(result["stop_reason"], "max_steps")
        self.assertIn("最大步骤限制", result["answer"])
        self.assertEqual(
            result["trace"],
            [
                {
                    "step": 1,
                    "tool": "calculator",
                    "arguments": first_call["function"]["arguments"],
                    "result": 2,
                },
                {
                    "step": 2,
                    "tool": "calculator",
                    "arguments": second_call["function"]["arguments"],
                    "result": 4,
                },
            ],
        )
        self.assertEqual(mock_post.call_count, 2)
        self._assert_tools_in_every_payload(payloads)

    @patch("knowledge_pilot.llm.ollama_client.execute_tool_call")
    @patch("knowledge_pilot.llm.ollama_client.requests.post")
    def test_executes_all_tool_calls_from_the_same_round(
        self,
        mock_post,
        mock_execute_tool_call,
    ):
        add_call = {
            "function": {
                "name": "calculator",
                "arguments": {"a": 1, "b": 2, "operation": "add"},
            }
        }
        multiply_call = {
            "function": {
                "name": "calculator",
                "arguments": {
                    "a": 3,
                    "b": 4,
                    "operation": "multiply",
                },
            }
        }
        payloads = self._capture_payloads(
            mock_post,
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [add_call, multiply_call],
            },
            {
                "role": "assistant",
                "content": "两个计算都已完成。",
            },
        )
        mock_execute_tool_call.side_effect = [3, 12]

        result = chat_with_ollama(self._messages())

        self.assertEqual(
            mock_execute_tool_call.call_args_list,
            [call(add_call), call(multiply_call)],
        )
        self._assert_agent_result(result)
        self.assertEqual(result["stop_reason"], "completed")
        self.assertEqual(
            result["trace"],
            [
                {
                    "step": 1,
                    "tool": "calculator",
                    "arguments": add_call["function"]["arguments"],
                    "result": 3,
                },
                {
                    "step": 1,
                    "tool": "calculator",
                    "arguments": multiply_call["function"]["arguments"],
                    "result": 12,
                },
            ],
        )
        tool_observations = [
            message
            for message in payloads[1]["messages"]
            if message.get("role") == "tool"
        ]
        self.assertEqual(
            [message["content"] for message in tool_observations],
            ["3", "12"],
        )
        self._assert_tools_in_every_payload(payloads)


if __name__ == "__main__":
    unittest.main()
