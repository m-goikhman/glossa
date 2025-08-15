import json
from groq import Groq
from config import GROQ_API_KEY, user_histories
from utils import load_system_prompt, log_message, combine_character_prompt

# Initialize the Groq API client
client = Groq(api_key=GROQ_API_KEY)



async def ask_for_dialogue(user_id: int, user_message: str, system_prompt: str) -> str:
    """The main function for all dialogue-based AI calls. Always expects and returns a simple string."""
    if user_id not in user_histories:
        user_histories[user_id] = []
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(user_histories[user_id][-10:])
    messages.append({"role": "user", "content": user_message})
    try:
        chat_completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=messages, temperature=0.8)
        assistant_reply = chat_completion.choices[0].message.content
        
        if not assistant_reply or assistant_reply.strip() == "":
            print(f"WARNING: Empty response from AI for user {user_id}")
            return "I'm not sure how to respond to that."
        
        user_histories[user_id].extend([{"role": "user", "content": user_message}, {"role": "assistant", "content": assistant_reply}])
        if len(user_histories[user_id]) > 20: user_histories[user_id] = user_histories[user_id][-20:]
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
        return json.loads(response_text)
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
        return json.loads(response_text)
    except (json.JSONDecodeError, Exception) as e:
        log_message(user_id, "tutor_error", f"Could not parse tutor explanation JSON: {e}", None)
        return {}


async def ask_word_spotter(text_to_analyze: str) -> list:
    """Asks the Word Spotter AI to find difficult words in a text."""
    prompt = load_system_prompt("prompts/prompt_lexicographer.md")
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": text_to_analyze}]
    try:
        chat_completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=messages, temperature=0.2)
        response_text = chat_completion.choices[0].message.content
        words = json.loads(response_text)
        return [word.lower() for word in words]
    except Exception as e:
        print(f"Error calling Word Spotter or parsing JSON: {e}"); return []

async def ask_director(user_id: int, context_text: str, message: str) -> dict:
    """Asks the Director LLM for the next scene and returns it as a dictionary."""
    director_prompt = load_system_prompt("prompts/prompt_director.md")
    full_context_for_director = f"Context: \"{context_text}\"\nMessage: \"{message}\""
    director_messages = [{"role": "system", "content": director_prompt}, {"role": "user", "content": full_context_for_director}]
    try:
        print(f"DEBUG: Calling director for user {user_id} with context: {context_text[:100]}...")
        chat_completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=director_messages, temperature=0.5)
        response_text = chat_completion.choices[0].message.content
        print(f"DEBUG: Director raw response for user {user_id}: {response_text[:200]}...")
        log_message(user_id, "director", response_text, None)
        
        # Try to parse the JSON response
        try:
            director_decision = json.loads(response_text)
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