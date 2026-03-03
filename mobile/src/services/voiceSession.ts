import {getToken} from './auth';
import {BASE_URL} from './api';
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
    const token = await getToken();
    const wsBase = BASE_URL.replace(/^http/, 'ws');
    let url = `${wsBase}/api/voice?token=${encodeURIComponent(token || '')}`;
    if (this.conversationId) {
      url += `&conversation_id=${encodeURIComponent(this.conversationId)}`;
    }

    return new Promise<void>((resolve, reject) => {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        resolve();
      };

      this.ws.onmessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data) as VoiceEvent;
          this.onEvent(data);
        } catch {
          // Skip malformed JSON
        }
      };

      this.ws.onclose = () => {
        this.onClose();
      };

      this.ws.onerror = () => {
        reject(new Error('WebSocket connection failed'));
      };
    });
  }

  sendAudioStart(config: {sample_rate: number} = {sample_rate: 16000}): void {
    this.send({type: 'audio_start', config});
  }

  sendAudioChunk(base64Pcm: string): void {
    this.send({type: 'audio_chunk', data: base64Pcm});
  }

  sendAudioEnd(): void {
    this.send({type: 'audio_end'});
  }

  sendText(content: string): void {
    this.send({type: 'text', content});
  }

  private send(data: Record<string, unknown>): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  disconnect(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}
