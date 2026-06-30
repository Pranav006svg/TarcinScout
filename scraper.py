import re
import time
import urllib3
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Suppress SSL warnings for insecure requests (common for some college websites)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration constants
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
TIMEOUT = 10
DELAY = 0.5  # polite request delay in seconds
MAX_PAGES = 25  # max unique pages to visit in one scraping run

PAGE_KEYWORDS = [
    "contact", "principal", "administration", "department", "faculty", 
    "hod", "placement", "training-placement", "tpo", "about", "staff",
    "people", "directory", "team", "members", "office", "academics", 
    "academic", "careers", "reach", "locate", "find-us", "governing",
    "trustees", "officers"
]

ROLE_KEYWORDS = {
    "Principal": ["principal", "director", "dean", "head of institution"],
    "HOD": ["hod", "head of department", "department head", "head of the department"],
    "Placement Officer": [
        "placement officer", "training and placement officer", "tpo", 
        "placement coordinator", "placement head", "placement cell"
    ]
}

# Regex definitions
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_REGEX = re.compile(r"(?:\+91[-\s]?)?[6-9]\d{9}|0\d{2,5}[-\s]?\d{6,8}")

# Name regex: looks for typical professional titles used in colleges
NAME_PATTERN = re.compile(
    r"\b(Dr\.|Prof\.|Mr\.|Ms\.|Mrs\.|Shri|Smt\.|Dr\s|Prof\s|Mr\s|Ms\s|Mrs\s)\s*([A-Z][a-zA-Z\s\.]{2,30})", 
    re.IGNORECASE
)

DEPT_KEYWORDS = {
    "Computer Science & Engineering": ["computer science", "cse", "cs & e"],
    "Information Technology": ["information technology", "it dept", "it department"],
    "Electronics & Communication Engineering": ["electronics & communication", "electronics and communication", "ece"],
    "Electrical & Electronics Engineering": ["electrical & electronics", "electrical and electronics", "eee"],
    "Mechanical Engineering": ["mechanical", "mech"],
    "Civil Engineering": ["civil"],
    "Chemical Engineering": ["chemical"],
    "Biotechnology": ["biotech", "biotechnology"],
    "Mechatronics Engineering": ["mechatronics"],
    "Architecture": ["architecture", "arch"],
    "Chemistry": ["chemistry", "chem"],
    "Physics": ["physics"],
    "Mathematics": ["mathematics", "maths", "math"],
    "English": ["english", "humanities"],
    "Computer Applications": ["computer applications", "mca"],
    "Management Studies": ["management studies", "mba", "management"],
    "Library": ["library", "librarian"],
    "Placement & Training": ["placement", "training and placement", "tpo", "career development"],
    "Examinations": ["controller of exam", "coe", "examination"],
    "Administration": ["administration", "office", "registrar", "accounts", "finance", "admin", "establishment"]
}

def detect_department_from_text(text, email=None):
    """Detects department name from a text snippet using DEPT_KEYWORDS."""
    if not text:
        return "General"
    cleaned = text
    if email:
        cleaned = cleaned.replace(email, " ")
    cleaned = re.sub(r'[a-zA-Z0-9.-]+\.[a-zA-Z]{2,6}', ' ', cleaned)
    cleaned_lower = re.sub(r'\s+', ' ', cleaned).lower()
    
    # 1. Primary check: Keyword matching with word-start boundary
    for dept, keywords in DEPT_KEYWORDS.items():
        for keyword in keywords:
            if re.search(r'\b' + re.escape(keyword), cleaned_lower):
                return dept
                
    # 2. Secondary check: Direct phrases
    dept_match = re.search(r'\b(?:department of|dept\. of)\s+([a-z\s&]{3,20})\b', cleaned_lower)
    if dept_match:
        return dept_match.group(1).strip().title()
        
    dept_match_reverse = re.search(r'\b([a-z\s&]{3,20})\s+(?:department|dept\.)\b', cleaned_lower)
    if dept_match_reverse:
        match_str = dept_match_reverse.group(1).strip()
        words = match_str.split()
        if len(words) <= 2:
            return match_str.title()

    return "General"

def deobfuscate_emails(text):
    """
    De-obfuscates email addresses in the text.
    Replaces patterns like 'user [at] domain [dot] edu' with 'user@domain.edu'.
    """
    if not text:
        return text
    
    # Pattern 1: Bracketed at (e.g. [at], (at), etc.) and bracketed dot or normal dot
    pattern1 = re.compile(
        r'([a-zA-Z0-9._%+-]+)'
        r'\s*[\(\[\{\<]\s*at\s*[\)\]\}\>]\s*'
        r'([a-zA-Z0-9.-]+)'
        r'(?:\s*[\(\[\{\<]\s*dot\s*[\)\]\}\>]\s*|\s*\.\s*)'
        r'([a-zA-Z]{2,6})',
        re.IGNORECASE
    )
    
    # Pattern 2: Unbracketed ' at ' and ' dot ' with spaces
    pattern2 = re.compile(
        r'([a-zA-Z0-9._%+-]+)'
        r'\s+at\s+'
        r'([a-zA-Z0-9.-]+)'
        r'\s+dot\s+'
        r'([a-zA-Z]{2,6})',
        re.IGNORECASE
    )
    
    def replace_email(match):
        user = match.group(1).strip()
        domain = match.group(2).strip()
        tld = match.group(3).strip()
        stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'and', 'but', 'or', 'if', 'then', 'else', 'at', 'to', 'in', 'on', 'for', 'with', 'by', 'from', 'of'}
        if user.lower() in stop_words or domain.lower() in stop_words or tld.lower() in stop_words:
            return match.group(0)
        return f"{user}@{domain}.{tld}"
        
    text = pattern1.sub(replace_email, text)
    text = pattern2.sub(replace_email, text)
    return text


def init_webdriver():
    """Initializes a headless Chrome webdriver."""
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")  # Use the newer headless mode
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(f"--user-agent={USER_AGENT}")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--log-level=3")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(15)
    return driver

def fetch_page_selenium(url):
    """Fetches a page using Selenium for JavaScript rendering fallback."""
    print(f"Running headless Selenium fallback for JS rendering: {url}")
    driver = None
    try:
        driver = init_webdriver()
        driver.get(url)
        # Wait a few seconds for content to load/scripts to run
        time.sleep(4)
        html = driver.page_source
        current_url = driver.current_url
        return html, current_url
    except Exception as e:
        print(f"Selenium fetch error for {url}: {e}")
        return None, None
    finally:
        if driver:
            try:
                driver.quit()
            except Exception as quit_err:
                print(f"Error closing webdriver: {quit_err}")

def fetch_page(url, force_selenium=False):
    """
    Fetches page content. If force_selenium is True, uses Selenium.
    Otherwise uses requests, falling back to Selenium if the response 
    seems to require JS rendering or fails to load.
    """
    if force_selenium:
        return fetch_page_selenium(url)
        
    headers = {"User-Agent": USER_AGENT}
    html, final_url = None, None
    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT, verify=True)
        html, final_url = response.text, response.url
    except requests.exceptions.SSLError:
        try:
            # Fallback to verify=False for misconfigured SSL certificates (common in academic sites)
            response = requests.get(url, headers=headers, timeout=TIMEOUT, verify=False)
            html, final_url = response.text, response.url
        except Exception as e:
            print(f"SSL fallback fetch error for {url}: {e}")
    except Exception as e:
        print(f"Standard fetch error for {url}: {e}")

    # Fallback checks
    requires_js = False
    if html:
        html_lower = html.lower()
        if len(html.strip()) < 2000 and any(keyword in html_lower for keyword in ["javascript", "noscript", "enable js", "enable cookies", "browser check"]):
            requires_js = True
        elif "checking your browser" in html_lower or "cloudflare" in html_lower:
            requires_js = True

    if not html or requires_js:
        sel_html, sel_url = fetch_page_selenium(url)
        if sel_html:
            return sel_html, sel_url

    return html, final_url

def get_domain(url):
    """Extracts the netloc domain from a URL."""
    return urlparse(url).netloc.lower()

def is_internal_link(url, base_domain):
    """Checks if the URL belongs to the same domain as the base domain."""
    return get_domain(url) == base_domain

def clean_url(url):
    """Cleans a URL by removing query parameters and hash anchors."""
    parsed = urlparse(url)
    # Rebuild URL without query/fragment
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

def find_relevant_pages(base_url, html_content):
    """
    Extracts all internal links from html_content that match PAGE_KEYWORDS.
    Normalizes links and filters duplicates.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    base_domain = get_domain(base_url)
    discovered_links = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith("javascript:") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        
        # Resolve relative URLs
        full_url = urljoin(base_url, href)
        cleaned_url = clean_url(full_url)

        if is_internal_link(cleaned_url, base_domain):
            # Check if link text or URL matches page keywords
            link_text = anchor.get_text().lower()
            url_path = urlparse(cleaned_url).path.lower()
            
            matches_keyword = any(keyword in link_text or keyword in url_path for keyword in PAGE_KEYWORDS)
            
            # Also allow homepages and about pages as starting points
            is_home_or_root = url_path in ["", "/", "/index.html", "/index.php", "/index.aspx"]
            
            if matches_keyword or is_home_or_root:
                discovered_links.add(cleaned_url)
                
    return list(discovered_links)

def detect_role_from_text(text):
    """Detects role from a text snippet using ROLE_KEYWORDS. Default is 'Faculty/Staff'."""
    text_lower = text.lower()
    for role, keywords in ROLE_KEYWORDS.items():
        for keyword in keywords:
            # Match word boundary or exact phrase
            if re.search(r'\b' + re.escape(keyword) + r'\b', text_lower):
                return role
    return "Faculty/Staff"

GENERIC_USERNAMES = {
    "info", "contact", "admin", "support", "office", "principal", "hod", "placement", 
    "careers", "admissions", "query", "mail", "jobs", "helpdesk", "enquiry", "registrar", 
    "dean", "director", "tpo", "feedback", "webmaster", "library", "exam", "controller",
    "accounts", "finance", "placementcell", "admission", "reception", "officecontact",
    "estt", "establishment", "grievance", "hostel", "sports", "cultural", "iqac", "placement.cell"
}

def extract_name_from_email(email):
    """Attempts to extract a clean person's name from an email address username if it looks like a person's name."""
    if not email or "@" not in email:
        return ""
    username = email.split("@")[0].lower()
    # Skip generic usernames
    if username in GENERIC_USERNAMES or any(g in username for g in ["office", "admin", "contact", "info", "support"]):
        return ""
    
    # Split by dot, underscore, or hyphen
    parts = re.split(r'[\._-]', username)
    # Check if parts are valid alphabetic strings and name-like
    cleaned_parts = [p.strip() for p in parts if p.strip().isalpha() and len(p.strip()) > 1]
    
    if len(cleaned_parts) >= 2:
        # e.g., john.doe -> John Doe
        return " ".join(p.capitalize() for p in cleaned_parts[:3])
    elif len(cleaned_parts) == 1 and len(cleaned_parts[0]) > 3:
        # e.g., janesmith -> Jane Smith
        return cleaned_parts[0].capitalize()
    return ""

def extract_name_from_text(text, email=None):
    """Tries to extract a person's name using professional title prefixes or fallback name heuristics."""
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # 1. Look for professional title prefix (Dr., Prof., Mr., Ms., Mrs., etc.) in each line
    for line in lines:
        match = NAME_PATTERN.search(line)
        if match:
            title = match.group(1).strip()
            name_part = match.group(2).strip()
            # Split by typical separator keywords to avoid capturing trailing labels or fields
            name_part = re.split(
                r'\b(email|phone|mobile|tel|fax|address|pincode|role|dept|website|link|page)\b|[:,\-\t]', 
                name_part, 
                flags=re.IGNORECASE
            )[0].strip()
            # Keep name part bounded to first few capitalized words
            words = name_part.split()
            cleaned_words = []
            for word in words:
                if word and (word[0].isupper() or word.replace(".", "").isupper()):
                    cleaned_words.append(word)
                else:
                    break
            if cleaned_words:
                return f"{title} {' '.join(cleaned_words)}"
                
    # Fallback 1: Extract from email username if available
    if email:
        email_name = extract_name_from_email(email)
        if email_name:
            return email_name
            
    # Fallback 2: Look for 1-3 capitalized words on a clean line in the context
    for line in lines:
        # Exclude lines that contain emails, phone numbers
        if "@" in line or any(char.isdigit() for char in line):
            continue
        # Exclude lines that contain label words
        if any(w in line.lower() for w in ["phone", "email", "fax", "department", "role", "address"]):
            continue
        # Exclude common roles/designations to avoid matching them as names
        role_words = ["principal", "director", "dean", "hod", "officer", "placement", "coordinator", "cell", "office", "contact", "faculty", "staff", "administration", "academic", "registrar"]
        if any(rw in line.lower() for rw in role_words):
            continue
        # Match 1 to 3 capitalized words or initials (e.g. "Chairman", "Arun Kumar", "S. K. Sharma")
        if re.match(r'^[A-Z][a-zA-Z\.]*(\s+[A-Z][a-zA-Z\.]*){0,3}$', line):
            if 3 <= len(line) <= 45:
                return line
    return ""

def parse_contacts_from_html(html_content, source_url):
    """
    Parses contact details from HTML.
    It isolates contacts by finding each unique email on the page first, 
    and then climbing up the DOM tree to extract its immediate container text context.
    """
    # De-obfuscate emails in raw HTML before parsing
    html_content = deobfuscate_emails(html_content)
    soup = BeautifulSoup(html_content, "html.parser")
    contacts = []
    
    # Remove script and style tags to prevent noise
    for script_or_style in soup(["script", "style", "noscript", "iframe"]):
        script_or_style.decompose()

    # Find all unique emails on the page
    text_content = soup.get_text(" ", strip=True)
    emails = EMAIL_REGEX.findall(text_content)
    unique_emails = set(email.strip() for email in emails)

    for email in unique_emails:
        # Find the element/node containing this email string
        email_tag = soup.find(string=re.compile(re.escape(email)))
        if not email_tag:
            context_text = text_content
        else:
            # Traveres up up to 3 levels to grab the block container (e.g. tr or contact card div)
            curr = email_tag
            context_text = curr.get_text("\n", strip=True)
            for _ in range(3):
                if curr.parent and curr.parent.name not in ['body', 'html']:
                    curr = curr.parent
                    parent_text = curr.get_text("\n", strip=True)
                    if len(parent_text) < 1000:
                        context_text = parent_text
                    if curr.name in ['tr', 'li']:
                        break
        
        # Extract phone numbers in the same context
        phones = PHONE_REGEX.findall(context_text)
        phone = "N/A"
        if phones:
            p = phones[0]
            phone = p[0] if isinstance(p, tuple) else p
            phone = phone.strip()
            
        # Extract role
        role = detect_role_from_text(context_text)
        
        # Extract name
        name = extract_name_from_text(context_text, email)
        if not name:
            name = "Official Contact"
            
        # Extract department with fallback
        dept = detect_department_from_text(context_text, email)
        if dept == "General":
            dept = "Administration" if role in ["Principal", "Placement Officer"] else "Academic"
        
        contacts.append({
            "person_name": name,
            "role": role,
            "department": dept,
            "email": email,
            "phone": phone,
            "address": "N/A",
            "source_url": source_url
        })
        
    return contacts

def get_college_name_from_html(html_content, base_url):
    """Attempts to extract the college name from the title tag or first h1."""
    soup = BeautifulSoup(html_content, "html.parser")
    title_tag = soup.find("title")
    if title_tag:
        title_text = title_tag.get_text().strip()
        # Clean title (e.g., remove "Home", "Welcome to", or URL elements)
        for junk in ["Home -", "Welcome to", "| Home", "Official Website"]:
            title_text = title_text.replace(junk, "").strip()
        if len(title_text) > 3:
            return title_text
            
    h1_tag = soup.find("h1")
    if h1_tag:
        h1_text = h1_tag.get_text().strip()
        if len(h1_text) > 3:
            return h1_text
            
    # Fallback to domain name
    parsed = urlparse(base_url)
    return parsed.netloc.replace("www.", "")

def scrape_college_website(start_url):
    """
    Crawling manager:
    1. Starts at start_url (homepage).
    2. Discovers relevant internal pages.
    3. Crawls links recursively up to depth 2, capping at MAX_PAGES.
    4. Extracts contacts and assigns the extracted College Name.
    """
    start_url = start_url.strip()
    if not start_url.startswith(("http://", "https://")):
        start_url = "https://" + start_url
        
    base_domain = get_domain(start_url)
    
    # Queue structure: (url, depth)
    queue = [(start_url, 0)]
    visited = set()
    all_contacts = []
    
    college_name = "Unknown College"
    site_wide_address = "N/A"
    
    print(f"Starting crawl for: {start_url} (depth cap=2, page cap={MAX_PAGES})")
    
    while queue and len(visited) < MAX_PAGES:
        url, depth = queue.pop(0)
        
        if url in visited:
            continue
            
        print(f"Crawling (depth {depth}): {url}")
        visited.add(url)
        
        # Polite crawling delay
        if len(visited) > 1:
            time.sleep(DELAY)
            
        html, final_url = fetch_page(url)
        if not html:
            continue
            
        # Parse college name from homepage
        if url == start_url or college_name == "Unknown College":
            college_name = get_college_name_from_html(html, start_url)
            # Try to fetch site-wide address from footer / homepage
            soup = BeautifulSoup(html, "html.parser")
            address_tag = soup.find(["address", "footer"])
            if address_tag:
                addr_text = address_tag.get_text(" ", strip=True)
                # Search for typical Indian address fragments (e.g. Pin code, district, state)
                pincode_match = re.search(r'\b\d{6}\b', addr_text)
                if pincode_match:
                    # Capture text around pincode
                    p_idx = pincode_match.start()
                    start_idx = max(0, p_idx - 150)
                    end_idx = min(len(addr_text), p_idx + 50)
                    site_wide_address = addr_text[start_idx:end_idx].strip()
                    # clean up line breaks
                    site_wide_address = re.sub(r'\s+', ' ', site_wide_address)
            
        # Parse contacts from this page
        page_contacts = parse_contacts_from_html(html, url)
        for contact in page_contacts:
            contact["college_name"] = college_name
            contact["website_url"] = start_url
            if contact["address"] == "N/A" and site_wide_address != "N/A":
                contact["address"] = site_wide_address
            all_contacts.append(contact)
            
        # Discovered internal pages (only if current depth < 2)
        if depth < 2:
            discovered = find_relevant_pages(url, html)
            for page in discovered:
                if page not in visited and page not in [q[0] for q in queue]:
                    queue.append((page, depth + 1))
                    
    # Format and deduplicate
    unique_contacts = []
    seen = set()
    for c in all_contacts:
        # Deduplicate results using email as the unique identifier
        key = c["email"].lower()
        if key not in seen:
            seen.add(key)
            unique_contacts.append(c)
            
    print(f"Scrape completed. Found {len(unique_contacts)} unique contacts across {len(visited)} visited pages.")
    return unique_contacts
