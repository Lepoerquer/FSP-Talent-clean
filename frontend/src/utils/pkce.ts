/**
 * Параметры OAuth 2.0 / OpenID Connect (Authorization Code + PKCE, RFC 7636).
 * Используются в имитации входа через ФСП ID: боевого Keycloak ФСП командам не дают,
 * поэтому интерфейс воспроизводит протокол и готов к подключению реального провайдера.
 */
const b64url = (bytes: ArrayBuffer | Uint8Array): string => {
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let s = '';
  arr.forEach((b) => (s += String.fromCharCode(b)));
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
};

export const randomUrlSafe = (bytes = 32): string => b64url(crypto.getRandomValues(new Uint8Array(bytes)));

export interface PkcePair {
  verifier: string;
  challenge: string;
  method: 'S256';
}

export const createPkce = async (): Promise<PkcePair> => {
  const verifier = randomUrlSafe(48);
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
  return { verifier, challenge: b64url(digest), method: 'S256' };
};
