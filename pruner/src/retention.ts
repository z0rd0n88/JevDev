export type InformationCategory = 'reference' | 'diagnostic' | 'result' | 'progress' | 'unknown';

const REFERENCE_PATTERN = new RegExp([
  '^#{1,6} +\\S|^```|^~~~',
  '^---\\r?\\n[\\w-]+:',
  '^\\S[^\\n]*\\n(?:={3,}|-{3,})[ \\t\\r]*$',
  '^Help on (?:class|function|module)',
  '^[ \\t]*\\|?[ \\t]*(?:Parameters|Returns|Examples)[ \\t\\r]*$',
  '^[ \\t]*(?:export[ \\t]+)?(?:async[ \\t]+)?(?:function|class|def)[ \\t]+\\w',
  '^[ \\t]*(?:export[ \\t]+)?(?:const|let|var)[ \\t]+\\w+[ \\t]*[=:]',
  '^[ \\t]*(?:from[ \\t]+[\\w.]+[ \\t]+import|import[ \\t]+.+(?:from[ \\t]+|;|$))',
  '^[ \\t]*#include[ \\t]*[<"]',
  '^[ \\t]*(?:(?:static|inline|const)[ \\t]+)*(?:void|int|char|float|double|bool)[ \\t]+\\w+[ \\t]*\\(',
  '^[ \\t]*(?:0x)?[\\da-fA-F]{4,}:[ \\t]+(?:(?:[\\da-fA-F]{2}[ \\t]+)+)?[a-zA-Z][\\w.]*[ \\t]+\\S',
  '^[ \\t]*[\\da-fA-F]{4,}[ \\t]+<[^>\\n]+>:[ \\t\\r]*$',
].join('|'), 'm');

const DIAGNOSTIC_PATTERN = new RegExp(
  [
    '\\b(ERROR|FATAL|FAILED|FAILURE|PANIC|WARN|WARNING)\\b',
    '\\b(error|warning|failure|exception|panic|traceback|assertion)s?\\s*:',
    '\\berror TS\\d+:|^E\\s+\\S',
    '\\b(failed|failing|cannot|could not|unable to|denied|refused|timed out)\\s+\\w',
    '\\b\\w*(Error|Exception)\\b\\s*[:(]',
    '\\bTraceback \\(most recent call last\\)',
    '^[ \\t]*at[ \\t]+\\S+\\(.*:\\d+',
    '\\b(severity )?vulnerabilit(y|ies)\\b',
    '\\bCrashLoopBackOff\\b|\\bOOMKilled\\b',
    '\\bHTTP/[0-9.]+ [45]\\d\\d\\b|\\bstatus[=: ]\\s*[45]\\d\\d\\b',
  ].join('|'),
  'm',
);
const RESULT_PATTERN = /^[ \t]*(?:(?:Test Suites|Tests|Snapshots|Coverage|Results?|Summary|Exit code|Exit status)[ \t]*:|(?:Build|Compilation|Tests?)[ \t]+(?:succeeded|completed|finished|passed|failed)\b|(?:Artifact|Output file|Report|Coverage report)(?: path)?[ \t]*[:=][ \t]*\S)/im;
const PYTEST_RESULT_PATTERN = /^=+ .*\b\d+ (?:passed|failed|skipped|deselected|xfailed|xpassed|errors?|warnings?)\b.*=+[ \t\r]*$/im;
const TEST_PROGRESS_PATTERN = /^\S+::\S+\s+PASSED(?:\s+\[\s*\d+%\])?\s*$/i;
const PROGRESS_PATTERN = /^\s*(?:\[[^\]\n]+\]\s*)?(?:INFO\s+)?(?:progress\b|cache(?:d)?\b|download(?:ing)?\b|compil(?:ing|ed)\b)/i;
const MAX_DISPOSABLE_KEEP_PROBABILITY = 0.1;

export function isProtectedLine(text: string): boolean {
  return DIAGNOSTIC_PATTERN.test(text) || RESULT_PATTERN.test(text) || PYTEST_RESULT_PATTERN.test(text);
}

export function classifyInformation(text: string): InformationCategory {
  const unnumbered = text.replace(/^(?:[^\n]*?:\d+(?::\d+)?:|[ \t]*\d+\t)[ \t]*/gm, '');
  if (REFERENCE_PATTERN.test(unnumbered)) return 'reference';
  if (DIAGNOSTIC_PATTERN.test(text)) return 'diagnostic';
  if (RESULT_PATTERN.test(text) || PYTEST_RESULT_PATTERN.test(text)) return 'result';
  const lines = text.split('\n').filter(line => line.trim().length > 0);
  if (lines.length > 0 && lines.every(line =>
    PROGRESS_PATTERN.test(line) || TEST_PROGRESS_PATTERN.test(line))) return 'progress';
  return 'unknown';
}

export function keepScore(score: number, threshold: number): boolean {
  return score >= threshold || score > MAX_DISPOSABLE_KEEP_PROBABILITY;
}
