import os
from logging import getLogger

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from bot.helper.ext_utils.bot_utils import SetInterval, async_to_sync
from bot.helper.ext_utils.files_utils import get_mime_type
from bot.helper.mirror_leech_utils.youtube_utils.youtube_helper import YouTubeHelper

LOGGER = getLogger(__name__)


class YouTubeUpload(YouTubeHelper):
    def __init__(
        self,
        listener,
        path,
        privacy="unlisted",
        tags=None,
        category="22",
        description=None,
        playlist_id=None,
        upload_mode="playlist",
    ):
        self.listener = listener
        self._updater = None
        self._path = path
        self._is_errored = False
        self.privacy = privacy
        self.tags = tags
        self.category = category
        self.description = description
        self.playlist_id = playlist_id
        self.upload_mode = upload_mode
        super().__init__()
        self.is_uploading = True

    def _upload_playlist(self, folder_path, playlist_name):
        """Uploads all videos in a folder and adds them to a new playlist."""
        video_infos = []
        video_files_count = 0
        LOGGER.info(f"Starting playlist upload for folder: {folder_path}")

        try:
            for item_name in os.listdir(folder_path):
                item_path = os.path.join(folder_path, item_name)
                if os.path.isfile(item_path):
                    mime_type = get_mime_type(item_path)
                    if mime_type and mime_type.startswith("video/"):
                        video_files_count += 1
                        LOGGER.info(f"Uploading video file: {item_path}")
                        try:
                            video_upload_result = self._upload_video(
                                item_path, item_name, mime_type
                            )
                            if video_upload_result and video_upload_result.get(
                                "url"
                            ):
                                video_id = video_upload_result["url"].split("=")[-1]
                                video_infos.append(
                                    {
                                        "id": video_id,
                                        "name": video_upload_result["name"],
                                    }
                                )
                                LOGGER.info(
                                    f"Successfully uploaded video: {item_name}, ID: {video_id}"
                                )
                            elif self.listener.is_cancelled:
                                LOGGER.info(
                                    "Playlist upload cancelled during video upload."
                                )
                                return None
                            else:
                                LOGGER.warning(
                                    f"Failed to upload video or extract ID/name: {item_name}"
                                )
                        except Exception as e:
                            LOGGER.error(f"Error uploading video {item_name}: {e}")
                    else:
                        LOGGER.debug(
                            f"Skipping non-video file: {item_path} (MIME: {mime_type})"
                        )
                if self.listener.is_cancelled:
                    LOGGER.info("Playlist upload process cancelled.")
                    return None

            if not video_infos:
                LOGGER.info("No videos found or uploaded in the folder.")
                if video_files_count > 0:
                    raise ValueError(
                        "No videos were successfully uploaded from the folder."
                    )
                return "No videos to upload in playlist."

            LOGGER.info(f"Creating playlist: {playlist_name}")
            playlist_request_body = {
                "snippet": {
                    "title": playlist_name,
                    "description": f"Playlist created from folder: {playlist_name}",
                    "tags": ["mirror-leech-bot", "playlist-upload"],
                },
                "status": {"privacyStatus": "private"},
            }
            playlist_insert_request = self.service.playlists().insert(
                part="snippet,status", body=playlist_request_body
            )
            playlist_response = playlist_insert_request.execute()
            playlist_id = playlist_response["id"]
            playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
            LOGGER.info(
                f"Playlist created: {playlist_name}, ID: {playlist_id}, URL: {playlist_url}"
            )

            for video_info in video_infos:
                if self.listener.is_cancelled:
                    LOGGER.info(
                        "Playlist upload cancelled before adding all videos to playlist."
                    )
                    break
                video_id_to_add = video_info["id"]
                LOGGER.info(
                    f"Adding video ID {video_id_to_add} ({video_info['name']}) to playlist {playlist_id}"
                )
                playlist_item_request_body = {
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": video_id_to_add,
                        },
                    }
                }
                playlist_item_insert_request = self.service.playlistItems().insert(
                    part="snippet", body=playlist_item_request_body
                )
                playlist_item_insert_request.execute()
                LOGGER.info(
                    f"Successfully added video ID {video_id_to_add} to playlist {playlist_id}"
                )

            self.total_files = len(video_infos)
            individual_video_data = [
                {
                    "url": f"https://www.youtube.com/watch?v={v_info['id']}",
                    "name": v_info["name"],
                }
                for v_info in video_infos
            ]
            return {
                "playlist_url": playlist_url,
                "individual_video_urls": individual_video_data,
            }

        except HttpError as e:
            LOGGER.error(f"YouTube API error during playlist operation: {e}")
            raise e
        except Exception as e:
            LOGGER.error(f"Error during playlist creation or video addition: {e}")
            raise e

    def user_setting(self):
        """Handle user-specific YouTube token settings"""
        if self.listener.up_dest.startswith("yt:"):
            self.token_path = f"tokens/{self.listener.user_id}.pickle"
            self.listener.up_dest = self.listener.up_dest.replace("yt:", "", 1)
        elif hasattr(self.listener, "user_id") and self.listener.user_id:
            self.token_path = f"tokens/{self.listener.user_id}.pickle"

    def upload(self):
        """Main upload function"""
        self.user_setting()
        try:
            self.service = self.authorize(
                self.listener.user_id if hasattr(self.listener, "user_id") else ""
            )
        except Exception as e:
            LOGGER.error(f"YouTube authorization failed: {e}")
            async_to_sync(
                self.listener.on_upload_error, f"YouTube authorization failed: {e!s}"
            )
            return

        LOGGER.info(f"Uploading to YouTube: {self._path}")
        self._updater = SetInterval(self.update_interval, self.progress)
        upload_result_dict = {}
        upload_type_str = "Unknown"
        files_processed = 0
        original_playlist_id = self.playlist_id

        try:
            if os.path.isfile(self._path):
                mime_type = get_mime_type(self._path)
                if not mime_type or not mime_type.startswith("video/"):
                    raise ValueError(f"File is not a video. MIME type: {mime_type}")

                if self.upload_mode == "playlist":
                    upload_type_str = "Playlist"
                    video_result = self._upload_video(
                        self._path,
                        self.listener.name,
                        mime_type,
                        playlist_id_override=original_playlist_id,
                    )
                    if not video_result and not self.listener.is_cancelled:
                        raise ValueError(
                            "Failed to upload video or video result is null."
                        )
                    if self.listener.is_cancelled:
                        return

                    if original_playlist_id:
                        playlist_url = f"https://www.youtube.com/playlist?list={original_playlist_id}"
                    else:
                        playlist_title = os.path.splitext(self.listener.name)[0]
                        LOGGER.info(
                            f"Creating new playlist for single video: {playlist_title}"
                        )
                        playlist_request_body = {
                            "snippet": {
                                "title": playlist_title,
                                "description": f"Playlist for: {self.listener.name}",
                            },
                            "status": {"privacyStatus": self.privacy},
                        }
                        playlist_insert_request = self.service.playlists().insert(
                            part="snippet,status", body=playlist_request_body
                        )
                        playlist_response = playlist_insert_request.execute()
                        new_playlist_id = playlist_response["id"]
                        playlist_url = f"https://www.youtube.com/playlist?list={new_playlist_id}"
                        LOGGER.info(f"New playlist created: {playlist_url}")

                        if video_result and video_result.get("url"):
                            playlist_item_request_body = {
                                "snippet": {
                                    "playlistId": new_playlist_id,
                                    "resourceId": {
                                        "kind": "youtube#video",
                                        "videoId": video_result["url"].split("=")[
                                            -1
                                        ],
                                    },
                                }
                            }
                            self.service.playlistItems().insert(
                                part="snippet", body=playlist_item_request_body
                            ).execute()
                            LOGGER.info(
                                f"Video {video_result['url']} added to new playlist {new_playlist_id}"
                            )

                    upload_result_dict = {
                        "playlist_url": playlist_url,
                        "individual_video_urls": [video_result]
                        if video_result
                        else [],
                    }
                    if video_result:
                        files_processed = 1
                    LOGGER.info(f"Uploaded single file to playlist: {self._path}")

                elif self.upload_mode == "individual":
                    upload_type_str = "Video"
                    video_result = self._upload_video(
                        self._path,
                        self.listener.name,
                        mime_type,
                        playlist_id_override=None,
                    )
                    if not video_result and not self.listener.is_cancelled:
                        raise ValueError(
                            "Failed to upload video or video result is null."
                        )
                    if self.listener.is_cancelled:
                        return

                    upload_result_dict = {
                        "individual_video_urls": [video_result]
                        if video_result
                        else []
                    }
                    if video_result:
                        upload_result_dict["video_url"] = video_result
                        files_processed = 1
                    LOGGER.info(f"Uploaded single file individually: {self._path}")
                else:
                    raise ValueError(
                        f"Invalid upload_mode for single file: {self.upload_mode}"
                    )

            elif os.path.isdir(self._path):
                playlist_name_for_new = os.path.basename(self._path)

                if self.upload_mode == "playlist":
                    upload_type_str = "Playlist"
                    if original_playlist_id:
                        self.playlist_id = original_playlist_id
                        individual_video_urls = []
                        processed_in_folder = 0
                        items = list(os.listdir(self._path))
                        self.total_files = sum(
                            1
                            for item_name in items
                            if os.path.isfile(os.path.join(self._path, item_name))
                            and get_mime_type(
                                os.path.join(self._path, item_name),
                            ).startswith("video/")
                        )

                        for item_name in items:
                            if self.listener.is_cancelled:
                                break
                            item_path = os.path.join(self._path, item_name)
                            if os.path.isfile(item_path):
                                mime_type = get_mime_type(item_path)
                                if mime_type and mime_type.startswith("video/"):
                                    video_result = self._upload_video(
                                        item_path,
                                        item_name,
                                        mime_type,
                                        playlist_id_override=original_playlist_id,
                                    )
                                    if video_result:
                                        individual_video_urls.append(video_result)
                                        processed_in_folder += 1

                        if self.listener.is_cancelled:
                            return
                        upload_result_dict = {
                            "playlist_url": f"https://www.youtube.com/playlist?list={original_playlist_id}",
                            "individual_video_urls": individual_video_urls,
                        }
                        files_processed = processed_in_folder
                        LOGGER.info(
                            f"Uploaded videos from folder to existing playlist ID: {original_playlist_id}"
                        )
                    else:
                        upload_result_dict = self._upload_playlist(
                            self._path, playlist_name_for_new
                        )
                        if self.listener.is_cancelled:
                            return
                        if (
                            upload_result_dict
                            and isinstance(upload_result_dict, dict)
                            and upload_result_dict.get("playlist_url")
                        ):
                            files_processed = self.total_files
                        elif isinstance(upload_result_dict, str):
                            raise ValueError(
                                f"Playlist creation failed: {upload_result_dict}"
                            )
                        else:
                            files_processed = 0
                        LOGGER.info(
                            f"Uploaded new playlist from folder: {self._path}"
                        )

                elif self.upload_mode == "individual":
                    upload_type_str = "Individual Videos"
                    individual_video_urls = []
                    processed_in_folder = 0
                    items = list(os.listdir(self._path))
                    self.total_files = sum(
                        1
                        for item_name in items
                        if os.path.isfile(os.path.join(self._path, item_name))
                        and get_mime_type(
                            os.path.join(self._path, item_name)
                        ).startswith("video/")
                    )

                    for item_name in items:
                        if self.listener.is_cancelled:
                            break
                        item_path = os.path.join(self._path, item_name)
                        if os.path.isfile(item_path):
                            mime_type = get_mime_type(item_path)
                            if mime_type and mime_type.startswith("video/"):
                                try:
                                    video_result = self._upload_video(
                                        item_path,
                                        item_name,
                                        mime_type,
                                        playlist_id_override=None,
                                    )
                                    if video_result:
                                        individual_video_urls.append(video_result)
                                        processed_in_folder += 1
                                except Exception as e:
                                    LOGGER.error(
                                        f"Failed to upload {item_name} individually: {e}"
                                    )
                    if self.listener.is_cancelled:
                        return
                    upload_result_dict = {
                        "individual_video_urls": individual_video_urls
                    }
                    files_processed = processed_in_folder
                    LOGGER.info(
                        f"Uploaded individual videos from folder: {self._path}"
                    )
                else:
                    raise ValueError(
                        f"Invalid upload_mode for directory: {self.upload_mode}"
                    )
            else:
                raise ValueError(f"Path is not a file or directory: {self._path}")

            if self.listener.is_cancelled:
                LOGGER.info("Upload cancelled by listener during main processing.")
                return

            if (
                not upload_result_dict
                or (
                    (
                        upload_result_dict.get("playlist_url")
                        and not upload_result_dict.get("individual_video_urls")
                    )
                    and files_processed == 0
                )
                or (
                    (
                        not upload_result_dict.get("playlist_url")
                        and not upload_result_dict.get("individual_video_urls")
                        and not upload_result_dict.get("video_url")
                    )
                    and files_processed == 0
                )
            ):
                if files_processed == 0 and self.total_files > 0:
                    raise ValueError(
                        f"{upload_type_str} upload: No videos were successfully processed out of {self.total_files}."
                    )
                if files_processed == 0:
                    raise ValueError(
                        f"{upload_type_str} upload: No video files found or processed."
                    )

        except Exception as err:
            if isinstance(err, RetryError):
                LOGGER.info(f"Total Attempts: {err.last_attempt.attempt_number}")
                err = err.last_attempt.exception()
            err_msg = str(err).replace(">", "").replace("<", "")
            LOGGER.error(f"YouTube Upload Error: {err_msg}")
            async_to_sync(
                self.listener.on_upload_complete,
                None,
                None,
                0,
                "Error",
                upload_result=err_msg,
            )
            self._is_errored = True
        finally:
            self.playlist_id = original_playlist_id
            self._updater.cancel()

        if self.listener.is_cancelled and not self._is_errored:
            LOGGER.info("Upload process was cancelled by listener.")
            return

        if self._is_errored:
            LOGGER.error("Upload process failed with an error. Listener notified.")
            return

        if (
            not upload_result_dict
            and files_processed == 0
            and not self.listener.is_cancelled
        ):
            final_err_msg = (
                "Upload resulted in no data and was not caught by other checks."
            )
            LOGGER.error(final_err_msg)
            async_to_sync(
                self.listener.on_upload_complete,
                None,
                None,
                0,
                "Error",
                upload_result=final_err_msg,
            )
            return

        async_to_sync(
            self.listener.on_upload_complete,
            None,
            None,
            files_processed,
            upload_type_str,
            upload_result=upload_result_dict,
        )
        LOGGER.info(
            f"Upload process completed. Type: {upload_type_str}, Files: {files_processed}"
        )

    @retry(
        wait=wait_exponential(multiplier=2, min=3, max=6),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(Exception),
    )
    def _upload_video(
        self, file_path, file_name, mime_type, playlist_id_override=None
    ):
        """
        Uploads a single video to YouTube.
        Optionally adds to a playlist if playlist_id_override is provided.
        If playlist_id_override is None, it will not be added to any playlist,
        regardless of self.playlist_id's original value.
        """
        current_playlist_target = playlist_id_override

        title = file_name
        privacy_status = self.privacy
        category_id = self.category
        description_base = self.description or f"Uploaded: {file_name}"
        description = f"{description_base}\n\nOriginal filename: {file_name}"
        tags_for_body = self.tags
        if tags_for_body is None:
            tags_for_body = ["mirror-leech-bot", "telegram-bot", "upload"]

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags_for_body,
                "categoryId": str(category_id),
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        media_body = MediaFileUpload(
            file_path,
            mimetype=mime_type,
            resumable=True,
            chunksize=1024 * 1024 * 4,
        )

        insert_request = self.service.videos().insert(
            part=",".join(body.keys()), body=body, media_body=media_body
        )

        response = None
        retries = 0
        self.upload_progress = 0

        while response is None and not self.listener.is_cancelled:
            try:
                self.status, response = insert_request.next_chunk()
                if self.status:
                    self.upload_progress = int(self.status.progress() * 100)
                    LOGGER.info(f"Uploading {file_name}: {self.upload_progress}%")
            except HttpError as err:
                if err.resp.status in [500, 502, 503, 504, 429] and retries < 5:
                    retries += 1
                    LOGGER.warning(
                        f"HTTP error {err.resp.status} for {file_name}, retrying... ({retries}/5)"
                    )
                    continue
                error_content = (
                    err.content.decode("utf-8")
                    if err.content
                    else f"Unknown error (status: {err.resp.status})"
                )
                LOGGER.error(
                    f"YouTube upload for {file_name} failed: {error_content}"
                )
                raise err
            except Exception as e:
                LOGGER.error(f"Unexpected error during {file_name} upload: {e}")
                raise e

        if self.listener.is_cancelled:
            LOGGER.info(f"Upload of {file_name} cancelled by listener.")
            return None

        if response:
            video_id = response["id"]
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            LOGGER.info(f"Video {file_name} uploaded successfully: {video_url}")

            if current_playlist_target:
                LOGGER.info(
                    f"Adding video {video_id} ({file_name}) to specified playlist ID {current_playlist_target}"
                )
                try:
                    playlist_item_request_body = {
                        "snippet": {
                            "playlistId": current_playlist_target,
                            "resourceId": {
                                "kind": "youtube#video",
                                "videoId": video_id,
                            },
                        }
                    }
                    self.service.playlistItems().insert(
                        part="snippet", body=playlist_item_request_body
                    ).execute()
                    LOGGER.info(
                        f"Successfully added video {video_id} to playlist {current_playlist_target}"
                    )
                except HttpError as e:
                    LOGGER.error(
                        f"Could not add video {video_id} to playlist {current_playlist_target}: {e}"
                    )
                except Exception as e:
                    LOGGER.error(
                        f"Unexpected error adding video {video_id} to playlist {current_playlist_target}: {e}"
                    )
            return {"url": video_url, "name": file_name}

        LOGGER.warning(
            f"Upload of {file_name} finished but no response object. Cancelled: {self.listener.is_cancelled}"
        )
        return None

    def get_upload_status(self):
        return {
            "progress": self.upload_progress,
            "speed": self.speed,
            "processed_bytes": self.processed_bytes,
            "total_files": self.total_files,
            "is_uploading": self.is_uploading,
        }
