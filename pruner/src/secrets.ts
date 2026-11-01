const SECRET_COMMAND =
  /(?:^|[|;&'"]\s*|\b(?:sh|bash|zsh)\s+-\w*c\s+)(?:printenv|env)\b|(?:^|[|;&'"]\s*)(?:export|set|declare)\s*(?:$|[|;&'"])|\.env\b|(?:^|[^a-z])(?:secrets?|credentials?|password|token|keychain|netrc|id_rsa|private[_-]?key)(?:$|[^a-z])/i;

const VALUE = String.raw`(?:[^\s'";,\`$]|\$(?!\()|,(?![A-Za-z_][\w.]{0,64}[(= \t])){1,4096}`;
const NAME = 'token|secret|password|passwd|api[_-]?key';

// The patterns of scope_sentinel.py's SECRETS (shadow-v6), so the pruner and the gates hide the same shapes.
// Keep the two lists in step. Added here: a bare PEM header and a token used as a URL's user name.
const SECRETS = [
  new RegExp(String.raw`(^[+-]?[ \t]*['"]?\w{0,64}(?:${NAME})\w{0,64}['"]?[ \t]*(?::[ \t]{0,64}(?:[|>][+-]?[ \t]{0,64})?|=[ \t]{0,64}\([ \t]{0,64})\r?\n[+-]?[ \t]+)(?:(['"])[^'"\n]{1,4096}\2|${VALUE})(?=[ \t]*\r?$)`, 'gim'),
  new RegExp(String.raw`(authorization:[ \t]*\S{1,64}[ \t]+)${VALUE}`, 'gi'),
  /(bearer[ \t]+)[A-Za-z0-9._~+/=-]{16,}/gi,
  new RegExp(String.raw`((?:${NAME})\w{0,64}[ \t]*(?:=(?!=)|:=?)[ \t]*)(?:(['"])[^'"\n]{1,4096}\2|['"]?${VALUE})`, 'gi'),
  new RegExp(String.raw`(["'](?:${NAME})\w{0,64}["'][ \t]*:[ \t]*["'])[^"'\n]+`, 'gi'),
  new RegExp(String.raw`(--(?:password|passwd|token|secret|api[-_]?key)[= \t]+)${VALUE}`, 'gi'),
  new RegExp(String.raw`(\s-u[ \t]+[^\s:'"]{1,64}:)${VALUE}`, 'g'),
  /(:\/\/[^/\s:@]*:)[^/\s@]+(?=@)/g,
  /(:\/\/)(?!git@)[^/\s:@]+(?=@)/g,
  /()\b(?:gh[pousr]_|github_pat_|glpat-)[\w-]{10,}/g,
  /()\bsk[-_](?=[\w-]{0,64}\d)[\w-]{20,}/g,
  /()\bts_[\w-]{16,}/g,
  /()\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/g,
  /()\bxox[abposr]-[\w-]{10,}/g,
  /()\beyJ[\w-]{10,256}\.[\w-]{10,}\.[\w-]{10,}/g,
  /(-----BEGIN [A-Z ]{0,32}PRIVATE KEY-----)(?:\r?\n[+-]? ?[A-Za-z0-9+/=]{12,}[ \t]*(?![^\r\n]))*/g,
];

export function redact(text: string): string {
  return SECRETS.reduce((current, pattern) => current.replace(pattern, '$1[REDACTED]'), text);
}

// A bare PEM header redacts to itself plus the marker, so a change always means a hit.
export function looksSecret(command: string, output: string): boolean {
  return SECRET_COMMAND.test(command) || redact(command) !== command || redact(output) !== output;
}
