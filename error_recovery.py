"""
Enhanced Error Recovery System for CoolDL
Provides intelligent error handling, retry logic, and user-friendly error messages.
"""

import asyncio
import random
import logging
from typing import Optional, Dict, List, Tuple
from datetime import datetime
import pytz

from telegram import Update
from telegram.ext import ContextTypes

from config import settings
import db

logger = logging.getLogger(__name__)


class ErrorRecoveryManager:
    """Manages intelligent error recovery with retry logic and user feedback."""
    
    def __init__(self):
        self.max_retries = 3
        self.retry_delays = {
            'network_error': (2, 5),
            'rate_limit': (10, 30),
            'timeout': (5, 15),
            'server_error': (10, 20),
            'default': (1, 3)
        }
        self.error_patterns = {
            'HTTP 429': 'rate_limit',
            'HTTP 403': 'network_error',
            'HTTP 404': 'not_found',
            'HTTP 500': 'server_error',
            'timeout': 'timeout',
            'connection': 'network_error',
            'rate limit': 'rate_limit'
        }
        
        # User-friendly error messages
        self.friendly_messages = {
            'rate_limit': "⚠️ Too many requests! Please wait a moment and try again.",
            'network_error': "🌐 Network issue! Please check your connection and try again.",
            'timeout': "⏱️ Request timeout! The server is busy, please try again later.",
            'not_found': "❌ Video not found or removed! Please check the URL and try again.",
            'server_error': "🔧 Server error! Please try again in a few minutes.",
            'file_too_large': "📁 File too large! Maximum size is {}MB.",
            'blocked_user': "🚫 Your access has been restricted. Please contact admin.",
            'default': "❌ Download failed! Please try again with a different URL."
        }
    
    def classify_error(self, error: Exception) -> str:
        """Classify error type for appropriate handling."""
        error_str = str(error).lower()
        
        for pattern, error_type in self.error_patterns.items():
            if pattern.lower() in error_str:
                return error_type
        
        # Default classification based on exception type
        error_type = type(error).__name__.lower()
        if 'timeout' in error_type:
            return 'timeout'
        elif 'connection' in error_type or 'network' in error_type:
            return 'network_error'
        
        return 'default'
    
    def get_retry_delay(self, error_type: str, attempt: int) -> float:
        """Calculate appropriate retry delay with exponential backoff."""
        min_delay, max_delay = self.retry_delays.get(error_type, self.retry_delays['default'])
        
        # Exponential backoff with jitter
        base_delay = min_delay * (2 ** (attempt - 1))
        delay = min(base_delay, max_delay)
        
        # Add jitter to prevent thundering herd
        jitter = random.uniform(0.8, 1.2)
        return delay * jitter
    
    def get_friendly_message(self, error_type: str, **kwargs) -> str:
        """Get user-friendly error message."""
        template = self.friendly_messages.get(error_type, self.friendly_messages['default'])
        
        # Format message with provided parameters
        try:
            return template.format(**kwargs)
        except KeyError:
            return template
    
    async def log_error(self, chat_id: int, error: Exception, url: str, error_type: str, conn):
        """Log error to database for analysis."""
        try:
            username = "unknown"
            name = "Unknown User"
            
            # Get user info if available
            cur = conn.cursor()
            cur.execute("SELECT username, name FROM users WHERE chat_id = ?", (chat_id,))
            user_data = cur.fetchone()
            if user_data:
                username = user_data['username'] or "unknown"
                name = user_data['name'] or "Unknown User"
            
            # Log error details
            error_details = f"{type(error).__name__}: {str(error)[:200]}"
            timestamp = datetime.now(pytz.timezone(settings.timezone)).strftime('%Y/%m/%d, %I:%M %p')
            
            db.log_to_db(conn, "errors", (
                error_details,
                "",  # file_id
                timestamp,
                username,
                chat_id,
                name,
                url
            ))
            
            logger.error(f"Error logged: {error_type} - {error_details} for user {chat_id}")
            
        except Exception as e:
            logger.error(f"Failed to log error: {e}")
    
    async def send_error_message(self, chat_id: int, error_type: str, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Send user-friendly error message."""
        try:
            message = self.get_friendly_message(error_type, **kwargs)
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")
    
    async def handle_rate_limit(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        """Handle rate limiting with user feedback."""
        try:
            wait_time = random.randint(10, 30)
            message = f"⚠️ Rate limit exceeded! Please wait {wait_time} seconds before trying again."
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode='HTML'
            )
            
            # Add small delay before allowing next request
            await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"Failed to handle rate limit: {e}")
    
    async def smart_retry_download(self, url: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE, 
                                 download_func, conn, **kwargs) -> Optional[any]:
        """
        Smart download with retry logic and error recovery.
        
        Args:
            url: URL to download
            chat_id: User's chat ID
            context: Telegram context
            download_func: Function to call for downloading
            conn: Database connection
            **kwargs: Additional arguments for download function
            
        Returns:
            Result of download or None if all attempts failed
        """
        last_error = None
        
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Download attempt {attempt}/{self.max_retries} for URL: {url}")
                
                result = await download_func(url, **kwargs)
                
                # Success - log and return
                logger.info(f"Download successful on attempt {attempt}")
                return result
                
            except Exception as e:
                last_error = e
                error_type = self.classify_error(e)
                
                logger.warning(f"Attempt {attempt} failed: {error_type} - {e}")
                
                # Log error to database
                await self.log_error(chat_id, e, url, error_type, conn)
                
                # If this is the last attempt, don't wait
                if attempt == self.max_retries:
                    break
                
                # Handle rate limits specially
                if error_type == 'rate_limit':
                    await self.handle_rate_limit(chat_id, context)
                
                # Get retry delay and wait
                delay = self.get_retry_delay(error_type, attempt)
                logger.info(f"Waiting {delay:.1f}s before retry {attempt + 1}")
                
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    logger.info("Retry cancelled")
                    return None
        
        # All attempts failed
        logger.error(f"All {self.max_retries} attempts failed for URL: {url}")
        
        # Send final error message to user
        error_type = self.classify_error(last_error) if last_error else 'default'
        
        # Handle file size errors specially
        if 'file too large' in str(last_error).lower():
            error_type = 'file_too_large'
            await self.send_error_message(
                chat_id, 
                error_type, 
                context, 
                max_mb=settings.rate_limit.max_file_size_mb
            )
        else:
            await self.send_error_message(chat_id, error_type, context)
        
        return None
    
    async def validate_url_safety(self, url: str, chat_id: int, conn) -> Tuple[bool, str]:
        """
        Validate URL safety and check for potential abuse.
        
        Returns:
            Tuple of (is_safe, reason)
        """
        try:
            # Check for known malicious patterns
            suspicious_patterns = [
                'malware', 'virus', 'trojan', 'phishing',
                'suspicious', 'dangerous', 'harmful'
            ]
            
            url_lower = url.lower()
            for pattern in suspicious_patterns:
                if pattern in url_lower:
                    return False, f"Suspicious URL pattern detected: {pattern}"
            
            # Check for excessive URL length (potential DoS)
            if len(url) > 2000:
                return False, "URL too long - potential abuse"
            
            # Check for rapid successive requests from same user
            # (This would be enhanced with user activity tracking)
            
            return True, "URL is safe"
            
        except Exception as e:
            logger.error(f"URL validation error: {e}")
            return False, "Validation error occurred"


# Global instance for easy access
error_recovery = ErrorRecoveryManager()


async def download_with_retry(url: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE, 
                             download_func, conn, **kwargs) -> Optional[any]:
    """
    Convenience function for downloads with retry logic.
    
    Args:
        url: URL to download
        chat_id: User's chat ID  
        context: Telegram context
        download_func: Function to call for downloading
        conn: Database connection
        **kwargs: Additional arguments for download function
        
    Returns:
        Result of download or None if all attempts failed
    """
    return await error_recovery.smart_retry_download(
        url, chat_id, context, download_func, conn, **kwargs
    )