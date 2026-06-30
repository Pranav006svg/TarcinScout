import unittest
from unittest.mock import patch, MagicMock
import io
import zipfile
import sys
import os
import pandas as pd

# Add parent directory to path so we can import scraper, app, database
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scraper
import app
import database
import discovery_engine

class TestScraperAndFeatures(unittest.TestCase):

    @patch('scraper.fetch_page_selenium')
    @patch('requests.get')
    def test_js_rendering_fallback(self, mock_get, mock_selenium):
        """Verify requests fallback to Selenium when JS requirements are detected."""
        # Setup mock response for requests.get containing browser check/JS indicators
        mock_response = MagicMock()
        mock_response.text = "<html><head><title>Checking your browser...</title></head><body>Please enable JavaScript to continue</body></html>"
        mock_response.url = "https://examplecollege.ac.in"
        mock_get.return_value = mock_response
        
        # Setup mock for selenium fetch
        mock_selenium.return_value = ("<html><body><h1>Rendered College Name</h1><p>contact@examplecollege.ac.in</p></body></html>", "https://examplecollege.ac.in")
        
        # Run fetch_page
        html, final_url = scraper.fetch_page("https://examplecollege.ac.in")
        
        # Verify Selenium fallback was called
        mock_selenium.assert_called_once_with("https://examplecollege.ac.in")
        self.assertIn("Rendered College Name", html)
        self.assertEqual(final_url, "https://examplecollege.ac.in")

    def test_name_extraction_heuristics(self):
        """Verify advanced heuristics split names from email usernames and context."""
        # Test extraction from email username
        email_name_1 = scraper.extract_name_from_email("john.doe@college.edu")
        self.assertEqual(email_name_1, "John Doe")
        
        email_name_2 = scraper.extract_name_from_email("janesmith@college.edu")
        self.assertEqual(email_name_2, "Janesmith") # capitalized fallback
        
        # Verify skipping generic emails
        generic_name = scraper.extract_name_from_email("admin@college.edu")
        self.assertEqual(generic_name, "")
        
        # Test name search in text
        text_with_title = "Contact: Dr. Johnathan Doe, Principal of the Engineering College"
        extracted = scraper.extract_name_from_text(text_with_title)
        self.assertEqual(extracted, "Dr. Johnathan Doe")
        
        # Test clean capitalized line name fallback
        clean_text_lines = "Some random header\nArun Kumar\nPhone: 9876543210\n"
        extracted_fallback = scraper.extract_name_from_text(clean_text_lines)
        self.assertEqual(extracted_fallback, "Arun Kumar")

    @patch('database.get_db_connection')
    def test_user_session_isolation(self, mock_db_conn):
        """Verify database queries are correctly scoped to user session ID."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db_conn.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        # Test get_all_contacts scopes to session ID
        database.get_all_contacts(session_id="test_user_session_123")
        mock_cursor.execute.assert_called_with(
            "SELECT * FROM college_contacts WHERE session_id = %s ORDER BY id DESC", 
            ("test_user_session_123",)
        )
        
        # Test clear_database scopes to session ID
        database.clear_database(session_id="test_user_session_123")
        mock_cursor.execute.assert_called_with(
            "DELETE FROM college_contacts WHERE session_id = %s;", 
            ("test_user_session_123",)
        )

    def test_zip_utf8_encoding(self):
        """Verify ZIP export correctly encodes CSV data in UTF-8 to prevent character corruption."""
        # Create mock data with UTF-8 non-ASCII characters (e.g. Indian college name characters or accents)
        contacts = [
            {
                'college_name': 'Savitribai Phule Pune University (SPPU) - 🎓 Pune',
                'website_url': 'http://unipune.ac.in',
                'person_name': 'Dr. Nitin R. Karmalkar',
                'role': 'Principal',
                'department': 'Administration',
                'email': 'nitin@unipune.ac.in',
                'phone': '020 25692656',
                'address': 'Ganeshkhind Road, Pune 411007',
                'source_url': 'http://unipune.ac.in/contact',
                'college_type': 'Government',
                'custom_notes': 'Only Principal'
            }
        ]
        
        df = pd.DataFrame(contacts)
        df_clean = df.rename(columns={
            'college_name': 'College Name',
            'website_url': 'Website URL',
            'person_name': 'Contact Name',
            'role': 'Role',
            'department': 'Department',
            'email': 'Email Address',
            'phone': 'Phone / Contact',
            'address': 'Office Address',
            'source_url': 'Scraped Page URL',
            'college_type': 'College Type',
            'custom_notes': 'Extraction Directives'
        })
        
        # Stream ZIP buffer
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            file_name = "test_contacts.csv"
            csv_data = df_clean.to_csv(index=False).encode('utf-8')
            zip_file.writestr(file_name, csv_data)
            
        zip_buffer.seek(0)
        
        # Read ZIP file and check if characters are properly encoded in UTF-8
        with zipfile.ZipFile(zip_buffer, 'r') as read_zip:
            file_list = read_zip.namelist()
            self.assertIn("test_contacts.csv", file_list)
            
            with read_zip.open("test_contacts.csv") as csv_file:
                content = csv_file.read().decode('utf-8')
                self.assertIn("SPPU", content)
                self.assertIn("🎓", content)  # Emoji verified
                self.assertIn("Pune", content)

if __name__ == "__main__":
    unittest.main()
