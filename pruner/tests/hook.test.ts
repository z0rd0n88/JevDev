// The review's required changes, proven through the engine's own `$`: nothing here reaches a network or a real key.
import { describe, expect, mock, test } from 'claude-code/testing';

const KEY = 'sk-or-v1-testkey';
const noisy = Array.from({ length: 200 }, (_, i) => `${'cache '.repeat(55)}compiled module ${i} successfully`).join('\n');

type Call = { url: string; init: { headers?: Record<string, string>; body?: string } };

function world(
  on: any,
  stdout: string,
  {
    key = KEY, isLink = false, silent = false, home = '/home/test', lateBy = 0, extra = {},
  }: {
    key?: string; isLink?: boolean; silent?: boolean; home?: string; lateBy?: number; extra?: Record<string, unknown>;
  } = {},
) {
  const fetches: Call[] = [];
  const writes: string[] = [];
  const runs: (readonly string[])[] = [];
  const logs: { text: string; to?: string }[] = [];
  const clock = mock.clock(on);
  on('tool.call', () => ({ result: { stdout, stderr: '', interrupted: false, ...extra } }));
  on('process.run', (_$: unknown, e: { argv: readonly string[] }) => {
    runs.push(e.argv);
    return { value: { exitCode: 0, stdout: e.argv.includes('printenv') ? `${key}\n` : `${home}\n`, stderr: '' } };
  });
  on('env.get', () => ({ value: '/evil/home' }));
  on('fs.stat', () => ({ value: { kind: 'directory', size: 0, mtimeMs: 0, isLink } }));
  on('fs.write', async (_$: unknown, e: { path: string }) => {
    writes.push(e.path);
    if (lateBy) await clock.advance(lateBy);
    return { value: undefined };
  });
  on('session.messages', () => ({
    value: [
      { role: 'user', text: 'Build it. OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz0123', toolUses: [] },
      { role: 'user', text: '<system-reminder>PRIVATE-REMINDER</system-reminder>\nAlso keep the logs.', toolUses: [] },
      { role: 'user', text: '<task-notification>PRIVATE-NOTIFICATION</task-notification>', toolUses: [] },
      { role: 'assistant', text: 'PRIVATE-ASSISTANT-TEXT', toolUses: [] },
      {
        role: 'assistant', text: '', toolUses: [{
          tool_use_id: 't1', tool: 'Read', input: { file_path: '.env' }, text: 'PRIVATE-FILE-CONTENT',
        }],
      },
    ],
  }));
  on('http.fetch', (_$: unknown, e: Call) => {
    if (silent) return new Promise(() => {});
    fetches.push(e);
    const { questions } = JSON.parse(e.init.body ?? '{}') as { questions: Record<string, unknown> };
    return {
      value: {
        status: 200, ok: true, headers: {},
        text: JSON.stringify({ answers: Object.fromEntries(Object.keys(questions).map(id => [id, { noul: 0.01 }])) }),
      },
    };
  });
  on('ui.toast', () => ({ value: undefined }));
  on('ui.log', (_$: unknown, e: { text: string; to?: string }) => { logs.push(e); return { value: undefined }; });
  return { fetches, writes, clock, runs, logs };
}

describe('OpenRouter route', () => {
  test('posts only to the OpenRouter endpoint with the sk-or key', async ($, on) => {
    const w = world(on, noisy);
    const answer = await $.tool.call({ tool: 'Bash', command: 'npm test' });
    expect(w.fetches.length).toBeGreaterThan(0);
    for (const { url, init } of w.fetches) {
      expect(url).toBe('https://openrouter.ai/api/v1/systemone');
      expect(init.headers?.authorization).toBe(`Bearer ${KEY}`);
      expect(JSON.parse(init.body!).model).toBe('jev-latest');
    }
    expect((answer.result as { stdout: string }).stdout).toContain('lines omitted');
  });

  test('sends nothing when the key is not an OpenRouter key', async ($, on) => {
    const w = world(on, noisy, { key: 'ts_not-an-openrouter-key' });
    const answer = await $.tool.call({ tool: 'Bash', command: 'npm test' });
    expect(w.fetches.length).toBe(0);
    expect((answer.result as { stdout: string }).stdout).toBe(noisy);
  });

  test('ignores a baseUrl, apiKey or model option', { options: { baseUrl: 'https://evil.example/x', apiKey: 'stolen', model: 'other' } }, async ($, on) => {
    const w = world(on, noisy);
    await $.tool.call({ tool: 'Bash', command: 'npm test' });
    expect(w.fetches.length).toBeGreaterThan(0);
    for (const { url, init } of w.fetches) {
      expect(url).toBe('https://openrouter.ai/api/v1/systemone');
      expect(init.headers?.authorization).toBe(`Bearer ${KEY}`);
      expect(JSON.parse(init.body!).model).toBe('jev-latest');
    }
  });

  test('the home and the key are read in an empty environment', async ($, on) => {
    const w = world(on, noisy);
    await $.tool.call({ tool: 'Bash', command: 'npm test' });
    const clean = ['/usr/bin/env', '-i', 'PATH=/usr/bin:/bin'];
    expect(w.runs[0]).toEqual([...clean, 'sh', '-c', 'getent passwd "$(id -u)" | cut -d: -f6']);
    expect(w.runs[1]!.slice(0, 5)).toEqual([...clean, 'HOME=/home/test', 'bash']);
    expect(w.runs[1]!.slice(-2)).toEqual(['printenv', 'OPENROUTER_API_KEY']);
  });

  test('sends nothing when the passwd file gives no absolute home', async ($, on) => {
    const w = world(on, noisy, { home: 'relative' });
    const answer = await $.tool.call({ tool: 'Bash', command: 'npm test' });
    expect(w.fetches.length).toBe(0);
    expect((answer.result as { stdout: string }).stdout).toBe(noisy);
  });
});

describe('notices', () => {
  test('a run that cannot trim says so once in the transcript', async ($, on) => {
    const w = world(on, noisy, { key: 'nope' });
    await $.tool.call({ tool: 'Bash', command: 'npm test' });
    await $.tool.call({ tool: 'Bash', command: 'npm test' });
    expect(w.logs.filter(l => l.to !== 'debug').length).toBe(1);
  });
});

describe('what leaves the machine', () => {
  test('a secret in the output sends nothing and saves nothing', async ($, on) => {
    const output = `${noisy}\nGITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz0123456789`;
    const w = world(on, output);
    const answer = await $.tool.call({ tool: 'Bash', command: 'npm test' });
    expect(w.fetches.length).toBe(0);
    expect(w.writes.length).toBe(0);
    expect((answer.result as { stdout: string }).stdout).toBe(output);
  });

  test('a secret-reading command sends nothing', async ($, on) => {
    const w = world(on, noisy);
    await $.tool.call({ tool: 'Bash', command: 'sh -c env' });
    expect(w.fetches.length).toBe(0);
  });

  test('no conversation history is sent and the task is redacted', async ($, on) => {
    const w = world(on, noisy);
    await $.tool.call({ tool: 'Bash', command: 'npm test' });
    expect(w.fetches.length).toBeGreaterThan(0);
    for (const { init } of w.fetches) {
      const { state } = JSON.parse(init.body!);
      expect('history' in state).toBe(false);
      expect(init.body!.includes('PRIVATE-')).toBe(false);
      expect(state.task).toContain('Build it.');
      expect(state.task).toContain('Also keep the logs.');
      expect(init.body!.includes('sk-abcdefghijklmnop')).toBe(false);
    }
  });
});

describe('limits', () => {
  test('no request is sent once the deadline has passed', async ($, on) => {
    const w = world(on, noisy, { lateBy: 61_000 });
    const answer = await $.tool.call({ tool: 'Bash', command: 'npm test' });
    expect(w.fetches.length).toBe(0);
    expect((answer.result as { stdout: string }).stdout).toBe(noisy);
  });

  test('output past the 1,000,000 cap sends nothing', async ($, on) => {
    const big = 'x y z\n'.repeat(200_000);
    const w = world(on, big);
    const answer = await $.tool.call({ tool: 'Bash', command: 'npm test' });
    expect(w.fetches.length).toBe(0);
    expect((answer.result as { stdout: string }).stdout).toBe(big);
  });

  test('output past the size cap passes through unscored', async ($, on) => {
    const huge = 'x y z\n'.repeat(700_000);
    const w = world(on, huge);
    const answer = await $.tool.call({ tool: 'Bash', command: 'npm test' });
    expect(w.fetches.length).toBe(0);
    expect((answer.result as { stdout: string }).stdout).toBe(huge);
  });

  test('a scorer that never answers fails open at the deadline', async ($, on) => {
    const w = world(on, noisy, { silent: true });
    const pending = $.tool.call({ tool: 'Bash', command: 'npm test' });
    await w.clock.advance(61_000);
    const answer = await pending;
    expect((answer.result as { stdout: string }).stdout).toBe(noisy);
  });
});

describe('persisted output', () => {
  test('keeps host notices in stderr and sends them nowhere', async ($, on) => {
    const w = world(on, noisy, {
      extra: { stderr: 'HOST-NOTICE', persistedOutputPath: '/tmp/out.txt', persistedOutputSize: noisy.length },
    });
    on('fs.read', () => ({ value: noisy }));
    const answer = await $.tool.call({ tool: 'Bash', command: 'npm test' });
    const result = answer.result as { stdout: string; stderr: string };
    expect(result.stdout).toContain('lines omitted');
    expect(result.stderr).toBe('HOST-NOTICE');
    for (const { init } of w.fetches) expect(init.body!.includes('HOST-NOTICE')).toBe(false);
  });
});

describe('archive', () => {
  test('a HOME from the environment cannot steer the path', async ($, on) => {
    const w = world(on, noisy);
    await $.tool.call({ tool: 'Bash', command: 'npm test', tool_use_id: 'toolu_1' });
    expect(w.writes).toEqual(['/home/test/.local/state/jevdev/pruner/bash-toolu_1.txt']);
  });

  test('goes under the private state dir, never the project', async ($, on) => {
    const w = world(on, noisy);
    const answer = await $.tool.call({ tool: 'Bash', command: 'npm test', tool_use_id: 'toolu_1' });
    expect(w.writes).toEqual(['/home/test/.local/state/jevdev/pruner/bash-toolu_1.txt']);
    expect((answer.result as { stdout: string }).stdout).toContain('/home/test/.local/state/jevdev/pruner/bash-toolu_1.txt');
  });

  test('a host-supplied id cannot steer the path', async ($, on) => {
    const w = world(on, noisy);
    await $.tool.call({ tool: 'Bash', command: 'npm test', tool_use_id: '../../evil' });
    for (const path of w.writes) expect(path.includes('..')).toBe(false);
  });

  test('a symlinked state dir sends nothing', async ($, on) => {
    const w = world(on, noisy, { isLink: true });
    await $.tool.call({ tool: 'Bash', command: 'npm test' });
    expect(w.fetches.length).toBe(0);
    expect(w.writes.length).toBe(0);
  });
});
