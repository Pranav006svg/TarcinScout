import re
import pandas as pd
from urllib.parse import urlparse

# Reuse role classification keywords from scraper
ROLE_KEYWORDS = {
    "Principal": ["principal", "director", "dean", "head of institution"],
    "HOD": ["hod", "head of department", "department head", "head of the department"],
    "Placement Officer": [
        "placement officer", "training and placement officer", "tpo", 
        "placement coordinator", "placement head", "placement cell"
    ]
}

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_REGEX = re.compile(r"[6-9]\d{9}|\b0\d{2,5}[-\s]?\d{6,8}\b")

def detect_role_from_text(text):
    """Detects role from a text snippet using ROLE_KEYWORDS. Default is 'Faculty/Staff'."""
    if not isinstance(text, str):
        return "Faculty/Staff"
    text_lower = text.lower()
    for role, keywords in ROLE_KEYWORDS.items():
        for keyword in keywords:
            if re.search(r'\b' + re.escape(keyword) + r'\b', text_lower):
                return role
    return "Faculty/Staff"

def clean_email(email):
    """Validates and cleans email string. Returns clean email or empty string."""
    if not isinstance(email, str):
        return ""
    email = email.strip().lower()
    # Basic domain exclusion for common test/placeholder addresses
    for invalid in ["example.com", "test.com", "placeholder.com", "yourdomain.com"]:
        if invalid in email:
            return ""
    match = EMAIL_REGEX.search(email)
    return match.group(0) if match else ""

def clean_phone(phone):
    """Standardizes phone number. Extracts 10-digit mobile or valid landline."""
    if not isinstance(phone, str):
        if pd.isna(phone):
            return "N/A"
        phone = str(phone)
    
    phone = phone.strip()
    if not phone or phone.lower() in ["n/a", "none", "nan", "null"]:
        return "N/A"
        
    # Check if it looks like a landline with hyphen/space
    if '-' in phone or ' ' in phone:
        cleaned_spaces = re.sub(r'\s+', ' ', phone).strip()
        if re.match(r'^0\d{2,5}[-\s]?\d{6,8}$', cleaned_spaces):
            return cleaned_spaces
    
    # Strip common prefix +91 or 91 if it makes the number 12 digits
    cleaned = re.sub(r'\D', '', phone)  # keep digits only
    if len(cleaned) == 12 and cleaned.startswith("91") and cleaned[2] in ('6', '7', '8', '9'):
        cleaned = cleaned[2:]
    elif len(cleaned) == 11 and cleaned.startswith("0") and cleaned[1] in ('6', '7', '8', '9'):
        cleaned = cleaned[1:]
        
    if len(cleaned) == 10 and cleaned.startswith(('6', '7', '8', '9')):
        return f"{cleaned[:5]} {cleaned[5:]}"
        
    # Standard landline detection fallback
    match = PHONE_REGEX.search(phone)
    if match:
        p = match.group(0)
        digits = re.sub(r'\D', '', p)
        if len(digits) == 10 and digits.startswith(('6', '7', '8', '9')):
            return f"{digits[:5]} {digits[5:]}"
        return p
        
    return phone

def clean_name(name):
    """Cleans person name by stripping whitespace, title casing and handling empty fields."""
    if not isinstance(name, str):
        return "Official Contact"
    name = re.sub(r'\s+', ' ', name).strip()
    if not name or name.lower() in ["n/a", "none", "nan", "null", "contact", "official"]:
        return "Official Contact"
    
    # Capitalize appropriately (Title Case)
    return name.title()

def map_columns(df):
    """
    Fuzzy-maps columns of the uploaded DataFrame to standard scraper schema:
    [college_name, website_url, person_name, role, department, email, phone, address, source_url]
    """
    standard_columns = {
        'college_name': ['college', 'institution', 'university', 'college name', 'school'],
        'website_url': ['website', 'url', 'college website', 'link', 'homepage'],
        'person_name': ['name', 'contact name', 'person', 'faculty name', 'staff name', 'person_name'],
        'role': ['role', 'designation', 'position', 'title'],
        'department': ['department', 'dept', 'branch', 'stream'],
        'email': ['email', 'e-mail', 'mail', 'email address', 'mail id', 'email_address'],
        'phone': ['phone', 'contact', 'mobile', 'telephone', 'phone number', 'contact number'],
        'address': ['address', 'office address', 'location', 'postal address'],
        'source_url': ['source', 'source url', 'page url', 'scraped page']
    }
    
    mapping = {}
    lowercase_cols = [c.lower().strip() for c in df.columns]
    
    for std_key, alt_names in standard_columns.items():
        found = False
        # Direct exact match check
        for col in df.columns:
            if col.lower().strip() == std_key:
                mapping[col] = std_key
                found = True
                break
        if found:
            continue
            
        # Fuzzy match checks
        for alt in alt_names:
            for original_col in df.columns:
                col_clean = original_col.lower().strip()
                if alt in col_clean or col_clean in alt:
                    mapping[original_col] = std_key
                    found = True
                    break
            if found:
                break
                
    return mapping

def refine_dataframe(df):
    """
    Processes the DataFrame, maps columns, cleans and validates values,
    and returns:
      1. The cleaned DataFrame
      2. A dictionary with cleanup metrics/statistics
    """
    # Create a copy to prevent modifying original
    df_clean = df.copy()
    
    # 1. Map columns
    col_mapping = map_columns(df_clean)
    df_clean = df_clean.rename(columns=col_mapping)
    
    # Check what expected columns are present
    expected_cols = [
        'college_name', 'website_url', 'person_name', 'role', 
        'department', 'email', 'phone', 'address', 'source_url'
    ]
    
    # Add missing expected columns as empty strings or N/A
    for col in expected_cols:
        if col not in df_clean.columns:
            if col in ['phone', 'address']:
                df_clean[col] = 'N/A'
            elif col == 'role':
                df_clean[col] = 'Faculty/Staff'
            elif col == 'department':
                df_clean[col] = 'Academic'
            else:
                df_clean[col] = ''
                
    # Filter only expected columns
    df_clean = df_clean[expected_cols]
    
    # Clean string data
    for col in df_clean.columns:
        df_clean[col] = df_clean[col].fillna('')
        
    metrics = {
        'total_rows_received': len(df),
        'duplicates_removed': 0,
        'invalid_emails_removed': 0,
        'phones_standardized': 0,
        'roles_classified': 0,
        'total_rows_cleaned': 0
    }
    
    # Track statistics
    cleaned_rows = []
    
    for idx, row in df_clean.iterrows():
        raw_email = str(row['email'])
        c_email = clean_email(raw_email)
        
        # If email is completely invalid, we mark it empty
        if raw_email and not c_email:
            metrics['invalid_emails_removed'] += 1
            
        raw_phone = str(row['phone'])
        c_phone = clean_phone(raw_phone)
        if raw_phone and c_phone != raw_phone and c_phone != 'N/A':
            metrics['phones_standardized'] += 1
            
        raw_role = str(row['role']).strip()
        c_role = raw_role
        
        # If it is empty or default generic, try to guess a more specific role
        if not c_role or c_role.lower() in ['n/a', 'faculty', 'staff', 'faculty/staff', 'professor', 'teacher']:
            context = f"{row['person_name']} {row['department']}"
            guessed_role = detect_role_from_text(context)
            if guessed_role != "Faculty/Staff":
                c_role = guessed_role
                metrics['roles_classified'] += 1
            elif not c_role:
                c_role = "Faculty/Staff"
            else:
                c_role = c_role.title()
        else:
            c_role = c_role.title()
            
        c_name = clean_name(row['person_name'])
        
        # Determine department based on role if missing/default
        c_dept = str(row['department']).strip()
        if not c_dept or c_dept.lower() in ['', 'n/a', 'academic']:
            c_dept = "Administration" if c_role in ["Principal", "Placement Officer"] else "Academic"
            
        c_college = str(row['college_name']).strip()
        if not c_college:
            # Fallback college name from URL domain
            if row['website_url']:
                parsed = urlparse(str(row['website_url']))
                c_college = parsed.netloc.replace("www.", "") or "Unknown College"
            else:
                c_college = "Unknown College"
        
        # Clean URLs
        c_web_url = str(row['website_url']).strip()
        if c_web_url and not c_web_url.startswith(("http://", "https://")):
            c_web_url = "https://" + c_web_url
            
        c_src_url = str(row['source_url']).strip()
        if c_src_url and not c_src_url.startswith(("http://", "https://")):
            c_src_url = "https://" + c_src_url
        elif not c_src_url:
            c_src_url = c_web_url
            
        cleaned_rows.append({
            'college_name': c_college.title() if '.' not in c_college else c_college,
            'website_url': c_web_url,
            'person_name': c_name,
            'role': c_role,
            'department': c_dept,
            'email': c_email,
            'phone': c_phone,
            'address': str(row['address']).strip() or 'N/A',
            'source_url': c_src_url
        })
        
    df_refined = pd.DataFrame(cleaned_rows)
    
    # Remove records that don't have ANY email or phone (junk records)
    initial_len = len(df_refined)
    junk_mask = ~(
        (df_refined['email'] != '') | 
        ((df_refined['phone'] != '') & (df_refined['phone'] != 'N/A'))
    )
    df_junk = df_refined[junk_mask].copy()
    if not df_junk.empty:
        df_junk['refiner_status'] = 'Filtered: No Email or Phone'
    
    df_refined = df_refined[~junk_mask]
    metrics['invalid_emails_removed'] += (initial_len - len(df_refined))
    
    # Deduplicate based on email + phone + name
    duplicate_mask = df_refined.duplicated(subset=['email', 'phone', 'person_name', 'college_name'], keep='first')
    df_duplicates = df_refined[duplicate_mask].copy()
    if not df_duplicates.empty:
        df_duplicates['refiner_status'] = 'Duplicate Removed'
        
    df_refined = df_refined[~duplicate_mask]
    metrics['duplicates_removed'] = len(df_duplicates)
    
    metrics['total_rows_cleaned'] = len(df_refined)
    
    # Combine duplicates and junk into a single df_removed
    if not df_junk.empty and not df_duplicates.empty:
        df_removed = pd.concat([df_duplicates, df_junk], ignore_index=True)
    elif not df_junk.empty:
        df_removed = df_junk
    else:
        df_removed = df_duplicates
        
    return df_refined, df_removed, metrics
