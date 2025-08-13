# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2025-08-13

### Added
- **Persistent Game State**: Automatic save/resume functionality using Google Cloud Storage
- **Secret Manager Integration**: Secure API key management via Google Secret Manager
- **Enhanced Commands**: Added `/restart` command for testing purposes
- **Privacy Protection**: Sanitized logging and PII protection
- **Performance Optimizations**: Lazy initialization and prompt caching
- **Comprehensive Logging**: Detailed logging for debugging and monitoring

### Changed
- **Architecture**: Migrated from local file storage to Google Cloud Storage
- **Configuration**: Replaced hardcoded secrets with Secret Manager integration
- **Error Handling**: Improved error handling for network and storage issues
- **Code Organization**: Better separation of concerns and modular design

### Fixed
- **Bucket Initialization**: Resolved GCS bucket creation issues
- **Startup Errors**: Fixed startup failures due to invalid bucket names
- **Secret Loading**: Added proper error handling for secret retrieval
- **Memory Management**: Improved memory usage with lazy initialization

### Security
- **API Key Security**: Moved from hardcoded secrets to secure storage
- **Logging Privacy**: Implemented PII sanitization and truncation
- **Access Control**: Proper IAM permissions for cloud resources

## [1.0.0] - 2025-08-06

### Added
- **Core Game Engine**: Interactive detective story with AI-powered characters
- **Multi-Role AI**: Seamless switching between suspects, narrator, and tutor
- **Language Learning**: Integrated English language tutoring system
- **Dynamic Scenarios**: AI-generated character interactions and responses
- **Progress Tracking**: Silent analysis of user language skills
- **Public/Private Modes**: Group and individual suspect interrogation

### Technical Features
- **Telegram Bot Integration**: Full webhook-based bot implementation
- **Groq API Integration**: AI model interactions for dialogue generation
- **Local File Storage**: Game state and progress persistence
- **Modular Architecture**: Extensible design for future enhancements

## [0.1.0] - 2025-08-01

### Added
- **Initial Project Setup**: Basic project structure and dependencies
- **Game Design**: Murder mystery scenario "The Chicago Formula"
- **Character Prompts**: AI system prompts for all game characters
- **Basic Bot Framework**: Foundation for Telegram bot integration

---

## Development Notes

This project was developed in close collaboration with an AI assistant using Google's Gemini Pro 2.5. The development process involved iterative design, testing, and refinement of both the game mechanics and technical architecture.

### Key Technical Decisions
- **Google Cloud Platform**: Chosen for scalability and security
- **Secret Manager**: Selected for secure credential management
- **Cloud Storage**: Used for persistent data storage
- **App Engine**: Deployed for reliable hosting and scaling

### Future Roadmap
- **Multi-language Support**: Expand beyond English language learning
- **Additional Scenarios**: More detective stories and scenarios
- **Advanced AI Features**: Enhanced character interactions and responses
- **Analytics Dashboard**: Detailed learning progress analytics
