"""
ai_extractor.py
Gemini Flash API integration for intelligent HTML → structured JSON contact extraction.
Supports automatic API key rotation and fallback to prevent quota exhaustion.
"""

import os
import json
import re
import time
import google.generativeai as genai
from dotenv import load_dotenv

# Load API keys from .env
load_dotenv()

# Rate limiting: Gemini free tier = 15 RPM
_last_call_time = 0
MIN_CALL_INTERVAL = 4.5  # seconds between calls (safe for 15 RPM)

# In-memory track of failing Gemini keys to avoid using them temporarily
_failing_gemini_keys = {}  # key -> timestamp of last failure

def get_gemini_keys():
    """Retrieves all available Gemini API keys from environment variables."""
    keys = []
    # 1. Check for single key or comma-separated list
    primary_key = os.getenv("GEMINI_API_KEY", "").strip()
    if primary_key:
        for k in primary_key.split(','):
            k_clean = k.strip()
            if k_clean and k_clean not in keys:
                keys.append(k_clean)
                
    # 2. Check for numbered keys: GEMINI_API_KEY_1, GEMINI_API_KEY_2, etc.
    for i in range(1, 10):
        key = os.getenv(f"GEMINI_API_KEY_{i}", "").strip()
        if key and key not in keys:
            keys.append(key)
            
    return keys

def get_active_gemini_key():
    """Selects an active Gemini API key, avoiding recently failed ones."""
    import random
    keys = get_gemini_keys()
    if not keys:
        return None
        
    now = time.time()
    # Filter keys that failed in the last 15 minutes (900 seconds)
    active_keys = [k for k in keys if now - _failing_gemini_keys.get(k, 0) > 900]
    
    if not active_keys:
        # Fall back to trying all keys anyway
        return random.choice(keys)
        
    return random.choice(active_keys)

def mark_gemini_key_failed(key):
    """Marks a Gemini API key as failing/exhausted."""
    _failing_gemini_keys[key] = time.time()
    print(f"[AI Extractor] Gemini API key ending in ...{key[-6:] if len(key) > 6 else key} marked as failed.")


def _rate_limit():
    """Enforces minimum interval between API calls to respect rate limits."""
    global _last_call_time
    now = time.time()
    elapsed = now - _last_call_time
    if elapsed < MIN_CALL_INTERVAL:
        time.sleep(MIN_CALL_INTERVAL - elapsed)
    _last_call_time = time.time()


def extract_contacts_with_ai(html_content, college_name, page_url, max_html_chars=15000, custom_directives=None):
    """
    Uses Gemini Flash to extract structured contact data from raw HTML.
    Supports key rotation on quota exhaustion. Upgraded to gemini-2.5-flash.
    """
    key = get_active_gemini_key()
    if not key:
        print("[AI Extractor] No Gemini API key configured. Skipping AI extraction.")
        return []
    
    # Clean HTML: remove scripts, styles, and excessive whitespace
    cleaned_html = _clean_html_for_llm(html_content)
    
    # Truncate if too long
    if len(cleaned_html) > max_html_chars:
        cleaned_html = cleaned_html[:max_html_chars] + "\n... [TRUNCATED]"
    
    # Skip nearly empty pages
    if len(cleaned_html.strip()) < 100:
        return []
    
    prompt = f"""You are an expert data extraction agent. Extract ALL contact information from this college website page.

College: {college_name}
Page URL: {page_url}

INSTRUCTIONS:
1. Extract EVERY person or office contact you can find
2. For each contact, provide a JSON object with these exact keys:
   - "person_name": Full name with title (Dr., Prof., Mr., Mrs., etc.) or fallback name, or "Office Contact" if no name. Make sure to extract the real person's name even if there is no title suffix/prefix.
   - "role": Their designation (Principal, HOD, Dean, TPO, Placement Officer, Faculty, Registrar, etc.)
   - "department": Department name if applicable, otherwise "Administration" or "General"
   - "email": Email address (null if not found)
   - "phone": Phone number(s) including STD codes (null if not found)  
   - "address": Office address if found (null if not found)"""

    if custom_directives:
        prompt += f"\n\nADDITIONAL USER EXTRACTION DIRECTIVES (CRITICAL): {custom_directives}\n"

    prompt += f"""
3. Do NOT invent or hallucinate any data — only extract what is explicitly present
4. If you find general college contact info (reception, enquiry desk), include those too
5. Ignore social media links, navigation menus, and unrelated content
6. Phone numbers should preserve their original format including country/STD codes

Return ONLY a valid JSON array. No markdown, no explanation, just the JSON array.
If no contacts are found, return an empty array: []

HTML CONTENT:
{cleaned_html}"""

    try:
        _rate_limit()
        
        # Configure with active key
        genai.configure(api_key=key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        
        try:
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,  # Low temperature for factual extraction
                    max_output_tokens=4096,
                )
            )
        except Exception as api_err:
            err_str = str(api_err).lower()
            if "429" in err_str or "quota" in err_str or "limit" in err_str:
                mark_gemini_key_failed(key)
                alt_key = get_active_gemini_key()
                if alt_key and alt_key != key:
                    print(f"[AI Extractor] Retrying Gemini extraction with alternative key...")
                    genai.configure(api_key=alt_key)
                    model = genai.GenerativeModel("gemini-2.5-flash")
                    response = model.generate_content(
                        prompt,
                        generation_config=genai.types.GenerationConfig(
                            temperature=0.1,
                            max_output_tokens=4096,
                        )
                    )
                else:
                    raise api_err
            else:
                raise api_err
        
        # Parse the response
        raw_text = response.text.strip()
        
        # Try to extract JSON from the response (handle markdown code blocks)
        contacts = _parse_json_response(raw_text)
        
        if not contacts:
            return []
        
        # Validate and normalize each contact
        validated_contacts = []
        for contact in contacts:
            if not isinstance(contact, dict):
                continue
                
            # Must have at least an email OR phone to be useful
            email = contact.get("email")
            phone = contact.get("phone")
            
            if not email and not phone:
                continue
            
            validated_contacts.append({
                "person_name": str(contact.get("person_name") or "Official Contact").strip(),
                "role": str(contact.get("role") or "Faculty/Staff").strip(),
                "department": str(contact.get("department") or "General").strip(),
                "email": str(email).strip() if email else "N/A",
                "phone": str(phone).strip() if phone else "N/A",
                "address": str(contact.get("address") or "N/A").strip(),
                "source_url": page_url,
                "college_name": college_name,
                "website_url": page_url,
                "extraction_method": "gemini_ai"
            })
        
        print(f"[AI Extractor] Extracted {len(validated_contacts)} contacts from {page_url}")
        return validated_contacts
        
    except Exception as e:
        print(f"[AI Extractor] Error during Gemini extraction for {page_url}: {e}")
        return []


def identify_college_from_html(html_content, url):
    """
    Uses Gemini to intelligently identify the college name from a webpage.
    Falls back to title/h1 parsing if AI fails. Upgraded to gemini-2.5-flash.
    """
    key = get_active_gemini_key()
    if not key:
        return _fallback_college_name(html_content, url)
    
    cleaned = _clean_html_for_llm(html_content)
    if len(cleaned) > 5000:
        cleaned = cleaned[:5000]
    
    prompt = f"""From this college website HTML, extract ONLY the full official name of the institution.
Return just the name as plain text, nothing else. No quotes, no explanation.
If you cannot determine the name, return "Unknown College".

URL: {url}

HTML:
{cleaned}"""
    
    try:
        _rate_limit()
        genai.configure(api_key=key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        
        try:
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.0,
                    max_output_tokens=100,
                )
            )
        except Exception as api_err:
            err_str = str(api_err).lower()
            if "429" in err_str or "quota" in err_str or "limit" in err_str:
                mark_gemini_key_failed(key)
                alt_key = get_active_gemini_key()
                if alt_key and alt_key != key:
                    print(f"[AI Extractor] Retrying name identification with alternative Gemini key...")
                    genai.configure(api_key=alt_key)
                    model = genai.GenerativeModel("gemini-2.5-flash")
                    response = model.generate_content(
                        prompt,
                        generation_config=genai.types.GenerationConfig(
                            temperature=0.0,
                            max_output_tokens=100,
                        )
                    )
                else:
                    raise api_err
            else:
                raise api_err
                
        name = response.text.strip().strip('"').strip("'")
        if name and len(name) > 3 and name != "Unknown College":
            return name
    except Exception as e:
        print(f"[AI Extractor] College name identification failed: {e}")
    
    return _fallback_college_name(html_content, url)



def _clean_html_for_llm(html_content):
    """Strips scripts, styles, and excessive tags to reduce token usage."""
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Remove non-content elements
    for tag in soup(["script", "style", "noscript", "iframe", "svg", "path", "meta", "link", "img"]):
        tag.decompose()
    
    # Get visible text with some structure preserved
    text = soup.get_text("\n", strip=True)
    
    # Collapse excessive whitespace/newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {3,}', ' ', text)
    
    return text


def _parse_json_response(raw_text):
    """Attempts to parse JSON from LLM response, handling markdown code blocks."""
    # Try direct parse first
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass
    
    # Try extracting from markdown code block
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw_text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1).strip())
        except json.JSONDecodeError:
            pass
    
    # Try finding array brackets
    bracket_match = re.search(r'\[.*\]', raw_text, re.DOTALL)
    if bracket_match:
        try:
            return json.loads(bracket_match.group(0))
        except json.JSONDecodeError:
            pass
    
    return []


def _fallback_college_name(html_content, url):
    """Extracts college name using simple heuristics when AI is unavailable."""
    from bs4 import BeautifulSoup
    from urllib.parse import urlparse
    
    soup = BeautifulSoup(html_content, "html.parser")
    
    title_tag = soup.find("title")
    if title_tag:
        title_text = title_tag.get_text().strip()
        for junk in ["Home -", "Welcome to", "| Home", "Official Website", "- Home"]:
            title_text = title_text.replace(junk, "").strip()
        if len(title_text) > 3:
            return title_text
    
    h1_tag = soup.find("h1")
    if h1_tag:
        h1_text = h1_tag.get_text().strip()
        if len(h1_text) > 3:
            return h1_text
    
    parsed = urlparse(url)
    return parsed.netloc.replace("www.", "")
