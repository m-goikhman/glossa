# Changelog

## [Unreleased] - Two-Attempt Accusation System

### Added
- **Two-Attempt Accusation System**: Players now have 2 attempts to identify the correct suspect
- **Early Accusation Access**: "Make an Accusation" button is now available in the main menu from the start
- **Smart Accusation Warning**: When players try to accuse before gathering all evidence, they get a warning with options to:
  - Proceed anyway with the accusation
  - Return to investigation to gather more evidence
- **Dynamic Warning Messages**: The warning shows exactly what evidence/interviews are still missing
- **Defense Responses**: When players make incorrect accusations, suspects defend themselves with alibis:
  - `defense_fiona.txt` - Fiona's defense emphasizing she called 911 to save Alex
  - `defense_pauline.txt` - Pauline's defense about driving Alex and finding him
  - `defense_ronnie.txt` - Ronnie's defense about arriving last and his Tesla vs Honda
- **Interactive Reveal System**: After failing both attempts, players can choose to learn the truth:
  - Separate reveal files: `reveal_1_truth.txt`, `reveal_2_killer.txt`, `reveal_3_evidence.txt`, `reveal_4_timeline.txt`, `reveal_5_motive.txt`
  - Step-by-step revelation with interactive buttons
  - Progressive disclosure: truth → evidence → timeline → motive
  - Reliable file-based system (replaced complex parsing)
- **Accusation Attempt Tracking**: Added `accusation_attempts` field to game state
- **Enhanced Accusation Flow**: After wrong accusation, players can choose to:
  - Make Another Accusation (if attempts < 2)
  - Continue Investigation (return to main menu)

### Changed
- **Simplified Accusation Flow**: Removed requirement for players to explain their accusation - now works instantly
- **Accusation Interface**: Updated accusation prompt to show attempt number (e.g., "Attempt 2/2")
- **Accusation Unlock Text**: Updated `accuse_unlocked.txt` to explain the two-attempt system
- **Game Over Flow**: Updated `outro_lose.txt` to offer choice between reveal and restart
- **Enhanced Game Logic**: Replaced `handle_accusation()` with `handle_accusation_direct()` for immediate processing
- **Accusation Accessibility**: Accusation button is now always visible in main menu (removed `accuse_unlocked` requirement)

### Technical Details
- Players get exactly 2 attempts to identify Tim Kane as the attacker
- **Instant Processing**: Accusations are processed immediately without asking for explanations
- First wrong accusation shows character defense and offers second chance
- Second wrong accusation shows character defense, then game over (no buttons)
- **Defense Always First**: Both wrong attempts show character defense before any other messages
- Correct accusation on any attempt results in victory
- Attempt counter persists through game state saves/loads
- Removed `waiting_for_accusation_reason` state - no longer needed
- **Reliable Reveal System**: Replaced parsing logic with individual text files for each revelation step
- **Fixed Game State**: Reveal actions are now properly allowed after game completion

### Game Flow
1. **Early Access**: Player can access accusations immediately from main menu
2. **Smart Warning**: If not all evidence gathered, show warning with option to proceed or investigate more
3. **Ready to Accuse**: If all evidence examined and suspects interviewed, proceed directly to accusation menu
4. **Accusation Processing**: Player selects suspect - accusation is processed instantly
5. **Wrong Accusation (first attempt)**: Show defense + options for second attempt or investigation
6. **Wrong Accusation (second attempt)**: Show defense → offer reveal or restart choice
7. **Reveal Option**: Progressive story revelation with interactive buttons
8. **Victory**: Correct accusation on any attempt results in victory