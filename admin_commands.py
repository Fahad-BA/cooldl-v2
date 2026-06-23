import logging
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from blocks import (
    block_user, 
    unblock_user, 
    get_blocked_users, 
    check_user_block_status,
    is_user_blocked
)
from user_commands import health_command

async def block_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /block command to block a user."""
    if not context.args:
        await update.message.reply_text(
            "Usage: /block <chat_id|username|filename> [reason]\n"
            "Example: /block 123456789 spam\n"
            "Example: /block @user123\n"
            "Example: /block video_123.mp4"
        )
        return
    
    identifier = context.args[0]
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else ""
    
    # Determine if identifier is chat_id, username, or filename
    chat_id = None
    username = None
    filename = None
    
    try:
        # Try to parse as chat_id (number)
        chat_id = int(identifier)
    except ValueError:
        # Check if it's a username (starts with @)
        if identifier.startswith('@'):
            username = identifier[1:]  # Remove @ symbol
        else:
            # Assume it's a filename
            filename = identifier
    
    # Get admin info
    admin_name = update.effective_user.username or str(update.effective_user.id)
    
    # Block the user
    result = block_user(
        chat_id=chat_id,
        username=username,
        filename=filename,
        reason=reason,
        blocked_by=admin_name
    )
    
    if result["success"]:
        response = f"✅ {result['message']}"
        if reason:
            response += f"\nReason: {reason}"
    else:
        response = f"❌ {result['message']}"
    
    await update.message.reply_text(response)

async def unblock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /unblock command to unblock a user."""
    if not context.args:
        await update.message.reply_text(
            "Usage: /unblock <chat_id|username|filename>\n"
            "Example: /unblock 123456789\n"
            "Example: /unblock @user123\n"
            "Example: /unblock video_123.mp4"
        )
        return
    
    identifier = context.args[0]
    
    # Determine if identifier is chat_id, username, or filename
    chat_id = None
    username = None
    filename = None
    
    try:
        # Try to parse as chat_id (number)
        chat_id = int(identifier)
    except ValueError:
        # Check if it's a username (starts with @)
        if identifier.startswith('@'):
            username = identifier[1:]  # Remove @ symbol
        else:
            # Assume it's a filename
            filename = identifier
    
    # Unblock the user
    result = unblock_user(
        chat_id=chat_id,
        username=username,
        filename=filename
    )
    
    if result["success"]:
        response = f"✅ {result['message']}"
    else:
        response = f"❌ {result['message']}"
    
    await update.message.reply_text(response)

async def blocked_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /blocked list command to show all blocked users."""
    blocked_users = get_blocked_users()
    
    if not blocked_users:
        await update.message.reply_text("📋 No blocked users found.")
        return
    
    response = "🚫 *Blocked Users List:*\n\n"
    
    for i, user in enumerate(blocked_users, 1):
        response += f"{i}. **Chat ID:** {user['chat_id']}\n"
        
        if user['username']:
            response += f"   **Username:** @{user['username']}\n"
            
        if user['filename']:
            response += f"   **Filename:** {user['filename']}\n"
            
        if user['reason']:
            response += f"   **Reason:** {user['reason']}\n"
            
        response += f"   **Blocked At:** {user['blocked_at']}\n"
        
        if user['blocked_by']:
            response += f"   **Blocked By:** {user['blocked_by']}\n"
        
        response += "\n"
    
    await update.message.reply_text(response, parse_mode='Markdown')

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /check command to check if a user is blocked."""
    if not context.args:
        await update.message.reply_text(
            "Usage: /check <chat_id>\n"
            "Example: /check 123456789"
        )
        return
    
    try:
        chat_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid chat_id. Please provide a numeric chat_id.")
        return
    
    block_info = check_user_block_status(chat_id)
    
    if block_info:
        response = f"🚫 **User {chat_id} is BLOCKED**\n\n"
        response += f"**Reason:** {block_info['reason'] or 'Not specified'}\n"
        response += f"**Blocked At:** {block_info['blocked_at']}\n"
        response += f"**Blocked By:** {block_info['blocked_by']}\n"
        
        if block_info['username']:
            response += f"**Username:** @{block_info['username']}\n"
            
        if block_info['filename']:
            response += f"**Filename:** {block_info['filename']}\n"
    else:
        response = f"✅ **User {chat_id} is NOT BLOCKED**"
    
    await update.message.reply_text(response, parse_mode='Markdown')

def get_admin_handlers():
    """Return list of admin command handlers."""
    return [
        ('health', health_command),
        ('block', block_command),
        ('unblock', unblock_command),
        ('blocked', blocked_list_command),
        ('check', check_command),
    ]

# Middleware function to check if user is blocked before processing any download
async def block_middleware(func):
    """Middleware to check if user is blocked before processing."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message and update.message.from_user:
            chat_id = update.message.from_user.id
            
            if is_user_blocked(chat_id):
                # User is blocked, send block message and log the attempt
                username = update.message.from_user.username or "Unknown"
                url = update.message.text if hasattr(update.message, 'text') else "Unknown"
                
                # Log the blocked attempt
                from blocks import log_blocked_attempt
                log_blocked_attempt(chat_id, url, username)
                
                # Send block message
                await update.message.reply_text(BLOCK_MESSAGE)
                return  # Stop processing
        
        # User is not blocked, continue with normal processing
        return await func(update, context)
    
    return wrapper