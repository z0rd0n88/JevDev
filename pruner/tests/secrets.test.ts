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
  ['make', "environ({'DISCORD_BOT_TOKEN': 'MTIz.Gabc.xyz'})"],
  ['make', "{'RUNPOD_API_KEY': 'rpa_abc'}"],
  ['make', '{"DISCORD_BOT_TOKEN": "abc"}'],
  ['make', '"access_token": "abc"'],
  ['make', '"refresh_token": "abc"'],
  ['make', '"client_secret": "abc"'],
  ['make', '"auth_token": "abc"'],
  ['make', '"private_key": "abc"'],
  ['make', '"id_token": "abc"'],
  ['make', '"SessionToken": "abc"'],
  ['make', '{\\"access_token\\":\\"abc\\"}'],
  ['make', `PRIVATE_KEY=0x${'ab12'.repeat(16)}`],
  ['make', `HYPERLIQUID_PRIVATE_KEY=0x${'ab12'.repeat(16)}`],
  ['make', `0x${'ab12'.repeat(16)}`],
  ['make', '4'.repeat(88)],
  ['make', 'MNEMONIC="abandon ability able"'],
  ['make', 'rpa_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345'],
  ['make', 'hf_abcdefghijklmnopqrstuvwxyz0123456789'],
  ['make', 'AIzaSyA1234567890abcdefghijklmnopqrstuv'],
  ['make', 'ya29.a0AfH6SMBabcdefghijklmnop'],
  ['make', 'xapp-1-A0123456-abcdef'],
  ['make', 'SG.abcdefghijklmnopqrstuv.abcdefghijklmnopqrstuvwxyz0123456789'],
  ['make', 'https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX'],
  ['make', 'https://discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz'],
  ['make', 'https://api.telegram.org/bot123456789:AAEabcdefghijklmnopqrstuvwxyz012345/getMe'],
  ['make', 'DefaultEndpointsProtocol=https;AccountName=x;AccountKey=abc123==;'],
  ['make', 'Cookie: session=abc'],
  ['make', 'Set-Cookie: sid=abc; Path=/'],
  ['make', 'passphrase=abc'],
  ['make', 'pwd=abc'],
  ['make', 'Server=x;UID=u;PWD=abc;'],
  ['make', 'docker login -u me -p abc reg.io'],
  ['make', 'mysql -u root -pPASS db'],
  ['make', `sk-${'a'.repeat(48)}`],
  ['/usr/bin/env', 'ok'],
  ['FOO=1 env', 'ok'],
  ['time env', 'ok'],
  ['sudo env', 'ok'],
  ['echo $(env)', 'ok'],
  ['cat ~/.ssh/id_ed25519', 'ok'],
  ['make', 'ENCRYPTION_KEY=abc'],
  ['make', 'SIGNING_KEY: abc'],
  ['make', 'JWT_KEY=abc'],
  ['make', 'MASTER_KEY=abc'],
  ['make', 'GITHUB_PAT=abc'],
  ['make', 'AWS_CREDENTIALS=abc'],
  ['make', `npm_${'aB3'.repeat(12)}`],
  ['make', `pypi-AgEIcHlwaS5vcmc${'a'.repeat(30)}`],
  ['make', `whsec_${'a'.repeat(24)}`],
  ['make', `dckr_pat_${'a'.repeat(20)}`],
  ['make', `shpat_${'a'.repeat(32)}`],
  ['make', `dop_v1_${'a'.repeat(64)}`],
  ['make', `sbp_${'a'.repeat(40)}`],
  ['make', `lin_api_${'a'.repeat(40)}`],
  ['make', 'client-key-data: LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQpNSUlF'],
  ['make', '-----BEGIN PGP PRIVATE KEY BLOCK-----'],
  ['make', 'Authorization: abcdef123456'],
  ['make', '--password "hunter2"'],
  ['make', "--token 'abc'"],
  ['make', '--token "x y"'],
  ['sshpass -p "my pw" ssh host', 'ok'],
  ['declare -p', 'ok'],
  ['export -p', 'ok'],
];

const CLEAN: [string, string][] = [
  ['npm test', 'Tests: 12 passed, 12 total'],
  ['npm run build', 'compiled module 3 successfully'],
  ['git log', 'fix(auth): refresh token rotation'],
  ['grep -rn tokenize src', 'src/lexer.ts:12: function tokenize(text) {'],
  ['pytest', 'tests/test_env.py::test_loads PASSED'],
  ['make', 'PWD=/home/alex/x'],
  ['make', `Digest: sha256:${'ab12'.repeat(16)}`],
  ['git log', `commit ${'ab12'.repeat(10)}`],
  ['mysql -u root -p', 'ok'],
  ['./env/bin/python x.py', 'ok'],
  ['node src/env.ts', 'ok'],
  ['make', 'SORT_KEY=x'],
  ['make', 'PRIMARY_KEY=id'],
  ['make', 'primary_key=True'],
  ['make', 'PATH=/usr/bin'],
  ['make', 'patch=1 pattern=a compat=2'],
  ['make', `npm_config_${'a'.repeat(30)}`],
  ['make', 'author_key=x'],
  ['set -e; npm test', 'ok'],
  ['compgen -e', 'ok'],
  ['aws configure list', 'access_key ****************ABCD shared-credentials-file'],
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
    ' '.repeat(200_000),
    `at ${'('.repeat(200_000)}`,
    `a::b${':'.repeat(200_000)}`,
    `= 1 passed ${'='.repeat(200_000)}x`,
    '*** ['.repeat(80_000),
    `${'1'.repeat(200_000)} failure`,
    '9 9 9 '.repeat(40_000),
    'Failed t'.repeat(25_000),
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
