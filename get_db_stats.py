#!/usr/bin/env python3
import sqlite3
import os
from datetime import datetime
from models import get_connection

def get_db_stats():
    """Get real statistics from the database"""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Get total downloads count
        cur.execute("SELECT COUNT(*) FROM downloads")
        total_downloads = cur.fetchone()[0]
        
        # Get total errors count  
        cur.execute("SELECT COUNT(*) FROM errors")
        total_errors = cur.fetchone()[0]
        
        # Get total sources count
        cur.execute("SELECT COUNT(*) FROM (SELECT source FROM downloads GROUP BY source)")
        total_sources = cur.fetchone()[0]
        
        # Calculate success rate
        total_operations = total_downloads + total_errors
        if total_operations > 0:
            success_rate = (total_downloads / total_operations) * 100
        else:
            success_rate = 100.0
            
        return {
            "total_downloads": total_downloads,
            "total_errors": total_errors, 
            "total_sources": total_sources,
            "success_rate": success_rate,
            "total_operations": total_operations
        }
        
    finally:
        conn.close()

if __name__ == "__main__":
    stats = get_db_stats()
    print(f"Total Downloads: {stats['total_downloads']}")
    print(f"Total Errors: {stats['total_errors']}")
    print(f"Total Sources: {stats['total_sources']}")
    print(f"Success Rate: {stats['success_rate']:.1f}%")
    print(f"Total Operations: {stats['total_operations']}")