import io
import os
import re
import uuid
import zipfile
import threading
from urllib.parse import urlparse
from flask import Flask, request, render_template, redirect, url_for, flash, send_file, session
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

import database
import scraper
import data_refiner
import discovery_engine

app = Flask(__name__)
# Set a secret key for session/flash messages
app.secret_key = os.urandom(24)

# In-memory batch state store for bulk scraping
scraping_batches = {}

# Ensure database is initialized before any requests
database.create_table()

@app.before_request
def ensure_session_id():
    """Generates a unique session ID for the user if it doesn't exist."""
    if 'user_session_id' not in session:
        session['user_session_id'] = uuid.uuid4().hex

def is_valid_url(url):
    """Checks if the URL structure is valid."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc]) or (url and '.' in url)
    except:
        return False

@app.route("/")
def index():
    """Renders the dashboard landing page."""
    return render_template("index.html")

@app.route("/scrape", methods=["POST"])
def scrape():
    """
    Receives URL from form, validates it, invokes scraping logic,
    stores results in the database, removes duplicates, and redirects.
    """
    url = request.form.get("url", "").strip()
    custom_directives = request.form.get("custom_directives", "").strip()
    
    if not url:
        flash("Please enter a website URL.", "error")
        return redirect(url_for("index"))
        
    # Standardize URL schema if missing
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    if not is_valid_url(url):
        flash("Please enter a valid website URL.", "error")
        return redirect(url_for("index"))

    try:
        # Perform AI scraping (with regex fallback)
        college_info = {"name": "", "url": url}
        session_id = session.get('user_session_id')
        result = discovery_engine.scrape_college_with_ai(
            college_info, session_id=session_id, custom_directives=custom_directives
        )
        contacts = result.get("contacts", [])
        
        if not contacts:
            # Re-render homepage with a warning or pass to error screen
            return render_template("error.html", 
                                   error_title="No Data Found", 
                                   error_message=f"We successfully reached {url}, but could not extract any contact information (emails/phones). The site might be javascript-heavy or blocks automated crawlers.", 
                                   target_url=url)

        # Store in database
        inserted_count = 0
        for contact in contacts:
            database.insert_contact(contact)
            inserted_count += 1
            
        # Clean duplicates scoped to session
        deleted_count = database.delete_duplicates(session_id)
        
        flash(f"Scraped {inserted_count} contact(s) successfully! Removed {deleted_count} duplicate(s).", "success")
        return redirect(url_for("results"))

    except Exception as e:
        print(f"Scrape error: {e}")
        return render_template("error.html", 
                               error_title="Scraping Failed", 
                               error_message=f"An unexpected error occurred while scraping {url}. Details: {str(e)}", 
                               target_url=url)

@app.route("/results")
def results():
    """Retrieves contacts for current session and renders results dashboard."""
    try:
        session_id = session.get('user_session_id')
        contacts = database.get_all_contacts(session_id)
        return render_template("results.html", contacts=contacts)
    except Exception as e:
        flash(f"Failed to retrieve contacts from database: {e}", "error")
        return redirect(url_for("index"))

@app.route("/clear", methods=["POST"])
def clear():
    """Clears all records for current user session from database."""
    try:
        session_id = session.get('user_session_id')
        count = database.clear_database(session_id)
        flash(f"Successfully cleared {count} record(s) from database.", "success")
    except Exception as e:
        flash(f"Failed to clear database: {e}", "error")
    return redirect(url_for("results"))

@app.route("/export/csv")
def export_csv():
    """Exports database contacts to CSV using Pandas and streams it to the user."""
    try:
        session_id = session.get('user_session_id')
        contacts = database.get_all_contacts(session_id)
        if not contacts:
            flash("No data available to export.", "warning")
            return redirect(url_for("results"))
            
        df = pd.DataFrame(contacts)
        if 'id' in df.columns:
            df = df.drop(columns=['id'])
            
        # Smarter Pandas deduplication prior to export
        df = df.drop_duplicates(subset=['college_name', 'email', 'phone', 'person_name'], keep='first')
            
        column_mapping = {
            'college_name': 'College Name',
            'website_url': 'Website URL',
            'person_name': 'Contact Name',
            'role': 'Role',
            'department': 'Department',
            'email': 'Email Address',
            'phone': 'Phone / Contact',
            'address': 'Office Address',
            'source_url': 'Scraped Page URL',
            'scraped_at': 'Timestamp',
            'college_type': 'College Type',
            'custom_notes': 'Extraction Directives'
        }
        df = df.rename(columns=column_mapping)
        
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)
        
        return send_file(
            io.BytesIO(csv_buffer.getvalue().encode('utf-8')),
            mimetype="text/csv",
            as_attachment=True,
            download_name="scraped_college_contacts.csv"
        )
    except Exception as e:
        flash(f"CSV export failed: {e}", "error")
        return redirect(url_for("results"))

@app.route("/export/excel")
def export_excel():
    """Exports database contacts to Excel format and streams it to the user."""
    try:
        session_id = session.get('user_session_id')
        contacts = database.get_all_contacts(session_id)
        if not contacts:
            flash("No data available to export.", "warning")
            return redirect(url_for("results"))
            
        df = pd.DataFrame(contacts)
        if 'id' in df.columns:
            df = df.drop(columns=['id'])
            
        # Smarter Pandas deduplication prior to export
        df = df.drop_duplicates(subset=['college_name', 'email', 'phone', 'person_name'], keep='first')
            
        column_mapping = {
            'college_name': 'College Name',
            'website_url': 'Website URL',
            'person_name': 'Contact Name',
            'role': 'Role',
            'department': 'Department',
            'email': 'Email Address',
            'phone': 'Phone / Contact',
            'address': 'Office Address',
            'source_url': 'Scraped Page URL',
            'scraped_at': 'Timestamp',
            'college_type': 'College Type',
            'custom_notes': 'Extraction Directives'
        }
        df = df.rename(columns=column_mapping)
        
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Contacts')
            
        excel_buffer.seek(0)
        return send_file(
            excel_buffer,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name="scraped_college_contacts.xlsx"
        )
    except Exception as e:
        flash(f"Excel export failed: {e}", "error")
        return redirect(url_for("results"))

def run_bulk_scrape(batch_id, urls, session_id=None, custom_directives=None):
    """Background thread job that processes bulk scraping tasks concurrently."""
    batch = scraping_batches.get(batch_id)
    if not batch:
        return
        
    from concurrent.futures import ThreadPoolExecutor
    import threading
    
    progress_lock = threading.Lock()
    completed_count = 0
    
    def process_single_url(raw_url):
        nonlocal completed_count
        url = raw_url.strip()
        if not url:
            return
            
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
            
        college_name = "Unknown College"
        try:
            # Run scraper
            contacts = scraper.scrape_college_website(url)
            
            if contacts:
                college_name = contacts[0].get('college_name', college_name)
                college_type = discovery_engine.classify_college_type(college_name, url)
                
                # Insert contacts to DB scoped to user session
                for contact in contacts:
                    contact['session_id'] = session_id
                    contact['college_type'] = college_type
                    contact['custom_notes'] = custom_directives or 'Bulk Scrape'
                    database.insert_contact(contact)
                    
                database.delete_duplicates(session_id)
                
                with progress_lock:
                    batch['completed_colleges'].append({
                        'url': url,
                        'college_name': college_name,
                        'status': 'success',
                        'count': len(contacts)
                    })
            else:
                try:
                    html, _ = scraper.fetch_page(url)
                    if html:
                        college_name = scraper.get_college_name_from_html(html, url)
                except:
                    pass
                
                with progress_lock:
                    batch['completed_colleges'].append({
                        'url': url,
                        'college_name': college_name,
                        'status': 'warning',
                        'count': 0
                    })
        except Exception as e:
            print(f"Bulk scrape error for {url}: {e}")
            with progress_lock:
                batch['completed_colleges'].append({
                    'url': url,
                    'college_name': college_name,
                    'status': 'failed',
                    'error': str(e)
                })
        
        with progress_lock:
            completed_count += 1
            batch['current_index'] = completed_count
            batch['current_college'] = url
            
    # Run concurrently with up to 4 worker threads
    with ThreadPoolExecutor(max_workers=4) as executor:
        executor.map(process_single_url, urls)
        
    batch['status'] = 'completed'

@app.route("/scrape_bulk", methods=["POST"])
def scrape_bulk():
    """Handles bulk URL scraping from uploaded Excel/CSV file."""
    if 'file' not in request.files:
        return {"status": "error", "message": "No file part in request."}, 400
        
    file = request.files['file']
    if file.filename == '':
        return {"status": "error", "message": "No file selected."}, 400
        
    custom_directives = request.form.get("custom_directives", "").strip()
        
    try:
        # Load the file
        filename = file.filename.lower()
        if filename.endswith('.csv'):
            df = pd.read_csv(file)
        elif filename.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(file)
        else:
            return {"status": "error", "message": "Invalid file format. Please upload a CSV or Excel file."}, 400
            
        # Try to find a URL column
        url_col = None
        for col in df.columns:
            col_clean = col.lower().strip()
            if 'url' in col_clean or 'website' in col_clean or 'link' in col_clean:
                url_col = col
                break
                
        if url_col is None:
            # Fallback to the first column
            url_col = df.columns[0]
            
        # Extract and clean URLs
        urls = df[url_col].dropna().astype(str).tolist()
        urls = [url.strip() for url in urls if url.strip()]
        
        if not urls:
            return {"status": "error", "message": "No URLs found in the uploaded file."}, 400
            
        # Start background task
        batch_id = uuid.uuid4().hex
        scraping_batches[batch_id] = {
            'status': 'running',
            'total': len(urls),
            'current_index': 0,
            'current_college': '',
            'completed_colleges': []
        }
        
        session_id = session.get('user_session_id')
        thread = threading.Thread(target=run_bulk_scrape, args=(batch_id, urls, session_id, custom_directives))
        thread.daemon = True
        thread.start()
        
        return {
            "status": "success",
            "batch_id": batch_id,
            "total": len(urls)
        }, 200
        
    except Exception as e:
        return {"status": "error", "message": f"Failed to process file: {str(e)}"}, 400

@app.route("/scrape_status/<batch_id>")
def scrape_status(batch_id):
    """API endpoint to fetch the real-time progress of a bulk scraping run."""
    batch = scraping_batches.get(batch_id)
    if not batch:
        return {"status": "error", "message": "Batch not found"}, 404
        
    return batch

@app.route("/export/grouped_excel")
def export_grouped_excel():
    """Exports scraped contacts separated by sheet per college."""
    try:
        session_id = session.get('user_session_id')
        contacts = database.get_all_contacts(session_id)
        if not contacts:
            flash("No data available to export.", "warning")
            return redirect(url_for("results"))
            
        df = pd.DataFrame(contacts)
        if 'id' in df.columns:
            df = df.drop(columns=['id'])
            
        # Smarter Pandas deduplication prior to export
        df = df.drop_duplicates(subset=['college_name', 'email', 'phone', 'person_name'], keep='first')
            
        # Group by college name
        grouped = df.groupby('college_name')
        
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            for college_name, group in grouped:
                # Sanitize sheet name: max 31 chars, remove forbidden characters: \ / ? * [ ] :
                sheet_name = re.sub(r'[\\/\?\*\[\]\:]', '', str(college_name))
                sheet_name = sheet_name[:30].strip() or "College"
                
                # Format columns
                group_clean = group.rename(columns={
                    'college_name': 'College Name',
                    'website_url': 'Website URL',
                    'person_name': 'Contact Name',
                    'role': 'Role',
                    'department': 'Department',
                    'email': 'Email Address',
                    'phone': 'Phone / Contact',
                    'address': 'Office Address',
                    'source_url': 'Scraped Page URL',
                    'scraped_at': 'Timestamp',
                    'college_type': 'College Type',
                    'custom_notes': 'Extraction Directives'
                })
                group_clean.to_excel(writer, index=False, sheet_name=sheet_name)
                
        excel_buffer.seek(0)
        return send_file(
            excel_buffer,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name="grouped_college_contacts.xlsx"
        )
    except Exception as e:
        flash(f"Grouped Excel export failed: {e}", "error")
        return redirect(url_for("results"))

@app.route("/export/zip_csv")
def export_zip_csv():
    """Exports scraped contacts as individual CSV files packaged in a single ZIP."""
    try:
        session_id = session.get('user_session_id')
        contacts = database.get_all_contacts(session_id)
        if not contacts:
            flash("No data available to export.", "warning")
            return redirect(url_for("results"))
            
        df = pd.DataFrame(contacts)
        if 'id' in df.columns:
            df = df.drop(columns=['id'])
            
        # Smarter Pandas deduplication prior to export
        df = df.drop_duplicates(subset=['college_name', 'email', 'phone', 'person_name'], keep='first')
            
        grouped = df.groupby('college_name')
        
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for college_name, group in grouped:
                # Sanitize file name
                file_name = re.sub(r'[\\/\?\*\[\]\:\s]', '_', str(college_name))
                file_name = f"{file_name[:40].strip()}_contacts.csv"
                
                group_clean = group.rename(columns={
                    'college_name': 'College Name',
                    'website_url': 'Website URL',
                    'person_name': 'Contact Name',
                    'role': 'Role',
                    'department': 'Department',
                    'email': 'Email Address',
                    'phone': 'Phone / Contact',
                    'address': 'Office Address',
                    'source_url': 'Scraped Page URL',
                    'scraped_at': 'Timestamp',
                    'college_type': 'College Type',
                    'custom_notes': 'Extraction Directives'
                })
                
                # Fix ZIP file corruption: encode to UTF-8 bytes explicitly before writing to the ZIP
                csv_data = group_clean.to_csv(index=False).encode('utf-8')
                zip_file.writestr(file_name, csv_data)
                
        zip_buffer.seek(0)
        return send_file(
            zip_buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name="college_contacts_csvs.zip"
        )
    except Exception as e:
        flash(f"ZIP export failed: {e}", "error")
        return redirect(url_for("results"))


# ============================================================
# SELECTIVE EXPORTS AND DELETIONS
# ============================================================

@app.route("/export/college/excel")
def export_college_excel():
    """Exports contacts of a specific college as an Excel workbook, scoped to session."""
    college_name = request.args.get("college", "").strip()
    if not college_name:
        flash("College name is required for export.", "error")
        return redirect(url_for("results"))
    try:
        session_id = session.get('user_session_id')
        contacts = database.get_all_contacts(session_id)
        college_contacts = [c for c in contacts if c['college_name'] == college_name]
        
        if not college_contacts:
            flash(f"No contacts found for {college_name}.", "warning")
            return redirect(url_for("results"))
            
        df = pd.DataFrame(college_contacts)
        if 'id' in df.columns:
            df = df.drop(columns=['id'])
            
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            sheet_name = re.sub(r'[\\/\?\*\[\]\:]', '', college_name)
            sheet_name = sheet_name[:30].strip() or "College"
            
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
                'scraped_at': 'Timestamp'
            })
            df_clean.to_excel(writer, index=False, sheet_name=sheet_name)
            
        excel_buffer.seek(0)
        filename = re.sub(r'[\\/\?\*\[\]\:\s]', '_', college_name)
        return send_file(
            excel_buffer,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"{filename[:40]}_contacts.xlsx"
        )
    except Exception as e:
        flash(f"Excel export failed for {college_name}: {e}", "error")
        return redirect(url_for("results"))


@app.route("/export/college/csv")
def export_college_csv():
    """Exports contacts of a specific college as a CSV file, scoped to session."""
    college_name = request.args.get("college", "").strip()
    if not college_name:
        flash("College name is required for export.", "error")
        return redirect(url_for("results"))
    try:
        session_id = session.get('user_session_id')
        contacts = database.get_all_contacts(session_id)
        college_contacts = [c for c in contacts if c['college_name'] == college_name]
        
        if not college_contacts:
            flash(f"No contacts found for {college_name}.", "warning")
            return redirect(url_for("results"))
            
        df = pd.DataFrame(college_contacts)
        if 'id' in df.columns:
            df = df.drop(columns=['id'])
            
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
            'scraped_at': 'Timestamp'
        })
        
        csv_buffer = io.StringIO()
        df_clean.to_csv(csv_buffer, index=False)
        
        mem_file = io.BytesIO()
        mem_file.write(csv_buffer.getvalue().encode('utf-8'))
        mem_file.seek(0)
        
        filename = re.sub(r'[\\/\?\*\[\]\:\s]', '_', college_name)
        return send_file(
            mem_file,
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"{filename[:40]}_contacts.csv"
        )
    except Exception as e:
        flash(f"CSV export failed for {college_name}: {e}", "error")
        return redirect(url_for("results"))


@app.route("/delete_contact/<int:contact_id>", methods=["POST"])
def delete_contact(contact_id):
    """Deletes a single contact record from the database, scoped to session."""
    try:
        session_id = session.get('user_session_id')
        deleted_count = database.delete_contact(contact_id, session_id)
        if deleted_count > 0:
            return {"status": "success", "message": "Contact deleted successfully."}, 200
        else:
            return {"status": "error", "message": "Contact not found."}, 404
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500


@app.route("/delete_college", methods=["POST"])
def delete_college():
    """Deletes all contacts belonging to a specific college, scoped to session."""
    try:
        data = request.get_json() or {}
        college_name = data.get("college_name", "").strip()
        if not college_name:
            return {"status": "error", "message": "College name is required."}, 400
            
        session_id = session.get('user_session_id')
        deleted_count = database.delete_college(college_name, session_id)
        if deleted_count > 0:
            return {"status": "success", "message": f"Deleted {deleted_count} contacts for {college_name}."}, 200
        else:
            return {"status": "error", "message": "College not found or no contacts to delete."}, 404
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500


@app.route("/refiner")
def refiner():
    """Renders the data refiner portal page."""
    return render_template("refiner.html")

@app.route("/refine", methods=["POST"])
def refine():
    """Processes uploaded raw contact sheet and cleans it using data_refiner heuristics."""
    if 'file' not in request.files:
        flash("No file uploaded.", "error")
        return redirect(url_for("refiner"))
        
    file = request.files['file']
    if file.filename == '':
        flash("No file selected.", "error")
        return redirect(url_for("refiner"))
        
    try:
        filename = file.filename.lower()
        if filename.endswith('.csv'):
            df = pd.read_csv(file)
        elif filename.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(file)
        else:
            flash("Invalid file format. Please upload a CSV or Excel file.", "error")
            return redirect(url_for("refiner"))
            
        # Run refinement
        refined_df, removed_df, metrics = data_refiner.refine_dataframe(df)
        
        # Save refined and removed files in the exports folder using UUID
        file_id = uuid.uuid4().hex
        exports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exports')
        os.makedirs(exports_dir, exist_ok=True)
        
        refined_filepath = os.path.join(exports_dir, f"refined_{file_id}.csv")
        refined_df.to_csv(refined_filepath, index=False)
        
        removed_filepath = os.path.join(exports_dir, f"removed_{file_id}.csv")
        removed_df.to_csv(removed_filepath, index=False)
        
        # Save ID and metrics in Flask session
        session['refined_file_id'] = file_id
        session['refined_metrics'] = metrics
        session['original_filename'] = file.filename
        
        flash("Data refined successfully!", "success")
        return redirect(url_for("refiner_results"))
        
    except Exception as e:
        flash(f"Data refinement failed: {str(e)}", "error")
        return redirect(url_for("refiner"))

@app.route("/refiner/results")
def refiner_results():
    """Displays dashboard with refinement statistics and data preview."""
    file_id = session.get('refined_file_id')
    metrics = session.get('refined_metrics')
    orig_filename = session.get('original_filename', 'data')
    
    if not file_id or not metrics:
        flash("No refined data found. Please upload a file first.", "warning")
        return redirect(url_for("refiner"))
        
    try:
        exports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exports')
        filepath = os.path.join(exports_dir, f"refined_{file_id}.csv")
        removed_filepath = os.path.join(exports_dir, f"removed_{file_id}.csv")
        
        if not os.path.exists(filepath):
            flash("Refined file was cleaned or missing from server. Please re-upload.", "error")
            return redirect(url_for("refiner"))
            
        df = pd.read_csv(filepath).fillna('')
        preview_data = df.head(50).to_dict(orient='records')
        
        removed_data = []
        if os.path.exists(removed_filepath):
            df_rem = pd.read_csv(removed_filepath).fillna('')
            removed_data = df_rem.head(50).to_dict(orient='records')
            
        return render_template(
            "refiner_results.html", 
            metrics=metrics, 
            preview_data=preview_data,
            removed_data=removed_data,
            file_id=file_id,
            orig_filename=orig_filename,
            columns=df.columns.tolist()
        )
    except Exception as e:
        flash(f"Error loading refined data preview: {e}", "error")
        return redirect(url_for("refiner"))


@app.route("/refiner/query/<file_id>", methods=["POST"])
def refiner_query(file_id):
    """
    AI-powered dynamic filtering on the refined dataset using Gemini.
    Generates a SQL query from natural language and runs it in-memory.
    """
    try:
        data = request.get_json() or {}
        user_query = data.get("query", "").strip()
        
        if not user_query:
            return {"status": "error", "message": "Query string is required."}, 400
            
        exports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exports')
        filepath = os.path.join(exports_dir, f"refined_{file_id}.csv")
        
        if not os.path.exists(filepath):
            return {"status": "error", "message": "Refined data file not found."}, 404
            
        df = pd.read_csv(filepath).fillna('')
        
        # Setup in-memory SQLite database
        import sqlite3
        conn = sqlite3.connect(":memory:")
        df.to_sql("refined_temp", conn, index=False)
        
        # AI SQL generation
        sql_query = "FALLBACK"
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
        
        if GEMINI_API_KEY:
            try:
                import google.generativeai as genai
                genai.configure(api_key=GEMINI_API_KEY)
                
                prompt = f"""You are a database query translator. Given a table 'refined_temp' with columns:
- college_name (text)
- website_url (text)
- person_name (text)
- role (text)
- department (text)
- email (text)
- phone (text)
- address (text)
- source_url (text)

Generate a single SQLite SELECT statement that fulfills the user request.
User request: "{user_query}"

RULES:
1. Return ONLY the SQL query string. No formatting, no markdown, no other text.
2. The query must start with 'SELECT * FROM refined_temp'.
3. Use case-insensitive LIKE matches for text fields, e.g., "WHERE role LIKE '%hod%'" or "WHERE college_name LIKE '%chennai%'".
4. Do NOT attempt UPDATE, DELETE, or INSERT statements. ONLY read SELECT statements are allowed.
5. If the request cannot be translated to a filter, return: SELECT * FROM refined_temp

SQL Query:"""

                model = genai.GenerativeModel("gemini-2.0-flash")
                response = model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.0,
                        max_output_tokens=300
                    )
                )
                
                sql_query = response.text.strip().replace("```sql", "").replace("```", "").replace("\n", " ").strip()
            except Exception as gemini_err:
                print(f"[Refiner AI Query] Gemini error: {gemini_err}. Falling back to simple keyword search.")
                sql_query = "FALLBACK"
        else:
            print("[Refiner AI Query] No Gemini API key. Falling back to simple keyword search.")
            sql_query = "FALLBACK"
            
        # Run query
        cursor = conn.cursor()
        try:
            if sql_query == "FALLBACK":
                raise Exception("AI Offline Fallback Triggered")
                
            # Simple security validation
            sql_query_lower = sql_query.lower()
            forbidden = ["delete", "update", "insert", "drop", "alter", "create", "replace", "truncate"]
            if not sql_query_lower.startswith("select") or any(f in sql_query_lower for f in forbidden):
                sql_query = "SELECT * FROM refined_temp"
                
            cursor.execute(sql_query)
            cols = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
            results = [dict(zip(cols, row)) for row in rows]
        except Exception as sql_err:
            print(f"[Refiner AI Query] SQL Execution/Fallback: {sql_err}.")
            cursor.execute("SELECT * FROM refined_temp WHERE college_name LIKE ? OR person_name LIKE ? OR department LIKE ? OR role LIKE ? OR email LIKE ?",
                           (f"%{user_query}%", f"%{user_query}%", f"%{user_query}%", f"%{user_query}%", f"%{user_query}%"))
            cols = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
            results = [dict(zip(cols, row)) for row in rows]
            sql_query = f"Simple Keyword Match (AI Offline) for: {user_query}"
            
        conn.close()
        
        return {
            "status": "success",
            "query": sql_query,
            "count": len(results),
            "data": results
        }, 200
        
    except Exception as e:
        return {"status": "error", "message": f"AI Query failed: {str(e)}"}, 500

@app.route("/refiner/export/<export_format>/<file_id>")
def refiner_export(export_format, file_id):
    """Downloads the refined data file in requested format."""
    try:
        exports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exports')
        filepath = os.path.join(exports_dir, f"refined_{file_id}.csv")
        
        if not os.path.exists(filepath):
            flash("Refined file not found.", "error")
            return redirect(url_for("refiner"))
            
        orig_filename = session.get('original_filename', 'data')
        base_name = os.path.splitext(orig_filename)[0]
        download_name = f"{base_name}_cleaned"
        
        if export_format == 'csv':
            return send_file(
                filepath,
                mimetype="text/csv",
                as_attachment=True,
                download_name=f"{download_name}.csv"
            )
        elif export_format == 'excel':
            df = pd.read_csv(filepath)
            df = df.fillna('')
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df_excel = df.rename(columns={
                    'college_name': 'College Name',
                    'website_url': 'Website URL',
                    'person_name': 'Contact Name',
                    'role': 'Role',
                    'department': 'Department',
                    'email': 'Email Address',
                    'phone': 'Phone / Contact',
                    'address': 'Office Address',
                    'source_url': 'Scraped Page URL'
                })
                df_excel.to_excel(writer, index=False, sheet_name='Cleaned Contacts')
            excel_buffer.seek(0)
            return send_file(
                excel_buffer,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                as_attachment=True,
                download_name=f"{download_name}.xlsx"
            )
        else:
            flash("Unsupported export format.", "error")
            return redirect(url_for("refiner_results"))
            
    except Exception as e:
        flash(f"Refined export failed: {e}", "error")
        return redirect(url_for("refiner_results"))

# ============================================================
# AI DISCOVERY ENDPOINTS
# ============================================================

@app.route("/discover", methods=["POST"])
def discover():
    """
    Starts an AI-powered discovery job.
    Accepts JSON body with:
    - mode: "region", "names", or "urls"
    - input: region string, comma/newline-separated names, or list of URLs
    - institution_type: "all", "engineering", "medical", "arts", "science"
    - custom_directives: Chatbox guidelines for contact extraction
    """
    try:
        data = request.get_json()
        if not data:
            return {"status": "error", "message": "No data provided."}, 400
        
        mode = data.get("mode", "").strip()
        raw_input = data.get("input", "").strip()
        institution_type = data.get("institution_type", "all").strip()
        custom_directives = data.get("custom_directives", "").strip()
        
        if not mode or not raw_input:
            return {"status": "error", "message": "Please provide a mode and input."}, 400
        
        session_id = session.get('user_session_id')
        
        if mode == "region":
            # input is a region string like "Tamil Nadu"
            job_id = discovery_engine.start_discovery_job("region", raw_input, institution_type, session_id=session_id, custom_directives=custom_directives)
        
        elif mode == "names":
            # input is comma or newline separated college names
            names = [n.strip() for n in re.split(r'[,\n]', raw_input) if n.strip()]
            if not names:
                return {"status": "error", "message": "No college names provided."}, 400
            job_id = discovery_engine.start_discovery_job("names", names, institution_type, session_id=session_id, custom_directives=custom_directives)
        
        elif mode == "urls":
            # input is comma or newline separated URLs
            urls = [u.strip() for u in re.split(r'[,\n]', raw_input) if u.strip()]
            if not urls:
                return {"status": "error", "message": "No URLs provided."}, 400
            job_id = discovery_engine.start_discovery_job("urls", urls, institution_type, session_id=session_id, custom_directives=custom_directives)
        
        else:
            return {"status": "error", "message": f"Unknown mode: {mode}"}, 400
        
        return {
            "status": "success",
            "job_id": job_id,
            "mode": mode
        }, 200
        
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500


@app.route("/discover_status/<job_id>")
def discover_status(job_id):
    """Returns the real-time progress of an AI discovery job."""
    job = discovery_engine.get_job_status(job_id)
    if not job:
        return {"status": "error", "message": "Job not found."}, 404
    return job


@app.route("/discover_upload", methods=["POST"])
def discover_upload():
    """
    Handles file upload for AI discovery.
    Reads college names or URLs from uploaded CSV/Excel and starts a discovery job.
    """
    if 'file' not in request.files:
        return {"status": "error", "message": "No file uploaded."}, 400
    
    file = request.files['file']
    if file.filename == '':
        return {"status": "error", "message": "No file selected."}, 400
    
    try:
        filename = file.filename.lower()
        if filename.endswith('.csv'):
            df = pd.read_csv(file)
        elif filename.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(file)
        else:
            return {"status": "error", "message": "Invalid file format. Upload CSV or Excel."}, 400
        
        if df.empty:
            return {"status": "error", "message": "File is empty."}, 400
        
        # Auto-detect: does the file contain URLs or college names?
        first_col = df.columns[0]
        
        # Check for URL-specific column names
        url_col = None
        name_col = None
        for col in df.columns:
            col_lower = col.lower().strip()
            if any(kw in col_lower for kw in ['url', 'website', 'link', 'site']):
                url_col = col
            if any(kw in col_lower for kw in ['name', 'college', 'institution', 'university']):
                name_col = col
        
        items = []
        mode = "names"  # default
        
        if url_col:
            items = df[url_col].dropna().astype(str).tolist()
            # Check if items look like URLs
            if items and ('http' in items[0] or '.com' in items[0] or '.in' in items[0] or '.edu' in items[0]):
                mode = "urls"
        elif name_col:
            items = df[name_col].dropna().astype(str).tolist()
            mode = "names"
        else:
            # Use first column and auto-detect
            items = df[first_col].dropna().astype(str).tolist()
            if items and ('http' in items[0] or '.' in items[0] and ' ' not in items[0]):
                mode = "urls"
            else:
                mode = "names"
        
        items = [item.strip() for item in items if item.strip()]
        
        if not items:
            return {"status": "error", "message": "No valid entries found in file."}, 400
        
        institution_type = request.form.get("institution_type", "all")
        custom_directives = request.form.get("custom_directives", "").strip()
        session_id = session.get('user_session_id')
        job_id = discovery_engine.start_discovery_job(mode, items, institution_type, session_id=session_id, custom_directives=custom_directives)
        
        return {
            "status": "success",
            "job_id": job_id,
            "mode": mode,
            "total": len(items)
        }, 200
        
    except Exception as e:
        return {"status": "error", "message": f"Failed to process file: {str(e)}"}, 500


@app.route("/mock_college")
def mock_college():
    """Returns a mock college website with structured and unstructured contact details."""
    return """
    <html>
        <head>
            <title>Mock Institute of Technology (MIT)</title>
        </head>
        <body>
            <h1>Welcome to Mock Institute of Technology (MIT) - Official Website</h1>
            <p>MIT is a premier institution offering high-quality technical education.</p>
            
            <div id="contact-section">
                <h2>Administration Contacts</h2>
                <table>
                    <tr>
                        <td>Principal Office</td>
                        <td>Dr. Aris Thorne</td>
                        <td>principal@mockcollege.edu.in</td>
                        <td>044-22334455</td>
                    </tr>
                    <tr>
                        <td>Computer Science HOD</td>
                        <td>Prof. Clara Oswald</td>
                        <td>clara.oswald@mockcollege.edu.in</td>
                        <td>9876543210</td>
                    </tr>
                    <tr>
                        <td>Placement Cell Head</td>
                        <td>Mr. Danny Pink</td>
                        <td>placement@mockcollege.edu.in</td>
                        <td>9876501234</td>
                    </tr>
                </table>
            </div>
            
            <footer>
                <p>Address: 123 Education Boulevard, Chennai, Tamil Nadu, Pincode: 600001</p>
                <p>&copy; 2026 Mock Institute of Technology. All rights reserved.</p>
            </footer>
        </body>
    </html>
    """


if __name__ == "__main__":
    # Create required export directory if missing
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exports'), exist_ok=True)
    app.run(debug=True, host="127.0.0.1", port=5000)

