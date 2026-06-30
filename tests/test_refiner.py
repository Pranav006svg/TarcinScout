import unittest
import pandas as pd
import sys
import os

# Add parent directory to path so we can import data_refiner
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import data_refiner

class TestDataRefiner(unittest.TestCase):

    def test_clean_email(self):
        # Valid emails
        self.assertEqual(data_refiner.clean_email("test@domain.com"), "test@domain.com")
        self.assertEqual(data_refiner.clean_email("  USER.NAME@college.edu.in "), "user.name@college.edu.in")
        
        # Invalid/placeholder emails
        self.assertEqual(data_refiner.clean_email("test@example.com"), "")
        self.assertEqual(data_refiner.clean_email("invalid-email"), "")
        self.assertEqual(data_refiner.clean_email("admin@test.com"), "")
        self.assertEqual(data_refiner.clean_email(""), "")
        self.assertEqual(data_refiner.clean_email(None), "")

    def test_clean_phone(self):
        # Indian Mobile numbers
        self.assertEqual(data_refiner.clean_phone("+91-98765-43210"), "98765 43210")
        self.assertEqual(data_refiner.clean_phone("09876543210"), "98765 43210")
        self.assertEqual(data_refiner.clean_phone("9876543210"), "98765 43210")
        
        # Landlines and general phone formats
        self.assertEqual(data_refiner.clean_phone("080-23456789"), "080-23456789")
        self.assertEqual(data_refiner.clean_phone("N/A"), "N/A")
        self.assertEqual(data_refiner.clean_phone(""), "N/A")
        self.assertEqual(data_refiner.clean_phone(None), "N/A")

    def test_clean_name(self):
        self.assertEqual(data_refiner.clean_name("dr. john  doe"), "Dr. John Doe")
        self.assertEqual(data_refiner.clean_name("  prof. jane smith  "), "Prof. Jane Smith")
        self.assertEqual(data_refiner.clean_name("N/A"), "Official Contact")
        self.assertEqual(data_refiner.clean_name(""), "Official Contact")

    def test_refine_dataframe(self):
        # Prepare a dirty dataframe
        raw_data = {
            "COLLEGE": ["A.B.C. College", "A.B.C. College", "X.Y.Z. Institution"],
            "Website": ["abc.edu.in", "abc.edu.in", "http://xyz.ac.in"],
            "Contact Person": ["dr. john doe", "dr. john doe", "prof. jane smith"],
            "Role Designation": ["principal", "principal", "faculty"],
            "E-mail Address": ["john@abc.edu.in", "john@abc.edu.in", "jane@xyz.ac.in"],
            "Phone Number": ["+91 98765 43210", "+91 98765 43210", "080-123456"]
        }
        
        df = pd.DataFrame(raw_data)
        
        # Run refinement
        df_refined, df_removed, metrics = data_refiner.refine_dataframe(df)
        
        # Verify deduplication (Row 0 and 1 are identical)
        self.assertEqual(len(df_refined), 2)
        self.assertEqual(metrics['duplicates_removed'], 1)
        
        # Verify column mapping worked
        self.assertIn('college_name', df_refined.columns)
        self.assertIn('website_url', df_refined.columns)
        self.assertIn('person_name', df_refined.columns)
        self.assertIn('email', df_refined.columns)
        
        # Verify values cleaned
        self.assertEqual(df_refined.iloc[0]['person_name'], "Dr. John Doe")
        self.assertEqual(df_refined.iloc[0]['role'], "Principal")
        self.assertEqual(df_refined.iloc[0]['department'], "Administration")
        self.assertEqual(df_refined.iloc[0]['phone'], "98765 43210")
        
        self.assertEqual(df_refined.iloc[1]['person_name'], "Prof. Jane Smith")
        self.assertEqual(df_refined.iloc[1]['role'], "Faculty")
        self.assertEqual(df_refined.iloc[1]['department'], "Academic")

if __name__ == "__main__":
    unittest.main()
