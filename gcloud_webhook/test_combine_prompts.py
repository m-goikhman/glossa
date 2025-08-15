#!/usr/bin/env python3
"""
Test script for the combine_character_prompt function
"""

from utils import combine_character_prompt

def test_combine_prompts():
    """Test combining character prompts with B1 requirements"""
    
    # Test with different characters
    game_characters = ["narrator", "tim", "fiona", "pauline", "ronnie"]  # Should include B1
    non_game_characters = ["tutor"]  # Should NOT include B1
    
    print("Testing game characters (should include B1 requirements):")
    print("=" * 60)
    
    for char in game_characters:
        try:
            combined_prompt = combine_character_prompt(char)
            print(f"\n{char.title()}:")
            print(f"  Length: {len(combined_prompt)} characters")
            print(f"  Contains B1 requirements: {'Language Requirements' in combined_prompt}")
            print(f"  Contains character prompt: {char.title() in combined_prompt or 'You are' in combined_prompt}")
            
        except Exception as e:
            print(f"Error with {char}: {e}")
    
    print("\n" + "=" * 60)
    print("Testing non-game characters (should NOT include B1 requirements):")
    print("=" * 60)
    
    for char in non_game_characters:
        try:
            combined_prompt = combine_character_prompt(char)
            print(f"\n{char.title()}:")
            print(f"  Length: {len(combined_prompt)} characters")
            print(f"  Contains B1 requirements: {'Language Requirements' in combined_prompt}")
            print(f"  Contains character prompt: {char.title() in combined_prompt or 'You are' in combined_prompt}")
            
            # Show the end of the prompt to verify B1 requirements are NOT included
            print(f"  Last 100 characters:")
            print(f"  {combined_prompt[-100:]}")
            
        except Exception as e:
            print(f"Error with {char}: {e}")

if __name__ == "__main__":
    test_combine_prompts()
