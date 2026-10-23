"""Official DeepSeek protocol fixtures; no live credentials or API calls."""
import io
import json
import unittest
from unittest.mock import patch

from backend.model import CRITERIA, ModelClient, ModelError


class DeepSeekTests(unittest.TestCase):
    def client(self, protocol='responses', base='https://api.deepseek.com'):
        return ModelClient({'api_key': 'SYNTHETIC_ONLY', 'base_url': base,
                            'model_id': 'deepseek-flash', 'review_model_id': 'SYNTHETIC_REVIEW',
                            'protocol': protocol})

    def plan(self):
        return {'kind': 'answer', 'message': 'SYNTHETIC 查询', 'payload_json': '{}', 'choices': []}

    def invoke(self, client, result, review=False, finish='stop'):
        if client.protocol == 'responses':
            value = {'status': 'completed', 'output': [
                {'type': 'reasoning', 'content': [{'type': 'reasoning_text', 'text': 'SYNTHETIC_PRIVATE'}]},
                {'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(result)}]}],
                'usage': {'input_tokens': 9, 'output_tokens': 7}}
        else:
            value = {'choices': [{'finish_reason': finish, 'message': {
                'reasoning_content': 'SYNTHETIC_PRIVATE', 'content': json.dumps(result)}}],
                'usage': {'prompt_tokens': 9, 'completion_tokens': 7}}
        sent = []
        def urlopen(request, **kwargs):
            sent.append((request.full_url, json.loads(request.data)))
            return io.BytesIO(json.dumps(value).encode())
        with patch('urllib.request.urlopen', urlopen):
            output = (client.review({}, {}, 'SYNTHETIC', 'setup') if review
                      else client.generate({'mode': 'query'}))
        return sent[0], output

    def test_responses_generation_and_independent_review(self):
        client = self.client()
        (url, body), (plan, usage) = self.invoke(client, self.plan())
        self.assertEqual(url, 'https://api.deepseek.com/responses')
        self.assertEqual(body['model'], 'deepseek-flash')
        self.assertEqual(body['text']['format']['name'], 'voyager_plan')
        self.assertEqual(body['text']['format']['type'], 'json_schema')
        self.assertNotIn('strict', body['text']['format'])
        self.assertNotIn('store', body)
        self.assertEqual(plan, self.plan())
        self.assertEqual(usage['input_tokens'], 9)
        (_, body), (verdict, _) = self.invoke(client, {'status': 'PASS', 'reasons': []}, review=True)
        self.assertEqual(body['model'], 'SYNTHETIC_REVIEW')
        self.assertEqual(body['text']['format']['name'], 'voyager_review')
        self.assertEqual(verdict['criteria'], CRITERIA)

    def test_chat_uses_deepseek_json_mode_and_token_parameter(self):
        client = self.client('chat_completions', 'https://api.deepseek.com/v1/')
        (url, body), (plan, usage) = self.invoke(client, self.plan())
        self.assertEqual(url, 'https://api.deepseek.com/v1/chat/completions')
        self.assertIn('max_tokens', body)
        self.assertNotIn('max_completion_tokens', body)
        self.assertEqual(body['response_format'], {'type': 'json_object'})
        self.assertIn('JSON Schema', body['messages'][0]['content'])
        self.assertIn('"required"', body['messages'][0]['content'])
        self.assertEqual(plan, self.plan())
        self.assertEqual(usage['prompt_tokens'], 9)
        (_, body), (verdict, _) = self.invoke(client, {'status': 'PASS', 'reasons': []}, review=True)
        self.assertEqual(body['model'], 'SYNTHETIC_REVIEW')
        self.assertEqual(verdict['status'], 'PASS')

    def test_malformed_output_rejected_in_both_protocols(self):
        for protocol in ('responses', 'chat_completions'):
            for result in ({'kind': 'answer'}, {**self.plan(), 'choices': [3]},
                           {**self.plan(), 'kind': 'commit'}, {**self.plan(), 'extra': 'forged'}):
                with self.subTest(protocol=protocol, result=result):
                    with self.assertRaisesRegex(ModelError, 'MODEL_SCHEMA_INVALID'):
                        self.invoke(self.client(protocol), result)
            with self.assertRaisesRegex(ModelError, 'MODEL_SCHEMA_INVALID'):
                self.invoke(self.client(protocol), {'status': 'PASS', 'reasons': [42]}, review=True)

    def test_truncated_chat_never_accepted(self):
        with self.assertRaisesRegex(ModelError, 'MODEL_INCOMPLETE_OR_REFUSED'):
            self.invoke(self.client('chat_completions'), self.plan(), finish='length')

    def test_other_hosts_keep_generic_protocol(self):
        for base in ('https://api.openai.com/v1', 'https://api.deepseek.com.example.org/v1'):
            with self.subTest(base=base):
                (_, body), _ = self.invoke(self.client(base=base), self.plan())
                self.assertFalse(body['store'])
                self.assertTrue(body['text']['format']['strict'])


if __name__ == '__main__':
    unittest.main()
