import * as FileSystem from 'expo-file-system';
import {BASE_URL} from './api';
import {getToken} from './auth';
import {emitAuthExpired} from './authEvents';

interface UploadImageResponse {
  media_id: string;
  upload_url: string;
}

/**
 * Upload an image for chat: get a presigned URL from the backend,
 * then PUT the file directly to S3.
 */
export async function uploadImage(
  uri: string,
  contentType: string,
  fileSize: number,
): Promise<string> {
  const token = await getToken();

  // Step 1: Get presigned upload URL
  const response = await fetch(`${BASE_URL}/api/chat/upload-image`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({content_type: contentType, file_size: fileSize}),
  });

  if (!response.ok) {
    if (response.status === 401) {
      emitAuthExpired();
    }
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || `Upload init failed: ${response.status}`);
  }

  const {media_id, upload_url}: UploadImageResponse = await response.json();

  // Step 2: Upload file directly to S3 via presigned URL
  await FileSystem.uploadAsync(upload_url, uri, {
    httpMethod: 'PUT',
    headers: {
      'Content-Type': contentType,
    },
    uploadType: FileSystem.FileSystemUploadType.BINARY_CONTENT,
  });

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
    default:
      return 'image/jpeg';
  }
}
