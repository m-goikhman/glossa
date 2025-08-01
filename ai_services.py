import json
from groq import Groq
from config import GROQ_API_KEY, user_histories
from utils import load_system_prompt, log_message

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
        user_histories[user_id].extend([{"role": "user", "content": user_message}, {"role": "assistant", "content": assistant_reply}])
        if len(user_histories[user_id]) > 20: user_histories[user_id] = user_histories[user_id][-20:]
        return assistant_reply
    except Exception as e:
        print(f"Error in ask_for_dialogue: {e}"); return "Sorry, a server error occurred."

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
        log_message(user_id, "tutor_error", f"Could not parse tutor analysis JSON: {e}")
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
        log_message(user_id, "tutor_error", f"Could not parse tutor explanation JSON: {e}")
        return {}


async def ask_word_spotter(text_to_analyze: str) -> list:
    """Asks the Word Spotter AI to find difficult words in a text."""
    prompt = load_system_prompt("prompts/prompt_lexicographer.mdown")
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": text_to_analyze}]
    try:
        chat_completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=messages, temperature=0.2)
        response_text = chat_completion.choices[0].message.content
        return json.loads(response_text)
    except Exception as e:
        print(f"Error calling Word Spotter or parsing JSON: {e}"); return []

async def ask_director(user_id: int, context_text: str, message: str) -> dict:
    """Asks the Director LLM for the next scene and returns it as a dictionary."""
    director_prompt = load_system_prompt("prompts/prompt_director.mdown")
    full_context_for_director = f"Context: \"{context_text}\"\nMessage: \"{message}\""
    director_messages = [{"role": "system", "content": director_prompt}, {"role": "user", "content": full_context_for_director}]
    try:
        chat_completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=director_messages, temperature=0.5)
        response_text = chat_completion.choices[0].message.content
        log_message(user_id, "director", response_text)
        return json.loads(response_text)
    except Exception as e:
        print(f"Error calling director or parsing JSON: {e}"); return {"scene": []}