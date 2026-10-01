// An unsigned JWT whose `exp` is `secondsLeft` from now. The client only ever
// reads the payload (token.ts, `expiresSoon`); the signature is the backend's
// business.
export function fakeJwt(secondsLeft: number, claims: Record<string, unknown> = {}): string {
  const encode = (value: object) =>
    btoa(JSON.stringify(value)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  const exp = Math.floor(Date.now() / 1000) + secondsLeft
  return `${encode({ alg: 'HS256', typ: 'JWT' })}.${encode({ sub: 'user', exp, ...claims })}.signature`
}
