#!/usr/bin/env python3
import sqlite3
import os
from datetime import datetime
import re

# Database path
DB_PATH = os.path.abspath('cooldl.db')

def convert_timestamp(timestamp_str):
    """Convert timestamp from '2026/02/04, 09:41 AM' to ISO format"""
    try:
        # Parse the timestamp
        dt = datetime.strptime(timestamp_str, '%Y/%m/%d, %I:%M %p')
        # Convert to ISO format with UTC timezone
        return dt.isoformat()
    except ValueError:
        # Fallback to current time if parsing fails
        return datetime.now().isoformat()

def generate_file_id():
    """Generate a random 5-digit file_id"""
    import random
    import string
    return ''.join(random.choices(string.digits, k=5))

def get_user_name(chat_id):
    """Get user name from users table"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    try:
        cur.execute("SELECT name FROM users WHERE chat_id = ?", (chat_id,))
        row = cur.fetchone()
        return row['name'] if row and row['name'] else f"User_{chat_id}"
    except:
        return f"User_{chat_id}"
    finally:
        conn.close()

def migrate_logs_to_downloads():
    """Migrate successful download logs to downloads table"""
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    try:
        # Get all successful downloads from logs
        cur.execute("""
            SELECT l.timestamp, l.username, l.chat_id, l.status
            FROM logs l
            WHERE l.action = 'Downloaded' AND l.status = 'Success'
            AND l.chat_id IS NOT NULL
            ORDER BY l.timestamp
        """)
        
        log_records = cur.fetchall()
        print(f"Found {len(log_records)} log records to migrate")
        
        inserted_count = 0
        for record in log_records:
            log_timestamp = record['timestamp']
            log_username = record['username']
            log_chat_id = record['chat_id']
            
            # Skip if chat_id is None or 0
            if not log_chat_id:
                continue
                
            # Convert timestamp format
            iso_timestamp = convert_timestamp(log_timestamp)
            
            # Generate a unique file_id
            file_id = generate_file_id()
            
            # Get user name
            user_name = get_user_name(log_chat_id)
            
            # Create a record with placeholder data
            # Use the username as filename for now
            filename = f"File{file_id}.mp4"
            
            # Default values for missing fields
            url = "https://example.com/migrated"
            source = "Unknown"
            user_id = f"user_{log_chat_id}"
            file_size = 0
            session = None
            
            try:
                # Insert the record
                cur.execute("""
                    INSERT INTO downloads 
                    (file_id, timestamp, username, chat_id, name, url, source, user_id, filename, file_size, session)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    file_id, iso_timestamp, log_username, log_chat_id, user_name,
                    url, source, user_id, filename, file_size, session
                ))
                
                inserted_count += 1
                if inserted_count % 100 == 0:
                    conn.commit()
                    print(f"Inserted {inserted_count} records...")
                    
            except sqlite3.IntegrityError as e:
                # Skip if there's a primary key conflict
                print(f"Skipping duplicate file_id: {file_id}")
                continue
            except Exception as e:
                print(f"Error inserting record: {e}")
                continue
        
        conn.commit()
        print(f"Migration completed. Inserted {inserted_count} records.")
        
    except Exception as e:
        print(f"Error during migration: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_logs_to_downloads()