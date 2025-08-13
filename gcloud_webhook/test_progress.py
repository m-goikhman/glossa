#!/usr/bin/env python3
"""
Test script for the ProgressManager to verify functionality.
Run this script to test the progress tracking system.
"""

import asyncio
from progress_manager import progress_manager

async def test_progress_manager():
    """Test the ProgressManager functionality."""
    print("🧪 Testing ProgressManager...")
    
    # Test user ID
    test_user_id = 999999999
    
    # Test 1: Add a word learned
    print("\n📚 Testing word learning...")
    word_success = progress_manager.add_word_learned(
        test_user_id, 
        "detective", 
        "A person who investigates crimes and mysteries"
    )
    print(f"Word learning result: {'✅ Success' if word_success else '❌ Failed'}")
    
    # Test 2: Add writing feedback
    print("\n✍️ Testing writing feedback...")
    feedback_success = progress_manager.add_writing_feedback(
        test_user_id,
        "I am detective",
        "I am a detective (add article 'a')"
    )
    print(f"Writing feedback result: {'✅ Success' if feedback_success else '❌ Failed'}")
    
    # Test 3: Get user progress
    print("\n📊 Testing progress retrieval...")
    progress_data = progress_manager.get_user_progress(test_user_id)
    print(f"Progress data: {progress_data}")
    
    # Test 4: Check if data was saved correctly
    if progress_data.get("words_learned"):
        print(f"✅ Words learned: {len(progress_data['words_learned'])} entries")
        for entry in progress_data["words_learned"]:
            print(f"  - {entry['query']}: {entry['feedback']}")
    else:
        print("❌ No words learned data found")
    
    if progress_data.get("writing_feedback"):
        print(f"✅ Writing feedback: {len(progress_data['writing_feedback'])} entries")
        for entry in progress_data["writing_feedback"]:
            print(f"  - '{entry['query']}' → '{entry['feedback']}'")
    else:
        print("❌ No writing feedback data found")
    
    # Test 5: Clear progress
    print("\n🗑️ Testing progress clearing...")
    clear_success = progress_manager.clear_user_progress(test_user_id)
    print(f"Clear result: {'✅ Success' if clear_success else '❌ Failed'}")
    
    # Test 6: Verify clearing
    print("\n🔍 Verifying progress clearing...")
    final_progress = progress_manager.get_user_progress(test_user_id)
    if not final_progress.get("words_learned") and not final_progress.get("writing_feedback"):
        print("✅ Progress successfully cleared")
    else:
        print("❌ Progress still exists after clearing")
    
    print("\n🎯 Progress test completed!")

if __name__ == "__main__":
    asyncio.run(test_progress_manager())

