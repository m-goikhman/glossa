"""
Система предопределённых ответов для режиссёра на основе ключевых слов.
Позволяет быстро отвечать на стандартные вопросы без обращения к AI.
"""

import re
import json
import random
from typing import Dict, List, Optional, Any
from config import GAME_STATE

# Словарь ключевых слов для основных тем расследования
KEYWORD_PATTERNS = {
    "christmas_card": {
        "keywords": ["card", "christmas", "threat", "threatening", "pay up", "handwriting", "threatening card", "received"],
        "characters_priority": ["tim", "fiona"],  # who knows the most
        "response_strategy": "all",
        "response_templates": {
            "tim": {
                "action": "character_reply",
                "data": {
                    "character_key": "tim",
                    "trigger_message": "The detective is asking about the threatening Christmas card you received. Share your experience and emotional reaction to receiving it. After mentioning it initially, refer to it as 'the card', 'the threat', or 'it' - don't keep repeating 'Christmas card'."
                }
            },
            "fiona": {
                "action": "character_reply", 
                "data": {
                    "character_key": "fiona",
                    "trigger_message": "Tim just shared his experience with the threatening card. As someone who witnessed his reaction, add your perspective on how the threat affected him and what you observed about his emotional state. Use natural language - refer to it as 'the threat', 'the message', or 'it'."
                }
            }
        },
        "topic_name": "Christmas card threat"
    },
    
    "usb_drive": {
        "keywords": ["usb", "guitar", "blue", "device", "usb-drive", "guitar-shaped", "flash drive", "memory stick", "silicone", "silicon"],
        "characters_priority": ["pauline", "fiona"],
        "response_strategy": "all",
        "response_templates": {
            "pauline": {
                "action": "character_reply",
                "data": {
                    "character_key": "pauline", 
                    "trigger_message": "The detective is asking about the USB drive Alex asked you to retrieve. Share what you know about getting this device for him - avoid repeating descriptive phrases, just call it 'the drive' or 'the USB'."
                }
            },
            "fiona": {
                "action": "character_reply",
                "data": {
                    "character_key": "fiona",
                    "trigger_message": "Pauline just explained how she retrieved the USB drive for Alex. As his girlfriend, add your personal perspective about this device - why Alex considered it 'lucky' and how it relates to your relationship. Refer to it naturally as 'it', 'the device', or 'his drive' rather than repeating the full description."
                }
            }
        },
        "topic_name": "Blue guitar-shaped USB drive"
    },
    
    "alibi_845": {
        "keywords": ["alibi", "8:45", "845", "where were", "where was", "time", "8.45", "whereabouts", "what were you doing"],
        "characters_priority": ["tim", "fiona", "ronnie", "pauline"],  # all can respond
        "response_strategy": "all",
        "response_templates": {
            "tim": {
                "action": "character_reply",
                "data": {
                    "character_key": "tim",
                    "trigger_message": "The detective is asking for your alibi at 8:45 PM. Provide your cover story about where you were. Use natural language - after establishing the time, refer to it as 'then', 'at that time', etc."
                }
            },
            "fiona": {
                "action": "character_reply",
                "data": {
                    "character_key": "fiona", 
                    "trigger_message": "Tim just provided his whereabouts for that evening. Now share your own location at that time, and note any details that might corroborate or contradict what Tim said. Avoid repeating '8:45 PM' - use 'then', 'at that time', 'when it happened'."
                }
            },
            "ronnie": {
                "action": "character_reply",
                "data": {
                    "character_key": "ronnie",
                    "trigger_message": "Both Tim and Fiona have shared where they were that evening. Tell them your location at that crucial time, keeping in mind what the others have already revealed. Use varied language - 'then', 'at that moment', etc."
                }
            },
            "pauline": {
                "action": "character_reply", 
                "data": {
                    "character_key": "pauline",
                    "trigger_message": "After hearing the others' accounts of that evening, explain where you were since you weren't at the party. Consider how your whereabouts fit with the timeline others have established. Use natural language variations."
                }
            }
        },
        "topic_name": "Alibis for 8:45 PM"
    },
    
    "money_debt": {
        "keywords": ["money", "debt", "debts", "business", "financial", "loan", "owe", "owed"],
        "characters_priority": ["pauline", "ronnie"],
        "response_strategy": "all",
        "response_templates": {
            "pauline": {
                "action": "character_reply",
                "data": {
                    "character_key": "pauline",
                    "trigger_message": "The detective is asking about Alex's money and debts. As his secret business partner, share what you know about his financial situation."
                }
            },
            "ronnie": {
                "action": "character_reply",
                "data": {
                    "character_key": "ronnie", 
                    "trigger_message": "The detective is asking about money and debts. You lent money to Alex - share details about his financial troubles."
                }
            }
        },
        "topic_name": "Alex's debts and money troubles"
    },
    
    "arrival_time": {
        "keywords": ["arrived", "arrive", "arrival", "when did you", "what time", "how did you get", "come to", "came to", "get here", "get to alex", "transport", "transportation"],
        "characters_priority": ["tim", "fiona", "ronnie", "pauline"],
        "response_strategy": "ordered_sequence",
        "ordered_responses": [
            {
                "action": "character_reply",
                "data": {
                    "character_key": "ronnie",
                    "trigger_message": "The detective is asking about when and how you arrived at Alex's apartment. Share your arrival time and transportation method."
                }
            },
            {
                "action": "character_reply",
                "data": {
                    "character_key": "fiona", 
                    "trigger_message": "The detective is asking about when and how you arrived at Alex's apartment. As Alex's girlfriend, explain your arrival details."
                }
            },
            {
                "action": "character_reply",
                "data": {
                    "character_key": "tim",
                    "trigger_message": "The detective is asking about when and how you arrived at Alex's apartment. Give your cover story about your arrival time and transportation method."
                }
            },
            {
                "action": "character_reply", 
                "data": {
                    "character_key": "pauline",
                    "trigger_message": "The detective is asking about arrivals. Mention that you saw Tim's blue Honda when you arrived at Alex's apartment."
                }
            },
            {
                "action": "character_reply",
                "data": {
                    "character_key": "tim",
                    "trigger_message": "Pauline mentioned seeing your blue Honda. Deny that it was your car - insist that everyone is mistaken about the Honda."
                }
            },
            {
                "action": "character_reply",
                "data": {
                    "character_key": "fiona",
                    "trigger_message": "Tim is denying the Honda was his. Support Pauline's account - confirm that you also saw Tim's blue Honda at Alex's apartment."
                }
            },
            {
                "action": "character_reply",
                "data": {
                    "character_key": "ronnie",
                    "trigger_message": "Both Pauline and Fiona have confirmed seeing Tim's Honda. Express skepticism about Tim's denials - say it's unlikely that everyone would be mistaken about the same detail."
                }
            }
        ],
        "response_templates": {
            "tim": {
                "action": "character_reply",
                "data": {
                    "character_key": "tim",
                    "trigger_message": "The detective is asking about when and how you arrived at Alex's apartment. Give your cover story about your arrival time and transportation method."
                }
            },
            "fiona": {
                "action": "character_reply",
                "data": {
                    "character_key": "fiona", 
                    "trigger_message": "The detective is asking about when and how you arrived at Alex's apartment. As Alex's girlfriend, explain your arrival details."
                }
            },
            "ronnie": {
                "action": "character_reply",
                "data": {
                    "character_key": "ronnie",
                    "trigger_message": "The detective is asking about when and how you arrived at Alex's apartment. Share your arrival time and transportation method."
                }
            },
            "pauline": {
                "action": "character_reply", 
                "data": {
                    "character_key": "pauline",
                    "trigger_message": "The detective is asking about when and how you arrived at Alex's apartment. Explain your arrival details and why you came."
                }
            }
        },
        "topic_name": "Arrival times and transportation to Alex's apartment"
    }
}

def detect_topic_from_keywords(message: str) -> Optional[str]:

    message_lower = message.lower()
    
    # Проверяем каждую тему
    for topic_key, topic_data in KEYWORD_PATTERNS.items():
        keywords = topic_data["keywords"]
        
        # Ищем совпадения ключевых слов
        for keyword in keywords:
            if keyword.lower() in message_lower:
                return topic_key
    
    return None

def extract_character_from_message(message: str) -> Optional[str]:

    message_lower = message.lower()
    
    character_names = {
        "tim": ["tim"],
        "pauline": ["pauline"],
        "fiona": ["fiona"],
        "ronnie": ["ronnie"]
    }
    
    for char_key, names in character_names.items():
        for name in names:
            if name in message_lower:
                return char_key
    
    return None

def get_characters_who_can_respond(topic_key: str, topic_memory: Dict) -> List[str]:

    if topic_key not in KEYWORD_PATTERNS:
        return []
    
    topic_data = KEYWORD_PATTERNS[topic_key]
    priority_characters = topic_data["characters_priority"]
    spoken_characters = topic_memory.get("spoken", [])

    available_characters = [char for char in priority_characters if char not in spoken_characters]
    
    return available_characters

def _mark_predefined_as_used(user_id: int, topic_key: str):
    """
    Маркирует предопределённый ответ как использованный в состоянии игры.
    """
    from config import GAME_STATE
    
    if user_id in GAME_STATE:
        topic_memory = GAME_STATE[user_id].get("topic_memory", {})
        predefined_used = topic_memory.get("predefined_used", [])
        
        if topic_key not in predefined_used:
            predefined_used.append(topic_key)
            topic_memory["predefined_used"] = predefined_used
            GAME_STATE[user_id]["topic_memory"] = topic_memory
            print(f"DEBUG PREDEFINED: Marked topic '{topic_key}' as used for user {user_id}")

def create_predefined_response(topic_key: str, character_keys: List[str], topic_memory: Dict) -> Dict[str, Any]:
    """
    Создаёт предопределённый ответ-сцену для одного или нескольких персонажей.
    """
    if topic_key not in KEYWORD_PATTERNS:
        return {"scene": []}
    
    topic_data = KEYWORD_PATTERNS[topic_key]
    response_strategy = topic_data.get("response_strategy", "all")
    scene_actions = []
    
    # Special handling for ordered_sequence strategy
    if response_strategy == "ordered_sequence" and "ordered_responses" in topic_data:
        # Use the predefined sequence of responses
        scene_actions = topic_data["ordered_responses"].copy()
    else:
        # Use the regular response_templates approach
        for character_key in character_keys:
            if character_key in topic_data["response_templates"]:
                scene_actions.append(topic_data["response_templates"][character_key])
    
    if not scene_actions:
        return {"scene": []}
        
    topic_name = topic_data["topic_name"]
    
    return {
        "scene": scene_actions,
        "new_topic": topic_name
    }

def try_predefined_response(user_id: int, message: str, topic_memory: Dict) -> Optional[Dict[str, Any]]:
 
    # Определяем тему по ключевым словам
    detected_topic = detect_topic_from_keywords(message)
    print(f"DEBUG PREDEFINED: User {user_id}, message: '{message}' -> detected topic: {detected_topic}")
    
    if not detected_topic:
        print(f"DEBUG PREDEFINED: No topic detected for user {user_id}")
        return None
    
    # Проверяем, использовался ли уже predefined response для этой темы
    predefined_used = topic_memory.get("predefined_used", [])
    topic_data = KEYWORD_PATTERNS[detected_topic]
    topic_name = topic_data["topic_name"]
    
    if detected_topic in predefined_used:
        print(f"DEBUG PREDEFINED: Predefined response for topic '{detected_topic}' already used for user {user_id}, skipping")
        return None
    
    # Если тема изменилась, создаём чистую память для новой темы
    current_topic = topic_memory.get("topic", "None")
    
    if current_topic != topic_name:
        # Новая тема - сбрасываем список говоривших, но сохраняем predefined_used
        adjusted_topic_memory = {"topic": topic_name, "spoken": [], "predefined_used": predefined_used}
        print(f"DEBUG PREDEFINED: Topic changed from '{current_topic}' to '{topic_name}', resetting spoken list")
    else:
        adjusted_topic_memory = topic_memory
    
    # Check if this is an ordered_sequence strategy
    response_strategy = topic_data.get("response_strategy", "all")
    
    if response_strategy == "ordered_sequence":
        # For ordered sequence, check if the topic has already been discussed
        if current_topic == topic_name:
            # This ordered sequence has already been shown, let AI director decide
            print(f"DEBUG PREDEFINED: Ordered sequence for topic {detected_topic} already shown, letting director decide")
            return None
        else:
            # Show the full ordered sequence and mark as used
            result = create_predefined_response(detected_topic, [], adjusted_topic_memory)
            # Mark this predefined response as used
            _mark_predefined_as_used(user_id, detected_topic)
            print(f"DEBUG PREDEFINED: Final response for user {user_id}: {result}")
            return result
    
    # Regular logic for other strategies
    # Проверяем, есть ли конкретный персонаж в сообщении
    specific_character = extract_character_from_message(message)
    
    if specific_character:
        # Игрок обращается к конкретному персонажу
        if specific_character in KEYWORD_PATTERNS[detected_topic]["characters_priority"]:
            result = create_predefined_response(detected_topic, [specific_character], adjusted_topic_memory)
            # Mark this predefined response as used
            _mark_predefined_as_used(user_id, detected_topic)
            return result
    
    # Игрок задаёт общий вопрос - выбираем всех подходящих персонажей для ответа
    available_characters = get_characters_who_can_respond(detected_topic, adjusted_topic_memory)
    print(f"DEBUG PREDEFINED: Available characters for user {user_id}: {available_characters}")
    
    if not available_characters:
        # Все персонажи уже говорили на эту тему, но возможно игрок задает новый связанный вопрос
        # Позволяем режиссёру решить, стоит ли отвечать или действительно пора переходить к другой теме
        print(f"DEBUG PREDEFINED: All characters have spoken on topic {detected_topic}, letting director decide")
        return None
    
    # Выбираем персонажей для ответа в зависимости от стратегии
    print(f"DEBUG PREDEFINED: Using strategy '{response_strategy}' for topic '{detected_topic}'")
    
    if response_strategy == "all":
        chosen_characters = available_characters
        print(f"DEBUG PREDEFINED: Strategy 'all', chosen characters for user {user_id}: {chosen_characters}")
    else:  # "random_one"
        chosen_characters = [random.choice(available_characters)]
        print(f"DEBUG PREDEFINED: Strategy 'random_one', chosen character for user {user_id}: {chosen_characters[0]}")
    
    result = create_predefined_response(detected_topic, chosen_characters, adjusted_topic_memory)
    # Mark this predefined response as used
    _mark_predefined_as_used(user_id, detected_topic)
    print(f"DEBUG PREDEFINED: Final response for user {user_id}: {result}")
    return result
