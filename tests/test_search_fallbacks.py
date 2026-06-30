import os
import sys
from dotenv import load_dotenv

# Add parent directory to path so we can import discovery_engine
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discovery_engine

load_dotenv()

def test_serpapi():
    print("\n--- Testing SerpAPI ---")
    key = os.getenv("SERPAPI_KEY")
    print(f"SerpAPI Key configured: {'Yes (ends with ' + key[-6:] + ')' if key else 'No'}")
    if not key:
        print("Skipping SerpAPI test (no key configured).")
        return False
        
    results = discovery_engine.search_serpapi("IIT Bombay website", num_results=3)
    print(f"SerpAPI returned {len(results)} results:")
    for idx, r in enumerate(results):
        print(f"  {idx+1}. {r['title']} - {r['link']}")
    return len(results) > 0

def test_duckduckgo():
    print("\n--- Testing DuckDuckGo Lite ---")
    results = discovery_engine.search_duckduckgo("IIT Madras website", num_results=3)
    print(f"DuckDuckGo Lite returned {len(results)} results:")
    for idx, r in enumerate(results):
        print(f"  {idx+1}. {r['title']} - {r['link']}")
    return len(results) > 0

def test_unified_search_success():
    print("\n--- Testing Unified search_web (Normal) ---")
    results = discovery_engine.search_web("IIT Delhi website", num_results=3)
    print(f"search_web returned {len(results)} results.")
    return len(results) > 0

def test_fallback_flow():
    print("\n--- Testing Fallback Flow (Simulated Serper Failure) ---")
    # Temporarily corrupt Serper keys to force Serper to fail
    original_serper_key = os.environ.get("SERPER_API_KEY")
    os.environ["SERPER_API_KEY"] = "invalid_serper_key_12345"
    
    # Also corrupt any potential SERPER_API_KEY_i
    for i in range(1, 10):
        if f"SERPER_API_KEY_{i}" in os.environ:
            del os.environ[f"SERPER_API_KEY_{i}"]
            
    # Reset discovery engine's failing keys tracker
    discovery_engine._failing_serper_keys.clear()
    
    try:
        print("Executing search with invalid Serper keys...")
        results = discovery_engine.search_web("IIT Kharagpur website", num_results=3)
        print(f"Fallback search returned {len(results)} results.")
        return len(results) > 0
    finally:
        # Restore key
        if original_serper_key:
            os.environ["SERPER_API_KEY"] = original_serper_key

if __name__ == "__main__":
    print("Starting Web Search Fallbacks Verification Tests")
    
    serpapi_ok = test_serpapi()
    ddg_ok = test_duckduckgo()
    unified_ok = test_unified_search_success()
    fallback_ok = test_fallback_flow()
    
    print("\n=== Verification Summary ===")
    print(f"SerpAPI Test:      {'PASSED' if serpapi_ok else 'FAILED'}")
    print(f"DuckDuckGo Test:   {'PASSED' if ddg_ok else 'FAILED'}")
    print(f"Unified Search:    {'PASSED' if unified_ok else 'FAILED'}")
    print(f"Fallback Flow:     {'PASSED' if fallback_ok else 'FAILED'}")
    
    if ddg_ok and fallback_ok:
        print("\nALL CRITICAL TESTS PASSED!")
    else:
        print("\nSOME TESTS FAILED. Please review output logs.")
