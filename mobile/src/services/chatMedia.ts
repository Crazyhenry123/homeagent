import {uploadMediaDirect} from './api';

/**
 * Upload an image for chat via the backend proxy.
 * The backend stores the file to S3 directly, avoiding presigned URL
 * reachability issues (e.g., phone can't reach MinIO in local dev).
 */
export async function uploadImage(
  uri: string,
  contentType: string,
  _fileSize: number,
): Promise<string> {
  const {media_id} = await uploadMediaDirect(uri, contentType);
  return media_id;
}

/**
 * Upload an audio file for chat via the backend proxy.
 */
export async function uploadAudio(
  uri: string,
  _fileSize: number,
): Promise<string> {
  const {media_id} = await uploadMediaDirect(uri, 'audio/wav');
  return media_id;
}

/**
 * Get the content type from a file URI.
 */
export function getContentType(uri: string): string {
  const ext = uri.split('.').pop()?.toLowerCase();
  switch (ext) {
    case 'jpg':
    case 'jpeg':
      return 'image/jpeg';
    case 'png':
      return 'image/png';
    case 'gif':
      return 'image/gif';
    case 'webp':
      return 'image/webp';
    case 'wav':
      return 'audio/wav';
    default:
      return 'image/jpeg';
  }
}
