"""
discovery_engine.py
Multi-source college discovery engine.
Supports 3 input modes:
1. Region/State search → finds ALL colleges in a region via Serper + NAAC
2. College name search → finds specific colleges by name via Serper
3. URL list → directly processes given URLs

Uses Serper API for web search and Gemini AI for intelligent extraction.
"""

import os
import re
import time
import json
import threading
import requests
from urllib.parse import urlparse
from dotenv import load_dotenv
from bs4 import BeautifulSoup

import ai_extractor
import scraper
import database

load_dotenv()

SERPER_ENDPOINT = "https://google.serper.dev/search"

BLACK_LISTED_DOMAINS = [
    "shiksha.com", "collegedunia.com", "careers360.com", "getmyuni.com",
    "targetadmission.com", "jagranjosh.com", "indiaix.com", "uniapply.com",
    "sarvgyan.com", "collegedekho.com", "university-directory.org", "indcareer.com",
    "admission24.com", "sulekha.com", "yellowpages.com", "justdial.com",
    "facebook.com", "linkedin.com", "twitter.com", "instagram.com", "youtube.com",
    "wikipedia.org", "indiatoday.in", "collegesearch.in", "vidyavision.com",
    "entrancecorner.com", "mhrd.gov.in", "education.gov.in"
]

# In-memory store for discovery job progress
discovery_jobs = {}

# In-memory track of failing Serper keys to avoid using them temporarily
_failing_serper_keys = {}  # key -> timestamp of last failure

def get_serper_keys():
    """Retrieves all available Serper API keys from environment variables."""
    keys = []
    # 1. Check for single key or comma-separated list
    primary_key = os.getenv("SERPER_API_KEY", "").strip()
    if primary_key:
        for k in primary_key.split(','):
            k_clean = k.strip()
            if k_clean and k_clean not in keys:
                keys.append(k_clean)
                
    # 2. Check for numbered keys: SERPER_API_KEY_1, SERPER_API_KEY_2, etc.
    for i in range(1, 10):
        key = os.getenv(f"SERPER_API_KEY_{i}", "").strip()
        if key and key not in keys:
            keys.append(key)
            
    return keys

def get_active_serper_key():
    """Selects an active Serper API key, avoiding recently failed ones if possible."""
    import random
    keys = get_serper_keys()
    if not keys:
        return None
        
    now = time.time()
    # Filter out keys that failed in the last 15 minutes (900 seconds)
    active_keys = [k for k in keys if now - _failing_serper_keys.get(k, 0) > 900]
    
    if not active_keys:
        # If all keys have failed, fall back to trying all keys anyway
        return random.choice(keys)
        
    return random.choice(active_keys)

def mark_serper_key_failed(key):
    """Marks a Serper API key as failing/exhausted."""
    _failing_serper_keys[key] = time.time()
    print(f"[Discovery] Serper API key ending in ...{key[-6:] if len(key) > 6 else key} marked as failed.")

def search_serper(query, num_results=10):
    """
    Performs a Google search via Serper API with automatic key rotation and credit balancing.
    
    Args:
        query: Search query string
        num_results: Number of results to return (max 100)
    
    Returns:
        List of dicts with 'title', 'link', 'snippet' keys
    """
    key = get_active_serper_key()
    if not key:
        print("[Discovery] No Serper API key configured.")
        return []
    
    headers = {
        "X-API-KEY": key,
        "Content-Type": "application/json"
    }
    
    payload = {
        "q": query,
        "num": min(num_results, 100),
        "gl": "in",  # India-specific results
        "hl": "en"
    }
    
    try:
        response = requests.post(SERPER_ENDPOINT, json=payload, headers=headers, timeout=15)
        
        # If key is exhausted (403/429), mark it as failed and retry once with another key
        if response.status_code in [403, 429]:
            mark_serper_key_failed(key)
            alt_key = get_active_serper_key()
            if alt_key and alt_key != key:
                print(f"[Discovery] Retrying search with alternative Serper key...")
                headers["X-API-KEY"] = alt_key
                response = requests.post(SERPER_ENDPOINT, json=payload, headers=headers, timeout=15)
                
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get("organic", []):
            results.append({
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", "")
            })
        
        return results
        
    except Exception as e:
        print(f"[Discovery] Serper search failed for '{query}': {e}")
        mark_serper_key_failed(key)
        return []

def search_serpapi(query, num_results=10):
    """
    Performs a Google search via SerpAPI.
    """
    serpapi_key = os.getenv("SERPAPI_KEY", "").strip()
    if not serpapi_key:
        print("[Discovery] No SerpAPI key configured.")
        return []
        
    params = {
        "engine": "google",
        "q": query,
        "api_key": serpapi_key,
        "num": min(num_results, 100),
        "gl": "in",  # India-specific results
        "hl": "en"
    }
    
    try:
        response = requests.get("https://serpapi.com/search", params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get("organic_results", []):
            results.append({
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", "")
            })
        return results
    except Exception as e:
        print(f"[Discovery] SerpAPI search failed for '{query}': {e}")
        return []

def search_duckduckgo(query, num_results=10):
    """
    Fallback web search using DuckDuckGo Lite HTML scraping (requires no API keys).
    """
    url = "https://lite.duckduckgo.com/lite/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    try:
        response = requests.post(url, data={"q": query}, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        
        results = []
        import urllib.parse
        for a in soup.find_all("a", class_="result-link"):
            link = a.get("href", "")
            if "uddg=" in link:
                parsed = urllib.parse.urlparse(link)
                query_params = urllib.parse.parse_qs(parsed.query)
                if "uddg" in query_params:
                    link = query_params["uddg"][0]
            elif link.startswith("/lite_dir/"):
                continue
                
            title = a.get_text(strip=True)
            snippet = ""
            tr = a.parent.parent  # td -> tr
            if tr:
                next_tr = tr.find_next_sibling("tr")
                if next_tr:
                    snippet_td = next_tr.find("td", class_="result-snippet")
                    if snippet_td:
                        snippet = snippet_td.get_text(strip=True)
            
            results.append({
                "title": title,
                "link": link,
                "snippet": snippet
            })
            if len(results) >= num_results:
                break
        return results
    except Exception as e:
        print(f"[Discovery] DuckDuckGo search failed for '{query}': {e}")
        return []

def search_web(query, num_results=10):
    """
    Performs web search across multiple providers with fallbacks.
    1. Serper API
    2. SerpAPI
    3. DuckDuckGo Lite (No key scraping fallback)
    """
    print(f"[Search] Executing search query: '{query}'")
    
    # 1. Try Serper
    results = search_serper(query, num_results)
    if results:
        print(f"[Search] Serper API successfully returned {len(results)} results.")
        return results
        
    # 2. Try SerpAPI
    serpapi_key = os.getenv("SERPAPI_KEY", "").strip()
    if serpapi_key:
        print("[Search] Serper API failed or returned empty results. Falling back to SerpAPI...")
        results = search_serpapi(query, num_results)
        if results:
            print(f"[Search] SerpAPI successfully returned {len(results)} results.")
            return results
            
    # 3. Try DuckDuckGo Lite
    print("[Search] API keys failed or returned empty results. Falling back to DuckDuckGo Lite...")
    results = search_duckduckgo(query, num_results)
    if results:
        print(f"[Search] DuckDuckGo Lite successfully returned {len(results)} results.")
        return results
        
    print("[Search] All search providers failed or returned no results.")
    return []

def fuzzy_match_score(name1, name2):
    """Computes a simple token-set similarity ratio between two names."""
    words1 = set(re.findall(r'\w+', name1.lower()))
    words2 = set(re.findall(r'\w+', name2.lower()))
    # Ignore common filler words
    fillers = {"college", "university", "institute", "of", "and", "technology", "science", "arts", "engineering", "management"}
    w1 = words1 - fillers
    w2 = words2 - fillers
    if not w1 or not w2:
        return 0.0
    intersection = w1.intersection(w2)
    union = w1.union(w2)
    return len(intersection) / len(union)

def classify_college_type(college_name, url):
    """
    Intelligently classifies a college as:
    - Government
    - Private
    - Autonomous
    - Deemed
    Based on keywords in name, domain, or default.
    """
    name_lower = college_name.lower()
    url_lower = url.lower()
    
    # Government indicators
    gov_keywords = [
        "government", "govt", "state", "national", "indian institute of", "iit", "nit", "iiit",
        "constituent", "municipal", "university department", "central university"
    ]
    if any(kw in name_lower for kw in gov_keywords) or ".gov.in" in url_lower or ".nic.in" in url_lower:
        return "Government"
        
    # Autonomous indicators
    auto_keywords = ["autonomous", "auto"]
    if any(kw in name_lower for kw in auto_keywords):
        return "Autonomous"
        
    # Deemed indicators
    deemed_keywords = ["deemed", "deemed university", "deemed-to-be"]
    if any(kw in name_lower for kw in deemed_keywords):
        return "Deemed"
        
    # Default private or general college
    private_keywords = ["private", "self-financing", "trust", "society", "foundation"]
    if any(kw in name_lower for kw in private_keywords):
        return "Private"
        
    return "Private" # Default fallback

def find_college_website(college_name):
    """
    Given a college name, searches for its official website.
    Verifies match using fuzzy scoring and blacklisted domains.
    Returns:
        dict with 'name', 'url', 'source', 'college_type' keys, or None if not found
    """
    query = f'"{college_name}" official website contact'
    results = search_web(query, num_results=5)
    
    if not results:
        results = search_web(f"{college_name} college website", num_results=5)
    
    if not results:
        return None
    
    best_result = None
    best_score = -1
    
    edu_domains = ['.edu', '.ac.in', '.edu.in', '.org.in', '.nic.in', '.gov.in']
    
    for result in results:
        url = result["link"]
        domain = urlparse(url).netloc.lower()
        title = result["title"].lower()
        score = 0
        
        # Prefer educational domains
        for ed in edu_domains:
            if ed in domain:
                score += 30
                break
        
        # Penalize aggregator/listing sites
        if any(agg in domain for agg in BLACK_LISTED_DOMAINS):
            score -= 60
        
        # Bonus if college name words appear in domain
        name_words = college_name.lower().split()
        for word in name_words:
            if len(word) > 3 and word in domain:
                score += 10
        
        # Bonus if title contains the college name
        if college_name.lower() in title:
            score += 15
            
        # Match verification using fuzzy name token matching
        f_score = fuzzy_match_score(college_name, result["title"])
        score += int(f_score * 40)
        
        if score > best_score:
            best_score = score
            best_result = result
            
    # Verify that the domain score is positive and name fuzzy score is acceptable
    if best_result and best_score > 10:
        # Check against blacklist again
        domain = urlparse(best_result["link"]).netloc.lower()
        if not any(agg in domain for agg in BLACK_LISTED_DOMAINS):
            return {
                "name": college_name,
                "url": best_result["link"],
                "source": "serper_search",
                "college_type": classify_college_type(college_name, best_result["link"])
            }
    
    # Fallback: use the first non-aggregator result
    for result in results:
        domain = urlparse(result["link"]).netloc.lower()
        if not any(agg in domain for agg in BLACK_LISTED_DOMAINS):
            f_score = fuzzy_match_score(college_name, result["title"])
            if f_score > 0.2:  # Safe minimum threshold
                return {
                    "name": college_name,
                    "url": result["link"],
                    "source": "serper_search",
                    "college_type": classify_college_type(college_name, result["link"])
                }
    
    return None


def discover_colleges_by_region(region, institution_type="all"):
    """
    Discovers all colleges in a region using multiple search queries.
    Returns:
        List of dicts with 'name', 'url', 'source', 'college_type' keys
    """
    colleges = []
    seen_domains = set()
    
    type_filter = ""
    if institution_type == "engineering":
        type_filter = "engineering college"
    elif institution_type == "medical":
        type_filter = "medical college"
    elif institution_type == "arts":
        type_filter = "arts and science college"
    elif institution_type == "science":
        type_filter = "science college"
    else:
        type_filter = "college"
    
    queries = [
        f"list of {type_filter}s in {region} official website",
        f"NAAC accredited {type_filter}s in {region}",
        f"{type_filter}s in {region} contact email",
        f"top {type_filter}s in {region} website",
        f"government {type_filter}s in {region}",
        f"private {type_filter}s in {region} official site",
        f"all {type_filter}s in {region} list",
        f"university in {region} departments contact",
    ]
    
    for query in queries:
        results = search_web(query, num_results=20)
        time.sleep(0.5)
        
        for result in results:
            url = result["link"]
            domain = urlparse(url).netloc.lower()
            
            if any(agg in domain for agg in BLACK_LISTED_DOMAINS):
                continue
            
            base_domain = '.'.join(domain.split('.')[-2:])
            if base_domain in seen_domains:
                continue
            seen_domains.add(base_domain)
            
            edu_indicators = ['.edu', '.ac.in', '.edu.in', '.org.in', '.nic.in',
                            'college', 'university', 'institute', 'polytechnic']
            title_lower = result["title"].lower()
            
            is_edu = any(ind in domain or ind in title_lower for ind in edu_indicators)
            
            if is_edu:
                name = result["title"].strip()
                for suffix in [" - Home", " | Home", " Official Website", " - Official", " | Official"]:
                    name = name.replace(suffix, "").strip()
                
                colleges.append({
                    "name": name,
                    "url": url,
                    "source": "region_search",
                    "college_type": classify_college_type(name, url)
                })
    
    print(f"[Discovery] Found {len(colleges)} colleges in {region}")
    return colleges


def score_page_url(page_url):
    """
    Scores a URL based on keywords to prioritize scanning of actual faculty and department pages.
    """
    url_lower = page_url.lower()
    score = 0
    
    # Highest priority: faculty rosters, staff directories, contact cards
    high_keywords = ["faculty", "staff", "people", "directory", "contact", "tpo", "placement", "principal", "hod", "members", "personnel", "about", "office"]
    # Department pages
    dept_keywords = ["cse", "ece", "eee", "mech", "civil", "mba", "mca", "it-dept", "computer-science", "information-technology", "engineering", "sciences", "humanities", "department", "academic"]
    
    for k in high_keywords:
        if k in url_lower:
            score += 100
            
    for k in dept_keywords:
        if k in url_lower:
            score += 80
            
    return score


def scrape_college_with_ai(college_info, job_id=None, session_id=None, custom_directives=None):
    """
    Full pipeline: fetches a college website and uses Gemini AI to extract contacts.
    Scopes contacts to user session_id.
    """
    url = college_info["url"]
    name = college_info.get("name", "Unknown College")
    college_type = college_info.get("college_type") or classify_college_type(name, url)
    
    result = {
        "college_name": name,
        "url": url,
        "contacts": [],
        "status": "processing"
    }
    
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        
        # Step 1: Fetch homepage
        html, final_url = scraper.fetch_page(url)
        if not html:
            result["status"] = "failed"
            result["error"] = "Could not reach website"
            return result
        
        # Step 2: Identify college name from homepage if generic
        if name in ["Unknown College", ""] or len(name) < 4:
            name = ai_extractor.identify_college_from_html(html, url)
            result["college_name"] = name
        
        # Step 3: Discover relevant internal pages recursively (depth 2)
        discovered_pages = set()
        queue = [(url, 0)]
        visited_discovery = set()
        
        # Max pages to crawl during discovery
        MAX_DISCOVERY_CRAWL = 15
        
        print(f"[Discovery AI] Starting depth-2 discovery crawl for: {url}...")
        while queue and len(visited_discovery) < MAX_DISCOVERY_CRAWL:
            curr_url, depth = queue.pop(0)
            if curr_url in visited_discovery:
                continue
            visited_discovery.add(curr_url)
            
            if curr_url == url:
                curr_html = html
            else:
                curr_html, _ = scraper.fetch_page(curr_url)
                
            if not curr_html:
                continue
                
            links = scraper.find_relevant_pages(curr_url, curr_html)
            for link in links:
                if link not in visited_discovery:
                    discovered_pages.add(link)
                    if depth < 1:  # Add to queue only if current page is depth 0 (homepage)
                        if link not in [q[0] for q in queue]:
                            queue.append((link, depth + 1))
                            
        # Clean and prioritize
        clean_homepage_url = scraper.clean_url(url)
        discovered_pages.discard(clean_homepage_url)
        discovered_pages.discard(url)
        
        sorted_pages = sorted(list(discovered_pages), key=score_page_url, reverse=True)
        
        # Take homepage + top 12 prioritized pages
        pages_to_process = [url] + sorted_pages[:12]
        print(f"[Discovery AI] Selected {len(pages_to_process)} pages for AI extraction (Discovered {len(discovered_pages)}).")
        
        # Step 4: Extract contacts from each page using AI
        all_contacts = []
        seen_emails = set()
        
        for page_url in pages_to_process:
            page_html, _ = scraper.fetch_page(page_url)
            if not page_html:
                continue
            
            # Use Gemini AI for extraction with custom directives
            contacts = ai_extractor.extract_contacts_with_ai(
                page_html, name, page_url, custom_directives=custom_directives
            )
            
            for contact in contacts:
                email_key = contact.get("email", "").lower()
                if email_key and email_key != "n/a" and email_key not in seen_emails:
                    seen_emails.add(email_key)
                    contact["college_name"] = name
                    contact["website_url"] = url
                    contact["session_id"] = session_id
                    contact["college_type"] = college_type
                    contact["custom_notes"] = custom_directives or "General Search"
                    all_contacts.append(contact)
            
            time.sleep(0.5)
        
        # If AI found nothing, fall back to regex scraper
        if not all_contacts:
            fallback_contacts = scraper.scrape_college_website(url)
            if fallback_contacts:
                all_contacts = fallback_contacts
                for c in all_contacts:
                    c["extraction_method"] = "regex_fallback"
                    c["session_id"] = session_id
                    c["college_type"] = college_type
                    c["custom_notes"] = custom_directives or "Regex Fallback"
        
        result["contacts"] = all_contacts
        result["status"] = "success" if all_contacts else "warning"
        result["count"] = len(all_contacts)
        
    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
        print(f"[Discovery] Error processing {url}: {e}")
    
    return result


def run_discovery_job(job_id, mode, input_data, institution_type="all", session_id=None, custom_directives=None):
    """
    Background worker for discovery jobs. Uses ThreadPoolExecutor for concurrent scraping.
    """
    job = discovery_jobs.get(job_id)
    if not job:
        return
    
    try:
        colleges_to_process = []
        
        # Phase 1: Discovery
        job["phase"] = "discovery"
        job["phase_label"] = "Discovering colleges..."
        
        if mode == "region":
            job["phase_label"] = f"Searching for colleges in {input_data}..."
            colleges_to_process = discover_colleges_by_region(input_data, institution_type)
            job["discovered_count"] = len(colleges_to_process)
            
        elif mode == "names":
            job["phase_label"] = f"Finding websites for {len(input_data)} college(s)..."
            for i, name in enumerate(input_data):
                name = name.strip()
                if not name:
                    continue
                job["current_item"] = f"Searching: {name}"
                result = find_college_website(name)
                if result:
                    colleges_to_process.append(result)
                else:
                    job["completed_colleges"].append({
                        "college_name": name,
                        "url": "",
                        "status": "not_found",
                        "count": 0,
                        "error": "Could not find official website"
                    })
                time.sleep(0.3)
            job["discovered_count"] = len(colleges_to_process)
            
        elif mode == "urls":
            for url in input_data:
                url = url.strip()
                if url:
                    colleges_to_process.append({
                        "name": "Unknown College",
                        "url": url,
                        "source": "direct_url",
                        "college_type": classify_college_type("Unknown College", url)
                    })
            job["discovered_count"] = len(colleges_to_process)
        
        # Phase 2: AI Extraction (Concurrent)
        job["phase"] = "extraction"
        job["total"] = len(colleges_to_process)
        job["phase_label"] = f"Extracting contacts from {len(colleges_to_process)} colleges concurrently using AI..."
        
        from concurrent.futures import ThreadPoolExecutor
        import threading
        
        progress_lock = threading.Lock()
        completed_count = 0
        
        def process_college_thread(college):
            nonlocal completed_count
            try:
                # Ensure type is set
                if "college_type" not in college:
                    college["college_type"] = classify_college_type(college["name"], college["url"])
                    
                result = scrape_college_with_ai(college, job_id, session_id, custom_directives)
                
                # Insert contacts to DB
                if result["contacts"]:
                    for contact in result["contacts"]:
                        database.insert_contact(contact)
                    database.delete_duplicates(session_id)
                
                with progress_lock:
                    completed_count += 1
                    job["current_index"] = completed_count
                    job["current_item"] = f"Finished: {result['college_name']}"
                    job["completed_colleges"].append({
                        "college_name": result["college_name"],
                        "url": result["url"],
                        "status": result["status"],
                        "count": len(result["contacts"]),
                        "error": result.get("error", "")
                    })
            except Exception as thread_err:
                print(f"[Thread Error] {thread_err}")
                with progress_lock:
                    completed_count += 1
                    job["current_index"] = completed_count
                    job["completed_colleges"].append({
                        "college_name": college.get("name", "Unknown"),
                        "url": college.get("url", ""),
                        "status": "failed",
                        "count": 0,
                        "error": str(thread_err)
                    })
        
        # Execute concurrently with 4 workers to avoid API key rate exhaustion
        with ThreadPoolExecutor(max_workers=4) as executor:
            executor.map(process_college_thread, colleges_to_process)
        
        # Phase 3: Complete
        job["phase"] = "completed"
        job["status"] = "completed"
        job["phase_label"] = "Discovery complete!"
        
        total_contacts = sum(c["count"] for c in job["completed_colleges"])
        successful = sum(1 for c in job["completed_colleges"] if c["status"] == "success")
        job["summary"] = {
            "total_colleges": len(job["completed_colleges"]),
            "successful": successful,
            "total_contacts": total_contacts
        }
        
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        print(f"[Discovery] Job {job_id} failed: {e}")


def start_discovery_job(mode, input_data, institution_type="all", session_id=None, custom_directives=None):
    """
    Creates and starts a new discovery background job.
    
    Returns:
        job_id string
    """
    import uuid
    job_id = uuid.uuid4().hex
    
    discovery_jobs[job_id] = {
        "status": "running",
        "phase": "initializing",
        "phase_label": "Initializing discovery engine...",
        "mode": mode,
        "total": 0,
        "current_index": 0,
        "current_item": "",
        "discovered_count": 0,
        "completed_colleges": [],
        "summary": {},
        "error": ""
    }
    
    thread = threading.Thread(
        target=run_discovery_job, 
        args=(job_id, mode, input_data, institution_type, session_id, custom_directives),
        daemon=True
    )
    thread.start()
    
    return job_id


def get_job_status(job_id):
    """Returns the current status of a discovery job."""
    return discovery_jobs.get(job_id)
