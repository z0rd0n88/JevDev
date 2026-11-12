import type {
  MatchedHook,
  On,
  PluginOptions,
  Register,
  SessionMessage,
} from 'claude-code';

import { buildJevRequest, estimateTokens, parseJevResponse } from '../src/jev.js';
import { classifyOutput, exceedsOutputThreshold, looksBinary, MIN_OUTPUT_TOKENS, recoveryFooter, trimOutput } from '../src/output.js';
import type { TrimOutputResult } from '../src/output.js';
import type { JevAsker } from '../src/jev.js';
import { looksSecret, redact } from '../src/secrets.js';
import { classifyInformation } from '../src/retention.js';
import type { InformationCategory } from '../src/retention.js';

const STATE_DIR = '.local/state/jevdev';
const CLEAN_ENV = ['/usr/bin/env', '-i', 'PATH=/usr/bin:/bin'];
const DEFAULT_MAX_SCORING_REQUESTS = 11;
const VISIBLE_CHARS_PER_REQUEST = 192;
const MAX_OUTPUT_CHARS = 1_000_000;
const SCORING_DEADLINE_MS = 60_000;
const DEFAULTS = {
  persistedMaxChars: 8_000,
  chunkLines: 20,
  keepThreshold: 0.5,
  maxStateTokens: 25_000,
  minTokens: MIN_OUTPUT_TOKENS,
};

type BashHook = MatchedHook<'tool.call', { tool: 'Bash' }>;

export type HookFetchInit = {
  method?: string;
  headers?: Record<string, string>;
  body?: string;
};

export type HookFetchResponse = {
  status: number;
  ok: boolean;
  text: string;
};

export type HookFetch = (
  url: string,
  init?: HookFetchInit,
) => Promise<HookFetchResponse>;

export type HookConfig = {
  chunkChars?: number;
  diagnostics?: boolean;
  chunkLines: number;
  keepThreshold: number;
  maxStateTokens: number;
  maxScoringRequests?: number;
  minTokens: number;
  persistedOutputs: boolean;
  persistedMaxChars: number;
};

function optionNumber(options: PluginOptions, key: string, fallback: number): number {
  const value = options[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

/** The manifest declares no userConfig, so `options` is empty and a project's `pluginConfigs` cannot change these defaults. */
export function resolveHookConfig(options: PluginOptions): HookConfig {
  const config: HookConfig = {
    chunkLines: optionNumber(options, 'chunkLines', DEFAULTS.chunkLines),
    keepThreshold: optionNumber(options, 'keepThreshold', DEFAULTS.keepThreshold),
    maxStateTokens: optionNumber(options, 'maxStateTokens', DEFAULTS.maxStateTokens),
    minTokens: Math.max(MIN_OUTPUT_TOKENS, optionNumber(options, 'minTokens', DEFAULTS.minTokens)),
    persistedOutputs:
      typeof options.persistedOutputs === 'boolean' ? options.persistedOutputs : true,
    persistedMaxChars: optionNumber(options, 'persistedMaxChars', DEFAULTS.persistedMaxChars),
  };
  const chunkChars = optionNumber(options, 'chunkChars', 0);
  if (chunkChars > 0) config.chunkChars = chunkChars;
  if (options.diagnostics !== false) config.diagnostics = true;
  if (options.maxScoringRequests !== undefined) {
    config.maxScoringRequests = Math.max(0, Math.floor(
      optionNumber(options, 'maxScoringRequests', DEFAULT_MAX_SCORING_REQUESTS),
    ));
  }
  return config;
}

/**
 * The model-visible budget for output core saved to a file. Not capped at core's ~2,200-char preview: no trim fits
 * that, so every saved output came back `budget_unfit`. The full output stays in the saved file.
 */
export function persistedBudget(persistedMaxChars: number, _previewChars?: number): number {
  return Math.max(0, persistedMaxChars) || Infinity;
}

export function jevAsker(
  fetchFn: HookFetch,
  apiKey: string,
): JevAsker {
  return {
    async ask(state, questions) {
      const request = buildJevRequest(apiKey, state, questions);
      const response = await fetchFn(request.url, {
        method: request.method,
        headers: request.headers,
        body: request.body,
      });
      return parseJevResponse(response.status, response.ok, response.text);
    },
  };
}

// The blocks of scope_sentinel.py's TAG_BLOCK. Anchored, so one attempt and linear.
const INJECTED = /^(?:\s*<(system-reminder|task-notification|bash-std\w+|local-command-[\w-]+)>[\s\S]*?<\/\1>)+\s*/;

// Walks back from the newest message until three are kept. A message with a secret in its first 4,000 characters is
// dropped whole: redact() leaves the words after the first space of `mnemonic: a b c`. Only the first 500 are sent.
export function goalFromMessages(messages: readonly SessionMessage[]): string {
  const goals: string[] = [];
  for (let i = messages.length - 1; i >= 0 && goals.length < 3; i--) {
    const message = messages[i]!;
    if (message.role !== 'user' || message.toolResults?.length) continue;
    const text = message.text.replace(INJECTED, '').slice(0, 4_000);
    if (text.trim() && redact(text) === text) goals.unshift(text.slice(0, 500));
  }
  return goals.join('\n');
}

/**
 * The account's home from the passwd file, never `HOME`, which a cloned repo's project `env` can set.
 * `sh`, not `bash`: `bash -c` sources ~/.bashrc when its stdin is a socket.
 */
async function realHome($: Parameters<BashHook>[0]): Promise<string | undefined> {
  const { exitCode, stdout } = await $.process.run(
    [...CLEAN_ENV, 'sh', '-c', 'getent passwd "$(id -u)" | cut -d: -f6'],
    { timeoutMs: 5_000 },
  );
  const home = stdout.trim();
  return exitCode === 0 && home.startsWith('/') ? home : undefined;
}

/**
 * Reads the key through JevDev's with_jev_key.sh in an empty environment, so a project `env`
 * cannot substitute its own account through OPENROUTER_API_KEY, HOME, PATH or BASH_ENV.
 */
async function getApiKey($: Parameters<BashHook>[0], home: string): Promise<string | undefined> {
  const { exitCode, stdout } = await $.process.run(
    [...CLEAN_ENV, `HOME=${home}`, 'bash', `${$.plugin.root}/../with_jev_key.sh`, 'printenv', 'OPENROUTER_API_KEY'],
    { timeoutMs: 5_000 },
  );
  const key = stdout.trim();
  return exitCode === 0 && key.startsWith('sk-or-') ? key : undefined;
}

/** The private archive folder: install_user.py makes its parent 0700, outside every repo. */
async function archiveDir($: Parameters<BashHook>[0], home: string): Promise<string | undefined> {
  const stat = await $.fs.stat(`${home}/${STATE_DIR}`).catch(() => undefined);
  return stat?.kind === 'directory' && !stat.isLink ? `${home}/${STATE_DIR}/pruner` : undefined;
}

export const register: Register = (on: On, options: PluginOptions) => {
  const configured = resolveHookConfig(options);
  const archives = new Set<string>();
  const noticed = new Set<string>();

  on('tool.call', { tool: 'Bash' }, async ($, event, next) => {
    const answer = await next(event);
    const started = await $.clock.now();
    let decision = answer.deny !== undefined ? 'denied' : answer.isError ? 'tool_error' : 'missing_result';
    let stage = 'result';
    let requests = 0;
    let sourceChars: number | null = null;
    let sourceEstimatedTokens: number | null = null;
    let modelVisibleBudgetChars: number | null = null;
    let requestLimit: number | null = null;
    let pruning: TrimOutputResult | undefined;
    let informationCategory: InformationCategory | null = null;
    const original = answer.deny === undefined && !answer.isError ? answer.result : undefined;
    const hookStdoutCharsBefore = original?.stdout.length ?? null;
    let hookStdoutCharsAfter = hookStdoutCharsBefore;
    try {
      if (answer.deny !== undefined || answer.isError || !answer.result) return answer;
      decision = 'archive_recovery';
      if ([...archives].some(path => event.command.includes(path))) return answer;
      const record = answer.result;
      const persisted = record.persistedOutputPath;
      decision = 'persisted_disabled';
      if (persisted && !configured.persistedOutputs) return answer;
      stage = 'read_output';
      const output = persisted ? await $.fs.read(persisted) : record.stdout;
      sourceChars = output.length;
      const combined = persisted ? output : output + (record.stderr ? `\n${record.stderr}` : '');
      decision = 'too_large';
      if (combined.length > MAX_OUTPUT_CHARS || event.command.length > MAX_OUTPUT_CHARS) return answer;
      if (configured.diagnostics) sourceEstimatedTokens = estimateTokens(output);
      decision = 'below_threshold';
      if (!exceedsOutputThreshold(output, configured.minTokens)) return answer;
      decision = 'binary';
      if (looksBinary(output)) return answer;
      informationCategory = classifyInformation(output);
      decision = 'document';
      if (classifyOutput(event.command, output) === 'document') return answer;
      decision = 'secret';
      if (looksSecret(event.command, combined)) return answer;
      stage = 'credentials';
      const home = await realHome($);
      const apiKey = home && await getApiKey($, home);
      decision = 'missing_key';
      if (!home || !apiKey) return answer;
      stage = 'archive_dir';
      const archive = persisted ? undefined : await archiveDir($, home);
      decision = 'no_archive_dir';
      if (!persisted && !archive) return answer;
      stage = 'history';
      const messages = await $.session.messages();
      const goal = goalFromMessages(messages);
      const id = event.tool_use_id && /^[\w-]+$/.test(event.tool_use_id) ? event.tool_use_id : Date.now();
      const path = persisted ?? `${archive}/bash-${id}.txt`;
      const footer = recoveryFooter(path);
      const maxChars = persisted ? persistedBudget(configured.persistedMaxChars, answer.text?.length) : Infinity;
      if (Number.isFinite(maxChars)) modelVisibleBudgetChars = maxChars;
      const visibleChars = Math.min(maxChars, answer.text?.length ?? combined.length);
      requestLimit = Math.min(
        1 + (configured.maxScoringRequests ?? DEFAULT_MAX_SCORING_REQUESTS),
        Math.max(1, Math.ceil(visibleChars / VISIBLE_CHARS_PER_REQUEST)),
      );
      decision = 'footer_exceeds_budget';
      if (maxChars <= footer.length) return answer;
      let archived: Promise<void> | undefined;
      const saveOutput = async (): Promise<void> => {
        if (!persisted) await $.fs.write(path, combined);
      };
      stage = 'scoring';
      const trimmed = await trimOutput(
        {
          command: event.command,
          goal,
          output,
          fullOutputPath: path,
        },
        jevAsker(
          async (url, init) => {
            stage = 'archive';
            await (archived ??= saveOutput());
            stage = 'scoring';
            const left = SCORING_DEADLINE_MS - (await $.clock.now() - started);
            if (left <= 0) throw new Error('scoring deadline passed');
            requests += 1;
            const response = await Promise.race([
              $.http.fetch(url, init),
              $.clock.sleep(left).then(() => { throw new Error('scoring deadline passed'); }),
            ]);
            return { status: response.status, ok: response.ok, text: response.text };
          },
          apiKey,
        ),
        {
          minTokens: configured.minTokens,
          maxChars: Number.isFinite(maxChars) ? maxChars : 0,
          compactMarkers: true,
          chunkLines: configured.chunkLines,
          chunkChars: configured.chunkChars,
          keepThreshold: configured.keepThreshold,
          maxStateTokens: configured.maxStateTokens,
          maxScoringRequests: requestLimit - 1,
          onDecision: reason => { decision = reason; },
        },
      );
      pruning = trimmed;
      if (!trimmed.trimmed) return answer;
      stage = 'publish';
      const stdout = trimmed.output;
      archives.add(path);
      const scores = trimmed.scores.map((score) => score.toFixed(2)).join(',');
      $.ui.log(
        `bash output: kept ${trimmed.kept}/${trimmed.chunks} chunks (${trimmed.charsBefore}→${stdout.length} chars) scores=${scores}`,
      );
      $.ui.toast(
        `trimmed Bash output ${trimmed.charsBefore}→${stdout.length} chars`,
        { timeoutMs: 8_000 },
      );
      const result = { ...record, stdout };
      delete result.persistedOutputPath;
      delete result.persistedOutputSize;
      hookStdoutCharsAfter = stdout.length;
      return { result };
    } catch (error) {
      decision = 'hook_error';
      const status = error instanceof Error ? /\((\d{3})\)/.exec(error.message)?.[1] : undefined;
      $.ui.log(`bash output trim skipped (stage=${stage}${status ? ` status=${status}` : ''})`, { to: 'debug' });
      return answer;
    } finally {
      if (['missing_key', 'no_archive_dir', 'hook_error'].includes(decision) && !noticed.has(decision)) {
        noticed.add(decision);
        $.ui.log(`Bash output left untrimmed (${decision}, stage=${stage}). The model got the full output. Repeats of this reason go to the debug log only.`);
      }
      if (configured.diagnostics) {
        try {
          $.ui.log(`fast-jev-output decision ${JSON.stringify({
            version: 1, toolUseId: event.tool_use_id ?? null, decision, stage,
            informationCategory,
            persisted: Boolean(original?.persistedOutputPath),
            modelVisibleCharsBefore: answer.text?.length ?? null,
            modelVisibleBudgetChars,
            sourceChars, sourceEstimatedTokens, hookStdoutCharsBefore, hookStdoutCharsAfter,
            hookStderrCharsBefore: original?.stderr.length ?? null,
            hookStderrCharsAfter: original?.stderr.length ?? null,
            chunks: pruning?.chunks ?? 0, kept: pruning?.kept ?? 0, dropped: pruning?.dropped ?? 0,
            withinChunkOnly: Boolean(pruning?.trimmed && pruning.dropped === 0),
            requests, requestLimit, elapsedMs: await $.clock.now() - started,
          })}`, { to: 'debug' });
        } catch {
          // Diagnostics cannot change the tool result.
        }
      }
    }
  });
};
