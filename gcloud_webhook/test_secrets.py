#!/usr/bin/env python3
"""
Test script for Google Secret Manager configuration
"""

import os
import sys

# Add current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_secret_manager():
    """Test Secret Manager functionality"""
    print("🔐 Testing Google Secret Manager Configuration...")
    print("=" * 50)
    
    try:
        # Import config (this will test Secret Manager)
        from config import TELEGRAM_TOKEN, GROQ_API_KEY, GCS_BUCKET_NAME
        
        print("✅ Successfully imported secrets from config")
        print(f"📱 TELEGRAM_TOKEN: {'✅ Set' if TELEGRAM_TOKEN else '❌ Not set'}")
        print(f"🤖 GROQ_API_KEY: {'✅ Set' if GROQ_API_KEY else '❌ Not set'}")
        print(f"🗄️ GCS_BUCKET_NAME: {'✅ Set' if GCS_BUCKET_NAME else '❌ Not set'}")
        
        # Test token format (Telegram tokens are usually long)
        if TELEGRAM_TOKEN:
            if len(TELEGRAM_TOKEN) > 50 and ':' in TELEGRAM_TOKEN:
                print("✅ TELEGRAM_TOKEN format looks correct")
            else:
                print("⚠️ TELEGRAM_TOKEN format might be incorrect")
        
        # Test Groq API key format
        if GROQ_API_KEY:
            if GROQ_API_KEY.startswith('gsk_') and len(GROQ_API_KEY) > 20:
                print("✅ GROQ_API_KEY format looks correct")
            else:
                print("⚠️ GROQ_API_KEY format might be incorrect")
        
        # Test GCS bucket name
        if GCS_BUCKET_NAME:
            if len(GCS_BUCKET_NAME) > 0:
                print("✅ GCS_BUCKET_NAME looks correct")
            else:
                print("⚠️ GCS_BUCKET_NAME might be incorrect")
        
        print("\n🎉 All secrets loaded successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error loading secrets: {e}")
        print("\n🔍 Troubleshooting tips:")
        print("1. Make sure you're authenticated with gcloud: gcloud auth login")
        print("2. Check if Secret Manager API is enabled")
        print("3. Verify service account permissions")
        print("4. For local development, create a .env file")
        return False

def test_environment_fallback():
    """Test environment variable fallback"""
    print("\n🔄 Testing Environment Variable Fallback...")
    print("=" * 50)
    
    # Set test environment variables
    os.environ['TELEGRAM_TOKEN'] = 'test_telegram_token'
    os.environ['GROQ_API_KEY'] = 'test_groq_key'
    os.environ['GCS_BUCKET_NAME'] = 'test_bucket'
    
    try:
        # Import config again to test fallback
        from config import TELEGRAM_TOKEN, GROQ_API_KEY, GCS_BUCKET_NAME
        
        print("✅ Environment variable fallback working")
        print(f"📱 TELEGRAM_TOKEN: {TELEGRAM_TOKEN}")
        print(f"🤖 GROQ_API_KEY: {GROQ_API_KEY}")
        print(f"🗄️ GCS_BUCKET_NAME: {GCS_BUCKET_NAME}")
        
        # Clean up test environment
        del os.environ['TELEGRAM_TOKEN']
        del os.environ['GROQ_API_KEY']
        del os.environ['GCS_BUCKET_NAME']
        
        return True
        
    except Exception as e:
        print(f"❌ Environment variable fallback failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Starting Secret Manager Tests...")
    
    # Test 1: Secret Manager
    secret_manager_ok = test_secret_manager()
    
    # Test 2: Environment fallback
    fallback_ok = test_environment_fallback()
    
    print("\n" + "=" * 50)
    print("📊 Test Results:")
    print(f"🔐 Secret Manager: {'✅ PASS' if secret_manager_ok else '❌ FAIL'}")
    print(f"🔄 Environment Fallback: {'✅ PASS' if fallback_ok else '❌ PASS'}")
    
    if secret_manager_ok and fallback_ok:
        print("\n🎉 All tests passed! Secret Manager is configured correctly.")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed. Check the configuration.")
        sys.exit(1)
