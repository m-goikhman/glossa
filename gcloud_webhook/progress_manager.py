import json
import datetime
import logging
from typing import Dict, Any, Optional, List
from google.cloud import storage
from config import GCS_BUCKET_NAME
import pytz

logger = logging.getLogger(__name__)

class ProgressManager:
    """Manages user learning progress using Google Cloud Storage."""
    
    def __init__(self):
        self.storage_client = None
        self.bucket = None
        
        if not GCS_BUCKET_NAME:
            logger.warning("GCS_BUCKET_NAME is not set. Progress tracking is disabled.")
    
    def _get_bucket(self):
        """Lazy initialization of storage client and bucket."""
        if self.storage_client is None and GCS_BUCKET_NAME:
            try:
                self.storage_client = storage.Client()
                self.bucket = self.storage_client.bucket(GCS_BUCKET_NAME)
            except Exception as e:
                logger.error(f"Failed to initialize GCS bucket '{GCS_BUCKET_NAME}': {e}")
                self.bucket = None
        return self.bucket
    
    def _get_progress_blob_name(self, user_id: int, participant_code: str = None) -> str:
        """Get the blob name for storing user's learning progress."""
        if participant_code:
            return f"participant_logs/{participant_code}_language_progress.json"
        return f"user_progress/user_{user_id}_progress.json"
    
    def add_word_learned(self, user_id: int, word: str, definition: str, participant_code: str = None) -> bool:
        """Add a new word to the user's learned words list."""
        bucket = self._get_bucket()
        if not bucket:
            logger.warning(f"Cannot save word progress for user {user_id}: No storage bucket configured")
            return False
        
        try:
            # Load existing progress
            progress_data = self.get_user_progress(user_id, participant_code)
            
            # Add new word entry
            cet_tz = pytz.timezone('Europe/Berlin')
            new_entry = {
                "timestamp": datetime.datetime.now(cet_tz).isoformat(),
                "query": word,
                "feedback": definition
            }
            
            # Check for duplicates
            if not any(entry.get('query') == word for entry in progress_data.get("words_learned", [])):
                progress_data.setdefault("words_learned", []).append(new_entry)
                
                # Save updated progress
                return self._save_progress(user_id, progress_data, participant_code)
            
            return True  # Word already exists, no need to save
            
        except Exception as e:
            logger.error(f"Failed to add word progress for user {user_id}: {e}")
            return False
    
    def add_writing_feedback(self, user_id: int, user_text: str, feedback: str, participant_code: str = None) -> bool:
        """Add writing feedback to the user's progress."""
        bucket = self._get_bucket()
        if not bucket:
            logger.warning(f"Cannot save writing feedback for user {user_id}: No storage bucket configured")
            return False
        
        try:
            # Load existing progress
            progress_data = self.get_user_progress(user_id, participant_code)
            
            # Add new feedback entry
            cet_tz = pytz.timezone('Europe/Berlin')
            new_entry = {
                "timestamp": datetime.datetime.now(cet_tz).isoformat(),
                "query": user_text,
                "feedback": feedback
            }
            
            # Check for duplicates
            if not any(entry.get('query') == user_text for entry in progress_data.get("writing_feedback", [])):
                progress_data.setdefault("writing_feedback", []).append(new_entry)
                
                # Save updated progress
                return self._save_progress(user_id, progress_data, participant_code)
            
            return True  # Feedback already exists, no need to save
            
        except Exception as e:
            logger.error(f"Failed to add writing feedback for user {user_id}: {e}")
            return False
    
    def get_user_progress(self, user_id: int, participant_code: str = None) -> Dict[str, Any]:
        """Get the user's learning progress data."""
        bucket = self._get_bucket()
        if not bucket:
            logger.warning(f"Cannot load progress for user {user_id}: No storage bucket configured")
            return {"words_learned": [], "writing_feedback": []}
        
        try:
            blob_name = self._get_progress_blob_name(user_id, participant_code)
            blob = bucket.blob(blob_name)
            
            if not blob.exists():
                logger.info(f"No progress data found for user {user_id}, creating new")
                return {"words_learned": [], "writing_feedback": []}
            
            # Download and parse the progress data
            content = blob.download_as_text(encoding="utf-8")
            progress_data = json.loads(content)
            
            # Ensure the structure exists
            if "words_learned" not in progress_data:
                progress_data["words_learned"] = []
            if "writing_feedback" not in progress_data:
                progress_data["writing_feedback"] = []
            
            logger.info(f"Successfully loaded progress for user {user_id}")
            return progress_data
            
        except Exception as e:
            logger.error(f"Failed to load progress for user {user_id}: {e}")
            return {"words_learned": [], "writing_feedback": []}
    
    def _save_progress(self, user_id: int, progress_data: Dict[str, Any], participant_code: str = None) -> bool:
        """Save progress data to Google Cloud Storage."""
        bucket = self._get_bucket()
        if not bucket:
            logger.warning(f"Cannot save progress for user {user_id}: No storage bucket configured")
            return False
        
        try:
            blob_name = self._get_progress_blob_name(user_id, participant_code)
            blob = bucket.blob(blob_name)
            
            blob.upload_from_string(
                json.dumps(progress_data, indent=2, ensure_ascii=False),
                content_type="application/json; charset=utf-8"
            )
            
            logger.info(f"Successfully saved progress for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save progress for user {user_id}: {e}")
            return False
    
    def clear_user_progress(self, user_id: int, participant_code: str = None) -> bool:
        """Clear all progress data for a user."""
        bucket = self._get_bucket()
        if not bucket:
            logger.warning(f"Cannot clear progress for user {user_id}: No storage bucket configured")
            return False
        
        try:
            blob_name = self._get_progress_blob_name(user_id, participant_code)
            blob = bucket.blob(blob_name)
            
            if blob.exists():
                blob.delete()
                logger.info(f"Successfully cleared progress for user {user_id}")
            else:
                logger.info(f"No progress to clear for user {user_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear progress for user {user_id}: {e}")
            return False

# Global instance
progress_manager = ProgressManager()
