type AuthEventListener = () => void;

const listeners: Set<AuthEventListener> = new Set();

export function onAuthExpired(listener: AuthEventListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function emitAuthExpired(): void {
  listeners.forEach(listener => listener());
}
