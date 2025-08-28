import json
import re
from groq import Groq
from config import GROQ_API_KEY, user_histories
from utils import load_system_prompt, log_message, combine_character_prompt

# Initialize the Groq API client
client = Groq(api_key=GROQ_API_KEY)

# Telegram's message length limit
TELEGRAM_MAX_MESSAGE_LENGTH = 4096

def validate_ai_response(response: str, character_key: str = None) -> tuple[bool, str]:
    """
    Validates an AI response for corruption, excessive length, and other issues.
    Returns (is_valid, cleaned_response_or_fallback)
    """
    if not response or not response.strip():
        return False, "I'm not sure how to respond to that."
    
    response = response.strip()
    
    # Check for excessive length (Telegram limit and corruption indicator)
    if len(response) > TELEGRAM_MAX_MESSAGE_LENGTH:
        print(f"WARNING: AI response too long ({len(response)} chars), truncating")
        response = response[:TELEGRAM_MAX_MESSAGE_LENGTH-50] + "..."
        return True, response
    
    # Check for suspiciously long responses that might indicate corruption
    if len(response) > 2000:
        # For longer responses, do additional corruption checks
        char_variety = len(set(response.replace(' ', '').replace('\n', '').replace('\t', '')))
        if char_variety < 20:  # Very low character variety suggests repetition
            print(f"WARNING: Suspiciously long response with low character variety ({char_variety} unique chars)")
            return False, _get_fallback_response(character_key)
    
    # Check for corruption patterns
    corruption_patterns = [
        # Excessive repetition of random words
        r'\b(\w+)(\s+\1){10,}',  # Same word repeated 10+ times
        # Random code-like patterns
        r'(BuilderFactory|externalActionCode|RODUCTION|\.visitInsn){5,}',
        # Excessive dashes or special characters
        r'[-]{20,}',
        # Random programming terms repeated
        r'(PSI|MAV|Basel|Toastr|contaminants|roscope){5,}',
        # Excessive parentheses or brackets
        r'[\(\)\[\]]{10,}',
        # Excessive quotes (new pattern for the reported issue)
        r'["\'"]{15,}',  # 15+ consecutive quote characters
        # Repeated test/option strings (new pattern)
        r'(test){8,}',  # "test" repeated 8+ times
        r'(option){8,}',  # "option" repeated 8+ times
        # Comma-separated repeated words (new pattern)
        r'("[^"]*",\s*){20,}',  # 20+ comma-separated quoted items
        # Excessive commas
        r'[,]{10,}',  # 10+ consecutive commas
    ]
    
    for pattern in corruption_patterns:
        if re.search(pattern, response, re.IGNORECASE):
            print(f"WARNING: Corrupted AI response detected (pattern: {pattern[:20]}...)")
            print(f"Corrupted response preview: {response[:200]}...")
            return False, _get_fallback_response(character_key)
    
    # Check for excessive repetition of any phrase
    words = response.split()
    if len(words) > 50:  # Only check longer responses
        # Look for phrases repeated more than 5 times
        for i in range(len(words) - 2):
            phrase = ' '.join(words[i:i+3])
            if response.count(phrase) > 5:
                print(f"WARNING: Excessive phrase repetition detected: '{phrase}'")
                return False, _get_fallback_response(character_key)
    
    # Check for reasonable character-to-word ratio (detect gibberish)
    if len(words) > 10:
        avg_word_length = len(response.replace(' ', '')) / len(words)
        if avg_word_length > 15:  # Unusually long average word length
            print(f"WARNING: Suspicious word length pattern (avg: {avg_word_length})")
            return False, _get_fallback_response(character_key)
    
    # Check for incomplete or cut-off responses that might indicate corruption
    suspicious_endings = [
        'AssistantClass', '<|python_tag|>', '<|reserved_special_token_', '"}"}"}"}',
        'scalablytyped', 'надлеж', 'кто-то', '...",",",",",",",",",",",",",",",",",",",",'
    ]
    for ending in suspicious_endings:
        if ending.lower() in response.lower():
            print(f"WARNING: Suspicious token/pattern detected: '{ending[:20]}...'")
            return False, _get_fallback_response(character_key)
    
    return True, response

def _get_fallback_response(character_key: str = None) -> str:
    """Returns an appropriate fallback response for a character."""
    if character_key:
        from config import CHARACTER_DATA
        char_data = CHARACTER_DATA.get(character_key, {})
        char_name = char_data.get("full_name", character_key)
        
        # Special fallback for narrator
        if character_key == "narrator":
            return "We step aside to talk in private, away from the others."
        
        # Generic fallback for other characters
        return f"I need a moment to think about that properly."
    return "I'm having trouble processing that request right now."

def clear_user_conversation_history(user_id: int):
    """Clears conversation history for a user, useful when corruption is detected."""
    history_key = str(user_id)
    if history_key in user_histories:
        print(f"WARNING: Clearing conversation history for user {user_id} due to corruption")
        user_histories[history_key] = []
        log_message(user_id, "history_cleared", "Conversation history cleared due to AI corruption", None)



async def ask_for_dialogue(user_id: int, user_message: str, system_prompt: str, character_key: str = None) -> str:
    """The main function for all dialogue-based AI calls. Always expects and returns a simple string."""
    # Use shared conversation history so characters can see what others have said
    # but enhance the system prompt to clearly identify the speaking character
    history_key = str(user_id)
    
    if history_key not in user_histories:
        user_histories[history_key] = []
    
    # Enhance system prompt with character identity reminder
    if character_key:
        from config import CHARACTER_DATA  # Local import to avoid circular dependency
        char_data = CHARACTER_DATA.get(character_key, {})
        char_name = char_data.get("full_name", character_key)
        enhanced_system_prompt = f"{system_prompt}\n\nIMPORTANT: You are {char_name}. You must respond ONLY as {char_name}, speaking in first person about YOUR OWN experiences and observations. Do not speak for other characters or describe their actions."
    else:
        enhanced_system_prompt = system_prompt
    
    messages = [{"role": "system", "content": enhanced_system_prompt}]
    messages.extend(user_histories[history_key][-10:])
    messages.append({"role": "user", "content": user_message})
    
    try:
        chat_completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=messages, temperature=0.7)  # Reduced from 0.8 for more stability
        assistant_reply = chat_completion.choices[0].message.content
        
        if not assistant_reply or assistant_reply.strip() == "":
            print(f"WARNING: Empty response from AI for user {user_id}")
            return "I'm not sure how to respond to that."
        
        # Validate the AI response for corruption and excessive length
        is_valid, validated_response = validate_ai_response(assistant_reply, character_key)
        if not is_valid:
            print(f"WARNING: AI response validation failed for user {user_id}, using fallback")
            log_message(user_id, "ai_validation_failed", f"Original response preview: {assistant_reply[:200]}...", None)
            
            # Clear conversation history more aggressively when corruption is detected
            # Lowered threshold from 5000 to 2000 chars, and also clear on certain patterns
            should_clear_history = (
                len(assistant_reply) > 2000 or  # Long corrupted responses
                '"""""""' in assistant_reply or  # Quote repetition pattern
                'testtesttest' in assistant_reply or  # Test repetition pattern
                'optionoptionoption' in assistant_reply or  # Option repetition pattern
                assistant_reply.count(',') > 50  # Excessive commas
            )
            
            if should_clear_history:
                print(f"WARNING: Severe AI corruption detected for user {user_id}, clearing conversation history")
                clear_user_conversation_history(user_id)
            
            assistant_reply = validated_response
        else:
            assistant_reply = validated_response
        
        # Clean up any character name prefixes from the response
        if character_key:
            # Remove patterns like "tim: ", "fiona: ", "Tim Kane: ", etc.
            from config import CHARACTER_DATA  # Local import to avoid circular dependency
            char_data = CHARACTER_DATA.get(character_key, {})
            char_name = char_data.get("full_name", character_key)
            
            # Try to remove various patterns of character name prefixes
            patterns_to_remove = [
                f"[{character_key}]: ",
                f"[{character_key.lower()}]: ",
                f"[{character_key.upper()}]: ",
                f"[{char_name}]: ",
                f"{character_key}: ",
                f"{character_key.lower()}: ",
                f"{character_key.upper()}: ",
                f"{char_name}: ",
                f"*{char_name}:* ",
                f"**{char_name}:** ",
            ]
            
            for pattern in patterns_to_remove:
                if assistant_reply.startswith(pattern):
                    assistant_reply = assistant_reply[len(pattern):].strip()
                    break
        
        # Store the conversation with character identification
        if character_key:
            tagged_user_message = f"[Detective to {character_key}]: {user_message}"
            tagged_assistant_reply = f"[{character_key}]: {assistant_reply}"
        else:
            tagged_user_message = user_message
            tagged_assistant_reply = assistant_reply
            
        user_histories[history_key].extend([
            {"role": "user", "content": tagged_user_message}, 
            {"role": "assistant", "content": tagged_assistant_reply}
        ])
        if len(user_histories[history_key]) > 20: 
            user_histories[history_key] = user_histories[history_key][-20:]
        return assistant_reply
    except Exception as e:
        print(f"ERROR: Failed in ask_for_dialogue for user {user_id}: {e}")
        log_message(user_id, "dialogue_error", f"ask_for_dialogue failed: {e}", None)
        return "Sorry, a server error occurred."

async def ask_tutor_for_analysis(user_id: int, text_to_analyze: str) -> dict:
    """A special function that calls the Tutor for text analysis and expects a JSON response."""
    from config import CHARACTER_DATA # Local import to avoid circular dependency
    tutor_prompt = load_system_prompt(CHARACTER_DATA["tutor"]["prompt_file"])
    analysis_request = f"Analyze this text: '{text_to_analyze}'"
    messages = [{"role": "system", "content": tutor_prompt}, {"role": "user", "content": analysis_request}]
    try:
        chat_completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=messages, temperature=0.5)
        response_text = chat_completion.choices[0].message.content
        
        # Validate response for corruption
        is_valid, validated_response = validate_ai_response(response_text)
        if not is_valid:
            print(f"WARNING: Tutor analysis response validation failed for user {user_id}")
            log_message(user_id, "tutor_validation_failed", f"Corrupted tutor response: {response_text[:200]}...", None)
            return {"improvement_needed": False, "feedback": ""}
        
        return json.loads(validated_response)
    except (json.JSONDecodeError, Exception) as e:
        log_message(user_id, "tutor_error", f"Could not parse tutor analysis JSON: {e}", None)
        return {"improvement_needed": False, "feedback": ""}

async def ask_tutor_for_explanation(user_id: int, text_to_explain: str, original_message: str = "") -> dict:
    """A special function that calls the Tutor for an explanation and expects a JSON response."""
    from config import CHARACTER_DATA
    tutor_prompt = load_system_prompt(CHARACTER_DATA["tutor"]["prompt_file"])
    
    explanation_request = f"Please explain the meaning of: '{text_to_explain}'."
    if original_message:
        explanation_request += f" Original message: '{original_message}'"
        
    messages = [{"role": "system", "content": tutor_prompt}, {"role": "user", "content": explanation_request}]
    try:
        chat_completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=messages, temperature=0.5)
        response_text = chat_completion.choices[0].message.content
        
        # Validate response for corruption
        is_valid, validated_response = validate_ai_response(response_text)
        if not is_valid:
            print(f"WARNING: Tutor explanation response validation failed for user {user_id}")
            log_message(user_id, "tutor_validation_failed", f"Corrupted tutor response: {response_text[:200]}...", None)
            return {}
        
        return json.loads(validated_response)
    except (json.JSONDecodeError, Exception) as e:
        log_message(user_id, "tutor_error", f"Could not parse tutor explanation JSON: {e}", None)
        return {}

async def ask_tutor_for_final_summary(user_id: int, progress_data: dict) -> dict:
    """A special function that calls the Tutor for final learning summary and expects a JSON response."""
    from config import CHARACTER_DATA
    tutor_prompt = load_system_prompt(CHARACTER_DATA["tutor"]["prompt_file"])
    
    # Prepare summary of user's progress
    words_learned = progress_data.get("words_learned", [])
    writing_feedback = progress_data.get("writing_feedback", [])
    
    # Handle cases with no errors/words differently
    if not words_learned and not writing_feedback:
        summary_request = f"Generate final learning summary. User completed the game with no new words learned and no writing errors that needed correction. This means they played excellently! Please congratulate them and suggest they might be ready for a more challenging difficulty level."
    else:
        summary_request = f"Generate final learning summary. User learned {len(words_learned)} words"
        
        if words_learned:
            summary_request += f" (words: {', '.join([entry['query'] for entry in words_learned[:5]])}{'...' if len(words_learned) > 5 else ''})"
        
        if writing_feedback:
            summary_request += f" and received {len(writing_feedback)} pieces of feedback on their writing"
            # Add examples of common mistakes for analysis
            feedback_examples = [entry['feedback'] for entry in writing_feedback[:3]]
            if feedback_examples:
                summary_request += f". Recent feedback included: {'; '.join(feedback_examples)}"
        
        summary_request += ". Please provide a warm summary using the good-areas to improve-good structure."
    
    messages = [{"role": "system", "content": tutor_prompt}, {"role": "user", "content": summary_request}]
    try:
        chat_completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=messages, temperature=0.7)
        response_text = chat_completion.choices[0].message.content
        
        # Validate response for corruption
        is_valid, validated_response = validate_ai_response(response_text)
        if not is_valid:
            print(f"WARNING: Tutor final summary response validation failed for user {user_id}")
            log_message(user_id, "tutor_validation_failed", f"Corrupted tutor response: {response_text[:200]}...", None)
            return {"summary": "Great job completing the game! You showed curiosity and engagement with English. Keep practicing and you'll continue to improve!"}
        
        return json.loads(validated_response)
    except (json.JSONDecodeError, Exception) as e:
        log_message(user_id, "tutor_error", f"Could not parse tutor final summary JSON: {e}", None)
        return {"summary": "Great job completing the game! You showed curiosity and engagement with English. Keep practicing and you'll continue to improve!"}


async def ask_word_spotter(text_to_analyze: str) -> list:
    """Asks the Word Spotter AI to find difficult words in a text."""
    prompt = load_system_prompt("prompts/prompt_lexicographer.md")
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": text_to_analyze}]
    try:
        chat_completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=messages, temperature=0.2)
        response_text = chat_completion.choices[0].message.content
        
        # Validate response for corruption
        is_valid, validated_response = validate_ai_response(response_text)
        if not is_valid:
            print(f"WARNING: Word spotter response validation failed")
            print(f"Corrupted word spotter response: {response_text[:200]}...")
            return []
        
        words = json.loads(validated_response)
        return [word.lower() for word in words]
    except Exception as e:
        print(f"Error calling Word Spotter or parsing JSON: {e}"); return []

async def ask_director(user_id: int, context_text: str, message: str) -> dict:
    """Asks the Director LLM for the next scene and returns it as a dictionary."""
    from predefined_responses import try_predefined_response
    from config import GAME_STATE
    
    # First, try to get a predefined response based on keywords
    try:
        print(f"DEBUG: Checking predefined responses for user {user_id}, message: '{message}'")
        state = GAME_STATE.get(user_id, {})
        topic_memory = state.get("topic_memory", {"topic": "None", "spoken": []})
        print(f"DEBUG: Topic memory for user {user_id}: {topic_memory}")
        
        predefined_response = try_predefined_response(user_id, message, topic_memory)
        print(f"DEBUG: Predefined response result for user {user_id}: {predefined_response is not None}")
        
        if predefined_response:
            print(f"DEBUG: Using predefined response for user {user_id}: {predefined_response}")
            log_message(user_id, "director_predefined", f"Used predefined response for message: {message[:100]}", None)
            return predefined_response
        else:
            print(f"DEBUG: No predefined response found for user {user_id}, falling back to AI director")
    except Exception as e:
        print(f"WARNING: Failed to check predefined responses for user {user_id}: {e}")
        import traceback
        traceback.print_exc()
        # Continue to AI director as fallback
    
    # Fallback to AI Director
    director_prompt = load_system_prompt("prompts/prompt_director.md")
    full_context_for_director = f"Context: \"{context_text}\"\nMessage: \"{message}\""
    director_messages = [{"role": "system", "content": director_prompt}, {"role": "user", "content": full_context_for_director}]
    try:
        print(f"DEBUG: Calling director for user {user_id} with context: {context_text[:100]}...")
        chat_completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=director_messages, temperature=0.5)
        response_text = chat_completion.choices[0].message.content
        print(f"DEBUG: Director raw response for user {user_id}: {response_text[:200]}...")
        log_message(user_id, "director", response_text, None)
        
        # Validate response for corruption before parsing JSON
        is_valid, validated_response = validate_ai_response(response_text)
        if not is_valid:
            print(f"WARNING: Director response validation failed for user {user_id}")
            log_message(user_id, "director_validation_failed", f"Corrupted director response: {response_text[:200]}...", None)
            return {"scene": []}
        
        # Try to parse the JSON response
        try:
            director_decision = json.loads(validated_response)
            print(f"DEBUG: Director parsed JSON for user {user_id}: {director_decision}")
            
            # Validate the response structure
            if not isinstance(director_decision, dict):
                print(f"ERROR: Director returned non-dict response: {type(director_decision)}")
                return {"scene": []}
            
            if "scene" not in director_decision:
                print(f"ERROR: Director response missing 'scene' key: {director_decision}")
                return {"scene": []}
            
            if not isinstance(director_decision["scene"], list):
                print(f"ERROR: Director 'scene' is not a list: {type(director_decision['scene'])}")
                return {"scene": []}
            
            return director_decision
            
        except json.JSONDecodeError as json_error:
            print(f"ERROR: Failed to parse director JSON response: {json_error}")
            print(f"Director response text: {response_text}")
            log_message(user_id, "director_error", f"JSON parse error: {json_error}. Response: {response_text[:500]}", None)
            return {"scene": []}
            
    except Exception as e:
        print(f"ERROR: Failed to call director: {e}")
        log_message(user_id, "director_error", f"Director call failed: {e}", None)
        return {"scene": []}