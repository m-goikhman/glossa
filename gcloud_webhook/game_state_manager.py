import json
import datetime
import logging
from typing import Dict, Any, Optional
from google.cloud import storage
from config import GCS_BUCKET_NAME
import pytz

logger = logging.getLogger(__name__)

class GameStateManager:
    """Manages persistent storage and retrieval of game state for users."""
    
    def __init__(self):
        self.storage_client = None
        self.bucket = None
        
        if not GCS_BUCKET_NAME:
            logger.warning("GCS_BUCKET_NAME is not set. Game state persistence is disabled.")
    
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
    
    def _get_state_blob_name(self, user_id: int) -> str:
        """Get the blob name for storing user's game state."""
        return f"game_states/user_{user_id}_state.json"
    
    async def save_game_state(self, user_id: int, state: Dict[str, Any]) -> bool:
        """Save the current game state for a user to persistent storage."""
        bucket = self._get_bucket()
        if not bucket:
            logger.warning(f"Cannot save game state for user {user_id}: No storage bucket configured")
            return False
        
        try:
            # Add timestamp for when state was saved
            cet_tz = pytz.timezone('Europe/Berlin')
            data = {
                "state": state,
                "last_saved": datetime.datetime.now(cet_tz).isoformat(),
                "user_id": user_id
            }
            
            blob_name = self._get_state_blob_name(user_id)
            blob = bucket.blob(blob_name)
            
            # Convert sets to lists for JSON serialization
            serializable_state = self._prepare_state_for_storage(data)
            
            blob.upload_from_string(
                json.dumps(serializable_state, indent=2, ensure_ascii=False),
                content_type="application/json; charset=utf-8"
            )
            
            logger.info(f"Successfully saved game state for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save game state for user {user_id}: {e}")
            return False
    
    async def load_game_state(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Load the saved game state for a user from persistent storage."""
        bucket = self._get_bucket()
        if not bucket:
            logger.warning(f"Cannot load game state for user {user_id}: No storage bucket configured")
            return None
        
        try:
            blob_name = self._get_state_blob_name(user_id)
            blob = bucket.blob(blob_name)
            
            if not blob.exists():
                logger.info(f"No saved game state found for user {user_id}")
                return None
            
            # Download and parse the state
            content = blob.download_as_text(encoding="utf-8")
            saved_data = json.loads(content)
            
            # Convert lists back to sets where appropriate
            restored_state = self._restore_state_from_storage(saved_data)
            
            logger.info(f"Successfully loaded game state for user {user_id}")
            return restored_state
            
        except Exception as e:
            logger.error(f"Failed to load game state for user {user_id}: {e}")
            return None
    
    async def delete_game_state(self, user_id: int) -> bool:
        """Delete the saved game state for a user (e.g., when game is completed)."""
        bucket = self._get_bucket()
        if not bucket:
            logger.warning(f"Cannot delete game state for user {user_id}: No storage bucket configured")
            return False
        
        try:
            blob_name = self._get_state_blob_name(user_id)
            blob = bucket.blob(blob_name)
            
            if blob.exists():
                blob.delete()
                logger.info(f"Successfully deleted game state for user {user_id}")
            else:
                logger.info(f"No game state to delete for user {user_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete game state for user {user_id}: {e}")
            return False
    
    def _prepare_state_for_storage(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare state for JSON serialization by converting sets to lists."""
        if isinstance(state, dict):
            prepared = {}
            for key, value in state.items():
                if isinstance(value, set):
                    prepared[key] = list(value)
                elif isinstance(value, dict):
                    prepared[key] = self._prepare_state_for_storage(value)
                else:
                    prepared[key] = value
            return prepared
        elif isinstance(state, list):
            return [self._prepare_state_for_storage(item) if isinstance(item, (dict, list)) else item for item in state]
        else:
            return state
    
    def _restore_state_from_storage(self, saved_data: Dict[str, Any]) -> Dict[str, Any]:
        """Restore state from storage by converting lists back to sets where appropriate."""
        if isinstance(saved_data, dict):
            restored = {}
            for key, value in saved_data.items():
                if key == "state" and isinstance(value, dict):
                    # This is the actual game state, restore sets
                    restored[key] = self._restore_game_state_sets(value)
                else:
                    restored[key] = value
            return restored
        return saved_data
    
    def _restore_game_state_sets(self, game_state: Dict[str, Any]) -> Dict[str, Any]:
        """Restore sets in the game state from lists."""
        restored = {}
        for key, value in game_state.items():
            if key in ["clues_examined", "suspects_interrogated"] and isinstance(value, list):
                restored[key] = set(value)
            elif key == "topic_memory" and isinstance(value, dict):
                # Handle nested topic_memory structure
                topic_memory = {}
                for topic_key, topic_value in value.items():
                    if topic_key in ["spoken", "predefined_used"] and isinstance(topic_value, list):
                        topic_memory[topic_key] = topic_value  # Keep as list for topic_memory
                    else:
                        topic_memory[topic_key] = topic_value
                restored[key] = topic_memory
            else:
                restored[key] = value
        return restored
    


# Global instance
game_state_manager = GameStateManager()
