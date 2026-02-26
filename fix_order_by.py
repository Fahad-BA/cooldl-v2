#!/usr/bin/env python3
"""
Emergency fix for SQLite ORDER BY parameter issue
"""

import re

def fix_order_by_params():
    with open('main.py', 'r') as f:
        content = f.read()
    
    # Find the problematic ORDER BY ? queries
    # We need to replace parameter placeholders with safe string formatting
    
    # Pattern 1: Static ORDER BY (safe)
    # Pattern 2: Dynamic ORDER BY with safe_columns mapping
    
    # Fix the api_users endpoint (around line 340)
    old_pattern1 = r'''cur\.execute\(f"""
            SELECT u\.chat_id, u\.name, u\.username, 
                   COUNT\(d\.chat_id\) as downloads_count,
                   MAX\(d\.timestamp\) as last_used
            FROM users u 
            LEFT JOIN downloads d ON u\.chat_id = d\.chat_id 
            GROUP BY u\.chat_id, u\.name, u\.username
            ORDER BY \?
            LIMIT \? OFFSET \?
        """, \(order_by_clause, ITEMS_PER_PAGE, offset\)\)'''
    
    new_pattern1 = '''cur.execute(f"""
            SELECT u.chat_id, u.name, u.username, 
                   COUNT(d.chat_id) as downloads_count,
                   MAX(d.timestamp) as last_used
            FROM users u 
            LEFT JOIN downloads d ON u.chat_id = d.chat_id 
            GROUP BY u.chat_id, u.name, u.username
            ORDER BY {order_by_clause}
            LIMIT ? OFFSET ?
        """, (ITEMS_PER_PAGE, offset))'''
    
    content = re.sub(old_pattern1, new_pattern1, content, flags=re.MULTILINE)
    
    # Fix the dashboard endpoint (around line 187)
    old_pattern2 = r'''cur\.execute\(f"""
            SELECT u\.chat_id, u\.name, u\.username, 
                   COUNT\(d\.chat_id\) as downloads_count,
                   MAX\(d\.timestamp\) as last_used
            FROM users u 
            LEFT JOIN downloads d ON u\.chat_id = d\.chat_id 
            GROUP BY u\.chat_id, u\.name, u\.username
            ORDER BY \?
            LIMIT \? OFFSET \?
        """, \(order_by_clause, ITEMS_PER_PAGE, users_offset\)\)'''
    
    new_pattern2 = '''cur.execute(f"""
            SELECT u.chat_id, u.name, u.username, 
                   COUNT(d.chat_id) as downloads_count,
                   MAX(d.timestamp) as last_used
            FROM users u 
            LEFT JOIN downloads d ON u.chat_id = d.chat_id 
            GROUP BY u.chat_id, u.name, u.username
            ORDER BY {order_by_clause}
            LIMIT ? OFFSET ?
        """, (ITEMS_PER_PAGE, users_offset))'''
    
    content = re.sub(old_pattern2, new_pattern2, content, flags=re.MULTILINE)
    
    with open('main.py', 'w') as f:
        f.write(content)
    
    print("✅ Fixed ORDER BY parameter issue")

if __name__ == "__main__":
    fix_order_by_params()
