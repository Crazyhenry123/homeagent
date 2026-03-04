import {buildVoiceWsUrl} from './api';
import type {VoiceEvent} from '../types';

/**
 * WebSocket client for bidirectional voice streaming with Nova Sonic.
 */
export class VoiceSessionClient {
  private ws: WebSocket | null = null;
  private onEvent: (event: VoiceEvent) => void;
  private onClose: () => void;
  private conversationId: string | null;

  constructor(
    conversationId: string | null,
    onEvent: (event: VoiceEvent) => void,
    onClose: () => void,
  ) {
    this.conversationId = conversationId;
    this.onEvent = onEvent;
    this.onClose = onClose;
  }

  async connect(): Promise<void> {
    const url = await buildVoiceWsUrl(this.conversationId);
    console.log('[VoiceWS] Connecting to:', url);

    return new Promise<void>((resolve, reject) => {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        console.log('[VoiceWS] Connected');
        resolve();
      };

      this.ws.onmessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data) as VoiceEvent;
          console.log('[VoiceWS] Received event:', data.type, data.type === 'audio_chunk' ? `(${(data.data?.length ?? 0)} chars b64)` : JSON.stringify(data).slice(0, 200));
          this.onEvent(data);
        } catch (e) {
          console.warn('[VoiceWS] Failed to parse message:', e, event.data?.toString().slice(0, 200));
        }
      };

      this.ws.onclose = (event) => {
        console.log('[VoiceWS] Closed, code:', event.code, 'reason:', event.reason);
        this.onClose();
      };

      this.ws.onerror = (event) => {
        console.error('[VoiceWS] Error:', event);
        reject(new Error('WebSocket connection failed'));
      };
    });
  }

  sendAudioStart(config: {sample_rate: number} = {sample_rate: 16000}): void {
    console.log('[VoiceWS] Sending audio_start');
    this.send({type: 'audio_start', config});
  }

  sendAudioChunk(base64Pcm: string): void {
    console.log('[VoiceWS] Sending audio_chunk:', base64Pcm.length, 'chars b64');
    this.send({type: 'audio_chunk', data: base64Pcm});
  }

  sendAudioEnd(): void {
    console.log('[VoiceWS] Sending audio_end');
    this.send({type: 'audio_end'});
  }

  sendText(content: string): void {
    console.log('[VoiceWS] Sending text:', content.slice(0, 100));
    this.send({type: 'text', content});
  }

  private send(data: Record<string, unknown>): void {
    const state = this.ws?.readyState;
    if (state === WebSocket.OPEN) {
      this.ws!.send(JSON.stringify(data));
    } else {
      console.warn('[VoiceWS] Cannot send, readyState:', state, '(0=CONNECTING, 1=OPEN, 2=CLOSING, 3=CLOSED)');
    }
  }

  disconnect(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}
