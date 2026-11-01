// Every miss from the review's table (HIGH-2), plus the shapes scope_sentinel.py already hides.
import { describe, expect, test } from 'claude-code/testing';
import { classifyInformation } from '../src/retention.js';
import { looksSecret, redact } from '../src/secrets.js';

const FLAGGED: [string, string][] = [
  ['npm test', 'OPENAI_API_KEY=sk-abc123'],
  ['npm test', 'DB_PASSWORD=hunter2'],
  ['npm test', 'GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz0123456789'],
  ['npm test', 'AKIAIOSFODNN7EXAMPLE'],
  ['curl -v https://x', '> Authorization: Bearer eyJhbGciOi.xxx.yyy'],
  ['npm test', 'api_key: abc'],
  ['npm test', 'password=abc'],
  ['npm test', 'export STRIPE_SECRET_KEY=sk_live_abc'],
  ['npm test', 'SECRET_KEY=abc'],
  ['npm test', 'postgres://user:pw@host/db'],
  ['npm test', 'redis://:pw@host:6379'],
  ['cat key.pem', '-----BEGIN OPENSSH PRIVATE KEY-----'],
  ['set', 'sk-or-v1-abcdef'],
  ['docker inspect c', '"Env": ["TYPESAFE_API_KEY=abc"]'],
  ['npm test', '"password": "abc"'],
  ['npm test', 'password : abc'],
  ['npm test', 'xoxb-123-456-abc'],
  ['git remote -v', 'origin https://ghp_abc@github.com/x/y'],
  ['npm test', 'NPM_TOKEN: npm_abc'],
  ['printenv', 'FOO=bar'],
  ['sh -c env', 'FOO=bar'],
  ['bash -c "env | sort"', 'FOO=bar'],
  ['export', 'declare -x FOO=bar'],
  ['npm test', 'ANTHROPIC_API_KEY=sk-ant-x'],
  ['curl -H "Authorization: Bearer abcdefghijklmnopqrst" https://x', 'ok'],
];

const CLEAN: [string, string][] = [
  ['npm test', 'Tests: 12 passed, 12 total'],
  ['npm run build', 'compiled module 3 successfully'],
  ['git log', 'fix(auth): refresh token rotation'],
  ['grep -rn tokenize src', 'src/lexer.ts:12: function tokenize(text) {'],
  ['pytest', 'tests/test_env.py::test_loads PASSED'],
];

describe('looksSecret', () => {
  for (const [command, output] of FLAGGED) {
    test(`flags ${command} / ${output}`, () => {
      expect(looksSecret(command, output)).toBe(true);
    });
  }
  for (const [command, output] of CLEAN) {
    test(`passes ${command} / ${output}`, () => {
      expect(looksSecret(command, output)).toBe(false);
    });
  }
});

describe('hostile output', () => {
  const HOSTILE = [
    '\n'.repeat(2_000_000),
    'x\n' + ' \n'.repeat(1_000_000),
    'token-'.repeat(600_000),
    'error\n\n'.repeat(500_000),
  ];
  for (const [index, text] of HOSTILE.entries()) {
    test(`classifies and redacts in linear time #${index}`, () => {
      const started = Date.now();
      classifyInformation(text);
      redact(text);
      expect(Date.now() - started).toBeLessThan(3_000);
    });
  }
});

describe('redact', () => {
  test('hides keyed values and token shapes, keeps the rest', () => {
    const text = redact('Build it. OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz0123 and ghp_abcdefghijklmnopqrstuvwxyz0123456789 now');
    expect(text).toContain('Build it.');
    expect(text).toContain('now');
    expect(text.includes('sk-abcdefghij')).toBe(false);
    expect(text.includes('ghp_abcdefghij')).toBe(false);
  });
});
