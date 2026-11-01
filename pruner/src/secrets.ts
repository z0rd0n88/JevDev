const SECRET_COMMAND =
  /(?:^|[\s|;&'"(`/])(?:printenv|env|sshpass)(?![\w./=-])|(?:^|[|;&'"]\s*)(?:export|set|declare)\s*(?:$|[|;&'"])|(?:^|[|;&'"]\s*)(?:export|declare|typeset)\s+-[a-z]*p\b|\.env\b|(?:^|[^a-z])(?:secrets?|credentials?|password|token|keychain|netrc|id_(?:rsa|dsa|ecdsa|ed25519)|private[_-]?key)(?:$|[^a-z])/i;

const VALUE = String.raw`(?:[^\s'";,\`$]|\$(?!\()|,(?![A-Za-z_][\w.]{0,64}[(= \t])){1,4096}`;
const NAME = 'token|secret|password|passwd|api[_-]?key|private[_-]?key|access[_-]?key|account[_-]?key|passphrase|mnemonic|seed[_-]?phrase|credentials?|(?:encryption|signing|jwt|master|hmac|session|auth)[_-]?key|(?<![a-z])pat(?![a-z])';

// The patterns of scope_sentinel.py's SECRETS (shadow-v6), so the pruner and the gates hide the same shapes.
// Keep the two lists in step. Added here: a bare or PGP PEM header, a token used as a URL's user name, the wider NAME,
// a quoted flag value, a scheme-less Authorization, a prefixed or escaped quoted key, and every pattern after the PEM line. A denylist: see pruner/README.md for what still passes.
const SECRETS = [
  new RegExp(String.raw`(^[+-]?[ \t]*['"]?\w{0,64}(?:${NAME})\w{0,64}['"]?[ \t]*(?::[ \t]{0,64}(?:[|>][+-]?[ \t]{0,64})?|=[ \t]{0,64}\([ \t]{0,64})\r?\n[+-]?[ \t]+)(?:(['"])[^'"\n]{1,4096}\2|${VALUE})(?=[ \t]*\r?$)`, 'gim'),
  new RegExp(String.raw`(authorization:[ \t]*(?:\S{1,64}[ \t]+)?)${VALUE}`, 'gi'),
  /(bearer[ \t]+)[A-Za-z0-9._~+/=-]{16,}/gi,
  new RegExp(String.raw`((?:${NAME})\w{0,64}[ \t]*(?:=(?!=)|:=?)[ \t]*)(?:(['"])[^'"\n]{1,4096}\2|['"]?${VALUE})`, 'gi'),
  new RegExp(String.raw`(["'][\w.-]{0,64}(?:${NAME})\w{0,64}\\?["'][ \t]*:[ \t]*\\?["'])[^"'\n]+`, 'gi'),
  new RegExp(String.raw`(--(?:password|passwd|token|secret|api[-_]?key)[= \t]+)(?:(['"])[^'"\n]{1,4096}\2|${VALUE})`, 'gi'),
  new RegExp(String.raw`(\s-u[ \t]+[^\s:'"]{1,64}:)${VALUE}`, 'g'),
  /(:\/\/[^/\s:@]*:)[^/\s@]+(?=@)/g,
  /(:\/\/)(?!git@)[^/\s:@]+(?=@)/g,
  /()\b(?:gh[pousr]_|github_pat_|glpat-)[\w-]{10,}/g,
  /()\bsk[-_](?=[\w-]{0,64}\d)[\w-]{20,}/g,
  /()\bts_[\w-]{16,}/g,
  /()\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/g,
  /()\b(?:xox[abposr]|xapp)-[\w-]{10,}/g,
  /()\beyJ[\w-]{10,256}\.[\w-]{10,}\.[\w-]{10,}/g,
  /(-----BEGIN [A-Z ]{0,32}PRIVATE KEY(?: BLOCK)?-----)(?:\r?\n[+-]? ?[A-Za-z0-9+/=]{12,}[ \t]*(?![^\r\n]))*/g,
  // A wallet key has no prefix: these also match every EVM transaction hash and Solana signature, which only skips a pruning.
  /()\b0x[0-9a-fA-F]{64}\b/g,
  /()\b[1-9A-HJ-NP-Za-km-z]{87,88}\b/g,
  /()\b(?:rpa_[A-Za-z0-9]{16,}|hf_[A-Za-z0-9]{16,}|AIza[\w-]{30,}|ya29\.[\w-]{16,}|SG\.[\w-]{16,}\.[\w-]{16,}|sk-[A-Za-z]{40,}|npm_[A-Za-z0-9]{36}|pypi-AgEI[\w-]{20,}|whsec_[\w]{16,}|dckr_pat_[\w-]{16,}|shp(?:at|ca|ss|pa)_[0-9a-f]{20,}|dop_v1_[0-9a-f]{20,}|sbp_[0-9a-f]{20,}|lin_api_[A-Za-z0-9]{20,}|LS0tLS1CRUdJTi[A-Za-z0-9+/=]{16,})/g,
  /()(?:hooks\.slack\.com\/services|discord(?:app)?\.com\/api\/webhooks)\/[\w/-]{16,}/g,
  /()(?<!\d)\d{6,12}:[\w-]{35,}/g,
  new RegExp(String.raw`(\b(?:set-)?cookie:[ \t]*)${VALUE}`, 'gi'),
  new RegExp(String.raw`(\b[Pp]wd[ \t]*=[ \t]*|;[ \t]*PWD=)${VALUE}`, 'g'),
  new RegExp(String.raw`(\b(?:docker[ \t]+login|mysql\w{0,16})\b[^\n]{0,256}?[ \t]-p[= \t]*)${VALUE}`, 'g'),
];

export function redact(text: string): string {
  return SECRETS.reduce((current, pattern) => current.replace(pattern, '$1[REDACTED]'), text);
}

// A bare PEM header redacts to itself plus the marker, so a change always means a hit.
export function looksSecret(command: string, output: string): boolean {
  return SECRET_COMMAND.test(command) || redact(command) !== command || redact(output) !== output;
}
