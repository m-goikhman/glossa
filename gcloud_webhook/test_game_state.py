#!/usr/bin/env python3
"""
Test script for the GameStateManager to verify functionality.
Run this script to test the game state persistence system.
"""

import asyncio
import json
from game_state_manager import game_state_manager

def test_game_state_manager():
    """Test the GameStateManager functionality."""
    print("🧪 Testing GameStateManager...")
    
    # Test user ID
    test_user_id = 999999999
    
    # Test state data
    test_state = {
        "mode": "public",
        "current_character": None,
        "waiting_for_word": False,
        "waiting_for_accusation": False,
        "accused_character": None,
        "clues_examined": {"1", "2"},
        "suspects_interrogated": {"tim", "pauline"},
        "accuse_unlocked": False,
        "topic_memory": {"topic": "Test conversation", "spoken": ["tim", "pauline"]}
    }
    
    print(f"📝 Test state: {json.dumps(test_state, default=str, indent=2)}")
    
    # Test 1: Save state
    print("\n💾 Testing state save...")
    save_success = game_state_manager.save_game_state(test_user_id, test_state)
    print(f"Save result: {'✅ Success' if save_success else '❌ Failed'}")
    
    # Test 2: Get state info
    print("\n📋 Testing state info retrieval...")
    state_info = game_state_manager.get_state_info(test_user_id)
    if state_info:
        print(f"State info: {json.dumps(state_info, default=str, indent=2)}")
    else:
        print("❌ No state info found")
    
    # Test 3: Load state
    print("\n📥 Testing state load...")
    loaded_state_data = game_state_manager.load_game_state(test_user_id)
    if loaded_state_data:
        print(f"Loaded state data: {json.dumps(loaded_state_data, default=str, indent=2)}")
        
        # Verify sets were restored correctly
        loaded_state = loaded_state_data.get("state", {})
        clues_examined = loaded_state.get("clues_examined", set())
        suspects_interrogated = loaded_state.get("suspects_interrogated", set())
        
        print(f"\n🔍 Verification:")
        print(f"Clues examined (should be set): {type(clues_examined)} - {clues_examined}")
        print(f"Suspects interviewed (should be set): {type(suspects_interrogated)} - {suspects_interrogated}")
        
        # Check if sets were restored correctly
        if isinstance(clues_examined, set) and isinstance(suspects_interrogated, set):
            print("✅ Sets restored correctly!")
        else:
            print("❌ Sets not restored correctly!")
    else:
        print("❌ Failed to load state")
    
    # Test 4: Delete state
    print("\n🗑️ Testing state deletion...")
    delete_success = game_state_manager.delete_game_state(test_user_id)
    print(f"Delete result: {'✅ Success' if delete_success else '❌ Failed'}")
    
    # Test 5: Verify deletion
    print("\n🔍 Verifying deletion...")
    final_state_info = game_state_manager.get_state_info(test_user_id)
    if not final_state_info:
        print("✅ State successfully deleted")
    else:
        print("❌ State still exists after deletion")
    
    print("\n🎯 Test completed!")

if __name__ == "__main__":
    test_game_state_manager()
