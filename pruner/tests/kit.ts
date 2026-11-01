// Runs the upstream vitest-style tests on `claude plugin test`, so the plugin needs no npm install.
import { describe, expect as base, test } from 'claude-code/testing';

export { describe };

type Body = (...args: any[]) => unknown;

export const it = Object.assign(
  (name: string, body: Body) => test(name, async () => { await body(); }),
  {
    each: (cases: readonly unknown[]) => (name: string, body: Body) => {
      cases.forEach((value, index) => test(`${name} #${index}`, async () => {
        await body(...(Array.isArray(value) ? value : [value]));
      }));
    },
  },
);

export const vi = {
  fn(impl?: Body) {
    const fn: any = (...args: unknown[]) => {
      fn.mock.calls.push(args);
      return fn.impl?.(...args);
    };
    fn.impl = impl;
    fn.mock = { calls: [] as unknown[][] };
    fn.mockResolvedValue = (value: unknown) => { fn.impl = async () => value; return fn; };
    fn.mockImplementation = (next: Body) => { fn.impl = next; return fn; };
    fn.mockClear = () => { fn.mock.calls.length = 0; return fn; };
    return fn;
  },
};

function calledMatchers(calls: unknown[][], negate: boolean) {
  const pass = (ok: boolean) => base(negate ? !ok : ok).toBe(true);
  return {
    toHaveBeenCalled: () => pass(calls.length > 0),
    toHaveBeenCalledOnce: () => pass(calls.length === 1),
    toHaveBeenCalledWith: (...args: unknown[]) => {
      if (negate) base(calls).not.toEqual(base.arrayContaining([args]));
      else base(calls).toEqual(base.arrayContaining([args]));
    },
  };
}

export const expect: any = Object.assign((received: any) => {
  if (typeof received !== 'function' || !received.mock) return base(received);
  const calls = received.mock.calls as unknown[][];
  return { ...calledMatchers(calls, false), not: calledMatchers(calls, true) };
}, base);
