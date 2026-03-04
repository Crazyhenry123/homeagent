import * as FileSystem from 'expo-file-system';
import {uploadChatImage} from './api';

/**
 * Upload an image for chat: get a presigned URL from the backend,
 * then PUT the file directly to S3.
 */
export async function uploadImage(
  uri: string,
  contentType: string,
  fileSize: number,
): Promise<string> {
  // Step 1: Get presigned upload URL via shared API client
  const {media_id, upload_url} = await uploadChatImage(contentType, fileSize);

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
 * Upload an audio file for chat: get a presigned URL from the backend,
 * then PUT the file directly to S3.
 */
export async function uploadAudio(
  uri: string,
  fileSize: number,
): Promise<string> {
  const contentType = 'audio/wav';
  const {media_id, upload_url} = await uploadChatImage(contentType, fileSize);

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
    case 'wav':
      return 'audio/wav';
    default:
      return 'image/jpeg';
  }
}
