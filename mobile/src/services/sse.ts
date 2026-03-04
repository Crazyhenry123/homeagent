import type {SSEEvent} from '../types';
import {getToken} from './auth';
import {BASE_URL} from './api';
import {emitAuthExpired} from './authEvents';

/**
 * SSE client using XMLHttpRequest for real-time streaming in React Native.
 * React Native's fetch does not reliably support ReadableStream,
 * so we use XHR's onprogress which fires as chunks arrive.
 */
export async function streamChat(
  message: string,
  conversationId: string | null,
  onEvent: (event: SSEEvent) => void,
  onError: (error: Error) => void,
  signal?: AbortSignal,
  media?: string[],
): Promise<void> {
  const token = await getToken();

  const body: Record<string, unknown> = {message};
  if (conversationId) {
    body.conversation_id = conversationId;
  }
  if (media && media.length > 0) {
    body.media = media;
  }

  return new Promise<void>(resolve => {
    const xhr = new XMLHttpRequest();
    let lastIndex = 0;

    xhr.open('POST', `${BASE_URL}/api/chat`);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    xhr.setRequestHeader('Accept', 'text/event-stream');

    if (signal) {
      signal.addEventListener('abort', () => {
        xhr.abort();
        resolve();
      });
    }

    xhr.onprogress = () => {
      const newData = xhr.responseText.substring(lastIndex);
      lastIndex = xhr.responseText.length;

      const lines = newData.split('\n');
      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith('data: ')) {
          const jsonStr = trimmed.slice(6);
          try {
            const event = JSON.parse(jsonStr) as SSEEvent;
            onEvent(event);
          } catch {
            // Skip malformed JSON
          }
        }
      }
    };

    xhr.onload = () => {
      if (xhr.status === 401) {
        emitAuthExpired();
      }
      if (xhr.status >= 400) {
        onError(new Error(`Chat failed: ${xhr.status} ${xhr.responseText}`));
      }
      resolve();
    };

    xhr.onerror = () => {
      onError(new Error('Network error during chat stream'));
      resolve();
    };

    xhr.send(JSON.stringify(body));
  });
}
