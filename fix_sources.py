#!/usr/bin/env python3
import sqlite3
import os

def fix_download_sources():
    """Update download sources based on URL patterns"""
    conn = sqlite3.connect(os.path.abspath('cooldl.db'))
    cur = conn.cursor()
    
    try:
        # Update TikTok URLs
        cur.execute("""
            UPDATE downloads 
            SET source = 'TikTok' 
            WHERE (url LIKE '%tiktok.com%' OR url LIKE '%vt.tiktok.com%') 
            AND source = 'Unknown'
        """)
        
        # Update X/Twitter URLs  
        cur.execute("""
            UPDATE downloads 
            SET source = 'X' 
            WHERE (url LIKE '%twitter.com%' OR url LIKE '%x.com%') 
            AND source = 'Unknown'
        """)
        
        # Update Instagram URLs
        cur.execute("""
            UPDATE downloads 
            SET source = 'Instagram' 
            WHERE url LIKE '%instagram.com%' 
            AND source = 'Unknown'
        """)
        
        # Update YouTube URLs
        cur.execute("""
            UPDATE downloads 
            SET source = 'YouTube' 
            WHERE (url LIKE '%youtube.com%' OR url LIKE '%youtu.be%') 
            AND source = 'Unknown'
        """)
        
        # Update Snapchat URLs
        cur.execute("""
            UPDATE downloads 
            SET source = 'Snapchat' 
            WHERE url LIKE '%snapchat.com%' 
            AND source = 'Unknown'
        """)
        
        # Update Tumblr URLs
        cur.execute("""
            UPDATE downloads 
            SET source = 'Tumblr' 
            WHERE url LIKE '%tumblr.com%' 
            AND source = 'Unknown'
        """)
        
        conn.commit()
        
        # Check updated counts
        cur.execute("SELECT source, COUNT(*) FROM downloads GROUP BY source ORDER BY COUNT(*) DESC")
        results = cur.fetchall()
        
        print("Updated source distribution:")
        for source, count in results:
            print(f"{source}: {count}")
            
        print(f"Total updates completed!")
        
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    fix_download_sources()