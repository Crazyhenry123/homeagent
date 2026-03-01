type AuthEventListener = () => void;

const listeners: Set<AuthEventListener> = new Set();

export function onAuthExpired(listener: AuthEventListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

let firing = false;

export function emitAuthExpired(): void {
  if (firing) return;
  firing = true;
  listeners.forEach(listener => listener());
  setTimeout(() => { firing = false; }, 1000);
}
