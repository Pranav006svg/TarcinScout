import os
import sys
from unittest.mock import patch

# Add parent directory to path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discovery_engine
import scraper

# Mock pages for our simulated college website:
# Homepage (depth 0) -> Departments list & Contact Page (depth 1)
# Departments list (depth 1) -> CSE & ME department pages (depth 2)
MOCK_PAGES = {
    "http://mockcollege.edu": """
        <html>
            <head><title>Mock Engineering College</title></head>
            <body>
                <a href="/academics/departments">Academics Departments List</a>
                <a href="/contact-us">Contact Us</a>
                <a href="/gallery">Photo Gallery</a>
            </body>
        </html>
    """,
    "http://mockcollege.edu/academics/departments": """
        <html>
            <head><title>Academics & Departments</title></head>
            <body>
                <a href="/departments/cse/faculty">Computer Science Faculty</a>
                <a href="/departments/mechanical/faculty">Mechanical Faculty</a>
                <a href="/admission/fees">Fee Structure</a>
            </body>
        </html>
    """,
    "http://mockcollege.edu/contact-us": """
        <html>
            <head><title>Contact Us</title></head>
            <body>
                <p>Email us at info@mockcollege.edu</p>
            </body>
        </html>
    """,
    "http://mockcollege.edu/departments/cse/faculty": """
        <html>
            <head><title>CSE Faculty</title></head>
            <body>
                <p>HOD: hod.cse@mockcollege.edu</p>
                <p>Professor: prof.cse@mockcollege.edu</p>
            </body>
        </html>
    """,
    "http://mockcollege.edu/departments/mechanical/faculty": """
        <html>
            <head><title>Mechanical Faculty</title></head>
            <body>
                <p>HOD: hod.mech@mockcollege.edu</p>
            </body>
        </html>
    """,
    "http://mockcollege.edu/gallery": "<html><body>Gallery Page</body></html>",
    "http://mockcollege.edu/admission/fees": "<html><body>Fees Page</body></html>"
}

def mock_fetch_page(url, force_selenium=False):
    # Normalize url (remove ending slash)
    normalized_url = url.rstrip('/')
    print(f"    [Mock Fetch] Fetching: {normalized_url}")
    if normalized_url in MOCK_PAGES:
        return MOCK_PAGES[normalized_url], normalized_url
    return None, None

@patch('scraper.fetch_page', side_effect=mock_fetch_page)
def test_deep_link_discovery(mock_fetch):
    test_url = "http://mockcollege.edu"
    print(f"Starting depth-2 discovery test for: {test_url}")
    
    # Run the actual steps of the discovery crawler loop in scrape_college_with_ai
    discovered_pages = set()
    queue = [(test_url, 0)]
    visited_discovery = set()
    
    MAX_DISCOVERY_CRAWL = 15
    
    while queue and len(visited_discovery) < MAX_DISCOVERY_CRAWL:
        curr_url, depth = queue.pop(0)
        if curr_url in visited_discovery:
            continue
        visited_discovery.add(curr_url)
        
        curr_html, _ = scraper.fetch_page(curr_url)
        if not curr_html:
            continue
            
        links = scraper.find_relevant_pages(curr_url, curr_html)
        print(f"    Visited depth {depth}: {curr_url} -> Found {len(links)} relevant links")
        for link in links:
            if link not in visited_discovery:
                discovered_pages.add(link)
                if depth < 1:  # Add to queue only if current page is depth 0
                    if link not in [q[0] for q in queue]:
                        queue.append((link, depth + 1))
                        
    # Clean and prioritize
    clean_homepage_url = scraper.clean_url(test_url)
    discovered_pages.discard(clean_homepage_url)
    discovered_pages.discard(test_url)
    
    print(f"\nTotal Discovered Pages: {len(discovered_pages)}")
    for p in discovered_pages:
        print(f"  - {p}")
        
    scored_pages = []
    for p in discovered_pages:
        score = discovery_engine.score_page_url(p)
        scored_pages.append((p, score))
        
    # Sort by score
    scored_pages.sort(key=lambda x: x[1], reverse=True)
    
    print("\nSorted & Scored Pages:")
    for idx, (p, score) in enumerate(scored_pages):
        print(f"  {idx+1}. Score={score:<3} | URL: {p}")
        
    # Validations:
    # 1. We should have visited the homepage, contact-us, and departments page
    assert "http://mockcollege.edu/contact-us" in discovered_pages
    assert "http://mockcollege.edu/departments/cse/faculty" in discovered_pages
    assert "http://mockcollege.edu/departments/mechanical/faculty" in discovered_pages
    
    # 2. CSE and Mechanical faculty pages should be prioritized at the top of the list (higher scores)
    # CSE page: contains "cse", "faculty", "department" -> should have score > 150
    # Mechanical page: contains "mechanical", "faculty", "department" -> should have score > 150
    # Contact Us page: contains "contact" -> should have score 100
    # Academics Departments page: contains "department", "academic" -> score should be around 80-160
    assert scored_pages[0][1] >= 180  # CSE or ME faculty list
    assert scored_pages[0][0].endswith("faculty")
    
    print("\nAll assertions passed!")
    return True

if __name__ == "__main__":
    try:
        success = test_deep_link_discovery()
        print(f"\n=== Test Summary ===")
        print(f"Deep Link Discovery & Scoring: {'PASSED' if success else 'FAILED'}")
        sys.exit(0 if success else 1)
    except AssertionError as ae:
        print(f"\nAssertion failed: {ae}")
        sys.exit(1)
